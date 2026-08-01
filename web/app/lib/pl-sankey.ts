/**
 * P&L Sankey derivation + layout (pure — no React, no D1).
 *
 * Turns one bank-period-kind's `bank_audit_profit_loss` rows into a flow
 * graph following the BRSA statement identities:
 *
 *   III = I − II            VIII = III + IV + V + VI + VII
 *   XIII = VIII − (IX+X+XI+XII)        XVII = XIII + XIV + XV + XVI
 *   XIX = XVII − XVIII                 XXV = XIX + discontinued (XX–XXIV)
 *
 * Sign handling
 * -------------
 * Expense lines (II., IX.–XII.) are stored as the filing prints them — positive
 * magnitude for most banks, NEGATIVE for the paren-negative banks (ING/KLNMA/
 * PASHA/TFKB/SKBNK/…). Rather than abs() them (which destroys a genuine reversal
 * — a net ECL release or a provision write-back), the storage convention is read
 * off a line that is always a real cost (personnel XI., then interest expense,
 * then other opex) and each expense's SIGNED contribution to subtract is `conv ×
 * stored`: positive = a real expense, negative = a credit that adds back.
 * Genuinely signed income lines (VI. trading, XV. equity-method, XVI. monetary
 * position) keep their stored sign. Tax (XVIII., "(±)") is sign-ambiguous across
 * the two conventions, so the tax CHARGE is derived from the unambiguous
 * subtotals as XVII − XIX and only cross-checked against |XVIII|.
 *
 * Negative re-routing rule
 * ------------------------
 * Sankey ribbons cannot carry negative flow. Any item that would enter a
 * subtotal with negative sign is moved ACROSS it, magnitude preserved:
 *   - a negative income item (trading loss, monetary loss, equity-method
 *     loss, negative net fees) becomes a red outflow ribbon LEAVING the
 *     subtotal it would have fed, alongside that stage's expense stack;
 *   - a negative expense (an expense reversal, or a tax credit) becomes a green
 *     inflow ribbon ENTERING the subtotal it offsets.
 * A subtotal node's drawn thickness is therefore Σin = Σout (conserved by
 * construction), which can exceed the filed figure by the re-routed amount —
 * the LABEL always prints the filed figure, and `notes[]` explains the gap.
 * If a stage's running flow itself goes negative (operating loss), the
 * shortfall is balanced by a synthetic red `kind:"loss"` source node feeding
 * that subtotal ("expenses funded by the period's loss") and the forward flow
 * is clamped to zero.
 *
 * Reconciliation
 * --------------
 * EXACT match required. Every statement identity is checked against the filed
 * subtotals; a diff within `noiseFloor` (0.1 % of interest income, to absorb
 * thousand-level rounding and near-zero subtotals) counts as exact. Any diff
 * that survives the noise floor is a real extraction gap — a dropped or
 * mis-signed line — so the flow is suppressed (`renderable: false`) rather than
 * drawn with numbers that don't add up; the table below it still shows the
 * filed rows. Ribbons anchor on the component lines as filed — values are NEVER
 * scaled.
 */
import type { PlRow } from "./audit";

// ---------------------------------------------------------------------------
// Public types
// ---------------------------------------------------------------------------

export type PlNodeKind =
  | "source" // income line feeding a subtotal
  | "subtotal" // III / VIII / XIII / XVII pass-through
  | "deduction" // terminal expense (interest expense, ECL, opex, tax…)
  | "rerouted" // terminal for a re-routed negative income item
  | "loss" // synthetic source balancing a loss-making stage
  | "result"; // final net profit / loss node

export interface PlSankeyNode {
  id: string;
  label: string;
  column: number;
  /** Drawn thickness = max(Σin, Σout) of its ribbons (TL thousands). */
  value: number;
  /** Filed figure printed in the label; null for synthetic nodes. */
  reported: number | null;
  kind: PlNodeKind;
}

export interface PlSankeyLink {
  source: string;
  target: string;
  value: number;
}

export interface SankeyCheck {
  id: string;
  label: string;
  computed: number;
  reported: number;
  pctDiff: number; // 0.012 = 1.2 %
}

export interface PlSankeyResult {
  nodes: PlSankeyNode[];
  links: PlSankeyLink[];
  checks: SankeyCheck[];
  worstPctDiff: number;
  renderable: boolean;
  notes: string[];
}

// ---------------------------------------------------------------------------
// Derivation
// ---------------------------------------------------------------------------

