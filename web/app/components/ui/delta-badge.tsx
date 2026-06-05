import * as React from "react";
import { Badge } from "./badge";

type DeltaFormat = "pp" | "trn" | "raw";

export interface DeltaBadgeProps {
  curr: number | null | undefined;
  prev: number | null | undefined;
  /** How to render the magnitude. "pp" = percentage points. */
  format?: DeltaFormat;
  decimals?: number;
  /**
   * Which direction reads as "good" and so colours the chip green.
   * Use "down" for metrics where lower is better (NPL), "neutral" to stay grey.
   */
  goodDirection?: "up" | "down" | "neutral";
}

function magnitude(abs: number, format: DeltaFormat, decimals: number): string {
  if (format === "trn") return `₺${(abs / 1_000_000).toFixed(decimals)} trn`;
  if (format === "pp") return `${abs.toFixed(decimals)}pp`;
  return abs.toFixed(decimals);
}

/**
 * Period-over-period change chip — shows the delta between the latest two
 * points with a direction arrow, coloured by whether the move is "good".
 * Renders nothing when either value is missing.
 */
export function DeltaBadge({
  curr,
  prev,
  format = "pp",
  decimals = 2,
  goodDirection = "up",
}: DeltaBadgeProps) {
  if (curr == null || prev == null) return null;
  const d = curr - prev;
  // Treat sub-precision moves as flat so rounding noise doesn't show a colour.
  const flat = Math.abs(d) < 0.5 * 10 ** -decimals;
  const up = d > 0;
  const arrow = flat ? "→" : up ? "▲" : "▼";

  let variant: "secondary" | "positive" | "negative" = "secondary";
  if (!flat && goodDirection !== "neutral") {
    const isGood = up === (goodDirection === "up");
    variant = isGood ? "positive" : "negative";
  }

  return (
    <Badge variant={variant} title="Change vs previous period">
      <span aria-hidden="true">{arrow}</span>
      {magnitude(Math.abs(d), format, decimals)}
    </Badge>
  );
}
