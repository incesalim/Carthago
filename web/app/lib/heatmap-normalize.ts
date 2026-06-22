/**
 * Cross-bank heatmap — pure normalization + color helpers.
 *
 * NO D1 / server imports: usable from both the server page (to precompute
 * scores) and the "use client" grid components. Color is emitted as a CSS
 * `color-mix(in oklch, …)` string referencing the theme tokens in globals.css
 * (--positive / --negative / --info / --card), so cells track light/dark
 * automatically — never a hard-coded hex.
 */

export type Direction = "higher_better" | "higher_worse" | "neutral";

/**
 * Per-column percentile rank over the non-null values, direction-adjusted so
 * 1 = best. Ties share their average rank; `higher_worse` columns are inverted
 * (1 - p) so high values score low. Null inputs stay null (excluded from the
 * distribution) and keep their slot, so the output aligns 1:1 with the input.
 *
 * Percentile rank (not min-max) is deliberate: it is robust to mega-bank
 * outliers (acute on total assets) and uses the full color range. The raw value
 * is always shown in-cell, so color encodes rank and text encodes level.
 */
export function normalizeColumn(
  values: (number | null)[],
  dir: Direction,
): (number | null)[] {
  const present: { i: number; v: number }[] = [];
  values.forEach((v, i) => {
    if (v != null && Number.isFinite(v)) present.push({ i, v });
  });
  const n = present.length;
  const out: (number | null)[] = values.map(() => null);
  if (n === 0) return out;
  if (n === 1) {
    out[present[0].i] = 0.5; // lone value sits mid-range (neutral color)
    return out;
  }

  // Ascending sort; assign each value its average 1-based rank across ties.
  const sorted = [...present].sort((a, b) => a.v - b.v);
  const rankByIndex = new Map<number, number>();
  let k = 0;
  while (k < sorted.length) {
    let j = k;
    while (j + 1 < sorted.length && sorted[j + 1].v === sorted[k].v) j++;
    const avgRank = (k + 1 + (j + 1)) / 2; // mean of the tied 1-based positions
    for (let t = k; t <= j; t++) rankByIndex.set(sorted[t].i, avgRank);
    k = j + 1;
  }

  for (const { i } of present) {
    const p = (rankByIndex.get(i)! - 1) / (n - 1); // 0 = worst value, 1 = best value (ascending)
    out[i] = dir === "higher_worse" ? 1 - p : p;
  }
  return out;
}

/**
 * Map a 0..1 score to a theme-aware CSS color string.
 *  - directional (default): green above the midpoint, red below, intensity
 *    growing with distance from 0.5. Mix % capped low (≤42) so mid-rank cells
 *    stay near-white and only genuine leaders/laggards read strongly — the grid
 *    breathes instead of flooding, and --foreground text stays legible.
 *  - neutral: a quiet low-chroma slate ramp (size / valuation metrics aren't
 *    good-or-bad, so no green↔red — and deliberately NOT a saturated hue, so it
 *    doesn't compete with the directional columns).
 * Uses the dedicated --heat-* tokens (purer green / softer red / slate), which
 * track light & dark via globals.css. Null score → "transparent" (cell shows a
 * muted "—").
 */
export function scoreToColor(score: number | null, neutral = false): string {
  if (score == null) return "transparent";
  if (neutral) {
    const pct = Math.min(30, Math.max(0, score * 30));
    return `color-mix(in oklch, var(--heat-neutral) ${pct}%, var(--card))`;
  }
  if (score >= 0.5) {
    const pct = Math.min(42, (score - 0.5) * 84);
    return `color-mix(in oklch, var(--heat-pos) ${pct}%, var(--card))`;
  }
  const pct = Math.min(42, (0.5 - score) * 84);
  return `color-mix(in oklch, var(--heat-neg) ${pct}%, var(--card))`;
}

/**
 * Format a raw metric value for display. Mirrors the en-US number style used
 * across the dashboard (BarByBank.tsx). NOTE: bank_audit_*.amount_total is in
 * THOUSAND-TL (BankCard.tsx), so trillions = value / 1e9 and billions =
 * value / 1e6 (not /1e6 and /1e3 as the sector-aggregate tables use).
 */
export function formatMetricValue(
  value: number | null,
  unit: "pct" | "trn" | "bn" | "raw" | "mult",
  decimals: number,
): string {
  if (value == null || !Number.isFinite(value)) return "—";
  const nf = new Intl.NumberFormat("en-US", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
  switch (unit) {
    case "pct":
      return `${nf.format(value * 100)}%`;
    case "trn":
      return `₺${nf.format(value / 1e9)} trn`;
    case "bn":
      return `₺${nf.format(value / 1e6)} bn`;
    case "mult":
      return `${nf.format(value)}×`;
    default:
      return nf.format(value);
  }
}