/** Roman-numeral subtotal codes are stored dotted ("VI.") for every bank
 *  except VAKBN, whose filing prints roman VI without the trailing dot ("VI")
 *  and the extractor keeps it verbatim across all periods. The subtotal
 *  lookups below key on the dotted form, so a bare roman code would drop that
 *  line (VAKBN's net trading loss vanished → VIII/XIII overstated → the >5%
 *  gate suppressed the chart every period). Canonicalize any all-roman code to
 *  the dotted form; numeric sub-codes ("1.1", "4.2") are left untouched. */
const canonHier = (h: string) => (/^[IVXLCDM]+$/.test(h) ? `${h}.` : h);

export interface LineIndex {
  get(h: string): number | null;
}

/** Filed P&L rows → hierarchy lookup, canonicalized and de-duplicated.
 *  Exported so `pl-shape.ts` (the waterfall + the interest fan) reads the
 *  statement through the SAME index — one place where the roman-code quirks and
 *  the larger-magnitude-wins rule live. */
export function indexRows(rows: PlRow[]): LineIndex {
  const byCode = new Map<string, { amount: number | null; name: string }>();
  for (const r of rows) {
    // Larger magnitude wins among duplicated codes. Some extractions capture a
    // footnote-reference fragment as a roman row with a tiny value (ZIRAAT
    // "IV. = 1", BURGAN "III. = 1") BEFORE the real subtotal; the old "first wins"
    // then read the stray and the flow couldn't balance (it suppressed even though
    // the real P&L reconciles). Strays are page/footnote fragments (~1); real
    // subtotals are large, so keeping the larger-magnitude occurrence picks the
    // real line.
    const code = canonHier(r.hierarchy);
    const prev = byCode.get(code);
    if (
      !prev ||
      (r.amount != null && (prev.amount == null || Math.abs(r.amount) > Math.abs(prev.amount)))
    ) {
      byCode.set(code, { amount: r.amount, name: r.item_name ?? "" });
    }
  }
  return {
    get: (h) => byCode.get(h)?.amount ?? null,
  };
}

const fmtM = (v: number) =>
  new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 }).format(v);

/** The roles `validator.pl_roles()` resolves against each filer's OWN numbering. */
export type PlRole =
  | "gross" | "net_op" | "pretax" | "tax" | "cont_net" | "period_net"
  | "opex_personnel" | "opex_other";

/** role → that filer's roman code, from `bank_audit_pl_roles`. */
export type PlRoleMap = Partial<Record<PlRole, string>>;

/** The standard template's ordinals — the fallback when no role map is supplied.
 *
 *  These are what this file USED to hardcode unconditionally, and the reason it
 *  had to stop: BRSA roman ordinals are not fixed across the corpus. The
 *  compressed template DUNYAK and TOMK file puts net-operating at XII and
 *  period-net at XXIV, not XIII/XXV. Rendered against these defaults, DUNYAK
 *  2024Q4 put ₺1.616bn of NET OPERATING PROFIT under "Other Operating Expenses"
 *  with `contra: true` — a profit drawn as a ₺1.6bn expense — while XVII (tax,
 *  ₺262m) read "Pre-tax Profit" and XXV, the bottom line, came back blank.
 *
 *  `heatmap.ts` was fixed by joining `bank_audit_pl_roles`; this consumer and
 *  `standard_lines.ts` were not. It matters most here because the filers on the
 *  compressed template are participation banks, and for those there is no second
 *  published source a reader could check the number against. */
const DEFAULT_ROLE_ORDINALS: Record<PlRole, string> = {
  gross: "VIII.",
  opex_personnel: "XI.",
  opex_other: "XII.",
  net_op: "XIII.",
  pretax: "XVII.",
  tax: "XVIII.",
  cont_net: "XIX.",
  period_net: "XXV.",
};


/** Roman numeral → integer. Returns null for numeric sub-codes ("1.1"). */
export function romanValue(h: string): number | null {
  const m = /^([IVXLCDM]+)\.?$/.exec(h.trim());
  if (!m) return null;
  const D: Record<string, number> = { I: 1, V: 5, X: 10, L: 50, C: 100, D: 500, M: 1000 };
  let total = 0;
  const s = m[1];
  for (let i = 0; i < s.length; i++) {
    const cur = D[s[i]], next = D[s[i + 1]] ?? 0;
    total += cur < next ? -cur : cur;
  }
  return total;
}

/** This filer's own code for a role, falling back to the standard ordinal. */
export const roleCode = (roles: PlRoleMap | undefined, role: PlRole): string =>
  roles?.[role] ?? DEFAULT_ROLE_ORDINALS[role];

