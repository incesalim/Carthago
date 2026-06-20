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

/** "YYYY-MM" → "YYYY-MM-01" so Date.parse gets a full calendar date. */
function pad(period: string): string {
  return period.length === 7 ? `${period}-01` : period;
}

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
  if (range === "YTD") return `${year}-01`; // Jan of the latest data year
  return `${year - YEARS_BACK[range]}${maxPeriod.slice(4)}`;
}

/**
 * Of the offered ranges, those that actually make sense for the data's span.
 * A trailing window (1Y/3Y/5Y) is kept only when the data is meaningfully
 * longer than it — i.e. selecting it would genuinely hide some history rather
 * than just duplicate "All" (5% slack). This drops a dead "5Y" on a 2-year
 * series, and avoids two buttons that render the identical full-history view
 * (e.g. "5Y" vs "All" on exactly 5 years of data). "YTD"/"All" always stay.
 */
export function applicableRanges(
  minPeriod: string,
  maxPeriod: string,
  ranges: RangeKey[],
): RangeKey[] {
  if (!minPeriod || !maxPeriod) return ranges;
  const spanDays =
    (Date.parse(pad(maxPeriod)) - Date.parse(pad(minPeriod))) / 86_400_000;
  return ranges.filter((r) => {
    if (r === "All" || r === "YTD") return true;
    return spanDays > YEARS_BACK[r] * 365 * 1.05;
  });
}
