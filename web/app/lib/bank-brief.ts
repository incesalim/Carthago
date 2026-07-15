/**
 * The per-bank brief — pure, deterministic, no LLM.
 *
 * Everything a bank's page says about itself is derived here from rows the page
 * already fetches (`heatmapPanel` — the same panel /cross-bank builds — plus the
 * CPI deflator). No sentence is authored per bank: a rank becomes a phrase
 * through `bandOf`, a threshold becomes a flag through the registry below, and
 * every flag prints the rule it fired on.
 *
 * UNITS (heatmap.ts): `car`/`cet1`/`lcr`/`fx_nop`/`repricing_gap_1y` arrive in
 * percentage POINTS; `roe`/`roa`/`nim`/`npl_ratio`/`cost_income`/`spread`/… are
 * FRACTIONS. Callers pass `scale` accordingly — see PEER_FIELDS.
 *
 * DEGRADATION IS THE POINT. Only 8 of 36 banks report branch counts, 11 are
 * listed, and the TTM engine (ROE, yield, funding cost, spread, cost of risk)
 * needs five quarter-ends of balances — a bank four filings old has none of it.
 * Every helper returns null rather than inventing a denominator, and the page
 * renders an explanation instead of an empty tile.
 */
import type { BankMetricRow, MetricKey } from "./heatmap";

export const CAR_MIN = 12; // BDDK regulatory minimum, incl. buffers

/** Where this bank sits in the field, on one metric. */
export interface PeerStat {
  value: number;
  median: number;
  min: number;
  max: number;
  /** 1 = best on this metric (direction-aware). */
  rank: number;
  /** Banks reporting the metric this quarter. */
  n: number;
}

export interface PeerFieldSpec {
  key: MetricKey;
  label: string;
  sub: string;
  /** Multiply the stored value (fractions → %). */
  scale: number;
  /** Is a higher number better? Drives the rank direction only. */
  higherIsBetter: boolean;
  decimals: number;
  /** Axis window for the strip; outliers beyond it are clamped and marked. */
  lo: number;
  hi: number;
}

/**
 * The five metrics the strip band shows, in reading order. CAR and NPL come
 * straight off the latest filing, so every bank that files has them; ROE, NIM
 * and Cost/Income are trailing-twelve-month and need five quarter-ends of
 * history, so they drop for banks with too little of it.
 */
export const PEER_FIELDS: PeerFieldSpec[] = [
  { key: "car", label: "Capital adequacy", sub: "CAR, §4", scale: 1, higherIsBetter: true, decimals: 1, lo: 12, hi: 30 },
  { key: "npl_ratio", label: "Asset quality", sub: "NPL ratio", scale: 100, higherIsBetter: false, decimals: 2, lo: 0, hi: 12 },
  { key: "roe", label: "Returns", sub: "ROE, TTM", scale: 100, higherIsBetter: true, decimals: 1, lo: 0, hi: 50 },
  { key: "nim", label: "Margin", sub: "NIM, TTM", scale: 100, higherIsBetter: true, decimals: 2, lo: 0, hi: 22 },
  { key: "cost_income", label: "Efficiency", sub: "cost / income", scale: 100, higherIsBetter: false, decimals: 1, lo: 20, hi: 140 },
];

const median = (xs: number[]): number => {
  const s = [...xs].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
};

/**
 * This bank against every bank reporting the same quarter. Returns null when the
 * bank has no value, or when fewer than `minField` peers reported (a "rank" out
 * of three banks is noise, not context).
 */