/** The two ordinal BANDS the statement identities depend on, derived from the
 *  role anchors rather than named outright.
 *
 *  Naming them (`IX. + X.` for provisions, `XIV.–XVI.` below the line) was a
 *  second hardcode, and a worse one than the subtotal lookups: on the compressed
 *  template `X.` is PERSONNEL, so it was counted twice — once as "other
 *  provisions" and once as opex — and net operating profit came out 52% below
 *  the filed figure, which suppresses the chart for a filing that is perfectly
 *  fine. Deriving each band from the roles that bound it holds for both:
 *
 *    standard   gross VIII → net_op XIII : IX, X, XI(pers), XII(other) → prov = X
 *    compressed gross VIII → net_op XII  : IX, X(pers), XI(other)      → prov = none
 */
export function plLineBands(rows: PlRow[], roles?: PlRoleMap) {
  const grossIdx = romanValue(roleCode(roles, "gross"));
  const netOpIdx = romanValue(roleCode(roles, "net_op"));
  const pretaxIdx = romanValue(roleCode(roles, "pretax"));
  const opexCodes = new Set([roleCode(roles, "opex_personnel"), roleCode(roles, "opex_other")]);

  const between = (lo: number | null, hi: number | null, skip?: Set<string>): string[] => {
    if (lo == null || hi == null) return [];
    const found: string[] = [];
    for (const r of rows) {
      const h = canonHier(r.hierarchy);
      const v = romanValue(h);
      if (v != null && v > lo && v < hi && !skip?.has(h)) found.push(h);
    }
    return [...new Set(found)].sort((a, b) => (romanValue(a) ?? 0) - (romanValue(b) ?? 0));
  };

  return {
    /** Provisions + ECL: gross → net_op, minus the two opex lines. The FIRST is
     *  the ECL/provision line in every filing in the corpus. */
    deductionBand: between(grossIdx, netOpIdx, opexCodes),
    /** Merger / equity-method / monetary: net_op → pretax. */
    belowLineBand: between(netOpIdx, pretaxIdx),
  };
}

/** The below-the-line items, matched by filed LABEL where possible.
 *  A compressed filer may omit the merger line entirely, and slotting monetary
 *  into "merger" would mislabel a real number. Anything unmatched still enters
 *  the identity, or pre-tax stops reconciling for a filing that is fine. */
export function belowLineItems(rows: PlRow[], roles: PlRoleMap | undefined, ix: LineIndex) {
  const { belowLineBand } = plLineBands(rows, roles);
  const labelOf = (h: string) => rows.find((r) => canonHier(r.hierarchy) === h)?.item_name ?? "";
  const pick = (re: RegExp) => belowLineBand.find((h) => re.test(labelOf(h)));
  const mergerCode = pick(/birleşme|merger/i);
  const equityCode = pick(/özkaynak\s*yönt|equity[-\s]?method|iştirak/i);
  const monetaryCode = pick(/parasal|monetary/i);
  const named = new Set([mergerCode, equityCode, monetaryCode].filter(Boolean) as string[]);
  const unnamed = belowLineBand.filter((h) => !named.has(h));
  return {
    merger: mergerCode ? (ix.get(mergerCode) ?? 0) : 0,
    equityMethod: equityCode ? (ix.get(equityCode) ?? 0) : 0,
    monetary:
      (monetaryCode ? (ix.get(monetaryCode) ?? 0) : 0) +
      unnamed.reduce((sum, h) => sum + (ix.get(h) ?? 0), 0),
  };
}

