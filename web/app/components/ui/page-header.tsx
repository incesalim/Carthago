import * as React from "react";
import { cn } from "@/app/lib/cn";
import { Badge } from "./badge";
import { GlobalRangeSelector } from "@/app/components/range-context";

export interface PageHeaderProps {
  title: React.ReactNode;
  description?: React.ReactNode;
  /** Small coloured label above the title. */
  eyebrow?: React.ReactNode;
  /**
   * Period string of the most recent data point on the tab — rendered as a
   * "Data through …" badge on the right. Accepts 'YYYY-MM' or 'YYYY-MM-DD'.
   */
  dataThrough?: string;
  /** Show the global chart date-range selector (1Y/3Y/5Y/YTD/All) on the right.
   *  Set on pages that render time-series charts. */
  rangeSelector?: boolean;
  /** Right-aligned actions (filters, buttons). */
  children?: React.ReactNode;
  className?: string;
}

const MONTHS = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

/** 'YYYY-MM' → 'Mar 2026'; 'YYYY-MM-DD' → '23 Mar 2026'; else the raw string. */
function formatPeriod(p: string): string {
  const m = /^(\d{4})-(\d{2})(?:-(\d{2}))?$/.exec(p.trim());
  if (!m) return p;
  const mon = MONTHS[Number(m[2]) - 1];
  if (!mon) return p;
  return m[3] ? `${Number(m[3])} ${mon} ${m[1]}` : `${mon} ${m[1]}`;
}

export function PageHeader({
  title,
  description,
  eyebrow,
  dataThrough,
  rangeSelector,
  children,
  className,
}: PageHeaderProps) {
  return (
    <header
      className={cn(
        "flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between",
        className,
      )}
    >
      <div className="space-y-1">
        {eyebrow && (
          <div className="text-[11px] font-medium uppercase tracking-wider text-primary">
            {eyebrow}
          </div>
        )}
        <h1 className="text-2xl font-semibold tracking-tight text-foreground">
          {title}
        </h1>
        {description && (
          <p className="max-w-2xl text-sm text-muted-foreground">{description}</p>
        )}
      </div>
      {(dataThrough || rangeSelector || children) && (
        <div className="flex flex-wrap items-center gap-2">
          {dataThrough && (
            <Badge variant="secondary" title={`Latest data point: ${dataThrough}`}>
              <span
                className="size-1.5 rounded-full bg-positive"
                aria-hidden="true"
              />
              Data through {formatPeriod(dataThrough)}
            </Badge>
          )}
          {rangeSelector && <GlobalRangeSelector />}
          {children}
        </div>
      )}
    </header>
  );
}
