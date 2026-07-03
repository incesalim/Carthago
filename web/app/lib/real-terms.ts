/**
 * Real-terms convention (display-study Phase 2): every headline nominal growth
 * series gets a CPI-deflated twin, so 30%+ prints stop reading as expansion by
 * default in a 28%+ CPI regime.
 *
 * CPI source: TP.TUKFIY2025.GENEL monthly levels (2025=100, backcast pre-2018 —
 * TP.FG.J0 died at the Jan-2026 TUIK rebase). Real growth uses the exact Fisher
 * form, not the g−π shortcut: real = (1+g)/(1+π) − 1.
 *
 * Honesty rule: points whose month has no published CPI yet (the current
 * month's weekly prints) are DROPPED from the real line rather than nowcast —
 * the real twin may end up to ~6 weeks behind the nominal line.
 */
import { evdsSeries } from "./metrics";

/** Series codes the nominal-vs-real TrendChart keys on. */
export const REAL_TERMS_LABELS: Record<string, string> = {
  NOMINAL: "Nominal (y/y)",
  REAL: "Real (CPI-deflated)",
};

/** CPI YoY (%) keyed by month 'YYYY-MM', from monthly index levels. */
export async function cpiYoYByMonth(yearsBack = 8): Promise<Map<string, number>> {
  const rows = await evdsSeries("TP.TUKFIY2025.GENEL", yearsBack);
  const sorted = rows.slice().sort((a, b) => a.period_date.localeCompare(b.period_date));
  const map = new Map<string, number>();
  for (let i = 12; i < sorted.length; i++) {
    const base = sorted[i - 12].value;
    if (base > 0) {
      map.set(sorted[i].period_date.slice(0, 7), (sorted[i].value / base - 1) * 100);
    }
  }
  return map;
}

/**
 * Pair a nominal YoY series with its CPI-deflated twin as long-form rows for
 * TrendChart (codes NOMINAL / REAL). Input must be a single pre-filtered
 * series; period 'YYYY-MM-DD' or 'YYYY-MM'.
 */
export function nominalVsReal(
  rows: Array<{ period: string; value: number | null }>,
  cpiYoY: Map<string, number>,
): Array<{ period: string; bank_type_code: string; value: number }> {
  const out: Array<{ period: string; bank_type_code: string; value: number }> = [];
  for (const r of rows) {
    if (r.value == null) continue;
    out.push({ period: r.period, bank_type_code: "NOMINAL", value: r.value });
    const pi = cpiYoY.get(r.period.slice(0, 7));
    if (pi == null) continue;
    out.push({
      period: r.period,
      bank_type_code: "REAL",
      value: ((1 + r.value / 100) / (1 + pi / 100) - 1) * 100,
    });
  }
  return out;
}