export function buildPlSankey(rows: PlRow[], roles?: PlRoleMap): PlSankeyResult {
  const ix = indexRows(rows);
  /** This filer's own code for a role, falling back to the standard ordinal. */
  const code = (role: PlRole): string => roleCode(roles, role);
  const at = (role: PlRole): number | null => ix.get(code(role));
  const notes: string[] = [];

  // Sign convention for the deduction stack (II., IX.–XII.). Most banks store
  // expense lines as positive magnitudes ("(-)" in the label); the paren-negative
  // banks (ING/KLNMA/PASHA and the participation banks) store them NEGATIVE. The
  // old rule blindly abs()-ed every deduction, which is wrong when a line is a
  // genuine reversal — a net ECL RELEASE (BURGAN) or a provision write-back
  // (DENIZ) is stored with the opposite sign and must be ADDED back, not
  // subtracted; abs()-ing it double-counted the swing and the VIII→XIII identity
  // failed by up to ~190%. Anchor the convention on a line that is ALWAYS a real
  // cost — personnel (XI.) first, since participation banks (TFKB) have no
  // interest expense II. — then interest expense, then other opex. `ded(h)`
  // returns the amount to SUBTRACT: >0 a real expense, <0 a reversal/credit.
  const convAnchor = at("opex_personnel") ?? ix.get("II.") ?? at("opex_other") ?? 0;
  const conv = convAnchor < 0 ? -1 : 1;
  const ded = (h: string): number | null => {
    const v = ix.get(h);
    return v == null ? null : conv * v;
  };
  /** `ded`, but resolved through the role map. */
  const dedRole = (role: PlRole): number | null => ded(code(role));

  // --- normalized line values -------------------------------------------
  const interestIncome = ix.get("I.");
  const netInterestReported = ix.get("III.");
  // Interest / profit-share expense is ALWAYS a magnitude, never a reversal, and
  // its storage sign is independent of the IX.–XII. block (TFKB stores II.
  // positive while its operating deductions are negative), so take abs() here
  // rather than the block's `conv`.
  const iiRaw = ix.get("II.");
  let interestExpense = iiRaw == null ? null : Math.abs(iiRaw);
  if (interestExpense == null && interestIncome != null && netInterestReported != null) {
    interestExpense = interestIncome - netInterestReported;
    notes.push("Interest expense derived as I. − III. (line missing from the extraction).");
  }
  const netInterest =
    netInterestReported ??
    (interestIncome != null && interestExpense != null ? interestIncome - interestExpense : null);
  const netFees = ix.get("IV.") ?? 0;
  const dividend = ix.get("V.") ?? 0;
  const trading = ix.get("VI.") ?? 0;
  const otherIncome = ix.get("VII.") ?? 0;
  const grossOpReported = at("gross");
  const { deductionBand: uniqueBand } = plLineBands(rows, roles);
  const ecl = uniqueBand.length > 0 ? (ded(uniqueBand[0]) ?? 0) : 0;
  const otherProv = uniqueBand.slice(1).reduce((sum, h) => sum + (ded(h) ?? 0), 0);
  const personnel = dedRole("opex_personnel") ?? 0;
  const otherOpex = dedRole("opex_other") ?? 0;
  const netOpReported = at("net_op");
  const { merger, equityMethod, monetary } = belowLineItems(rows, roles, ix);
  const pretaxReported = at("pretax");
  const netContReported = at("cont_net");
  const netTotalReported = at("period_net") ?? netContReported;

  if (netInterest == null || netTotalReported == null) {
    return {
      nodes: [],
      links: [],
      checks: [],
      worstPctDiff: Infinity,
      renderable: false,
      notes: ["Core P&L lines (net interest income / net profit) missing for this period."],
    };
  }

  // Tax charge from the unambiguous subtotals; fall back to |XVIII|.
  let tax: number;
  if (pretaxReported != null && netContReported != null) {
    tax = pretaxReported - netContReported;
  } else {
    tax = Math.abs(at("tax") ?? 0);
    notes.push(`Tax derived from |${code("tax")}| — pre-tax or continuing-ops subtotal missing.`);
  }
  const disc =
    netContReported != null && at("period_net") != null ? netTotalReported - netContReported : 0;

  // --- reconciliation checks ---------------------------------------------
  // Relative to max(|computed|, |reported|); diffs under 0.1 % of interest
  // income are treated as rounding noise even when the subtotal is near zero.
  const noiseFloor = 0.001 * Math.abs(interestIncome ?? netInterest);
  const checks: SankeyCheck[] = [];
  const addCheck = (id: string, label: string, computed: number, reported: number | null) => {
    if (reported == null) return;
    const diff = Math.abs(computed - reported);
    const denom = Math.max(Math.abs(computed), Math.abs(reported));
    const pctDiff = diff <= noiseFloor || denom === 0 ? 0 : diff / denom;
    checks.push({ id, label, computed, reported, pctDiff });
  };
  if (interestIncome != null && interestExpense != null) {
    addCheck("net_interest", "Net interest income (I − II)", interestIncome - interestExpense, netInterestReported);
  }
  const grossOpComputed = netInterest + netFees + dividend + trading + otherIncome;
  addCheck("gross_op", "Gross operating profit (III+IV+V+VI+VII)", grossOpComputed, grossOpReported);
  const netOpComputed = grossOpComputed - (ecl + otherProv + personnel + otherOpex);
  addCheck("net_op", "Net operating profit (VIII − IX..XII)", netOpComputed, netOpReported);
  const pretaxComputed = netOpComputed + merger + equityMethod + monetary;
  addCheck("pretax", "Pre-tax profit (XIII+XIV+XV+XVI)", pretaxComputed, pretaxReported);
  const worstPctDiff = checks.reduce((w, c) => Math.max(w, c.pctDiff), 0);

  // Non-gating tax cross-check.
  const taxFiled = at("tax");
  if (taxFiled != null && Math.abs(Math.abs(tax) - Math.abs(taxFiled)) > Math.max(noiseFloor, 0.01 * Math.abs(tax))) {
    notes.push(
      `Tax derived from subtotals (${fmtM(tax)}) differs from the filed ${code("tax")} line (${fmtM(taxFiled)}).`,
    );
  }

  // Exact match required: the flow only renders when every statement identity
  // reconciles to the filed subtotals (diffs within `noiseFloor` count as exact
  // rounding). Anything that survives the noise floor is a real extraction gap —
  // a dropped line or a mis-signed figure — so the chart is suppressed rather
  // than drawn with numbers that don't add up. `worst.label` names the first
  // failing identity in the note below the suppression message.
  if (worstPctDiff > 0) {
    const worst = checks.reduce((a, b) => (b.pctDiff > a.pctDiff ? b : a));
    return {
      nodes: [],
      links: [],
      checks,
      worstPctDiff,
      renderable: false,
      notes: [
        ...notes,
        `${worst.label} does not reconcile to the filed figure (off by ${(worst.pctDiff * 100).toFixed(1)}%) — flow chart suppressed; see the table below.`,
      ],
    };
  }

  // --- graph construction --------------------------------------------------
  const nodes: PlSankeyNode[] = [];
  const links: PlSankeyLink[] = [];
  const node = (n: PlSankeyNode) => {
    nodes.push(n);
    return n.id;
  };
  const link = (source: string, target: string, value: number) => {
    if (value > 0) links.push({ source, target, value });
  };

  // Stage A — interest decomposition (skipped if I/II missing or III < 0).
  let netInterestFlow = Math.max(netInterest, 0);
  let stageAVisible = false;
  if (interestIncome != null && interestExpense != null && netInterest >= 0 && interestIncome > 0) {
    stageAVisible = true;
    // Anchor on I and II as filed; the III ribbon is the exact remainder so
    // flux conserves even when the filed III is a hair off.
    netInterestFlow = Math.max(interestIncome - interestExpense, 0);
    node({ id: "interest_income", label: "Interest income", column: 0, value: interestIncome, reported: interestIncome, kind: "source" });
    node({ id: "interest_expense", label: "Interest expense", column: 1, value: interestExpense, reported: interestExpense, kind: "deduction" });
    link("interest_income", "interest_expense", interestExpense);
  }
  node({
    id: "net_interest",
    label: "Net interest income",
    column: 1,
    value: netInterestFlow,
    reported: netInterestReported ?? netInterest,
    kind: stageAVisible ? "subtotal" : "source",
  });
  if (stageAVisible) link("interest_income", "net_interest", netInterestFlow);

  // Stage B — gross operating profit (VIII).
  // Positive contributions flow in; negative ones re-route to the right.
  const contributions: { id: string; label: string; value: number }[] = [
    { id: "net_fees", label: "Net fees & commissions", value: netFees },
    { id: "dividend", label: "Dividend income", value: dividend },
    { id: "trading", label: "Net trading income", value: trading },
    { id: "other_income", label: "Other operating income", value: otherIncome },
  ];
  if (!stageAVisible && netInterest < 0) {
    contributions.push({ id: "net_interest_neg", label: "Net interest loss", value: netInterest });
    // remove the zero-flow net_interest node added above
    nodes.splice(nodes.findIndex((n) => n.id === "net_interest"), 1);
    netInterestFlow = 0;
  }

  let grossIn = netInterestFlow;
  let grossRerouted = 0;
  const grossId = node({
    id: "gross_op",
    label: "Gross operating profit",
    column: 2,
    value: 0, // patched below
    reported: grossOpReported ?? grossOpComputed,
    kind: "subtotal",
  });
  if (netInterestFlow > 0) link("net_interest", grossId, netInterestFlow);
  const LOSS_LABELS: Record<string, string> = {
    net_fees: "Net fees & commissions (net paid)",
    dividend: "Dividend loss",
    trading: "Net trading loss",
    other_income: "Other operating loss",
    net_interest_neg: "Net interest loss",
    merger: "Merger loss",
    equity_method: "Equity-method loss",
    monetary: "Monetary position loss",
  };
  for (const c of contributions) {
    if (c.value > 0) {
      node({ id: c.id, label: c.label, column: 1, value: c.value, reported: c.value, kind: "source" });
      link(c.id, grossId, c.value);
      grossIn += c.value;
    } else if (c.value < 0) {
      const v = Math.abs(c.value);
      const lossLabel = LOSS_LABELS[c.id] ?? c.label;
      node({ id: `${c.id}_loss`, label: lossLabel, column: 3, value: v, reported: c.value, kind: "rerouted" });
      link(grossId, `${c.id}_loss`, v);
      grossRerouted += v;
      notes.push(`${lossLabel} shown as an outflow of Gross operating profit; node width exceeds the filed VIII. accordingly.`);
    }
  }

  const deductions: { id: string; label: string; value: number; credit: string }[] = [
    { id: "ecl", label: "Expected credit losses", value: ecl, credit: "Net ECL release" },
    { id: "other_prov", label: "Other provisions", value: otherProv, credit: "Provision reversal" },
    { id: "personnel", label: "Personnel expenses", value: personnel, credit: "Personnel expense credit" },
    { id: "other_opex", label: "Other operating expenses", value: otherOpex, credit: "Other operating credit" },
  ];
  let grossOut = grossRerouted;
  for (const d of deductions) {
    if (d.value > 0) {
      node({ id: d.id, label: d.label, column: 3, value: d.value, reported: d.value, kind: "deduction" });
      link(grossId, d.id, d.value);
      grossOut += d.value;
    } else if (d.value < 0) {
      // Genuine reversal (net release / write-back): a credit that ADDS to the
      // running flow. Draw it as a green inflow to gross operating profit, like
      // an income source — the node width then exceeds the filed VIII. by the
      // reversal, matching the re-routed-loss convention.
      const v = -d.value;
      node({ id: `${d.id}_credit`, label: d.credit, column: 1, value: v, reported: d.value, kind: "source" });
      link(`${d.id}_credit`, grossId, v);
      grossIn += v;
      notes.push(`${d.credit} shown as an inflow to Gross operating profit; node width exceeds the filed VIII. accordingly.`);
    }
  }

  // Forward flow VIII → XIII; a loss-making stage gets a balancing red source.
  let netOpFlow = grossIn - grossOut;
  if (netOpFlow < 0) {
    const gap = -netOpFlow;
    node({ id: "op_loss_fund", label: "Operating loss", column: 1, value: gap, reported: null, kind: "loss" });
    link("op_loss_fund", grossId, gap);
    grossIn += gap;
    netOpFlow = 0;
    notes.push("Operating expenses exceed gross operating profit — the shortfall is drawn as a red inflow (funded by the period's loss).");
  }
  patchValue(nodes, grossId, Math.max(grossIn, grossOut));

  if (netOpFlow > 0) {
    node({ id: "net_op", label: "Net operating profit", column: 3, value: netOpFlow, reported: netOpReported ?? netOpComputed, kind: "subtotal" });
    link(grossId, "net_op", netOpFlow);
  }

  // Stage C — pre-tax profit (XVII).
  const pretaxContribs: { id: string; label: string; value: number }[] = [
    { id: "merger", label: "Merger income", value: merger },
    { id: "equity_method", label: "Equity-method income", value: equityMethod },
    { id: "monetary", label: "Monetary position gain", value: monetary },
  ];
  const pretaxId = node({
    id: "pretax",
    label: "Pre-tax profit",
    column: 4,
    value: 0, // patched below
    reported: pretaxReported ?? pretaxComputed,
    kind: "subtotal",
  });
  let pretaxIn = netOpFlow;
  let pretaxRerouted = 0;
  if (netOpFlow > 0) link("net_op", pretaxId, netOpFlow);
  for (const c of pretaxContribs) {
    if (c.value > 0) {
      node({ id: c.id, label: c.label, column: 3, value: c.value, reported: c.value, kind: "source" });
      link(c.id, pretaxId, c.value);
      pretaxIn += c.value;
    } else if (c.value < 0) {
      const v = Math.abs(c.value);
      const lossLabel = LOSS_LABELS[c.id] ?? c.label;
      node({ id: `${c.id}_loss`, label: lossLabel, column: 5, value: v, reported: c.value, kind: "rerouted" });
      link(pretaxId, `${c.id}_loss`, v);
      pretaxRerouted += v;
      notes.push(`${lossLabel} shown as an outflow of Pre-tax profit; node width exceeds the filed XVII. accordingly.`);
    }
  }

  // Stage D — tax, discontinued ops, and the result node. All pre-tax
  // outflows are settled BEFORE the forward ribbon to the result is sized.
  let pretaxOut = pretaxRerouted;
  if (tax > 0) {
    node({ id: "tax", label: "Tax", column: 5, value: tax, reported: tax, kind: "deduction" });
    link(pretaxId, "tax", tax);
    pretaxOut += tax;
  }
  const discMaterial = Math.abs(disc) > Math.max(noiseFloor, 0.005 * Math.abs(netTotalReported));
  if (discMaterial && disc < 0) {
    const v = Math.abs(disc);
    node({ id: "disc_ops_loss", label: "Discontinued ops loss", column: 5, value: v, reported: disc, kind: "rerouted" });
    link(pretaxId, "disc_ops_loss", v);
    pretaxOut += v;
    notes.push("Discontinued-operations loss drawn as an outflow of Pre-tax profit.");
  }
  let netFlow = pretaxIn - pretaxOut;
  if (netFlow < 0) {
    const gap = -netFlow;
    node({ id: "pretax_loss_fund", label: "Pre-tax loss", column: 3, value: gap, reported: null, kind: "loss" });
    link("pretax_loss_fund", pretaxId, gap);
    pretaxIn += gap;
    netFlow = 0;
    notes.push("Deductions exceed pre-tax inflows — the shortfall is drawn as a red inflow (funded by the period's loss).");
  }
  patchValue(nodes, pretaxId, Math.max(pretaxIn, pretaxOut));

  const resultId = node({
    id: "net_profit",
    label: netTotalReported < 0 ? "Net loss" : "Net profit",
    column: 5,
    value: 0, // patched below
    reported: netTotalReported,
    kind: netTotalReported < 0 ? "loss" : "result",
  });
  let resultIn = 0;
  if (netFlow > 0) {
    link(pretaxId, resultId, netFlow);
    resultIn += netFlow;
  }
  if (tax < 0) {
    const v = Math.abs(tax);
    node({ id: "tax_credit", label: "Tax credit", column: 4, value: v, reported: tax, kind: "source" });
    link("tax_credit", resultId, v);
    resultIn += v;
    notes.push("Tax is a net credit this period — drawn as an inflow to net profit.");
  }
  if (discMaterial && disc > 0) {
    node({ id: "disc_ops", label: "Discontinued operations", column: 4, value: disc, reported: disc, kind: "source" });
    link("disc_ops", resultId, disc);
    resultIn += disc;
  }
  patchValue(nodes, resultId, Math.max(resultIn, Math.abs(netTotalReported)));

  if (resultIn === 0 && netTotalReported >= 0) {
    // Degenerate: profitable on paper but no positive flow reached the end —
    // reconciliation should have caught this; fail safe.
    return { nodes: [], links: [], checks, worstPctDiff, renderable: false, notes: [...notes, "Flow chart could not be balanced for this period."] };
  }

  return { nodes, links, checks, worstPctDiff, renderable: true, notes };
}

