"use client";

/**
 * A labelled assumption control: a slider you can drag plus an editable number
 * field (NumberField) showing the exact value. All values are in DISPLAY units
 * (e.g. percent, years, ×) — the AssumptionsPanel converts to/from the fractions
 * the valuation maths expect. Local to /valuation; styled with the design tokens.
 */
import { NumberField } from "./NumberField";

export interface RangeInputProps {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (v: number) => void;
  suffix?: string;
  decimals?: number;
  hint?: string;
}

const round = (v: number, d: number) => {
  const f = 10 ** d;
  return Math.round(v * f) / f;
};

export function RangeInput({
  label,
  value,
  min,
  max,
  step,
  onChange,
  suffix,
  decimals = 1,
  hint,
}: RangeInputProps) {
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between gap-2">
        <label className="text-xs font-medium text-foreground">{label}</label>
        <NumberField
          value={round(value, decimals)}
          min={min}
          max={max}
          step={step}
          onChange={onChange}
          suffix={suffix}
          ariaLabel={label}
        />
      </div>
      <input
        type="range"
        value={value}
        min={min}
        max={max}
        step={step}
        aria-label={label}
        onChange={(e) => onChange(Number(e.target.value))}
        className="h-1.5 w-full cursor-pointer accent-primary"
      />
      {hint && <p className="text-[10px] leading-tight text-muted-foreground">{hint}</p>}
    </div>
  );
}