export function peerStat(
  panel: BankMetricRow[],
  ticker: string,
  period: string,
  spec: PeerFieldSpec,
  minField = 8,
): PeerStat | null {
  const field = panel
    .filter((r) => r.period === period && r[spec.key] != null)
    .map((r) => ({ t: r.bank_ticker, v: (r[spec.key] as number) * spec.scale }));
  if (field.length < minField) return null;
  const me = field.find((r) => r.t === ticker);
  if (!me) return null;

  const vals = field.map((r) => r.v);
  const ordered = [...field].sort((a, b) => (spec.higherIsBetter ? b.v - a.v : a.v - b.v));
  return {
    value: me.v,
    median: median(vals),
    min: Math.min(...vals),
    max: Math.max(...vals),
    rank: ordered.findIndex((r) => r.t === ticker) + 1,
    n: field.length,
  };
}

/** A rank becomes a phrase — this is the whole "prose engine". */
export function bandOf(rank: number, n: number): string {
  const p = rank / n;
  if (p <= 0.25) return "top quartile";
  if (p <= 0.5) return "upper half";
  if (p <= 0.75) return "lower half";
  return "bottom quartile";
}

export const ordinal = (n: number): string => {
  const s = ["th", "st", "nd", "rd"];
  const v = n % 100;
  return `${n}${s[(v - 20) % 10] ?? s[v] ?? s[0]}`;
};

/** Real return: a nominal rate less inflation, in points. */
export const realOf = (nominalPct: number, cpiPct: number): number => nominalPct - cpiPct;

/** Real growth: a nominal growth rate deflated by CPI (not a subtraction). */
export const realGrowth = (nominalPct: number, cpiPct: number): number =>
  ((1 + nominalPct / 100) / (1 + cpiPct / 100) - 1) * 100;

// ---------------------------------------------------------------------------
// The engine gate — why a section may be absent
// ---------------------------------------------------------------------------

export interface EngineGate {
  ready: boolean;
  /** Quarters this bank has filed (rows in the panel). */
  filings: number;
  /** The first period we hold. */
  firstPeriod: string | null;
  /** Plain-language reason, printed instead of an empty tile. */
  reason: string | null;
}

/**
 * The TTM margin engine needs four quarters of income statement over five
 * quarter-ends of average balances. A bank that has filed fewer simply has no
 * yield, funding cost, spread, cost of risk or ROE — and the page says so.
 */
/**
 * Two years of filings. Past this, a cost base above income is not a build-out —
 * it is a franchise that does not cover itself, and the page should say so.
 */
export const BUILD_OUT_QUARTERS = 8;

export function engineGate(rows: BankMetricRow[]): EngineGate {
  const latest = rows[rows.length - 1];
  const filings = rows.length;
  const first = rows[0]?.period ?? null;
  const ready = !!latest && latest.spread != null && latest.roe != null;
  if (ready) return { ready, filings, firstPeriod: first, reason: null };
  return {
    ready: false,
    filings,
    firstPeriod: first,
    reason:
      filings < 5
        ? `Trailing-twelve-month figures need four quarters of income statement over five quarter-ends of average balances. This bank has filed ${filings} quarter${filings === 1 ? "" : "s"}${first ? ` (first: ${first})` : ""}, so yield, funding cost, spread, cost of risk and ROE cannot be formed without inventing a denominator.`
        : "The trailing-twelve-month figures did not resolve for this bank — the income statement or the average balances are missing from the filings we hold.",
  };
}

// ---------------------------------------------------------------------------
// Flags — a registry; each prints the rule it fired on
// ---------------------------------------------------------------------------

export interface BriefFlag {
  id: string;
  kind: "flag" | "note" | "ok";
  title: string;
  detail: string;
  /** The literal rule, printed under the flag (automation honesty). */
  rule: string;
}

export interface FlagInput {
  car: number | null;
  carQoq: number | null;
  carRank: { rank: number; n: number } | null;
  assetsQoqPct: number | null;
  roe: number | null;
  cpi12m: number | null;
  npl: number | null;
  nplRises: number;
  nplMedian: number | null;
  stage2Share: number | null;
  costIncome: number | null;
  filings: number;
  lcr: number | null;
  ldr: number | null;
}

const pp = (v: number, d = 1) => `${v >= 0 ? "+" : "−"}${Math.abs(v).toFixed(d)}pp`;