function patchValue(nodes: PlSankeyNode[], id: string, value: number) {
  const n = nodes.find((x) => x.id === id);
  if (n) n.value = value;
}

// ---------------------------------------------------------------------------
// Layout
// ---------------------------------------------------------------------------

export interface PlacedNode extends PlSankeyNode {
  x: number;
  y: number;
  w: number;
  h: number;
  /** Label side: left column anchors end-left, others start-right. */
  labelSide: "left" | "right";
}

export interface PlacedRibbon {
  source: string;
  target: string;
  value: number;
  path: string;
  /** Midpoint for tooltip anchoring. */
  mx: number;
  my: number;
}

export interface PlSankeyLayout {
  W: number;
  H: number;
  nodes: PlacedNode[];
  ribbons: PlacedRibbon[];
}

const NODE_W = 12;
const NODE_GAP = 14;
const PAD_T = 16;
const PAD_B = 16;
const PAD_L = 8;
const PAD_R = 170;
const MIN_H = 2;

export function layoutPlSankey(g: PlSankeyResult, W = 960, H = 440): PlSankeyLayout {
  const cols = Math.max(...g.nodes.map((n) => n.column)) + 1;
  const colX = (c: number) => PAD_L + (c * (W - PAD_L - PAD_R - NODE_W)) / Math.max(cols - 1, 1);

  // Vertical scale: consistent across columns, fit the tallest stack.
  const byCol = new Map<number, PlSankeyNode[]>();
  for (const n of g.nodes) {
    if (!byCol.has(n.column)) byCol.set(n.column, []);
    byCol.get(n.column)!.push(n);
  }
  let scale = Infinity;
  for (const [, ns] of byCol) {
    const sum = ns.reduce((s, n) => s + n.value, 0);
    const avail = H - PAD_T - PAD_B - NODE_GAP * (ns.length - 1);
    if (sum > 0) scale = Math.min(scale, avail / sum);
  }
  if (!isFinite(scale)) scale = 1;

  const placed = new Map<string, PlacedNode>();
  const nodesOut: PlacedNode[] = [];
  for (const [c, ns] of byCol) {
    const stackH = ns.reduce((s, n) => s + Math.max(n.value * scale, MIN_H), 0) + NODE_GAP * (ns.length - 1);
    let y = PAD_T + Math.max(0, (H - PAD_T - PAD_B - stackH) / 2);
    for (const n of ns) {
      const h = Math.max(n.value * scale, MIN_H);
      const p: PlacedNode = {
        ...n,
        x: colX(c),
        y,
        w: NODE_W,
        h,
        labelSide: "right",
      };
      placed.set(n.id, p);
      nodesOut.push(p);
      y += h + NODE_GAP;
    }
  }

  // Ribbons — running offsets per node edge, in link declaration order
  // (which already follows the statement's top-to-bottom reading order).
  const outOff = new Map<string, number>();
  const inOff = new Map<string, number>();
  const ribbons: PlacedRibbon[] = [];
  for (const l of g.links) {
    const s = placed.get(l.source);
    const t = placed.get(l.target);
    if (!s || !t) continue;
    const h = Math.max(l.value * scale, 1);
    const sy = s.y + (outOff.get(l.source) ?? 0);
    const ty = t.y + (inOff.get(l.target) ?? 0);
    outOff.set(l.source, (outOff.get(l.source) ?? 0) + h);
    inOff.set(l.target, (inOff.get(l.target) ?? 0) + h);
    const x0 = s.x + s.w;
    const x1 = t.x;
    const mx = (x0 + x1) / 2;
    const path =
      `M ${x0} ${sy} C ${mx} ${sy} ${mx} ${ty} ${x1} ${ty} ` +
      `L ${x1} ${ty + h} C ${mx} ${ty + h} ${mx} ${sy + h} ${x0} ${sy + h} Z`;
    ribbons.push({ source: l.source, target: l.target, value: l.value, path, mx, my: (sy + ty + h) / 2 });
  }

  return { W, H, nodes: nodesOut, ribbons };
}

