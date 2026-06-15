"use client";

/**
 * Balance-of-payments flow chart — signed stacked (or grouped) bars with an
 * optional overlay line on a secondary axis. Reproduces the Albaraka
 * "Ödemeler Dengesi" report style: monthly USD-bn financial-account flows
 * stacked above/below zero, sometimes with a 12-month cumulative line on the
 * right axis (Şekil 4/5) or a dotted reference line (Şekil 10).
 *
 * Bars stack with stackOffset="sign" so positive segments rise and negative
 * segments fall from the zero baseline, mirroring the source charts. Pass
 * `grouped` to render side-by-side bars instead (Şekil 10).
 */
import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useChartTheme, tooltipStyles } from "@/app/lib/chart-theme";
import { nf } from "@/app/lib/chart-format";

export interface BarSeries {
  key: string;
  label: string;
  /** Light/dark fill pair; falls back to the theme palette by index. */
  fill?: { light: string; dark: string };
}

export interface OverlayLine {
  key: string;
  label: string;
  color?: { light: string; dark: string };
  /** Plot against a separate right-hand axis (e.g. 12-month cumulative). */
  rightAxis?: boolean;
  dotted?: boolean;
}

interface Props {
  /** Wide rows: { x: "01/24", <barKey>: number, <lineKey>: number }. `null`
   *  marks a gap (a bar/line skips that point). */
  data: Array<Record<string, number | string | null>>;
  bars: BarSeries[];
  line?: OverlayLine;
  /** false → signed stacked bars (default); true → grouped side-by-side. */
  grouped?: boolean;
  /** Decimals in tooltip values. */
  decimals?: number;
  /** Suffix appended to tooltip values (e.g. " bn"). */
  unit?: string;
  height?: number;
}

// Warm/cool palette tuned to the source report (orange / maroon / grey / amber).
const FALLBACK_FILLS: Array<{ light: string; dark: string }> = [
  { light: "#e8833a", dark: "#f0a35e" }, // orange
  { light: "#9c1f2f", dark: "#d65a5a" }, // maroon
  { light: "#9ca3af", dark: "#9ca3af" }, // grey
  { light: "#f5c518", dark: "#fbd34d" }, // amber
  { light: "#1f4068", dark: "#6f9fe0" }, // navy
];

export default function BopFlowChart({
  data,
  bars,
  line,
  grouped = false,
  decimals = 1,
  unit = "",
  height = 320,
}: Props) {
  const t = useChartTheme();
  const tt = tooltipStyles(t);
  const isLight = t.palette[0] === "#7a0d2e";
  const variant = isLight ? "light" : "dark";

  const fillOf = (s: BarSeries, i: number) =>
    (s.fill ?? FALLBACK_FILLS[i % FALLBACK_FILLS.length])[variant];
  const lineColor =
    (line?.color ?? { light: "#171717", dark: "#ededed" })[variant];

  // Grouped tooltip: each bar segment + the overlay line, in stack order.
  const renderTooltip = ({
    active,
    payload,
    label,
  }: {
    active?: boolean;
    payload?: ReadonlyArray<{ payload?: Record<string, number | string> }>;
    label?: unknown;
  }) => {
    if (!active || !payload?.length) return null;
    const row = payload[0].payload ?? {};
    const item = (
      key: string,
      name: string,
      color: string,
      isLine = false,
    ) => {
      const v = row[key];
      if (typeof v !== "number") return null;
      return (
        <div key={key} style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span
            style={{
              display: "inline-block",
              width: isLine ? 14 : 9,
              height: isLine ? 0 : 9,
              borderRadius: isLine ? 0 : 2,
              borderTop: isLine ? `2px ${line?.dotted ? "dotted" : "solid"} ${color}` : undefined,
              background: isLine ? undefined : color,
              flex: "none",
            }}
          />
          <span style={{ color: t.axis }}>{name}</span>
          <span style={{ marginLeft: "auto", paddingLeft: 16, fontVariantNumeric: "tabular-nums" }}>
            {nf(v, decimals)}
            {unit}
          </span>
        </div>
      );
    };
    return (
      <div style={{ ...tt.contentStyle, minWidth: 200, lineHeight: 1.7 }}>
        <div style={tt.labelStyle}>{String(label)}</div>
        {bars.map((s, i) => item(s.key, s.label, fillOf(s, i)))}
        {line && item(line.key, line.label, lineColor, true)}
      </div>
    );
  };

  return (
    <div style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart
          data={data}
          stackOffset={grouped ? undefined : "sign"}
          margin={{ top: 10, right: line?.rightAxis ? 12 : 20, left: 6, bottom: 28 }}
          barCategoryGap={grouped ? "16%" : "18%"}
        >
          <CartesianGrid strokeDasharray="3 3" stroke={t.grid} />
          <XAxis
            dataKey="x"
            tick={{ fontSize: 10, fill: t.axis }}
            tickMargin={6}
            minTickGap={18}
            axisLine={{ stroke: t.grid }}
            tickLine={{ stroke: t.grid }}
          />
          <YAxis
            yAxisId="left"
            tick={{ fontSize: 11, fill: t.axis }}
            tickFormatter={(v) => nf(Number(v), 0)}
            axisLine={{ stroke: t.grid }}
            tickLine={{ stroke: t.grid }}
          />
          {line?.rightAxis && (
            <YAxis
              yAxisId="right"
              orientation="right"
              tick={{ fontSize: 11, fill: t.axis }}
              tickFormatter={(v) => nf(Number(v), 0)}
              axisLine={{ stroke: t.grid }}
              tickLine={{ stroke: t.grid }}
            />
          )}
          <ReferenceLine y={0} yAxisId="left" stroke={t.reference} />
          <Tooltip cursor={{ fill: t.cursor }} content={renderTooltip} />
          <Legend
            wrapperStyle={{ fontSize: 11, paddingTop: 4 }}
            content={() => (
              <ul
                style={{
                  display: "flex",
                  flexWrap: "wrap",
                  justifyContent: "center",
                  gap: "2px 14px",
                  listStyle: "none",
                  margin: 0,
                  padding: 0,
                }}
              >
                {bars.map((s, i) => (
                  <li
                    key={s.key}
                    style={{ display: "inline-flex", alignItems: "center", gap: 5, color: t.axis }}
                  >
                    <span
                      style={{
                        display: "inline-block",
                        width: 11,
                        height: 11,
                        borderRadius: 2,
                        background: fillOf(s, i),
                      }}
                    />
                    {s.label}
                  </li>
                ))}
                {line && (
                  <li style={{ display: "inline-flex", alignItems: "center", gap: 5, color: t.axis }}>
                    <span
                      style={{
                        display: "inline-block",
                        width: 14,
                        borderTop: `2px ${line.dotted ? "dotted" : "solid"} ${lineColor}`,
                      }}
                    />
                    {line.label}
                  </li>
                )}
              </ul>
            )}
          />
          {bars.map((s, i) => (
            <Bar
              key={s.key}
              yAxisId="left"
              dataKey={s.key}
              name={s.label}
              stackId={grouped ? undefined : "bop"}
              fill={fillOf(s, i)}
              isAnimationActive={false}
            />
          ))}
          {line && (
            <Line
              yAxisId={line.rightAxis ? "right" : "left"}
              dataKey={line.key}
              name={line.label}
              stroke={lineColor}
              strokeWidth={2}
              strokeDasharray={line.dotted ? "2 3" : undefined}
              dot={false}
              isAnimationActive={false}
              connectNulls
            />
          )}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