/**
 * Six rules, evaluated in order. Note the capital pair: a big quarterly CAR drop
 * is only a *flag* when the buffer is thin. A new bank deploying a large opening
 * capital base (Colendi: −21pp q/q, buffer still 28.7pp) is doing the opposite of
 * running out of capital, and gets a note instead — the level qualifies the move.
 */
export function bankFlags(d: FlagInput): BriefFlag[] {
  const out: BriefFlag[] = [];
  const buffer = d.car != null ? d.car - CAR_MIN : null;

  if (d.car != null && d.carQoq != null && buffer != null && d.carQoq < -1 && buffer < 8) {
    out.push({
      id: "car-step",
      kind: "flag",
      title: "Capital step-down",
      detail:
        `CAR fell ${Math.abs(d.carQoq).toFixed(1)}pp in a quarter to ${d.car.toFixed(1)}% — a ${buffer.toFixed(1)}pp buffer over the ${CAR_MIN}% minimum` +
        `${d.carRank ? `, ${ordinal(d.carRank.rank)} of ${d.carRank.n}` : ""}` +
        `${d.assetsQoqPct != null ? `, while the balance sheet grew ${d.assetsQoqPct.toFixed(1)}% q/q` : ""}.`,
      rule: `Δcar_qoq < −1pp AND buffer < 8pp`,
    });
  } else if (d.car != null && d.carQoq != null && buffer != null && d.carQoq < -5 && buffer >= 8) {
    out.push({
      id: "car-normalise",
      kind: "note",
      title: "Capital normalising",
      detail:
        `CAR fell ${Math.abs(d.carQoq).toFixed(1)}pp to ${d.car.toFixed(1)}% as the book grew` +
        `${d.assetsQoqPct != null ? ` ${d.assetsQoqPct.toFixed(1)}% q/q` : ""}, but ${buffer.toFixed(1)}pp of buffer remains. Capital being deployed, not depleted.`,
      rule: `Δcar_qoq < −5pp AND buffer ≥ 8pp → note, not flag`,
    });
  }

  if (d.roe != null && d.cpi12m != null && d.roe - d.cpi12m < 0) {
    out.push({
      id: "real-roe",
      kind: "flag",
      title: "Real returns",
      detail: `ROE ${d.roe.toFixed(1)}% against ${d.cpi12m.toFixed(1)}% 12-month-average CPI: equity compounds a ${Math.abs(d.roe - d.cpi12m).toFixed(1)}pp real loss.`,
      rule: `roe − cpi_12m_avg < 0`,
    });
  }

  if (d.npl != null && d.nplRises >= 4) {
    const vsMed =
      d.nplMedian != null
        ? d.npl < d.nplMedian
          ? " The level is still better than the field median; the direction is the signal."
          : " Level and direction are both adverse."
        : "";
    out.push({
      id: "npl-drift",
      kind: "flag",
      title: "NPL drift",
      detail:
        `${d.nplRises} consecutive quarterly rises, to ${d.npl.toFixed(2)}%.${vsMed}` +
        `${d.stage2Share != null ? ` Stage-2 — the pre-NPL watchlist — sits at ${d.stage2Share.toFixed(1)}% of the book.` : ""}`,
      rule: `consecutive_rise(npl) ≥ 4q`,
    });
  }

  // A young bank spending more than it earns is a build-out. A bank with twenty
  // quarters of filings doing the same thing is not — it is a bank having a bad
  // year, and calling that "normal, N quarters into a build-out" is flattery. The
  // guard used to fire on cost_income alone; the age is what makes it a build-out.
  if (d.costIncome != null && d.costIncome > 100) {
    const buildOut = d.filings <= BUILD_OUT_QUARTERS;
    out.push({
      id: "below-breakeven",
      kind: "flag",
      title: "Below break-even",
      detail:
        `Cost / income ${d.costIncome.toFixed(1)}% — the bank spends ₺${(d.costIncome / 100).toFixed(2)} for every ₺1 of income. ` +
        (buildOut
          ? `Normal ${d.filings} quarters into a build-out; the test is the trend.`
          : `${d.filings} quarters in, this is not a build-out cost base — the franchise is not covering itself.`),
      rule: `cost_income > 100% · build-out = filings ≤ ${BUILD_OUT_QUARTERS}q`,
    });
  }

  const liqOk = d.lcr != null && d.lcr >= 120 && (d.ldr == null || d.ldr < 100);
  if (liqOk) {
    out.push({
      id: "liquidity",
      kind: "ok",
      title: "Liquidity clear",
      detail: `LCR ${d.lcr!.toFixed(0)}%${d.ldr != null ? ` and loan/deposit ${d.ldr.toFixed(0)}%` : ""} — funding is not a constraint this quarter.`,
      rule: `lcr < 120 OR ldr > 100 → would fire; neither did`,
    });
  }

  void pp;
  return out;
}