/** PL_LINES catalog id → the role that decides which roman it really is. */
const PL_LINE_ROLE: Record<string, PlRole> = {
  gross_op_profit: "gross",
  personnel_expense: "opex_personnel",
  other_op_expense: "opex_other",
  net_op_profit: "net_op",
  pretax_profit_cont: "pretax",
  tax_provision: "tax",
  net_profit_cont: "cont_net",
  net_profit_total: "period_net",
};

/**
 * Re-point a P&L line catalog at THIS filer's own roman numbering.
 *
 * `PL_LINES` maps a roman code to a label, and the statement table renders each
 * catalog row with the catalog's label. That is fine while the ordinals are
 * fixed — and they are not. On the compressed template DUNYAK and TOMK file,
 * `XII.` is NET OPERATING PROFIT, so the table printed ₺1.616bn of profit under
 * "Other Operating Expenses" with `contra: true`, showed the tax line as
 * "Pre-tax Profit", and left the bottom line blank because `XXV.` does not
 * exist there.
 *
 * The eight role-bearing lines move to whatever `bank_audit_pl_roles` says. The
 * provisions band (between gross and net-operating) and the below-the-line band
 * (between net-operating and pre-tax) are re-pointed positionally, since those
 * lines carry no role. A catalog line with no counterpart in this filing is
 * dropped rather than left pointing at a row that means something else — an
 * absent line is honest, a mislabelled one is not.
 */
