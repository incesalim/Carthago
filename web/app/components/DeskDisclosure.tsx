"use client";

import * as React from "react";

type DeskDisclosureProps = {
  kind: "secondary" | "depth";
  title: React.ReactNode;
  closedLabel: React.ReactNode;
  meta?: React.ReactNode;
  action?: React.ReactNode;
  children: React.ReactNode;
  initiallyOpen?: boolean;
};

/**
 * Mount disclosure contents only after the reader opens them. Besides reducing
 * the default page weight, this keeps responsive charts from measuring a
 * display:none parent and emitting zero-width warnings.
 */
export default function DeskDisclosure({
  kind,
  title,
  closedLabel,
  meta,
  action,
  children,
  initiallyOpen = false,
}: DeskDisclosureProps) {
  const [open, setOpen] = React.useState(initiallyOpen);
  const isDepth = kind === "depth";

  return (
    <section className={isDepth ? "mt-9 border-t-2 border-foreground" : "mt-8 border-t border-hair"}>
      <details
        open={open}
        onToggle={(event) => setOpen(event.currentTarget.open)}
        className="group"
      >
        <summary className="flex cursor-pointer list-none flex-wrap items-baseline gap-2.5 py-2 marker:content-none">
          <h2 className={isDepth ? "text-[14.5px] font-bold text-foreground" : "text-[13.5px] font-bold text-foreground"}>
            {title}
          </h2>
          {!open && (
            <span className="font-mono text-[8.5px] uppercase tracking-[0.07em] text-faint">
              {closedLabel}
            </span>
          )}
          {meta && (
            <span className="ml-auto font-mono text-[8.5px] uppercase tracking-[0.07em] text-faint">
              {meta}
            </span>
          )}
        </summary>
        {open && (
          <>
            {action && <div className="border-t border-hair pt-2">{action}</div>}
            <div className={isDepth ? "mt-4 space-y-8" : "space-y-8 border-t border-hair pt-4"}>
              {children}
            </div>
          </>
        )}
      </details>
    </section>
  );
}
