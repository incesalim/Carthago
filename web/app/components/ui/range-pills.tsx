"use client";

/**
 * Compact date-range selector (1Y / 3Y / 5Y / YTD / All) for a chart card
 * header. Drop into ChartCard's `action` slot via the useDateRange hook.
 *
 * Marked `data-chart-no-export` so the PNG/Copy capture (chart-export.tsx)
 * leaves the pills out of the exported image. Renders nothing when there's
 * at most one applicable range (no choice to offer).
 */
import { Button } from "./button";
import { cn } from "@/app/lib/cn";
import type { RangeKey } from "@/app/lib/chart-range";

export function RangePills({
  ranges,
  active,
  onSelect,
  className,
}: {
  ranges: RangeKey[];
  active: RangeKey;
  onSelect: (r: RangeKey) => void;
  className?: string;
}) {
  if (ranges.length <= 1) return null;
  return (
    <div data-chart-no-export="" className={cn("flex items-center gap-0.5", className)}>
      {ranges.map((r) => (
        <Button
          key={r}
          type="button"
          size="sm"
          variant={active === r ? "default" : "outline"}
          className="h-6 px-2 text-[11px] font-medium"
          aria-pressed={active === r}
          onClick={() => onSelect(r)}
        >
          {r}
        </Button>
      ))}
    </div>
  );
}
