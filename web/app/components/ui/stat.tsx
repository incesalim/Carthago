import * as React from "react";
import { cn } from "@/app/lib/cn";
import { Card } from "./card";

const toneText = {
  neutral: "text-foreground",
  positive: "text-positive",
  warning: "text-warning",
  negative: "text-negative",
} as const;

export interface StatProps {
  label: string;
  value: React.ReactNode;
  /** Sub-line below the value (e.g. period · context). */
  hint?: React.ReactNode;
  tone?: keyof typeof toneText;
  /** Slot rendered to the right of the label — typically a <Badge>. */
  badge?: React.ReactNode;
  /** Visual rendered under the value (e.g. a sparkline). */
  children?: React.ReactNode;
  className?: string;
}

/** Compact KPI tile: label, large tabular value, optional hint + sparkline. */
export function Stat({
  label,
  value,
  hint,
  tone = "neutral",
  badge,
  children,
  className,
}: StatProps) {
  return (
    <Card className={cn("p-5 transition-colors hover:border-primary/40", className)}>
      <div className="flex items-center justify-between gap-2">
        <span className="font-mono text-[10px] font-medium uppercase tracking-[0.06em] text-muted-foreground">
          {label}
        </span>
        {badge}
      </div>
      <div
        className={cn(
          "mt-2 font-mono text-2xl font-medium tabular-nums tracking-tight",
          toneText[tone],
        )}
      >
        {value}
      </div>
      {hint != null && hint !== "" && (
        <div className="mt-0.5 text-xs text-muted-foreground">{hint}</div>
      )}
      {children && <div className="mt-3 -mx-1">{children}</div>}
    </Card>
  );
}
