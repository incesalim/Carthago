import { createText } from "../../i18n/text";
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
import { BANK_TYPE_BY_TICKER } from "./bank_names";

// Re-exported because `BriefLayer.tsx` consumes it. Was `CAR_MIN = 12` commented
// "BDDK regulatory minimum" — 12% is BDDK's TARGET ratio; the statutory floor is
// 8%. See capital-thresholds.ts for why that distinction is load-bearing.
export { CAR_TARGET } from "./capital-thresholds";
import { CAR_TARGET } from "./capital-thresholds";
import { realRate } from "./real-terms";

/** Where this bank sits in the field, on one metric. */
export interface PeerStat {
  value: number;
  median: number;
  min: number;
  max: number;
  /** 1 = best on this metric (direction-aware). */
  rank: number;
  /** Banks reporting the metric this quarter, within `universe`. */
  n: number;
  /** Which field this was ranked against — "deposit banks", "all banks", … */
  universe: string;
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
 * Licence class, which is the peer boundary that actually matters — BDDK
 * partitions the sector the same way (mevduat / katılım / kalkınma-yatırım).
 * `BANK_TYPE_BY_TICKER` codes OWNERSHIP (state/private/foreign are three codes
 * for one business model), so it has to be collapsed before it is useful here.
 */
const PEER_CLASS_LABEL: Record<string, string> = {
  deposit: "deposit banks",
  participation: "participation banks",
  devinv: "development & investment banks",
};

function peerClassOf(ticker: string): string | null {
  switch (BANK_TYPE_BY_TICKER[ticker]) {
    case "10005":
    case "10006":
    case "10007":
      return "deposit";
    case "10003":
      return "participation";
    case "10004":
      return "devinv";
    default:
      return null;
  }
}

/**
 * This bank against its peer class in the same quarter. Returns null when the
 * bank has no value, or when fewer than `minField` peers reported (a "rank" out
 * of three banks is noise, not context).
 *
 * ⚠️ This used to compare against the ENTIRE licensed universe — every bank
 * reporting, no class filter. Development & investment banks fund themselves
 * without deposits and run capital ratios up to ~85%, and the recent digital
 * entrants are tiny, so they set the level: at 2026Q1 the universe CAR median is
 * 17.1% (n=37) against 15.3% for the big deposit banks. Every large bank's page
 * therefore read "below the field" on capital while sitting AT its true peers'
 * median. Comparing a deposit bank to Eximbank is not a peer comparison.
 *
 * Falls back to the whole field when the class is too thin to rank within, or
 * when the ticker's class is unknown — and reports which universe it used, so
 * the page can say so rather than implying one it did not use.
 */
export function peerStat(
  panel: BankMetricRow[],
  ticker: string,
  period: string,
  spec: PeerFieldSpec,
  minField = 8,
  universe: "class" | "all" = "class",
): PeerStat | null {
  const all = panel
    .filter((r) => r.period === period && r[spec.key] != null)
    .map((r) => ({ t: r.bank_ticker, v: (r[spec.key] as number) * spec.scale }));

  const cls = universe === "class" ? peerClassOf(ticker) : null;
  const classField = cls ? all.filter((r) => peerClassOf(r.t) === cls) : [];
  // Only narrow to the class if it is deep enough to rank inside; otherwise the
  // wider field is the more honest context, labelled as such.
  const useClass = cls != null && classField.length >= minField;
  const field = useClass ? classField : all;
  const universeLabel = useClass ? PEER_CLASS_LABEL[cls] : "all banks";

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
    universe: universeLabel,
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

export const ordinal = (n: number, locale = "en"): string => {
  if (locale === "tr") return `${n}.`;
  const s = ["th", "st", "nd", "rd"];
  const v = n % 100;
  return `${n}${s[(v - 20) % 10] ?? s[v] ?? s[0]}`;
};

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
  /**
   * Set when the bank takes no deposits, so the ladder legitimately has no
   * funding cost and no spread. Printed under the rows so their absence reads as
   * a fact about the bank rather than a hole in our data.
   */
  fundingNote: string | null;
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

export function engineGate(
  rows: BankMetricRow[],
  opts?: {
    /** Quarters actually on file for this bank (from its own statement
     *  periods), independent of the ratio panel. Lets the gate tell "never
     *  filed" apart from "the panel does not carry this bank". */
    auditedQuarters?: number;
    /** True when the bank is deliberately excluded from the peer ratio panel
     *  (`PEER_EXCLUDED_TICKERS` — Takasbank: market infrastructure, not a
     *  lender). */
    peerExcluded?: boolean;
  },
  locale = "en",
): EngineGate {
  const tx = createText(locale);
  const latest = rows[rows.length - 1];
  const filings = rows.length;
  const first = rows[0]?.period ?? null;
  // ROE is the ladder's anchor and the one row that must exist for the section to
  // say anything. Do NOT also require `spread`: a development/investment bank
  // (TSKB, KLNMA) takes no deposits, so it has no deposit cost and no spread BY
  // CONSTRUCTION — gating on spread suppressed its whole ladder, ROE included,
  // and then told the reader the filings were missing when 34 quarters were on
  // file. Rows that cannot be formed drop out individually (the caller filters
  // null values); the section stands as long as ROE does.
  const ready = !!latest && latest.roe != null;
  if (ready) {
    // A missing spread must never be a silent hole. It is either structural (the
    // bank takes no deposits) or a gap in what we hold — say which.
    const fundingNote =
      latest.spread != null
        ? null
        : latest.deposits_stock === 0
          ? "No deposit cost or spread: this bank takes no deposits — it funds itself in the market, so the ladder starts at what the assets earn. These rows are absent because they do not exist for this funding model, not because the figures are missing."
          : "No deposit cost or spread: we hold no deposits line for this period, so the funding leg cannot be formed. The rest of the ladder stands on its own.";
    return { ready, filings, firstPeriod: first, reason: null, fundingNote };
  }
  // The panel is a RANKING, not the universe (heatmap.ts `ensure` refuses
  // peer-excluded banks): Takasbank has no rows HERE while holding years of
  // filings on its own Financials tab. Saying "has filed 0 quarters" about 17
  // audited quarters was a false sentence on a section built never to print one.
  const audited = opts?.auditedQuarters ?? 0;
  if (filings === 0 && audited > 0) {
    return {
      ready: false,
      filings,
      firstPeriod: first,
      fundingNote: null,
      reason: opts?.peerExcluded
        ? tx("{0} audited quarter{1} on file, but this institution is deliberately excluded from the peer ratio panel — market infrastructure, not a lender — so yield, funding cost, spread, cost of risk and ROE are not computed for it. The statements themselves are under Financials.", {0: audited, 1: audited === 1 ? " is" : "s are"})
        : tx("{0} audited quarter{1} on file, but the ratio panel holds no rows for this bank, so yield, funding cost, spread, cost of risk and ROE were not computed. The statements themselves are under Financials.", {0: audited, 1: audited === 1 ? " is" : "s are"}),
    };
  }
  return {
    ready: false,
    filings,
    firstPeriod: first,
    fundingNote: null,
    reason:
      filings < 5
        ? tx("Trailing-twelve-month figures need four quarters of income statement over five quarter-ends of average balances. This bank has filed {0} quarter{1}{2}, so yield, funding cost, spread, cost of risk and ROE cannot be formed without inventing a denominator.", {0: filings, 1: filings === 1 ? "" : "s", 2: first ? tx(" (first: {0})", {0: first}) : ""})
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
export function bankFlags(d: FlagInput, locale = "en"): BriefFlag[] {
  const tx = createText(locale);
  const out: BriefFlag[] = [];
  const buffer = d.car != null ? d.car - CAR_TARGET : null;

  if (d.car != null && d.carQoq != null && buffer != null && d.carQoq < -1 && buffer < 8) {
    out.push({
      id: "car-step",
      kind: "flag",
      title: "Capital step-down",
      detail:
        tx("CAR fell {0}pp in a quarter to {1}% — a {2}pp buffer over the {3}% target ratio", {0: Math.abs(d.carQoq).toFixed(1), 1: d.car.toFixed(1), 2: buffer.toFixed(1), 3: CAR_TARGET}) +
        `${d.carRank ? tx(", {0} of {1}", {0: ordinal(d.carRank.rank, tx.locale), 1: d.carRank.n}) : ""}` +
        `${d.assetsQoqPct != null ? tx(", while the balance sheet grew {0}% q/q", {0: d.assetsQoqPct.toFixed(1)}) : ""}.`,
      rule: `Δcar_qoq < −1pp AND buffer < 8pp`,
    });
  } else if (d.car != null && d.carQoq != null && buffer != null && d.carQoq < -5 && buffer >= 8) {
    out.push({
      id: "car-normalise",
      kind: "note",
      title: "Capital normalising",
      detail:
        tx("CAR fell {0}pp to {1}% as the book grew", {0: Math.abs(d.carQoq).toFixed(1), 1: d.car.toFixed(1)}) +
        tx("{0}, but {1}pp of buffer remains. Capital being deployed, not depleted.", {0: d.assetsQoqPct != null ? tx(" {0}% q/q", {0: d.assetsQoqPct.toFixed(1)}) : "", 1: buffer.toFixed(1)}),
      rule: `Δcar_qoq < −5pp AND buffer ≥ 8pp → note, not flag`,
    });
  }

  // Deflate with the exact Fisher form, not `roe − cpi`. real-terms.ts:19-22
  // measures the shortcut at 1.2-1.8pp adrift around 32% CPI, and
  // real-terms.test.ts asserts the two must NOT agree — yet this flag shipped the
  // shortcut, so the per-bank page and the Fisher-deflated pages disagreed on the
  // same bank. GARAN 2026Q1: subtraction −1.55pp, Fisher −1.18%.
  const realRoePct =
    d.roe != null && d.cpi12m != null ? realRate(d.roe, d.cpi12m) : null;
  if (realRoePct != null && realRoePct < 0) {
    out.push({
      id: "real-roe",
      kind: "flag",
      title: "Real returns",
      detail: tx("ROE {0}% against {1}% 12-month-average CPI: equity compounds a {2}pp real loss.", {0: d.roe!.toFixed(1), 1: d.cpi12m!.toFixed(1), 2: Math.abs(realRoePct).toFixed(1)}),
      rule: `(1 + roe) / (1 + cpi_12m_avg) − 1 < 0`,
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
        tx("{0} consecutive quarterly rises, to {1}%.{2}", {0: d.nplRises, 1: d.npl.toFixed(2), 2: vsMed}) +
        `${d.stage2Share != null ? tx(" Stage-2 — the pre-NPL watchlist — sits at {0}% of the book.", {0: d.stage2Share.toFixed(1)}) : ""}`,
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
        tx("Cost / income {0}% — the bank spends ₺{1} for every ₺1 of income. ", {0: d.costIncome.toFixed(1), 1: (d.costIncome / 100).toFixed(2)}) +
        (buildOut
          ? tx("Normal {0} quarters into a build-out; the test is the trend.", {0: d.filings})
          : tx("{0} quarters in, this is not a build-out cost base — the franchise is not covering itself.", {0: d.filings})),
      rule: `cost_income > 100% · build-out = filings ≤ ${BUILD_OUT_QUARTERS}q`,
    });
  }

  const liqOk = d.lcr != null && d.lcr >= 120 && (d.ldr == null || d.ldr < 100);
  if (liqOk) {
    out.push({
      id: "liquidity",
      kind: "ok",
      title: "Liquidity clear",
      detail: tx("LCR {0}%{1} — funding is not a constraint this quarter.", {0: d.lcr!.toFixed(0), 1: d.ldr != null ? tx(" and TL+FC loan/deposit {0}%", {0: d.ldr.toFixed(0)}) : ""}),
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
  locale = "en",
): string {
  const tx = createText(locale);
  const gap = Math.abs(s.value - s.median);
  const place = tx("{0} of {1}", {0: ordinal(s.rank, tx.locale), 1: s.n});

  switch (key) {
    case "car": {
      const b = ctx.buffer;
      if (b != null && b < 4) return tx("{0}. One of the field's thinnest buffers — {1}pp over the {2}% target ratio.", {0: place, 1: b.toFixed(1), 2: CAR_TARGET});
      if (b != null && b > 20) return tx("{0}. {1}pp of headroom — capital raised well ahead of the book.", {0: place, 1: b.toFixed(1)});
      return `${place} — ${bandOf(s.rank, s.n)}${b != null ? tx(", {0}pp over the target", {0: b.toFixed(1)}) : ""}.`;
    }
    case "npl_ratio":
      return s.value < s.median
        ? tx("Cleaner than the median — {0}pp below it. The worst book in the field runs {1}%.", {0: gap.toFixed(2), 1: s.max.toFixed(1)})
        : tx("{0}pp above the median. The worst book in the field runs {1}%.", {0: gap.toFixed(2), 1: s.max.toFixed(1)});
    case "roe": {
      const r = ctx.realRoe;
      return (
        tx("{0} — {1}pp {2} the median", {0: place, 1: gap.toFixed(1), 2: s.value < s.median ? "under" : "over"}) +
        (r != null ? tx(" and {0}pp {1} inflation.", {0: Math.abs(r).toFixed(1), 1: r < 0 ? "under" : "over"}) : ".")
      );
    }
    case "nim":
      return tx("{0}. {1}pp {2} the median margin.", {0: place, 1: gap.toFixed(2), 2: s.value < s.median ? "under" : "over"});
    case "cost_income":
      if (s.value > 100) {
        // Only a YOUNG bank is in a build-out. See BUILD_OUT_QUARTERS.
        return ctx.filings != null && ctx.filings > BUILD_OUT_QUARTERS
          ? tx("{0}. Costs exceed income — {1} quarters in, the franchise is not covering itself.", {0: place, 1: ctx.filings})
          : tx("{0}. Costs exceed income — the build-out has not reached break-even.", {0: place});
      }
      if (s.rank <= Math.ceil(s.n * 0.25))
        return tx("{0} — top quartile. {1}pp better than the median: scale is earning its keep.", {0: place, 1: gap.toFixed(1)});
      return tx("{0} — {1}, {2}pp {3} than the median.", {0: place, 1: bandOf(s.rank, s.n), 2: gap.toFixed(1), 3: s.value < s.median ? "better" : "worse"});
    default:
      return place;
  }
}
