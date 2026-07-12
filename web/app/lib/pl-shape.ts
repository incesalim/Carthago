/**
 * The income statement's SHAPE — pure derivations, no React, no D1.
 *
 * Two readings of the same filed quarter, both anchored on the BRSA identities
 * and both reconciled EXACTLY (the gate `pl-sankey.ts` established — a diff that
 * survives the noise floor is a real extraction gap, so the picture is suppressed
 * rather than drawn with numbers that don't add up; the table below it still
 * shows the filed rows):
 *
 *   buildWaterfall()     — how the profit is BUILT. Interest income → −interest
 *                          expense → net interest income → +fees +dividend
 *                          +trading +other → gross operating profit → −ECL
 *                          −provisions −personnel −other opex → net operating
 *                          profit → ±below-the-line → pre-tax → −tax → net profit.
 *                          Running totals, so every bar is where the money stands.
 *
 *   buildInterestFlow()  — where the interest money COMES FROM and GOES. The
 *                          branching the waterfall cannot show: interest income
 *                          fanned out by SOURCE (loans / securities / required
 *                          reserves / money market / banks — PL sub-items 1.1–1.5)
 *                          and by DESTINATION (interest paid on deposits / money
 *                          market / funds borrowed / issued securities / lease —
 *                          2.1–2.5) plus the NET INTEREST INCOME the bank keeps.
 *
 * Both sides of the fan CLOSE against the filed statement:
 *   Σ sources               == filed I.        (any gap becomes an explicit "Other")
 *   Σ destinations + NII    == filed I.        (ditto)
 * Nothing is scaled, nothing is dropped: a residual gets its own node and a note.
 *
 * Sign handling is inherited from `pl-sankey.ts` — expense lines (II., IX.–XII.)
 * are stored positive by most banks and NEGATIVE by the paren-negative banks, so
 * the convention is read off a line that is always a real cost (personnel XI.,
 * then interest expense, then other opex) and each expense's SIGNED contribution
 * is `conv × stored`: positive = a real expense, negative = a credit that adds back.
 */
import type { PlRow } from "./audit";
import { indexRows, type LineIndex } from "./pl-sankey";

// ---------------------------------------------------------------------------
// Shared
// ---------------------------------------------------------------------------

/** Diffs under 0.1 % of interest income are thousand-level rounding, not gaps. */
const noiseFloor = (income: number): number => Math.max(Math.abs(income) * 0.001, 1);

/** The deduction-sign convention for this bank's filing (see the header note). */
function dedSign(ix: LineIndex): 1 | -1 {
  const anchor = ix.get("XI.") ?? ix.get("II.") ?? ix.get("XII.") ?? 0;
  return anchor < 0 ? -1 : 1;
}

const pct = (v: number, d = 1) => `${v.toFixed(d)}%`;

// ---------------------------------------------------------------------------
// The waterfall
// ---------------------------------------------------------------------------

export type StepKind = "open" | "in" | "out" | "subtotal" | "result";

export interface WaterfallStep {
  id: string;
  label: string;
  /** Signed contribution to the running total (0 on subtotal / result rows). */
  delta: number;
  /** Running total AFTER this step — where the money stands. */
  running: number;
  /** The figure the row prints: the filed subtotal, or the step's own delta. */
  reported: number;
  kind: StepKind;
}

export interface Waterfall {
  steps: WaterfallStep[];
  /** [min, max] running total — the bar domain (min ≤ 0). */
  domain: [number, number];
  renderable: boolean;
  notes: string[];
  /** One computed sentence, or null when its inputs don't resolve. */
  lead: string | null;
}

const EMPTY_WATERFALL = (note: string): Waterfall => ({
  steps: [],
  domain: [0, 0],
  renderable: false,
  notes: [note],
  lead: null,
});

