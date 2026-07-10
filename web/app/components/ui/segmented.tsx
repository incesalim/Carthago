"use client";

/**
 * Segmented — the app's single segmented-control idiom (redesign phase D1).
 *
 * One bordered pill container with inner segments; the ACTIVE segment is
 * always `bg-primary/10 text-primary font-semibold` — the same treatment as
 * BankTypeFilter / BankSectionNav — so every toggle in the product reads the
 * same. Use this for new toggles instead of hand-rolling; bespoke toggles that
 * can't adopt the markup should still use these active classes.
 */
import * as React from "react";
import { cn } from "@/app/lib/cn";

export interface SegmentedOption<T extends string = string> {
  value: T;
  label: React.ReactNode;
}

export function Segmented<T extends string>({
  options,
  value,
  onChange,
  className,
  "aria-label": ariaLabel,
}: {
  options: SegmentedOption<T>[];
  value: T;
  onChange: (value: T) => void;
  className?: string;
  "aria-label"?: string;
}) {
  return (
    <div
      role="group"
      aria-label={ariaLabel}
      className={cn(
        "inline-flex items-center gap-0.5 rounded-[9px] border border-border bg-card p-[3px]",
        className,
      )}
    >
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          aria-pressed={value === o.value}
          onClick={() => onChange(o.value)}
          className={cn(
            "rounded-md px-3 py-1 text-xs font-medium transition-colors",
            value === o.value
              ? "bg-primary/10 font-semibold text-primary"
              : "text-muted-foreground hover:bg-accent hover:text-foreground",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
