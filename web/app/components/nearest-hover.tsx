"use client";

/**
 * Nearest-series hover helpers for multi-line charts.
 *
 * Recharts line/area charts only support axis-wide tooltips — they hard-code
 * `allowedTooltipTypes = ['axis']`, so `<Tooltip shared={false}>` is silently
 * ignored and the default box lists *every* series at the hovered date. These
 * two helpers show just the one series under the cursor instead: for a
 * horizontal layout `coordinate.y` is the mouse y, so the nearest series is the
 * one whose pixel y (`yScale(value)`) is closest to it.
 *
 * Both are rendered by Recharts as components (`<Tooltip content>` via
 * `createElement`, `<NearestActiveDot>` as a chart child), so the chart-context
 * hooks (`useYAxisScale`, …) are valid inside them.
 */
import {
  useActiveTooltipCoordinate,
  useActiveTooltipLabel,
  useIsTooltipActive,
  useYAxisScale,
} from "recharts";
import type { Coordinate, TooltipPayloadEntry } from "recharts";
import { useChartTheme, tooltipStyles } from "@/app/lib/chart-theme";

/** Custom `<Tooltip content>` that renders only the nearest series' value. */
export function NearestSeriesTooltip({
  active,
  payload,
  label,
  coordinate,
  formatValue,
  formatLabel,
}: {
  active?: boolean;
  payload?: ReadonlyArray<TooltipPayloadEntry>;
  label?: string | number;
  coordinate?: Coordinate;
  formatValue: (value: number) => string;
  formatLabel?: (label: string | number) => string;
}) {
  const t = useChartTheme();
  const tt = tooltipStyles(t);
  const yScale = useYAxisScale();
  if (!active || !payload?.length || !coordinate || !yScale) return null;
  let best: TooltipPayloadEntry | null = null;
  let bestDist = Infinity;
  for (const p of payload) {
    if (typeof p.value !== "number") continue;
    const py = yScale(p.value);
    if (py == null) continue;
    const d = Math.abs(py - coordinate.y);
    if (d < bestDist) {
      bestDist = d;
      best = p;
    }
  }
  if (!best) return null;
  const heading =
    label == null ? "" : formatLabel ? formatLabel(label) : String(label);
  return (
    <div style={tt.contentStyle}>
      <div style={tt.labelStyle}>{heading}</div>
      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
        <span
          style={{
            display: "inline-block",
            width: 9,
            height: 9,
            borderRadius: 9999,
            background: best.color,
          }}
        />
        <span>{best.name}</span>
        <span style={{ marginLeft: 12, fontWeight: 600 }}>
          {typeof best.value === "number" ? formatValue(best.value) : "—"}
        </span>
      </div>
    </div>
  );
}

/**
 * A single cased dot on the nearest line at the active date. Render as a chart
 * child (after the lines, so it sits on top). Mirrors the tooltip's pick.
 */
export function NearestActiveDot({
  rows,
  periodKey,
  keys,
  colorFor,
}: {
  rows: ReadonlyArray<Record<string, string | number | null>>;
  periodKey: string;
  keys: string[];
  colorFor: (key: string) => string;
}) {
  const t = useChartTheme();
  const active = useIsTooltipActive();
  const coord = useActiveTooltipCoordinate();
  const label = useActiveTooltipLabel();
  const yScale = useYAxisScale();
  if (!active || !coord || !yScale || label == null) return null;
  const row = rows.find((r) => String(r[periodKey]) === String(label));
  if (!row) return null;
  let bestKey: string | null = null;
  let bestY = 0;
  let bestDist = Infinity;
  for (const k of keys) {
    const v = row[k];
    if (typeof v !== "number") continue;
    const py = yScale(v);
    if (py == null) continue;
    const d = Math.abs(py - coord.y);
    if (d < bestDist) {
      bestDist = d;
      bestY = py;
      bestKey = k;
    }
  }
  if (bestKey == null) return null;
  return (
    <circle
      cx={coord.x}
      cy={bestY}
      r={4}
      fill={colorFor(bestKey)}
      stroke={t.tooltipBg}
      strokeWidth={1.5}
    />
  );
}
