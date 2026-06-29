import * as React from "react";
import { cn } from "@/app/lib/cn";

export interface SectionProps {
  title?: React.ReactNode;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  /** Editorial section index (e.g. "01") rendered in mono before the title. */
  index?: string;
  children: React.ReactNode;
  className?: string;
  contentClassName?: string;
}

/**
 * A labelled content block with an optional heading row. Content is stacked
 * with `space-y-4` by default (the common dashboard-page layout); pass
 * `contentClassName=""` for blocks whose children carry their own margins.
 */
export function Section({
  title,
  description,
  actions,
  index,
  children,
  className,
  contentClassName = "space-y-4",
}: SectionProps) {
  return (
    <section className={cn("space-y-4", className)}>
      {(title || actions) && (
        <div className="flex items-end justify-between gap-3">
          <div className="space-y-0.5">
            <div className="flex items-baseline gap-2.5">
              {index && (
                <span className="font-mono text-[10px] font-medium uppercase tracking-[0.14em] text-faint">
                  {index}
                </span>
              )}
              {title && (
                <h2 className="font-serif text-xl font-semibold tracking-tight text-foreground">
                  {title}
                </h2>
              )}
            </div>
            {description && (
              <p className="text-xs text-muted-foreground">{description}</p>
            )}
          </div>
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </div>
      )}
      <div className={contentClassName}>{children}</div>
    </section>
  );
}
