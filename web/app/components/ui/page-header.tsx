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
  /**
   * Pin the header to the top on lg+ while scrolling (default true). Pass false
   * on pages that nest the header inside their own sticky group, so it doesn't
   * become a second element fighting for top-0 (e.g. /banks/[ticker], which
   * stacks the header above a sticky section-nav). The frosted band is kept
   * either way, so the header still works as part of a pinned group.
   */
  sticky?: boolean;
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
  sticky = true,
  children,
  className,
}: PageHeaderProps) {
  return (
    <header
      className={cn(
        "flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between",
        // Frosted full-bleed band on lg+, so when the header is pinned (here or
        // as part of a parent sticky group) scrolling content doesn't bleed
        // through it.
        "lg:-mx-8 lg:bg-background/90 lg:px-8 lg:py-3 lg:backdrop-blur",
        // Pin the header (with the global range selector) to the top while
        // scrolling, so the date-range control stays reachable on long chart
        // pages. Below lg the mobile nav bar owns the sticky top-0 slot, so this
        // is lg-only. Pages with their own sticky sub-nav pass sticky={false}
        // and pin the header via a shared wrapper instead (avoids two elements
        // colliding at top-0 — see /banks/[ticker]).
        sticky && "lg:sticky lg:top-0 lg:z-20",
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
