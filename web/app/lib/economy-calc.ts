/**
 * The economy tab's PURE half — every transform and the forecast scorecard,
 * with no D1 import anywhere in the module graph.
 *
 * Split out of economy.ts for the same reason series.ts was split out of
 * credit.ts: the loader needs `evdsMulti`, which reaches Cloudflare bindings, and
 * a module that touches those cannot be unit-tested here (there is no path alias
 * in the vitest setup, by design — the tested libs are the pure ones). The
 * arithmetic that decides what the page ASSERTS — the Fisher real rate, the
 * %-of-GDP conversion, and above all the scorecard's refusal to grade a year it
 * only half holds — is exactly the arithmetic that has to be pinned.
 *
 * economy.ts re-exports all of this, so importers are unchanged.
 */
import { type EvdsRow } from "./metrics";
// The buffer itself is assembled by the loader (economy.ts); this module only
// needs its SHAPE, to type the field on EconomyData.
import { type ReserveBuffer } from "./reserves";

export interface Point {
  period_date: string;
  value: number;
}

// ---------------------------------------------------------------------------
// Pure transforms
// ---------------------------------------------------------------------------

/** % change vs `lag` observations earlier (12 = y/y monthly, 4 = y/y quarterly). */
export function pctChange(rows: EvdsRow[], lag: number): Point[] {
  const out: Point[] = [];
  for (let i = lag; i < rows.length; i++) {
    const prev = rows[i - lag].value;
    if (prev === 0) continue;
    out.push({
      period_date: rows[i].period_date,
      value: 100 * (rows[i].value / prev - 1),
    });
  }
  return out;
}

/** Rolling sum over the trailing `window` observations, scaled. */
export function rollingSum(rows: EvdsRow[], window: number, scale = 1): Point[] {
  const out: Point[] = [];
  let acc = 0;
  for (let i = 0; i < rows.length; i++) {
    acc += rows[i].value;
    if (i >= window) acc -= rows[i - window].value;
    if (i >= window - 1) {
      out.push({ period_date: rows[i].period_date, value: acc * scale });
    }
  }
  return out;
}

/** Collapse a daily/weekly series to monthly averages (dated at month start). */
export function monthlyAverage(rows: EvdsRow[]): Point[] {
  const acc = new Map<string, { sum: number; n: number }>();
  for (const r of rows) {
    const month = `${r.period_date.slice(0, 7)}-01`;
    const cur = acc.get(month) ?? { sum: 0, n: 0 };
    cur.sum += r.value;
    cur.n += 1;
    acc.set(month, cur);
  }
  return Array.from(acc.entries())
    .sort((a, b) => a[0].localeCompare(b[0]))
    .map(([period_date, { sum, n }]) => ({ period_date, value: sum / n }));
}

/** Simple value scaling (unit conversions). */
export function scaled(rows: EvdsRow[], scale: number): Point[] {
  return rows.map((r) => ({ period_date: r.period_date, value: r.value * scale }));
}

/** Element-wise a − b over the dates both series carry. */
export function spread(a: Point[], b: Point[]): Point[] {
  const m = new Map(b.map((r) => [r.period_date, r.value]));
  const out: Point[] = [];
  for (const p of a) {
    const v = m.get(p.period_date);
    if (v === undefined) continue;
    out.push({ period_date: p.period_date, value: p.value - v });
  }
  return out;
}

/**
 * Ex-ante real rate: nominal monthly rate deflated by the 12m-ahead
 * inflation expectation, compounded — ((1+i)/(1+πᵉ) − 1) × 100.
 *
 * Fisher, not subtraction: at ~30% inflation the two differ by several points,
 * and the gap is largest exactly where the sign of the real rate is in question.
 */
export function exAnteReal(nominal: Point[], expectation: EvdsRow[]): Point[] {
  const exp = new Map(expectation.map((r) => [r.period_date, r.value]));
  const out: Point[] = [];
  for (const p of nominal) {
    const e = exp.get(p.period_date);
    if (e === undefined) continue;
    out.push({
      period_date: p.period_date,
      value: 100 * ((1 + p.value / 100) / (1 + e / 100) - 1),
    });
  }
  return out;
}

