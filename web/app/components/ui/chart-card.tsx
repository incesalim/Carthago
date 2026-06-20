import * as React from "react";
import { cn } from "@/app/lib/cn";
import { Card } from "./card";
import ChartExport from "./chart-export";

export interface ChartCardProps {
  title?: React.ReactNode;
  description?: React.ReactNode;
  /** Right-aligned slot in the header (legend toggle, filter…). */
  action?: React.ReactNode;
  className?: string;
  bodyClassName?: string;
  children: React.ReactNode;
}

/** Card chrome shared by every chart: padded surface + header row. */
export function ChartCard({
  title,
  description,
  action,
  className,
  bodyClassName,
  children,
}: ChartCardProps) {
  return (
    <Card
      data-chart-card=""
      className={cn("group p-4 transition-shadow hover:shadow-md", className)}
    >
      <div className="mb-3 flex items-start justify-between gap-3">
        <div className="min-w-0 space-y-0.5">
          {title && (
            <div data-chart-title="" className="text-sm font-medium text-foreground">
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
    </Card>
  );
}
