/**
 * A deterministic sample series for the chart-loading comparison.
 *
 * Sample, not live: this page is about how a chart ARRIVES, not what it says.
 * Real data would add a D1 read to a page whose whole point is measuring
 * client-side cost, and would make two options look different for a reason that
 * has nothing to do with the option.
 *
 * Deterministic (no Math.random) so every reload and every strategy on the page
 * draws the identical line — otherwise the four panels differ visually and the
 * eye reads that as a difference between the strategies.
 */
import type { TrendPoint } from "@/app/components/TrendChart";

const SERIES = [
  { code: "A", base: 16.2, amp: 0.9, phase: 0 },
  { code: "B", base: 13.4, amp: 1.4, phase: 1.1 },
  { code: "C", base: 11.8, amp: 0.6, phase: 2.3 },
];

export const SAMPLE_LABELS: Record<string, string> = {
  A: "Series A",
  B: "Series B",
  C: "Series C",
};

/** 24 monthly points × 3 series — about the density of a real sector chart. */
export const SAMPLE: TrendPoint[] = (() => {
  const out: TrendPoint[] = [];
  for (let i = 0; i < 24; i++) {
    const year = 2024 + Math.floor((i + 6) / 12);
    const month = ((i + 6) % 12) + 1;
    const period = `${year}-${String(month).padStart(2, "0")}`;
    for (const s of SERIES) {
      const drift = (i / 23) * s.amp;
      const wave = Math.sin(i / 3.1 + s.phase) * (s.amp / 2);
      out.push({
        period,
        bank_type_code: s.code,
        value: Number((s.base + drift + wave).toFixed(2)),
      });
    }
  }
  return out;
})();
