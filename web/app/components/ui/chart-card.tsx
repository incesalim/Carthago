import * as React from "react";
import { cn } from "@/app/lib/cn";
import { Card } from "./card";
import ChartExport from "./chart-export";

export interface ChartCardProps {
  title?: React.ReactNode;
  description?: React.ReactNode;
  /** Right-aligned slot in the header (legend toggle, filter…). */
  action?: React.ReactNode;
  /** Editorial source line (e.g. "BDDK monthly bulletin") in a mono footer. */
  source?: React.ReactNode;
  /**
   * Drop the card surface: on a Desk page the chart sits directly on the sheet
   * (DESIGN.md ground rule 1 — no boxes inside the sheet), with a finding title,
   * a mono-caps sub-line and the footer as its only chrome.
   */
  plain?: boolean;
  className?: string;
  bodyClassName?: string;
  children: React.ReactNode;
}

/** Card chrome shared by every chart: padded surface + header row. */
export function ChartCard({
  title,
  description,
  action,
  source,
  plain = false,
  className,
  bodyClassName,
  children,
}: ChartCardProps) {
  if (plain) {
    return (
      <div data-chart-card="" className={cn("group min-w-0", className)}>
        <div className="mb-2 flex items-start justify-between gap-3">
          <div className="min-w-0">
            {title && (
              <div
                data-chart-title=""
                className="text-[12.5px] font-semibold leading-snug text-foreground"
              >
                {title}
              </div>
            )}
            {description && (
              <div className="mt-0.5 font-mono text-[8.5px] uppercase tracking-[0.07em] text-faint">
                {description}
              </div>
            )}
          </div>
          <div className="flex shrink-0 items-start gap-2">
            {action}
            <ChartExport />
          </div>
        </div>
        <div className={bodyClassName}>{children}</div>
        {source && <div className="mt-2 border-t border-hair pt-1.5">{source}</div>}
      </div>
    );
  }
  return (
    <Card
      data-chart-card=""
      className={cn("group p-4 transition-colors hover:border-primary/40", className)}
    >
      <div className="mb-3 flex items-start justify-between gap-3">
        <div className="min-w-0 space-y-0.5">
          {title && (
            <div
              data-chart-title=""
              className="font-serif text-[15px] font-semibold leading-tight text-foreground"
            >
              {title}
            </div>
          )}
          {description && (
            <div className="text-xs text-muted-foreground">{description}</div>
          )}
        </div>
        {/* Existing header action (toggle/filter…) sits beside the export pills. */}
        <div className="flex shrink-0 items-start gap-2">
          {action}
          <ChartExport />
        </div>
      </div>
      <div className={bodyClassName}>{children}</div>
      {source && (
        <div className="mt-3 border-t border-border pt-2.5 font-mono text-[9.5px] text-faint">
          {source}
        </div>
      )}
    </Card>
  );
}
