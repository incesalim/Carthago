"use client";

/**
 * Small controlled number input — the "type it" half of an assumption control,
 * paired with RangeInput's slider. Local to /valuation (the only place the
 * dashboard takes free-form numeric input), so it stays out of the shared ui
 * barrel per the route-folder convention.
 */
import { cn } from "@/app/lib/cn";

export interface NumberFieldProps {
  value: number;
  min?: number;
  max?: number;
  step?: number;
  onChange: (v: number) => void;
  suffix?: string;
  ariaLabel?: string;
  className?: string;
}

export function NumberField({
  value,
  min,
  max,
  step,
  onChange,
  suffix,
  ariaLabel,
  className,
}: NumberFieldProps) {
  return (
    <span className="inline-flex items-center gap-1">
      <input
        type="number"
        value={Number.isFinite(value) ? value : ""}
        min={min}
        max={max}
        step={step}
        aria-label={ariaLabel}
        onChange={(e) => {
          const n = Number(e.target.value);
          if (!Number.isNaN(n)) onChange(n);
        }}
        className={cn(
          "w-16 rounded-md border border-border bg-background px-1.5 py-0.5 text-right text-xs tabular-nums",
          "outline-none focus-visible:ring-2 focus-visible:ring-ring",
          className,
        )}
      />
      {suffix && <span className="text-xs text-muted-foreground">{suffix}</span>}
    </span>
  );
}
