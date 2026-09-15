"use client";

/**
 * Global chart date-range state. One selector (rendered once in the page header
 * via `GlobalRangeSelector`) drives every time-series chart on the page — the
 * charts read the active range from this context and window their data
 * client-side (the full history is already shipped, so it's a pure display
 * zoom, no refetch).
 *
 * The provider lives in the root layout, so the selection persists across
 * client-side navigation between tabs and resets to the default on a hard
 * reload. No localStorage — keeping the server and first client render identical
 * avoids a hydration mismatch.
 */
import { createContext, useContext, useState } from "react";
import { type RangeKey, DEFAULT_RANGES } from "@/app/lib/chart-range";
import { RangePills } from "@/app/components/ui/range-pills";
import { useText } from "@/i18n/use-text";

const DEFAULT_RANGE: RangeKey = "3Y";

interface RangeContextValue {
  range: RangeKey;
  setRange: (r: RangeKey) => void;
}

const RangeContext = createContext<RangeContextValue>({
  range: DEFAULT_RANGE,
  setRange: () => {},
});

export function RangeProvider({ children }: { children: React.ReactNode }) {
  const [range, setRange] = useState<RangeKey>(DEFAULT_RANGE);
  return (
    <RangeContext.Provider value={{ range, setRange }}>
      {children}
    </RangeContext.Provider>
  );
}

/** Active range + setter for the whole dashboard. */
export function useChartRange(): RangeContextValue {
  return useContext(RangeContext);
}

/** The single range selector — drop into the page header on chart pages. */
export function GlobalRangeSelector({ compact = false }: { compact?: boolean }) {
  const { range, setRange } = useChartRange();
  const tx = useText();
  if (compact) return <label className="flex items-center gap-2 text-[12px] text-muted-foreground">
    <span>{tx("Period")}</span>
    <select aria-label={tx("Chart period")} value={range} onChange={event => setRange(event.target.value as RangeKey)} className="rounded-md border border-border bg-card px-2 py-1.5 text-[13px] font-medium text-foreground focus-visible:outline-2 focus-visible:outline-primary">
      {DEFAULT_RANGES.map(value => <option key={value} value={value}>{tx(value)}</option>)}
    </select>
  </label>;
  return <RangePills ranges={DEFAULT_RANGES} active={range} onSelect={setRange} />;
}
