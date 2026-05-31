import * as React from "react";
import { cn } from "@/app/lib/cn";
import { Card } from "./card";

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
    <Card className={cn("p-4 transition-shadow hover:shadow-md", className)}>
      {(title || action) && (
        <div className="mb-3 flex items-start justify-between gap-3">
          <div className="space-y-0.5">
            {title && (
              <div className="text-sm font-medium text-foreground">{title}</div>
            )}
            {description && (
              <div className="text-xs text-muted-foreground">{description}</div>
            )}
          </div>
          {action}
        </div>
      )}
      <div className={bodyClassName}>{children}</div>
    </Card>
  );
}