export function buildWaterfall(rows: PlRow[]): Waterfall {
  const ix = indexRows(rows);
  const notes: string[] = [];
  const conv = dedSign(ix);
  /** Amount to SUBTRACT for a deduction line: >0 a real expense, <0 a reversal. */
  const ded = (h: string): number => {
    const v = ix.get(h);
    return v == null ? 0 : conv * v;
  };

  const income = ix.get("I.");
  const niiFiled = ix.get("III.");
  const iiRaw = ix.get("II.");
  // Interest expense is ALWAYS a magnitude, never a reversal, and its storage
  // sign is independent of the IX.–XII. block — take abs() rather than `conv`.
  let expense = iiRaw == null ? null : Math.abs(iiRaw);
  if (expense == null && income != null && niiFiled != null) {
    expense = income - niiFiled;
    notes.push("Interest expense derived as I. − III. — the line is missing from the extraction.");
  }
  if (income == null || expense == null) {
    return EMPTY_WATERFALL(
      "Interest income / expense not filed for this period — the waterfall is built on the interest block.",
    );
  }
  const netProfit = ix.get("XXV.") ?? ix.get("XIX.");
  if (netProfit == null) {
    return EMPTY_WATERFALL("Net period profit (XXV.) missing for this period — nothing to build to.");
  }

  const noise = noiseFloor(income);
  const steps: WaterfallStep[] = [];
  const failures: string[] = [];
  let run = 0;

  const step = (id: string, label: string, delta: number, kind: "open" | "in" | "out") => {
    run += delta;
    steps.push({ id, label, delta, running: run, reported: delta, kind });
  };
  /** A filed subtotal — and the point where the running total must agree with it. */
  const subtotal = (id: string, label: string, filed: number | null) => {
    if (filed != null && Math.abs(filed - run) > noise) {
      failures.push(
        `${label} does not reconcile: the lines above sum to ${fmtCompact(run)} against the filed ${fmtCompact(filed)}.`,
      );
    }
    steps.push({ id, label, delta: 0, running: run, reported: filed ?? run, kind: "subtotal" });
  };
  /** An optional ± line. A line the bank did not file (null) or filed as nil (0)
   *  is not a bar. Anything it DID file enters the chain at full value however
   *  small — the noise floor decides whether a DIFFERENCE is rounding, never
   *  whether a filed line counts. (AKBNK's ₺71m dividend is 0.04 % of interest
   *  income: floor it and the running total silently drifts off the filed VIII.) */
  const optional = (id: string, label: string, v: number | null) => {
    if (v == null || v === 0) return;
    step(id, label, v, v >= 0 ? "in" : "out");
  };

  step("interest_income", "Interest income", income, "open");
  step("interest_expense", "Interest expense", -expense, "out");
  subtotal("nii", "Net interest income", niiFiled);

  optional("net_fees", "Net fees & commissions", ix.get("IV."));
  optional("dividend", "Dividend income", ix.get("V."));
  optional("trading", "Net trading income", ix.get("VI."));
  optional("other_income", "Other operating income", ix.get("VII."));
  subtotal("gross_op", "Gross operating profit", ix.get("VIII."));

  optional("ecl", "Expected credit losses", ix.get("IX.") == null ? null : -ded("IX."));
  optional("other_prov", "Other provisions", ix.get("X.") == null ? null : -ded("X."));
  optional("personnel", "Personnel expenses", ix.get("XI.") == null ? null : -ded("XI."));
  optional("other_opex", "Other operating expenses", ix.get("XII.") == null ? null : -ded("XII."));
  subtotal("net_op", "Net operating profit", ix.get("XIII."));

  optional("merger", "Merger surplus", ix.get("XIV."));
  optional("equity_method", "Equity-method subsidiaries", ix.get("XV."));
  optional("monetary", "Net monetary position", ix.get("XVI."));
  const pretaxFiled = ix.get("XVII.");
  subtotal("pretax", "Pre-tax profit", pretaxFiled);
  const pretax = pretaxFiled ?? run;

  // Tax from the unambiguous subtotals (XVII − XIX); the filed XVIII. line is
  // sign-ambiguous across the two storage conventions, so it's only a fallback.
  const netContFiled = ix.get("XIX.");
  const taxFiled = ix.get("XVIII.");
  let tax: number;
  if (pretaxFiled != null && netContFiled != null) {
    tax = pretaxFiled - netContFiled;
  } else if (taxFiled != null) {
    tax = Math.abs(taxFiled);
    notes.push("Tax derived from |XVIII.| — the pre-tax or continuing-operations subtotal is missing.");
  } else {
    tax = pretax - netProfit;
    notes.push("Tax derived as pre-tax profit − net profit — the tax line is missing from the extraction.");
  }
  if (tax !== 0) step("tax", tax >= 0 ? "Tax" : "Tax credit", -tax, tax >= 0 ? "out" : "in");

  const disc = netContFiled != null && ix.get("XXV.") != null ? netProfit - netContFiled : 0;
  optional("disc_ops", "Discontinued operations", disc);

  if (Math.abs(run - netProfit) > noise) {
    failures.push(
      `Net period profit does not reconcile: the steps sum to ${fmtCompact(run)} against the filed ${fmtCompact(netProfit)}.`,
    );
  }
  steps.push({
    id: "net_profit",
    label: netProfit < 0 ? "Net period loss" : "Net period profit",
    delta: 0,
    running: run,
    reported: netProfit,
    kind: "result",
  });

  if (failures.length > 0) {
    return {
      steps: [],
      domain: [0, 0],
      renderable: false,
      notes: [
        ...notes,
        `${failures[0]} The waterfall is suppressed rather than drawn with numbers that don't add up — the filed rows are in the table below.`,
      ],
      lead: null,
    };
  }

  const runs = steps.map((s) => s.running);
  const domain: [number, number] = [Math.min(0, ...runs), Math.max(0, ...runs)];

  // ── The lead sentence — computed, never authored ─────────────────────────
  const parts: string[] = [];
  if (income > 0) {
    parts.push(
      `Of every ₺100 of interest income, ₺${((expense / income) * 100).toFixed(1)} leaves again as interest expense`,
    );
  }
  const netFees = ix.get("IV.");
  const costBase = ded("XI.") + ded("XII.");
  if (netFees != null && netFees > 0 && costBase > 0) {
    parts.push(`fees cover ${pct((netFees / costBase) * 100, 0)} of the cost base`);
  }
  if (tax > 0 && pretax > 0) {
    parts.push(`tax takes ${pct((tax / pretax) * 100)}`);
  }
  const lead = parts.length > 0 ? `${parts.join("; ")}.` : null;

  return { steps, domain, renderable: true, notes, lead };
}

