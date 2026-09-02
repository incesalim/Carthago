import { useText } from "@/i18n/use-text";
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
  const tx = useText();
  if (plain) {
    return (
      <div data-chart-card="" className={cn("group min-w-0 border-t border-hair pt-3", className)}>
        <div className="mb-3 flex min-h-11 flex-wrap items-start gap-3">
          <div className="min-w-0 flex-[1_1_14rem]">
            {title && (
              <div
                data-chart-title=""
                className="text-[14px] font-semibold leading-snug tracking-[-0.01em] text-foreground"
              >
                {tx(title)}
              </div>
            )}
            {description && (
              <div className="mt-1 max-w-[90ch] font-mono text-[9px] uppercase leading-relaxed tracking-[0.065em] text-faint">
                {tx(description)}
              </div>
            )}
          </div>
          <div className="flex max-w-full flex-[0_1_auto] flex-wrap items-start gap-2 sm:ml-auto sm:justify-end">
            {action}
            <ChartExport />
          </div>
        </div>
        <div data-chart-body="" className={bodyClassName ?? "max-w-[52rem]"}>{children}</div>
        {source && (
          <div className="mt-2 border-t border-hair pt-1.5 font-mono text-[9px] text-faint">
            {tx(source)}
          </div>
        )}
      </div>
    );
  }
  return (
    <Card
      data-chart-card=""
      className={cn("group p-4 transition-colors hover:border-primary/40", className)}
    >
      <div className="mb-3 flex flex-wrap items-start gap-3">
        <div className="min-w-0 flex-[1_1_14rem] space-y-0.5">
          {title && (
            <div
              data-chart-title=""
              className="font-serif text-[15px] font-semibold leading-tight text-foreground"
            >
              {tx(title)}
            </div>
          )}
          {description && (
            <div className="text-xs text-muted-foreground">{tx(description)}</div>
          )}
        </div>
        {/* Existing header action (toggle/filter…) sits beside the export pills. */}
        <div className="flex max-w-full flex-[0_1_auto] flex-wrap items-start gap-2 sm:ml-auto sm:justify-end">
          {action}
          <ChartExport />
        </div>
      </div>
      <div className={bodyClassName}>{children}</div>
      {source && (
        <div className="mt-3 border-t border-border pt-2.5 font-mono text-[9.5px] text-faint">
          {tx(source)}
        </div>
      )}
    </Card>
  );
}
