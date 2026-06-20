/**
 * Pure helpers for the client-side date-range selector (1Y / 3Y / 5Y / YTD / All).
 *
 * Chart period strings are zero-padded ISO ("YYYY-MM" or "YYYY-MM-DD"), so a
 * date window is just a lexicographic `period >= lowerBound` compare that works
 * uniformly across monthly / weekly / daily / quarterly cadences. No React in
 * here — see use-date-range.tsx for the hook and range-pills.tsx for the UI.
 */

export type RangeKey = "1Y" | "3Y" | "5Y" | "YTD" | "All";

export const DEFAULT_RANGES: RangeKey[] = ["1Y", "3Y", "5Y", "YTD", "All"];

// Trailing-window length (years) for the year-shift ranges.
const YEARS_BACK: Record<"1Y" | "3Y" | "5Y", number> = { "1Y": 1, "3Y": 3, "5Y": 5 };

/**
 * Lower-bound period string for a range, given the latest period in the data.
 * Returns "" for "All" (no lower bound). The result is only ever compared with
 * `>=` against the data's ISO period strings, so it need not be a real calendar
 * date — a year-shifted prefix is enough for a correct lexicographic cut, and it
 * keeps the same width as the input ("YYYY-MM" → "YYYY-MM", daily → daily).
 */
export function lowerBound(maxPeriod: string, range: RangeKey): string {
  if (range === "All" || !maxPeriod) return "";
  const year = Number(maxPeriod.slice(0, 4));
  // Guard non-ISO / unparseable periods: no year → no bound (show everything)
  // rather than risk a lexicographic cut that empties the chart.
  if (!Number.isFinite(year)) return "";
  if (range === "YTD") return `${year}-01`; // Jan of the latest data year
  return `${year - YEARS_BACK[range]}${maxPeriod.slice(4)}`;
}
