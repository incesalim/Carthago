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
  className,
  bodyClassName,
  children,
}: ChartCardProps) {
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
