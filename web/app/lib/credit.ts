/**
 * Credit-tab transforms — the arithmetic behind the /credit brief.
 *
 * The tab's central problem: a 36%+ nominal loan print in a 32% CPI regime with
 * a depreciating lira is mostly NOT credit. Two adjustments already existed on
 * the page but were never composed:
 *
 *   nominal  → strip currency (FX book at the base period's USD/TRY)
 *            → strip inflation (Fisher, CPI y/y)
 *            = real, constant-FX growth — the only line that says whether the
 *              loan book actually grew.
 *
 * Neither adjustment alone reveals it: at W/E 2026-06-26 real-only reads +3.3%
 * and FX-adjusted-only reads +29%, while the composition reads −2.1%.
 *
 * Honesty rules carried from real-terms.ts:
 *  - CPI is monthly. Weeks whose month has no published CPI are DROPPED, never
 *    nowcast — so the real lines can trail the nominal line by up to ~6 weeks.
 *  - The FX book is proxied as all-USD (BDDK publishes the TL-equivalent only).
 *    This is the single biggest modelling assumption here; it is stated in the
 *    UI, not buried.
 *
 * Pairing is by DATE (±1 week), never by row offset — a hole in a weekly series
 * would otherwise silently stretch the comparison window. Same rule as
 * computeWeeklyGrowth in weekly-growth.ts.
 */

import {
  baseFor,
  deflate,
  shiftDays,
  toMap,
  YEAR_DAYS,
  type Pt,
} from "./series";

// The generic series primitives live in series.ts — /asset-quality needs them too.
// Re-exported so existing importers (and the credit tests) keep working.
export {
  baseFor,
  contributions,
  deflate,
  growthSeries,
  sumSeries,
  toMap,
  trailingRun,
  trailingRunVs,
  YEAR_DAYS,
  type Contribution,
  type Pt,
} from "./series";

/**
 * FX-adjusted growth (BBVA convention): value BOTH periods' FX book at the BASE
 * period's USD/TRY, so lira depreciation stops printing as credit growth. The
 * base FX book is already at the base rate, so only the current leg is restated.
 */
export function fxAdjustedGrowth(
  tl: Pt[],
  fx: Pt[],
  usdTry: Array<{ period_date: string; value: number }>,
  windowDays = YEAR_DAYS,
): Pt[] {
  const rate = new Map(usdTry.map((r) => [r.period_date, r.value]));
  /** USD/TRY on `d`, else the most recent quote in the preceding ~2 weeks. */
  const rateOnOrBefore = (d: string): number | null => {
    for (let i = 0; i < 12; i++) {
      const v = rate.get(shiftDays(d, i));
      if (v != null && v > 0) return v;
    }
    return null;
  };

  const tlMap = toMap(tl);
  const fxMap = toMap(fx);
  const out: Pt[] = [];
  for (const r of fx) {
    if (r.value == null) continue;
    const fxBase = baseFor(fxMap, r.period, windowDays);
    const tlBase = baseFor(tlMap, r.period, windowDays);
    const tlCur = tlMap.get(r.period);
    if (!fxBase || !tlBase || tlCur == null) continue;

    const rCur = rateOnOrBefore(r.period);
    const rBase = rateOnOrBefore(shiftDays(r.period, fxBase.elapsed));
    if (rCur == null || rBase == null) continue;

    const numerator = tlCur + (r.value / rCur) * rBase; // current FX book at the base rate
    const denominator = tlBase.value + fxBase.value;
    if (denominator <= 0) continue;
    out.push({ period: r.period, value: (numerator / denominator - 1) * 100 });
  }
  return out;
}

export interface CreditBridge {
  /** The latest nominal print — the vitals' headline. May LEAD the real legs. */
  nominal: number | null;
  /**
   * The nominal print read at `asOfReal` — the bridge's own starting bar.
   * Every other bridge field is read at `asOfReal`, so anything that composes
   * with a leg (a bar, a sentence) must start here and NOT at `nominal`, or a
   * CPI lag silently mixes a July nominal with a June real.
   */
  nominalAtReal: number | null;
  /** Nominal with the FX book held at a constant USD/TRY. */
  fxAdj: number | null;
  /** Nominal deflated by CPI (the page's existing "real" twin). */
  real: number | null;
  /** BOTH adjustments composed — the figure neither twin shows alone. */
  realFxAdj: number | null;
  cpi: number | null;
  /** How many pp of the nominal print is lira depreciation. */
  currencyPp: number | null;
  /** How many pp of the FX-adjusted print is inflation. */
  inflationPp: number | null;
  /** The nominal print's week. */
  asOfNominal: string | null;
  /** The real lines' week — may TRAIL asOfNominal when CPI has not printed. */
  asOfReal: string | null;
  /** True when the real figure is older than the nominal one. */
  lagged: boolean;
}

/**
 * The bridge: nominal → −currency → FX-adjusted → −inflation → real.
 * Each leg is the difference between two series that are themselves computed,
 * so the bars always reconcile to the endpoints by construction.
 */
export function creditBridge(
  nominalYoY: Pt[],
  fxAdjYoY: Pt[],
  cpiYoY: Map<string, number>,
): CreditBridge {
  const realYoY = deflate(nominalYoY, cpiYoY);
  const realFxAdjYoY = deflate(fxAdjYoY, cpiYoY);

  const lastOf = (s: Pt[]) => s.filter((r) => r.value != null).at(-1) ?? null;
  const nomPt = lastOf(nominalYoY);
  const realFxPt = lastOf(realFxAdjYoY);
  const realPt = lastOf(realYoY);

  // Compare like with like: read every leg at the week the REAL lines end, so a
  // CPI lag can't silently mix a July nominal with a June real.
  const at = (s: Pt[], period: string | null) =>
    period == null ? null : (s.find((r) => r.period === period)?.value ?? null);
  const asOfReal = realFxPt?.period ?? null;

  const nominalAtReal = at(nominalYoY, asOfReal);
  const fxAdjAtReal = at(fxAdjYoY, asOfReal);
  const realFxAdj = realFxPt?.value ?? null;

  return {
    nominal: nomPt?.value ?? null,
    nominalAtReal,
    fxAdj: fxAdjAtReal,
    real: realPt?.value ?? null,
    realFxAdj,
    cpi: asOfReal ? (cpiYoY.get(asOfReal.slice(0, 7)) ?? null) : null,
    currencyPp:
      nominalAtReal != null && fxAdjAtReal != null ? nominalAtReal - fxAdjAtReal : null,
    inflationPp: fxAdjAtReal != null && realFxAdj != null ? fxAdjAtReal - realFxAdj : null,
    asOfNominal: nomPt?.period ?? null,
    asOfReal,
    lagged: !!(nomPt && asOfReal && nomPt.period > asOfReal),
  };
}