/**
 * 12-month rolling fiscal balance as % of rolling-4-quarter nominal GDP.
 * Both sides are in TL thousand, so units cancel. Each month is matched
 * with the most recent completed 4-quarter GDP window at or before it.
 */
export function pctOfGdp(monthlyFlow: EvdsRow[], nominalGdpQ: EvdsRow[]): Point[] {
  const gdp4q = rolling4qGdp(nominalGdpQ);
  const flow12 = rollingSum(monthlyFlow, 12);
  const out: Point[] = [];
  for (const f of flow12) {
    const g = stepAt(gdp4q, f.period_date);
    if (!g) continue;
    out.push({ period_date: f.period_date, value: 100 * (f.value / g) });
  }
  return out;
}

/** Trailing-4-quarter nominal GDP (TL thousand). */
export function rolling4qGdp(nominalGdpQ: EvdsRow[]): Point[] {
  const out: Point[] = [];
  for (let i = 3; i < nominalGdpQ.length; i++) {
    out.push({
      period_date: nominalGdpQ[i].period_date,
      value:
        nominalGdpQ[i].value + nominalGdpQ[i - 1].value +
        nominalGdpQ[i - 2].value + nominalGdpQ[i - 3].value,
    });
  }
  return out;
}

/** Latest value at or before `date` — a stepped read over an ascending series. */
export function stepAt(pts: Point[], date: string): number | null {
  for (let i = pts.length - 1; i >= 0; i--) {
    if (pts[i].period_date <= date) return pts[i].value;
  }
  return null;
}

/** Sum several series date-by-date, scaled (dates present in the first input). */
export function sumByDate(sets: EvdsRow[][], scale = 1): Point[] {
  const acc = new Map<string, number>();
  for (const set of sets) {
    for (const r of set) acc.set(r.period_date, (acc.get(r.period_date) ?? 0) + r.value);
  }
  return Array.from(acc.entries())
    .sort((a, b) => a[0].localeCompare(b[0]))
    .map(([period_date, v]) => ({ period_date, value: v * scale }));
}

/**
 * Mean of a series' observations inside one calendar year, with the count.
 *
 * The count is returned, never hidden: an "average so far" over two months is a
 * different claim from one over twelve, and the caller has to be able to print
 * which it is. Scoring a full-year forecast against a partial year without
 * saying so is the whole failure mode this guards.
 */
export function yearMean(pts: Point[], year: string): { mean: number; n: number } | null {
  const w = pts.filter((p) => p.period_date.startsWith(year));
  if (!w.length) return null;
  return { mean: w.reduce((a, p) => a + p.value, 0) / w.length, n: w.length };
}

export interface EconomyData {
  gdpGrowth: Point[];          // y/y %, quarterly
  ipGrowth: Point[];           // y/y %, monthly (SA index)
  unemployment: Point[];       // SA %
  participation: Point[];      // SA %
  employedMn: Point[];         // million persons, SA
  cpiYoY: Point[];             // y/y %
  cpiMoM: Point[];             // m/m %
  expCurrentYearEnd: Point[];  // survey, %
  expNextYearEnd: Point[];     // survey, %
  exp12m: Point[];             // market participants' survey, %
  hhExp12m: Point[];           // households' survey, % (thin series — guard it)
  expGap: Point[];             // households − market participants, pp
  fundingMonthly: Point[];     // CBRT effective funding cost, monthly avg %
  policyRate: Point[];         // 1-week repo, monthly avg %
  realRate: Point[];           // ex-ante real funding rate, %
  depositRate: Point[];        // TL deposit rate, monthly avg %
  realDepositRate: Point[];    // deposit rate deflated by the 12m expectation, %
  loanCommercial: Point[];     // commercial loan rate, monthly avg %
  loanConsumer: Point[];       // consumer loan rate, monthly avg %
  loanHousing: Point[];        // housing loan rate, monthly avg %
  loanDepositSpread: Point[];  // commercial loan − deposit, pp
  usdtry: Point[];             // daily level
  eurtry: Point[];             // daily level
  reer: Point[];               // monthly index
  ca12m: Point[];              // 12m rolling, USD bn
  caExGold12m: Point[];        // 12m rolling, USD bn
  caExGoldEnergy12m: Point[];  // 12m rolling, USD bn
  neo12m: Point[];             // net errors & omissions, 12m rolling, USD bn
  caPctGdp: Point[];           // 12m CA as % of 4Q nominal GDP (USD-converted)
  budgetPctGdp: Point[];       // 12m rolling, % GDP
  primaryPctGdp: Point[];      // 12m rolling, % GDP
  cashPctGdp: Point[];         // 12m rolling, % GDP
  nominalGdp4q: Point[];       // trailing-4Q nominal GDP, ₺ trillion
  reserves: ReserveBuffer;     // gross / net / net-excl-swaps, USD bn
  importCover: number | null;  // months of the goods import bill gross covers
  imports12m: Point[];         // 12m rolling customs imports, USD bn
  householdFx: Point[];        // residents' FX cash (USD+EUR), USD bn
  householdGold: Point[];      // residents' precious metals, USD bn
  /** The year the forecast scorecard is scored against, from the data itself. */
  scoreYear: string;
}