const COMPACT = new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 });
const fmtCompact = (v: number) => COMPACT.format(v);

// ---------------------------------------------------------------------------
// The interest flow (the Sankey)
// ---------------------------------------------------------------------------

/** PL sub-items under I. — where the interest money comes FROM. */
const SOURCE_LINES: Array<{ h: string; label: string }> = [
  { h: "1.1", label: "Loans" },
  { h: "1.5", label: "Securities portfolio" },
  { h: "1.2", label: "Required reserves" },
  { h: "1.4", label: "Money market" },
  { h: "1.3", label: "Banks" },
];

/** PL sub-items under II. — where it GOES. */
const DEST_LINES: Array<{ h: string; label: string }> = [
  { h: "2.1", label: "Deposits / funds collected" },
  { h: "2.2", label: "Funds borrowed" },
  { h: "2.3", label: "Money market" },
  { h: "2.4", label: "Issued securities" },
  { h: "2.5", label: "Lease" },
];

export type FlowSide = "source" | "hub" | "dest";

export interface FlowNode {
  id: string;
  label: string;
  side: FlowSide;
  value: number;
  /** % of filed interest income. */
  share: number;
  /** The net-interest-income node — the hero, drawn in navy. */
  hero?: boolean;
}

export interface InterestFlow {
  /** Filed interest income (I.) — both sides close to this. */
  income: number;
  expense: number;
  nii: number;
  sources: FlowNode[];
  /** Destinations, NII first (the hero the bank keeps), then the expense fan. */
  dests: FlowNode[];
  renderable: boolean;
  notes: string[];
  lead: string | null;
}

const EMPTY_FLOW = (note: string): InterestFlow => ({
  income: 0,
  expense: 0,
  nii: 0,
  sources: [],
  dests: [],
  renderable: false,
  notes: [note],
  lead: null,
});