export function remapPlLines<T extends { id: string; hierarchy: string }>(
  lines: T[],
  rows: PlRow[],
  roles?: PlRoleMap,
): T[] {
  if (!roles || Object.keys(roles).length === 0) return lines;

  const { deductionBand, belowLineBand } = plLineBands(rows, roles);
  const labelOf = (h: string) => rows.find((r) => canonHier(r.hierarchy) === h)?.item_name ?? "";
  const pick = (re: RegExp) => belowLineBand.find((h) => re.test(labelOf(h)));

  const byId: Record<string, string | undefined> = {
    ecl_provisions: deductionBand[0],
    other_provisions: deductionBand[1],
    equity_method: pick(/özkaynak\s*yönt|equity[-\s]?method|iştirak/i) ?? belowLineBand[0],
    monetary_position: pick(/parasal|monetary/i),
  };

  const out: T[] = [];
  for (const line of lines) {
    const role = PL_LINE_ROLE[line.id];
    if (role) {
      out.push({ ...line, hierarchy: roleCode(roles, role) });
      continue;
    }
    if (line.id in byId) {
      const h = byId[line.id];
      if (h) out.push({ ...line, hierarchy: h });
      continue; // no counterpart in this filing → drop, don't mislabel
    }
    out.push(line);
  }
  return out;
}