// ---------------------------------------------------------------------------
// The published-forecast scorecard
// ---------------------------------------------------------------------------

/**
 * A third party's published baseline, scored against what actually happened.
 *
 * This was a static table: thirteen rows of BBVA's March-2026 forecasts printed
 * as-is, with a 2026 column nobody ever came back to check. Five months later the
 * page was still presenting an unexamined forecast as content while the site held
 * the realized series that settle most of it.
 *
 * So the numbers stay (they are a real, attributable published view — the reader
 * gains from seeing what the sell side expected) and the page now scores them. A
 * row is scorable only when we hold a series on the SAME BASIS; the rest print
 * their reason instead of a number, because a scorecard that quietly omits its
 * misses is worse than no scorecard.
 *
 * The two structural non-scorables:
 *   eop rows      An end-of-period forecast is not settled by a partial year, and
 *                 scoring it against the latest print would grade December in
 *                 August.
 *   % of GDP      BBVA quotes CENTRAL GOVERNMENT; our 12m ratio (TP.KB.GEN*) is
 *                 the GENERAL budget. Different populations, so subtracting one
 *                 from the other flatters or damns the forecast by an amount
 *                 nobody could see (DESIGN.md, "compare like with like").
 */
export type ScoreBasis =
  /** Mean of the forecast year's observations so far. */
  | { kind: "mean"; series: keyof EconomyData }
  /** Not settled until the year ends. */
  | { kind: "eop" }
  /** We hold no series on the forecast's basis. */
  | { kind: "basis"; why: string };

export interface BaselineRow {
  label: string;
  values: readonly string[];
  /** How (and whether) the forecast column can be scored from our own series. */
  score: ScoreBasis;
  /** Decimals for the realized figure. */
  decimals?: number;
  /** Unit suffix on the realized figure. */
  unit?: string;
}