export function buildInterestFlow(rows: PlRow[]): InterestFlow {
  const ix = indexRows(rows);
  const notes: string[] = [];

  const income = ix.get("I.");
  const niiFiled = ix.get("III.");
  const iiRaw = ix.get("II.");
  let expense = iiRaw == null ? null : Math.abs(iiRaw);
  if (expense == null && income != null && niiFiled != null) {
    expense = income - niiFiled;
    notes.push("Interest expense derived as I. − III. — the line is missing from the extraction.");
  }
  if (income == null || expense == null || income <= 0) {
    return EMPTY_FLOW(
      "Interest income / expense not filed for this period — there is no interest flow to fan out.",
    );
  }
  const nii = niiFiled ?? income - expense;
  if (nii < 0) {
    return EMPTY_FLOW(
      "Interest expense exceeds interest income this period — the flow cannot be drawn as a fan (nothing is kept). The waterfall tab shows the same quarter as a bridge.",
    );
  }
  const noise = noiseFloor(income);
  // A residual is drawn as an explicit "Other" node, never dropped — the floor
  // below is TEN TIMES tighter than the reconciliation noise floor, so a real
  // "Diğer" line the catalog doesn't name (AKBNK files interest expense 2.6 at
  // 0.03 % of income) still gets its own node. Anything under it is literal
  // thousand-TL rounding, and even that is named in a note rather than vanishing.
  const roundFloor = Math.abs(income) * 1e-4;
  const closeNote = (side: string, residual: number) =>
    notes.push(
      `The filed ${side} sub-items close to within ${fmtCompact(residual)} of the filed total — thousand-level rounding, left unallocated.`,
    );

  // ── Sources — Σ must close to the filed I. ───────────────────────────────
  const sources: FlowNode[] = [];
  let srcSum = 0;
  for (const s of SOURCE_LINES) {
    const v = ix.get(s.h);
    if (v == null || v <= 0) continue;
    sources.push({ id: `src_${s.h}`, label: s.label, side: "source", value: v, share: (v / income) * 100 });
    srcSum += v;
  }
  if (sources.length === 0) {
    sources.push({
      id: "src_all",
      label: "Interest income (not broken out)",
      side: "source",
      value: income,
      share: 100,
    });
    notes.push("This filing does not break interest income into sub-items 1.1–1.5, so the left fan is a single node.");
    srcSum = income;
  } else {
    const residual = income - srcSum;
    if (residual > roundFloor) {
      sources.push({
        id: "src_other",
        label: "Other interest income",
        side: "source",
        value: residual,
        share: (residual / income) * 100,
      });
      srcSum += residual;
      notes.push(
        `Sub-items 1.1–1.5 account for ${fmtCompact(income - residual)} of the ${fmtCompact(income)} interest income; the ${fmtCompact(residual)} remainder is drawn as an explicit “Other” node rather than dropped.`,
      );
    } else if (residual > 0) {
      closeNote("interest-income", residual);
    } else if (residual < -noise) {
      return EMPTY_FLOW(
        `The filed interest sub-items sum to ${fmtCompact(srcSum)}, MORE than the filed interest income of ${fmtCompact(income)} — an extraction gap. The fan is suppressed rather than drawn with numbers that don't add up.`,
      );
    }
  }

  // ── Destinations — Σ expense fan + the NII kept must close to the filed I. ─
  const dests: FlowNode[] = [
    { id: "nii", label: "Net interest income", side: "dest", value: nii, share: (nii / income) * 100, hero: true },
  ];
  const expenseNodes: FlowNode[] = [];
  let dstSum = 0;
  for (const d of DEST_LINES) {
    const raw = ix.get(d.h);
    const v = raw == null ? null : Math.abs(raw);
    if (v == null || v <= 0) continue;
    expenseNodes.push({ id: `dst_${d.h}`, label: d.label, side: "dest", value: v, share: (v / income) * 100 });
    dstSum += v;
  }
  if (expense > noise) {
    if (expenseNodes.length === 0) {
      expenseNodes.push({
        id: "dst_all",
        label: "Interest expense (not broken out)",
        side: "dest",
        value: expense,
        share: (expense / income) * 100,
      });
      notes.push("This filing does not break interest expense into sub-items 2.1–2.5, so the right fan is a single node.");
      dstSum = expense;
    } else {
      const residual = expense - dstSum;
      if (residual > roundFloor) {
        expenseNodes.push({
          id: "dst_other",
          label: "Other interest expense",
          side: "dest",
          value: residual,
          share: (residual / income) * 100,
        });
        dstSum += residual;
        notes.push(
          `Sub-items 2.1–2.5 account for ${fmtCompact(expense - residual)} of the ${fmtCompact(expense)} interest expense; the ${fmtCompact(residual)} remainder is drawn as an explicit “Other” node rather than dropped.`,
        );
      } else if (residual > 0) {
        closeNote("interest-expense", residual);
      } else if (residual < -noise) {
        return EMPTY_FLOW(
          `The filed interest-expense sub-items sum to ${fmtCompact(dstSum)}, MORE than the filed interest expense of ${fmtCompact(expense)} — an extraction gap. The fan is suppressed rather than drawn with numbers that don't add up.`,
        );
      }
    }
  }
  expenseNodes.sort((a, b) => b.value - a.value);
  dests.push(...expenseNodes);

  // The two closing assertions the fan is only allowed to draw on.
  const srcGap = Math.abs(sources.reduce((s, n) => s + n.value, 0) - income);
  const dstGap = Math.abs(dests.reduce((s, n) => s + n.value, 0) - income);
  if (srcGap > noise || dstGap > noise) {
    return EMPTY_FLOW(
      "The interest fan does not close against the filed interest income — flow suppressed; the filed rows are in the table below.",
    );
  }

  sources.sort((a, b) => b.value - a.value);

  const topSrc = sources[0];
  const topDst = expenseNodes[0];
  const parts: string[] = [];
  if (topSrc) parts.push(`₺${topSrc.share.toFixed(1)} of every ₺100 of interest income comes from ${topSrc.label.toLowerCase()}`);
  if (topDst) parts.push(`₺${topDst.share.toFixed(1)} goes straight back out as interest on ${topDst.label.toLowerCase()}`);
  parts.push(`the bank keeps ₺${((nii / income) * 100).toFixed(1)} as net interest income`);

  return {
    income,
    expense,
    nii,
    sources,
    dests,
    renderable: true,
    notes,
    lead: `${parts.join("; ")}.`,
  };
}

