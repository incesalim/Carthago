/**
 * Date-aware rolling growth over the BDDK weekly bulletin.
 *
 * Pairs each observation with the one closest to `windowWeeks` × 7 days
 * earlier — exact date first, then ±1 week (BDDK skips the odd holiday
 * week) — and annualizes by the ACTUAL elapsed days. A row-offset LAG()
 * is not safe here: a hole in one group's history (e.g. the 13-week
 * private-bank SME gap of late 2024) silently stretches the comparison
 * window, which inflated the "YoY" line for a full year after the gap.
 */

export interface WeeklyGrowthInput {
  period: string; // ISO date (YYYY-MM-DD)
  bank_type_code: string;
  value: number | null;
}

export interface WeeklyGrowthPoint {
  period: string;
  bank_type_code: string;
  value: number;
}

const DAY_MS = 86_400_000;

function shiftDays(iso: string, days: number): string {
  return new Date(Date.parse(iso + "T00:00:00Z") - days * DAY_MS)
    .toISOString()
    .slice(0, 10);
}

/**
 * @param rows    raw weekly series, ordered by (period, bank_type_code)
 * @param windowWeeks growth window; annualization exponent = 364 / elapsed days
 * @param cutoff  ISO date — emit points on/after this date (older rows serve
 *                only as comparison bases)
 */
export function computeWeeklyGrowth(
  rows: WeeklyGrowthInput[],
  windowWeeks: number,
  cutoff: string,
): WeeklyGrowthPoint[] {
  const byBank = new Map<string, Map<string, number>>();
  for (const r of rows) {
    if (r.value == null) continue;
    let m = byBank.get(r.bank_type_code);
    if (!m) {
      m = new Map();
      byBank.set(r.bank_type_code, m);
    }
    m.set(r.period, r.value);
  }

  const windowDays = windowWeeks * 7;
  const out: WeeklyGrowthPoint[] = [];
  for (const r of rows) {
    if (r.value == null || r.period < cutoff) continue;
    const m = byBank.get(r.bank_type_code)!;
    for (const elapsed of [windowDays, windowDays + 7, windowDays - 7]) {
      const prev = m.get(shiftDays(r.period, elapsed));
      if (prev === undefined) continue; // week not published — try a neighbor
      if (prev > 0) {
        out.push({
          period: r.period,
          bank_type_code: r.bank_type_code,
          value: (Math.pow(r.value / prev, 364 / elapsed) - 1) * 100,
        });
      }
      break; // nearest published base found — emit or skip, never both
    }
  }
  return out;
}
