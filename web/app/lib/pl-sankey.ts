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
 * Contra lines ("… (-)" in the label: II., 2.x, 4.2, IX.–XII.) are stored as
 * the filing prints them — positive magnitude for most banks, NEGATIVE for the
 * paren-negative banks (ING/KLNMA/PASHA/TFKB/SKBNK/…). They are normalized to
 * magnitudes here, same rule as audit.ts `balanceSheetMultiPeriod`. Genuinely
 * signed lines (VI. trading, XV. equity-method, XVI. monetary position) keep
 * their stored sign. Tax (XVIII., "(±)") is sign-ambiguous across the two
 * storage conventions, so the tax CHARGE is derived from the unambiguous
 * subtotals as XVII − XIX and only cross-checked against |XVIII|.
 *
 * Negative re-routing rule
 * ------------------------
 * Sankey ribbons cannot carry negative flow. Any item that would enter a
 * subtotal with negative sign is moved ACROSS it, magnitude preserved:
 *   - a negative income item (trading loss, monetary loss, equity-method
 *     loss, negative net fees) becomes a red outflow ribbon LEAVING the
 *     subtotal it would have fed, alongside that stage's expense stack;
 *   - a negative expense (tax credit) becomes an inflow ribbon ENTERING the
 *     next subtotal.
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
 * All statement identities are checked against the filed subtotals. Worst
 * relative diff ≤ 0.5 % → render silently; 0.5–5 % → render with a warning
 * note (ribbons anchor on component lines as filed — values are NEVER
 * scaled); > 5 % → `renderable: false`.
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

const CONTRA_RE = /\(\s*-\s*\)/;

/** Hierarchy codes that are deductions by template even when the extracted
 *  label lost its "(-)" marker (Turkish filings vary). */
const DEDUCTION_CODES = new Set(["II.", "IX.", "X.", "XI.", "XII."]);

interface LineIndex {
  get(h: string): number | null;
  /** Deduction magnitude: abs() when contra-labelled or a known deduction code. */
  mag(h: string): number | null;
}

function indexRows(rows: PlRow[]): LineIndex {
  const byCode = new Map<string, { amount: number | null; name: string }>();
  for (const r of rows) {
    // First occurrence wins — duplicated codes (current vs prior columns are
    // already separated upstream; dupes here would be extraction noise).
    if (!byCode.has(r.hierarchy)) byCode.set(r.hierarchy, { amount: r.amount, name: r.item_name ?? "" });
  }
  return {
    get: (h) => byCode.get(h)?.amount ?? null,
    mag: (h) => {
      const e = byCode.get(h);
      if (!e || e.amount == null) return null;
      return CONTRA_RE.test(e.name) || DEDUCTION_CODES.has(h) ? Math.abs(e.amount) : e.amount;
    },
  };
}

const fmtM = (v: number) =>
  new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 }).format(v);

export function buildPlSankey(rows: PlRow[]): PlSankeyResult {
  const ix = indexRows(rows);
  const notes: string[] = [];

  // --- normalized line values -------------------------------------------
  const interestIncome = ix.get("I.");
  const netInterestReported = ix.get("III.");
  let interestExpense = ix.mag("II.");
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
  const grossOpReported = ix.get("VIII.");
  const ecl = ix.mag("IX.") ?? 0;
  const otherProv = ix.mag("X.") ?? 0;
  const personnel = ix.mag("XI.") ?? 0;
  const otherOpex = ix.mag("XII.") ?? 0;
  const netOpReported = ix.get("XIII.");
  const merger = ix.get("XIV.") ?? 0;
  const equityMethod = ix.get("XV.") ?? 0;
  const monetary = ix.get("XVI.") ?? 0;
  const pretaxReported = ix.get("XVII.");
  const netContReported = ix.get("XIX.");
  const netTotalReported = ix.get("XXV.") ?? netContReported;

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
    tax = Math.abs(ix.get("XVIII.") ?? 0);
    notes.push("Tax derived from |XVIII.| — pre-tax or continuing-ops subtotal missing.");
  }
  const disc =
    netContReported != null && ix.get("XXV.") != null ? netTotalReported - netContReported : 0;

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
  const taxFiled = ix.get("XVIII.");
  if (taxFiled != null && Math.abs(Math.abs(tax) - Math.abs(taxFiled)) > Math.max(noiseFloor, 0.01 * Math.abs(tax))) {
    notes.push(
      `Tax derived from subtotals (${fmtM(tax)}) differs from the filed XVIII. line (${fmtM(taxFiled)}).`,
    );
  }

  if (worstPctDiff > 0.05) {
    return {
      nodes: [],
      links: [],
      checks,
      worstPctDiff,
      renderable: false,
      notes: [
        ...notes,
        "Internal-sum checks failed by more than 5% — flow chart suppressed; see the table below.",
      ],
    };
  }
  if (worstPctDiff > 0.005) {
    const worst = checks.reduce((a, b) => (b.pctDiff > a.pctDiff ? b : a));
    notes.push(
      `${worst.label} computed from line items differs from the filed figure by ${(worst.pctDiff * 100).toFixed(1)}% — extraction noise; ribbons use the line items as filed.`,
    );
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

  const deductions: { id: string; label: string; value: number }[] = [
    { id: "ecl", label: "Expected credit losses", value: ecl },
    { id: "other_prov", label: "Other provisions", value: otherProv },
    { id: "personnel", label: "Personnel expenses", value: personnel },
    { id: "other_opex", label: "Other operating expenses", value: otherOpex },
  ];
  let grossOut = grossRerouted;
  for (const d of deductions) {
    if (d.value > 0) {
      node({ id: d.id, label: d.label, column: 3, value: d.value, reported: d.value, kind: "deduction" });
      link(grossId, d.id, d.value);
      grossOut += d.value;
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
