/**
 * The Financials section's lenses and the balance sheet's SHAPE — pure, no I/O.
 *
 * The statement table on /banks/[ticker] can be read through four lenses, all
 * driven by the same `?mode=` URL param so every view stays server-rendered and
 * shareable:
 *
 *   abs   — the filed figure, TL thousands (the default).
 *   yoy   — nominal year-over-year % vs the same quarter a year earlier.
 *   real  — the SAME nominal y/y, DEFLATED by CPI. Turkish nominal growth is
 *           mostly the lira losing value: at 30-40% inflation a balance sheet
 *           that grows 35% has stood still. `realGrowth` divides — (1+n)/(1+cpi)−1
 *           — it is NOT a subtraction (a 40% line against 32% CPI is +6.1% real,
 *           not +8).
 *   size  — common-size: every line as a % of total assets (balance sheet) or of
 *           interest income (income statement), which is what makes two banks of
 *           different size comparable line-for-line — and, on the balance sheet,
 *           against the sector median share.
 *
 * The SHAPE layer above the table answers the question the table cannot: not
 * "what are the numbers" but "what IS this bank" — the composition of what it
 * owns and what funds it, each line carrying its share and its REAL growth.
 */
import { realGrowth } from "./bank-brief";
import { ordOf, periodFromOrd, yoyPct } from "./period-math";
import type { Pt } from "./desk";

export type StatementMode = "abs" | "yoy" | "real" | "size";

/** Period→value series, as the per-bank page's pivots hold it. */
export type PeriodSeries = Map<string, number | null>;

// ---------------------------------------------------------------------------
// The deflator
// ---------------------------------------------------------------------------

const QUARTER_END_MONTH: Record<string, string> = { "1": "03", "2": "06", "3": "09", "4": "12" };

export interface CpiPick {
  /** CPI y/y, %. */
  value: number;
  /** The month it was read at ("2026-03"). */
  month: string;
  /** True when it is the quarter-end print, false when it is the latest print
   *  standing in for a quarter the CPI series doesn't reach. The caption says which. */
  matched: boolean;
}

/**
 * The CPI y/y to deflate a statement period with: the print at the quarter END
 * if the series reaches it, else the latest print — flagged, never silently
 * substituted.
 */
export function cpiForPeriod(cpiYoy: Pt[], period: string | null): CpiPick | null {
  const m = period ? /^(\d{4})Q([1-4])$/.exec(period) : null;
  if (m) {
    const key = `${m[1]}-${QUARTER_END_MONTH[m[2]]}`;
    const hit = cpiYoy.find((p) => p.period === key);
    if (hit?.value != null) return { value: hit.value, month: key, matched: true };
  }
  const last = cpiYoy.at(-1);
  if (last?.value == null) return null;
  return { value: last.value, month: last.period, matched: false };
}

// ---------------------------------------------------------------------------
// The real lens
// ---------------------------------------------------------------------------

export type Verdict = "growing" | "standing still" | "shrinking";

/** A real growth rate becomes a word. ±3pp is the "standing still" band. */
export function verdictOf(realPct: number): Verdict {
  if (realPct > 3) return "growing";
  if (realPct < -3) return "shrinking";
  return "standing still";
}

export interface RealRead {
  nominal: number | null;
  cpi: number | null;
  real: number | null;
  verdict: Verdict | null;
}

/** Nominal y/y for one period from a raw series, then the real rate off it. */
export function realRead(series: PeriodSeries, period: string | null, cpi: number | null): RealRead {
  const o = period ? ordOf(period) : null;
  if (o == null) return { nominal: null, cpi, real: null, verdict: null };
  const curr = series.get(period as string) ?? null;
  const prior = series.get(periodFromOrd(o - 4)) ?? null;
  const nominal = yoyPct(curr, prior);
  const real = nominal != null && cpi != null ? realGrowth(nominal, cpi) : null;
  return { nominal, cpi, real, verdict: real == null ? null : verdictOf(real) };
}

// ---------------------------------------------------------------------------
// The shape — what the balance sheet is made of
// ---------------------------------------------------------------------------

export interface CompLine {
  hierarchy: string;
  label: string;
  /** An "of which" detail line — shown nested, NOT counted in the total. */
  sub?: boolean;
}

export interface CompRow {
  key: string;
  label: string;
  value: number;
  /** % of total assets. */
  share: number;
  nominal: number | null;
  real: number | null;
  sub: boolean;
}

/**
 * One side of the balance sheet as a composition: every roman parent that is at
 * least `minShare` of total assets, with its share and its REAL y/y, plus an
 * explicit "Other" row carrying the remainder — so the column closes to 100 %
 * without a single line being quietly dropped.
 */
export function compositionRows(
  pivot: Map<string, PeriodSeries>,
  statement: "assets" | "liabilities",
  lines: CompLine[],
  period: string,
  totalAssets: number,
  cpi: number | null,
  minShare = 0.4,
): CompRow[] {
  if (!(totalAssets > 0)) return [];
  const o = ordOf(period);
  const prior = o == null ? null : periodFromOrd(o - 4);
  const at = (h: string, p: string | null): number | null =>
    p == null ? null : (pivot.get(`${statement}::${h}`)?.get(p) ?? null);

  const rows: CompRow[] = [];
  let named = 0;
  for (const l of lines) {
    const v = at(l.hierarchy, period);
    if (v == null) continue;
    if (!l.sub) named += v;
    const share = (v / totalAssets) * 100;
    if (Math.abs(share) < minShare) continue;
    const nominal = yoyPct(v, at(l.hierarchy, prior));
    rows.push({
      key: `${statement}::${l.hierarchy}`,
      label: l.label,
      value: v,
      share,
      nominal,
      real: nominal != null && cpi != null ? realGrowth(nominal, cpi) : null,
      sub: !!l.sub,
    });
  }

  const residual = totalAssets - named;
  if ((residual / totalAssets) * 100 >= minShare) {
    rows.push({
      key: `${statement}::__other`,
      label: "Other / not broken out",
      value: residual,
      share: (residual / totalAssets) * 100,
      nominal: null,
      real: null,
      sub: false,
    });
  }
  return rows;
}

/**
 * The balance sheet's lead sentence — computed from the same series the
 * composition columns draw. Null when the deflator or the prior year is missing;
 * the page then simply prints nothing rather than a hedged claim.
 */
export function balanceSheetLead(
  totalAssets: RealRead,
  loans: RealRead | null,
  deposits: RealRead | null,
): string | null {
  if (totalAssets.nominal == null) return null;
  const sgn = (v: number, d = 1) => `${v >= 0 ? "+" : "−"}${Math.abs(v).toFixed(d)}%`;
  if (totalAssets.cpi == null || totalAssets.real == null) {
    return `The balance sheet grew ${sgn(totalAssets.nominal)} year-over-year in nominal lira; the CPI print needed to deflate it is not available for this quarter.`;
  }
  const head = `Nominally ${sgn(totalAssets.nominal)}, but with CPI at ${totalAssets.cpi.toFixed(1)}% that is ${sgn(totalAssets.real)} real`;
  const tail: string[] = [];
  if (loans?.real != null) tail.push(`loans ${sgn(loans.real)} real`);
  if (deposits?.real != null) tail.push(`deposits ${sgn(deposits.real)} real`);
  return tail.length > 0 ? `${head} — ${tail.join(" while ")}.` : `${head}.`;
}