/** Consecutive rises at the end of a series (used by the NPL-drift rule). */
export function risingStreak(values: (number | null)[]): number {
  let n = 0;
  for (let i = values.length - 1; i > 0; i--) {
    const c = values[i];
    const p = values[i - 1];
    if (c == null || p == null) break;
    if (c > p) n++;
    else break;
  }
  return n;
}

// ---------------------------------------------------------------------------
// The peer read — a strip's sentence, chosen by rank band and gap to median
// ---------------------------------------------------------------------------

export function peerRead(
  key: MetricKey,
  s: PeerStat,
  ctx: { buffer?: number | null; realRoe?: number | null; filings?: number | null },
): string {
  const gap = Math.abs(s.value - s.median);
  const place = `${ordinal(s.rank)} of ${s.n}`;

  switch (key) {
    case "car": {
      const b = ctx.buffer;
      if (b != null && b < 4) return `${place}. One of the field's thinnest buffers — ${b.toFixed(1)}pp over the ${CAR_MIN}% floor.`;
      if (b != null && b > 20) return `${place}. ${b.toFixed(1)}pp of headroom — capital raised well ahead of the book.`;
      return `${place} — ${bandOf(s.rank, s.n)}${b != null ? `, ${b.toFixed(1)}pp over the floor` : ""}.`;
    }
    case "npl_ratio":
      return s.value < s.median
        ? `Cleaner than the median — ${gap.toFixed(2)}pp below it. The worst book in the field runs ${s.max.toFixed(1)}%.`
        : `${gap.toFixed(2)}pp above the median. The worst book in the field runs ${s.max.toFixed(1)}%.`;
    case "roe": {
      const r = ctx.realRoe;
      return (
        `${place} — ${gap.toFixed(1)}pp ${s.value < s.median ? "under" : "over"} the median` +
        (r != null ? ` and ${Math.abs(r).toFixed(1)}pp ${r < 0 ? "under" : "over"} inflation.` : ".")
      );
    }
    case "nim":
      return `${place}. ${gap.toFixed(2)}pp ${s.value < s.median ? "under" : "over"} the median margin.`;
    case "cost_income":
      if (s.value > 100) {
        // Only a YOUNG bank is in a build-out. See BUILD_OUT_QUARTERS.
        return ctx.filings != null && ctx.filings > BUILD_OUT_QUARTERS
          ? `${place}. Costs exceed income — ${ctx.filings} quarters in, the franchise is not covering itself.`
          : `${place}. Costs exceed income — the build-out has not reached break-even.`;
      }
      if (s.rank <= Math.ceil(s.n * 0.25))
        return `${place} — top quartile. ${gap.toFixed(1)}pp better than the median: scale is earning its keep.`;
      return `${place} — ${bandOf(s.rank, s.n)}, ${gap.toFixed(1)}pp ${s.value < s.median ? "better" : "worse"} than the median.`;
    default:
      return place;
  }
}