// Declared as `readonly BaselineRow[]` rather than `as const`: a const-asserted
// literal narrows each row to its own type, so the optional `unit`/`decimals`
// stop existing on the union and the scorer can't read them.
const BASELINE_ROWS: readonly BaselineRow[] = [
    { label: "GDP growth (avg)", values: ["5.0%", "3.3%", "3.6%", "4.0%"], score: { kind: "mean", series: "gdpGrowth" }, unit: "%" },
    { label: "Unemployment rate (avg)", values: ["9.4%", "8.7%", "8.4%", "9.0%"], score: { kind: "mean", series: "unemployment" }, unit: "%" },
    { label: "Inflation (avg)", values: ["53.9%", "58.5%", "34.9%", "28.0%"], score: { kind: "mean", series: "cpiYoY" }, unit: "%" },
    { label: "Inflation (eop)", values: ["64.8%", "44.4%", "30.9%", "25.0%"], score: { kind: "eop" } },
    { label: "CBRT cost of funding (avg)", values: ["20.5%", "49.6%", "43.6%", "35.8%"], score: { kind: "mean", series: "fundingMonthly" }, unit: "%" },
    { label: "CBRT cost of funding (eop)", values: ["42.5%", "47.5%", "38.0%", "32.0%"], score: { kind: "eop" } },
    { label: "USD/TRY (avg)", values: ["23.7", "32.8", "39.5", "47.3"], score: { kind: "mean", series: "usdtry" }, decimals: 2 },
    { label: "USD/TRY (eop)", values: ["29.4", "35.3", "42.8", "52.0"], score: { kind: "eop" } },
    { label: "EUR/TRY (avg)", values: ["25.7", "35.5", "44.7", "55.7"], score: { kind: "mean", series: "eurtry" }, decimals: 2 },
    { label: "EUR/TRY (eop)", values: ["32.6", "36.7", "50.3", "62.2"], score: { kind: "eop" } },
    { label: "Current account (% GDP)", values: ["-3.6%", "-1.0%", "-1.9%", "-2.4%"], score: { kind: "mean", series: "caPctGdp" }, unit: "%" },
    { label: "CG primary balance (% GDP)", values: ["-2.6%", "-1.9%", "0.4%", "0.1%"], score: { kind: "basis", why: "central govt; we hold the general budget" } },
    { label: "CG budget balance (% GDP)", values: ["-5.1%", "-4.7%", "-2.9%", "-3.5%"], score: { kind: "basis", why: "central govt; we hold the general budget" } },
];

export const BBVA_BASELINE = {
  asOf: "March 2026",
  source: "Garanti BBVA Research — Türkiye Economic Outlook 1Q26",
  years: ["2023", "2024", "2025", "2026 (f)"],
  /** The calendar year the forecast column covers. */
  forecastYear: "2026",
  rows: BASELINE_ROWS,
} as const;

export interface ScoredRow {
  label: string;
  values: readonly string[];
  /** Realized figure for the forecast year, formatted — null when not scorable. */
  realized: string | null;
  /** Observations behind `realized`, so the page can print the basis. */
  n: number | null;
  /** Realized − forecast, in the row's own units. Null when not scorable. */
  gap: number | null;
  /** Why there is no realized figure, when there isn't one. */
  note: string | null;
}

/** Parse "47.3" / "-2.4%" from the forecast column. */
function parseForecast(v: string): number | null {
  const n = Number(v.replace(/[%\s]/g, ""));
  return Number.isFinite(n) ? n : null;
}

/**
 * Score every baseline row against the series we hold. Pure — takes the loaded
 * data, so it is unit-testable and cannot drift from what the page rendered.
 */
export function scoreBaseline(d: EconomyData): ScoredRow[] {
  const year = BBVA_BASELINE.forecastYear;
  return BBVA_BASELINE.rows.map((r): ScoredRow => {
    const fc = parseForecast(r.values[r.values.length - 1]);
    const base = { label: r.label, values: r.values };
    if (r.score.kind === "eop") {
      return { ...base, realized: null, n: null, gap: null, note: `eop — settles in December ${year}` };
    }
    if (r.score.kind === "basis") {
      return { ...base, realized: null, n: null, gap: null, note: r.score.why };
    }
    const series = d[r.score.series];
    if (!Array.isArray(series)) {
      return { ...base, realized: null, n: null, gap: null, note: "series unavailable" };
    }
    const m = yearMean(series as Point[], year);
    if (!m) {
      return { ...base, realized: null, n: null, gap: null, note: `no ${year} observations yet` };
    }
    const dec = r.decimals ?? 1;
    return {
      ...base,
      realized: `${m.mean.toFixed(dec)}${r.unit ?? ""}`,
      n: m.n,
      gap: fc != null ? m.mean - fc : null,
      note: null,
    };
  });
}

/** Mean of the `n` observations ending at or before `date`. */
export function trailingMean(pts: Point[], date: string, n: number): number | null {
  const upTo = pts.filter((p) => p.period_date <= date);
  if (upTo.length < n) return null;
  const w = upTo.slice(-n);
  return w.reduce((a, p) => a + p.value, 0) / w.length;
}
