/**
 * Series primitives shared by the sector tabs.
 *
 * These were written for /credit and are not credit-specific — /asset-quality
 * needs every one of them. Pairing is by DATE (±1 week), never by row offset: a
 * hole in a weekly series would otherwise silently stretch the comparison window
 * (see computeWeeklyGrowth in weekly-growth.ts for the same rule).
 */

export interface Pt {
  period: string; // ISO date, YYYY-MM-DD
  value: number | null;
}

const DAY_MS = 86_400_000;
const WEEK_DAYS = 7;
/** 52 weeks. Annualisation elsewhere uses 364/elapsed for the same reason. */
export const YEAR_DAYS = 364;

export function shiftDays(iso: string, days: number): string {
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
 * Deflate a growth series by CPI (exact Fisher form, not the g−π shortcut).
 *
 * Weeks whose month has no published CPI are DROPPED, never nowcast — so a real
 * line can trail its nominal twin by up to ~6 weeks. (real-terms.ts rule.)
 */
export function deflate(rows: Pt[], cpiYoY: Map<string, number>): Pt[] {
  const out: Pt[] = [];
  for (const r of rows) {
    if (r.value == null) continue;
    const pi = cpiYoY.get(r.period.slice(0, 7));
    if (pi == null) continue;
    out.push({ period: r.period, value: ((1 + r.value / 100) / (1 + pi / 100) - 1) * 100 });
  }
  return out;
}

/** Growth over `windowDays`, annualised by the ACTUAL elapsed days. */
export function growthSeries(rows: Pt[], windowDays = YEAR_DAYS): Pt[] {
  const m = toMap(rows);
  const out: Pt[] = [];
  for (const r of rows) {
    if (r.value == null) continue;
    const b = baseFor(m, r.period, windowDays);
    if (!b || b.value <= 0) continue;
    out.push({
      period: r.period,
      value: (Math.pow(r.value / b.value, YEAR_DAYS / b.elapsed) - 1) * 100,
    });
  }
  return out;
}

export interface Contribution {
  key: string;
  label: string;
  /** pp of the total's growth contributed by this part (or % of its increase). */
  pp: number;
  /** Change over the window, in source units. */
  delta: number;
  level: number;
  /** The part's own growth over the window (%). */
  growth: number;
}

/**
 * Decompose a total's change into per-part contributions:
 *   pp = Δpart ÷ total_base × 100
 *
 * The parts MUST be disjoint and exhaustive — that they sum to the total's own
 * growth is the proof the cut is right, and callers print it. A part that is a
 * CUT of another (SME ⊂ commercial) must never be passed here; carry it as a
 * memo via `memo` instead.
 */
export function contributions(
  total: Pt[],
  parts: Array<{ key: string; label: string; rows: Pt[] }>,
  windowDays = YEAR_DAYS,
): { at: string | null; items: Contribution[]; sumPp: number; totalPp: number | null } {
  const totMap = toMap(total);
  const last = total.filter((r) => r.value != null).at(-1);
  if (!last) return { at: null, items: [], sumPp: 0, totalPp: null };

  const totBase = baseFor(totMap, last.period, windowDays);
  if (!totBase || totBase.value <= 0) {
    return { at: last.period, items: [], sumPp: 0, totalPp: null };
  }

  const items: Contribution[] = [];
  for (const p of parts) {
    const m = toMap(p.rows);
    const now = m.get(last.period);
    const base = baseFor(m, last.period, windowDays);
    if (now == null || !base) continue;
    const delta = now - base.value;
    items.push({
      key: p.key,
      label: p.label,
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

/** Sum several level series period-by-period (only periods every leg covers). */
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
    .filter(([, v]) => v.n === series.length)
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

/** Trailing run comparing each point to another series' same-date point. */
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

/** Trailing run of strictly rising observations (monthly ratio streaks). */
export function risingRun(rows: Pt[]): number {
  let n = 0;
  for (let i = rows.length - 1; i > 0; i--) {
    const cur = rows[i].value;
    const prev = rows[i - 1].value;
    if (cur == null || prev == null || cur <= prev) break;
    n++;
  }
  return n;
}
