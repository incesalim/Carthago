"use client";

/**
 * Client-side date-range zoom for chart components. Pages already ship the full
 * history to the browser, so a range button is a pure display filter — no server
 * refetch. Opt-in: pass an options object to enable, omit to leave the chart
 * untouched.
 *
 * Returns both shapes a chart might need:
 *   - `filtered`   — the row array windowed to the active range (TrendChart,
 *                    StackedArea — they filter one flat array before pivoting).
 *   - `predicate`  — a `(period) => boolean` test for callers that hold many
 *                    arrays (TimeSeriesChart filters each series in place).
 *   - `control`    — the <RangePills> element for ChartCard's `action` slot
 *                    (null when disabled or only one range applies).
 */
import { useState } from "react";
import { RangePills } from "@/app/components/ui/range-pills";
import {
  type RangeKey,
  DEFAULT_RANGES,
  applicableRanges,
  lowerBound,
} from "@/app/lib/chart-range";

export interface RangeOptions {
  /** Buttons to offer before span-based auto-hide. Default: 1Y/3Y/5Y/YTD/All. */
  ranges?: RangeKey[];
  /** Initial selection. Default: "All". */
  default?: RangeKey;
  /** Set false to disable entirely (pass-through, no control). */
  enabled?: boolean;
}

export interface UseDateRangeResult<T> {
  filtered: T[];
  control: React.ReactNode;
  predicate: (period: string) => boolean;
}

export function useDateRange<T>(
  rows: T[],
  accessor: (row: T) => string,
  opts?: RangeOptions,
): UseDateRangeResult<T> {
  const ranges = opts?.ranges ?? DEFAULT_RANGES;
  // Keep the hook call unconditional; the disabled branch is handled below.
  const [active, setActive] = useState<RangeKey>(opts?.default ?? "All");

  if (opts?.enabled === false) {
    return { filtered: rows, control: null, predicate: () => true };
  }

  // Min/max period across the data — ISO strings sort lexicographically.
  let min = "";
  let max = "";
  for (const r of rows) {
    const p = accessor(r);
    if (!p) continue;
    if (!min || p < min) min = p;
    if (p > max) max = p;
  }

  const applicable = applicableRanges(min, max, ranges);
  // The chosen default may not survive span-based auto-hide (e.g. a "3Y"
  // default on a 1-year series) — fall back to the always-present "All".
  const effective = applicable.includes(active) ? active : "All";
  const lb = lowerBound(max, effective);
  const predicate = (period: string) => lb === "" || period >= lb;

  const filtered = lb === "" ? rows : rows.filter((r) => predicate(accessor(r)));
  const control = (
    <RangePills ranges={applicable} active={effective} onSelect={setActive} />
  );
  return { filtered, control, predicate };
}