// ---------------------------------------------------------------------------
// Layout — three columns, collision-resolved labels with leader lines
// ---------------------------------------------------------------------------

export interface FlowPlacedNode extends FlowNode {
  x: number;
  y: number;
  w: number;
  h: number;
  /** Text anchor point for the label block. */
  labelX: number;
  labelY: number;
  labelAnchor: "start" | "end";
  /** Leader line back to the node when the label was pushed off its centre. */
  leader: { x1: number; y1: number; x2: number; y2: number } | null;
}

export interface FlowRibbon {
  id: string;
  path: string;
  /** "in" = a source feeding the hub; "out" = the hub paying an expense;
   *  "keep" = the hub's net interest income (the hero ribbon). */
  kind: "in" | "out" | "keep";
}

export interface FlowLayout {
  W: number;
  H: number;
  nodes: FlowPlacedNode[];
  ribbons: FlowRibbon[];
}

const NODE_W = 11;
const NODE_GAP = 12;
const PAD_T = 14;
const PAD_B = 14;
const LABEL_L = 200; // left label gutter (source names, end-anchored)
const LABEL_R = 232; // right label gutter (destination names, start-anchored)
/** Two-line label (name + mono figure) — the minimum vertical pitch. */
const LABEL_PITCH = 25;

/**
 * Push a column's labels apart so none overlap: forward pass drives them down
 * from their targets, backward pass recovers if the stack overran the bottom.
 * Same idea as `chart-end-labels.tsx`, in plain numbers.
 */
function resolveLabels(targets: number[], top: number, bottom: number): number[] {
  const idx = targets.map((y, i) => ({ y, i })).sort((a, b) => a.y - b.y);
  const out = new Array<number>(targets.length);
  let prev = -Infinity;
  for (const it of idx) {
    const y = Math.min(Math.max(it.y, Math.max(top, prev + LABEL_PITCH)), bottom);
    out[it.i] = y;
    prev = y;
  }
  for (let k = idx.length - 2; k >= 0; k--) {
    const cur = idx[k].i;
    const next = idx[k + 1].i;
    out[cur] = Math.min(out[cur], out[next] - LABEL_PITCH);
  }
  return out;
}

