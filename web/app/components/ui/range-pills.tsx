"use client";

/**
 * Compact date-range selector (1Y / 3Y / 5Y / YTD / All) — the single global
 * chart range control, rendered once in the page header (see
 * `web/app/components/range-context.tsx`).
 *
 * Styled as one unified segmented control (a single bordered container with
 * inner segments) so it reads as a distinct filter widget rather than blending
 * in with neighbouring outline buttons (e.g. the section-nav links on the
 * Economy hub). Renders nothing when there's at most one range to offer.
 */
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
    <div
      data-chart-no-export=""
      role="group"
      aria-label="Chart date range"
      className={cn(
        "inline-flex items-center gap-0.5 rounded-[9px] border border-border bg-card p-[3px]",
        className,
      )}
    >
      {ranges.map((r) => (
        <button
          key={r}
          type="button"
          aria-pressed={active === r}
          onClick={() => onSelect(r)}
          className={cn(
            "rounded-md px-3 py-1 text-xs font-medium transition-colors",
            active === r
              ? "bg-primary/10 font-semibold text-primary"
              : "text-muted-foreground hover:bg-accent hover:text-foreground",
          )}
        >
          {r}
        </button>
      ))}
    </div>
  );
}
