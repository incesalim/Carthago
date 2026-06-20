"use client";

/**
 * Windows chart rows to the dashboard's global date range (see
 * `web/app/components/range-context.tsx`). Pages already ship the full history
 * to the browser, so this is a pure client-side display filter — no refetch.
 *
 * Returns both shapes a chart might need:
 *   - `filtered`  — the row array windowed to the active range (TrendChart,
 *                   StackedArea filter one flat array before pivoting).
 *   - `predicate` — a `(period) => boolean` test for callers holding many
 *                   arrays (TimeSeriesChart filters each series in place).
 * The selector itself is global, so there's no per-chart control to render.
 */
import { useChartRange } from "@/app/components/range-context";
import { lowerBound } from "@/app/lib/chart-range";

export interface RangeFilterResult<T> {
  filtered: T[];
  predicate: (period: string) => boolean;
}

export function useRangeFilter<T>(
  rows: T[],
  accessor: (row: T) => string,
): RangeFilterResult<T> {
  const { range } = useChartRange();

  // Latest period in the data — ISO strings sort lexicographically.
  let max = "";
  for (const r of rows) {
    const p = accessor(r);
    if (p > max) max = p;
  }

  const lb = lowerBound(max, range);
  const predicate = (period: string) => lb === "" || period >= lb;
  const filtered = lb === "" ? rows : rows.filter((r) => predicate(accessor(r)));
  return { filtered, predicate };
}
