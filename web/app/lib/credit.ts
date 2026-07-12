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

export interface Pt {
  period: string; // ISO date, YYYY-MM-DD
  value: number | null;
}

const DAY_MS = 86_400_000;
const WEEK_DAYS = 7;
/** 52 weeks. Annualisation elsewhere uses 364/elapsed for the same reason. */
export const YEAR_DAYS = 364;

function shiftDays(iso: string, days: number): string {
  return new Date(Date.parse(iso + "T00:00:00Z") - days * DAY_MS).toISOString().slice(0, 10);
}

/** period → value, skipping nulls. */
export function toMap(rows: Pt[]): Map<string, number> {
  const m = new Map<string, number>();
  for (const r of rows) if (r.value != null) m.set(r.period, r.value);
  return m;
}

/**
 * The observation ~`windowDays` before `period`: exact date first, then ±1 week
 * (BDDK skips the odd holiday week). Returns null rather than reaching further.
 */
export function baseFor(
  m: Map<string, number>,
  period: string,
  windowDays = YEAR_DAYS,
): { value: number; elapsed: number } | null {
  for (const elapsed of [windowDays, windowDays + WEEK_DAYS, windowDays - WEEK_DAYS]) {
    const v = m.get(shiftDays(period, elapsed));
    if (v != null) return { value: v, elapsed };
  }
  return null;
}

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

/**
 * Deflate a growth series by CPI (exact Fisher form, not the g−π shortcut).
 * Weeks whose month has no published CPI are dropped — see the honesty rule.
 */
export function deflate(rows: Pt[], cpiYoY: Map<string, number>): Pt[] {
  const out: Pt[] = [];
  for (const r of rows) {
    if (r.value == null) continue;
    const pi = cpiYoY.get(r.period.slice(0, 7));
    if (pi == null) continue; // no CPI for this month — drop, never nowcast
    out.push({ period: r.period, value: ((1 + r.value / 100) / (1 + pi / 100) - 1) * 100 });
  }
  return out;
}

export interface CreditBridge {
  nominal: number | null;
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

export interface Contribution {
  key: string;
  label: string;
  /** pp of the sector's growth rate contributed by this book. */
  pp: number;
  /** TL change over the window (source units — TL millions). */
  delta: number;
  level: number;
  /** The book's own growth over the window (%). */
  growth: number;
}

/**
 * Decompose the sector's growth into per-segment contributions:
 *   pp = Δsegment / total_base × 100
 *
 * The segments passed in MUST be disjoint and exhaustive — housing + auto + GPL
 * + cards + commercial reconciles to the BDDK sector total. SME is a CUT of
 * commercial (~36% of it), so passing it here would double-count; it is carried
 * separately as `nested`.
 */
export function contributions(
  total: Pt[],
  segments: Array<{ key: string; label: string; rows: Pt[] }>,
  windowDays = YEAR_DAYS,
): { at: string | null; items: Contribution[]; sumPp: number; totalPp: number | null } {
  const totMap = toMap(total);
  const last = total.filter((r) => r.value != null).at(-1);
  if (!last) return { at: null, items: [], sumPp: 0, totalPp: null };

  const totBase = baseFor(totMap, last.period, windowDays);
  if (!totBase || totBase.value <= 0) return { at: last.period, items: [], sumPp: 0, totalPp: null };

  const items: Contribution[] = [];
  for (const s of segments) {
    const m = toMap(s.rows);
    const now = m.get(last.period);
    const base = baseFor(m, last.period, windowDays);
    if (now == null || !base) continue;
    const delta = now - base.value;
    items.push({
      key: s.key,
      label: s.label,
      pp: (delta / totBase.value) * 100,
      delta,
      level: now,
      growth: base.value > 0 ? (now / base.value - 1) * 100 : 0,
    });
  }

  const totNow = totMap.get(last.period)!;
  return {
    at: last.period,
    items,
    sumPp: items.reduce((a, c) => a + c.pp, 0),
    totalPp: (totNow / totBase.value - 1) * 100,
  };
}

/** Sum two level series period-by-period (e.g. cards + GPL = the unsecured book). */
export function sumSeries(...series: Pt[][]): Pt[] {
  const acc = new Map<string, { sum: number; n: number }>();
  for (const s of series) {
    for (const r of s) {
      if (r.value == null) continue;
      const cur = acc.get(r.period) ?? { sum: 0, n: 0 };
      acc.set(r.period, { sum: cur.sum + r.value, n: cur.n + 1 });
    }
  }
  return [...acc.entries()]
    .filter(([, v]) => v.n === series.length) // only periods every series covers
    .map(([period, v]) => ({ period, value: v.sum }))
    .sort((a, b) => a.period.localeCompare(b.period));
}

/**
 * How many trailing observations satisfy `test`, counting back from the latest.
 * Powers the flag rules ("negative for 10 consecutive weeks").
 */
export function trailingRun(rows: Pt[], test: (v: number) => boolean): number {
  let n = 0;
  for (let i = rows.length - 1; i >= 0; i--) {
    const v = rows[i].value;
    if (v == null || !test(v)) break;
    n++;
  }
  return n;
}

/** Trailing run where each point is compared against another series' same-date point. */
export function trailingRunVs(
  rows: Pt[],
  other: Pt[],
  test: (v: number, o: number) => boolean,
): number {
  const o = toMap(other);
  let n = 0;
  for (let i = rows.length - 1; i >= 0; i--) {
    const v = rows[i].value;
    const ov = o.get(rows[i].period);
    if (v == null || ov == null || !test(v, ov)) break;
    n++;
  }
  return n;
}