export function layoutInterestFlow(f: InterestFlow, W = 980, H = 440): FlowLayout {
  if (!f.renderable) return { W, H, nodes: [], ribbons: [] };

  const srcX = LABEL_L;
  const dstX = W - LABEL_R - NODE_W;
  const hubX = (srcX + NODE_W + dstX) / 2 - NODE_W / 2;

  // One vertical scale for both fans — each column sums to the filed income.
  const avail = (n: number) => H - PAD_T - PAD_B - NODE_GAP * Math.max(n - 1, 0);
  const scale = Math.min(
    avail(f.sources.length) / f.income,
    avail(f.dests.length) / f.income,
  );

  const nodes: FlowPlacedNode[] = [];
  const place = (list: FlowNode[], x: number, anchor: "start" | "end") => {
    const stackH =
      list.reduce((s, n) => s + Math.max(n.value * scale, 2), 0) + NODE_GAP * Math.max(list.length - 1, 0);
    let y = PAD_T + Math.max(0, (H - PAD_T - PAD_B - stackH) / 2);
    const placed: FlowPlacedNode[] = [];
    for (const n of list) {
      const h = Math.max(n.value * scale, 2);
      placed.push({
        ...n,
        x,
        y,
        w: NODE_W,
        h,
        labelX: anchor === "end" ? x - 9 : x + NODE_W + 9,
        labelY: y + h / 2,
        labelAnchor: anchor,
        leader: null,
      });
      y += h + NODE_GAP;
    }
    const resolved = resolveLabels(
      placed.map((p) => p.y + p.h / 2),
      PAD_T + 8,
      H - PAD_B - 6,
    );
    placed.forEach((p, i) => {
      const target = p.y + p.h / 2;
      p.labelY = resolved[i];
      if (Math.abs(resolved[i] - target) > 3) {
        p.leader = {
          x1: anchor === "end" ? p.labelX + 4 : p.labelX - 4,
          y1: resolved[i],
          x2: anchor === "end" ? p.x : p.x + p.w,
          y2: target,
        };
      }
    });
    nodes.push(...placed);
    return placed;
  };

  const srcPlaced = place(f.sources, srcX, "end");
  const dstPlaced = place(f.dests, dstX, "start");

  const hubH = f.income * scale;
  const hubY = PAD_T + Math.max(0, (H - PAD_T - PAD_B - hubH) / 2);
  const hub: FlowPlacedNode = {
    id: "hub",
    label: "Interest income",
    side: "hub",
    value: f.income,
    share: 100,
    x: hubX,
    y: hubY,
    w: NODE_W,
    h: hubH,
    labelX: hubX + NODE_W / 2,
    labelY: hubY - 8,
    labelAnchor: "start",
    leader: null,
  };
  nodes.push(hub);

  const ribbon = (
    id: string,
    x0: number,
    y0: number,
    x1: number,
    y1: number,
    h0: number,
    h1: number,
    kind: FlowRibbon["kind"],
  ): FlowRibbon => {
    const mx = (x0 + x1) / 2;
    return {
      id,
      kind,
      path:
        `M ${x0} ${y0} C ${mx} ${y0} ${mx} ${y1} ${x1} ${y1} ` +
        `L ${x1} ${y1 + h1} C ${mx} ${y1 + h1} ${mx} ${y0 + h0} ${x0} ${y0 + h0} Z`,
    };
  };

  const ribbons: FlowRibbon[] = [];
  let hubIn = 0;
  for (const s of srcPlaced) {
    const h = Math.max(s.value * scale, 1);
    ribbons.push(
      ribbon(`in_${s.id}`, s.x + s.w, s.y + s.h / 2 - h / 2, hub.x, hub.y + hubIn, h, h, "in"),
    );
    hubIn += h;
  }
  let hubOut = 0;
  for (const d of dstPlaced) {
    const h = Math.max(d.value * scale, 1);
    ribbons.push(
      ribbon(
        `out_${d.id}`,
        hub.x + hub.w,
        hub.y + hubOut,
        d.x,
        d.y + d.h / 2 - h / 2,
        h,
        h,
        d.hero ? "keep" : "out",
      ),
    );
    hubOut += h;
  }

  return { W, H, nodes, ribbons };
}
