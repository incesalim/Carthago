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
import { useText } from "@/i18n/use-text";
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
import { ChartData } from "@/app/components/ui/chart-csv";
import {
  useChartTheme,
  tooltipStyles,
  crosshairCursor,
  PLOT_MARGIN_LEFT,
  Y_AXIS_WIDTH,
} from "@/app/lib/chart-theme";
import { wideToTable } from "@/app/lib/chart-csv";
import { nf } from "@/app/lib/chart-format";
import { useRangeFilter } from "@/app/lib/use-date-range";

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
  /** Sector pages use the shared data palette and larger chart typography. */
  appearance?: "report" | "sector";
  /** Only time-series callers opt in; bucket/scenario categories stay intact. */
  respectRange?: boolean;
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
  appearance = "report",
  respectRange = false,
}: Props) {
  const tx = useText();
  const t = useChartTheme();
  const tt = tooltipStyles(t);
  const isLight = t.mode === "light";
  const variant = isLight ? "light" : "dark";
  const sector = appearance === "sector";
  const { filtered } = useRangeFilter(data, (row) => String(row.x ?? ""));
  const chartData = respectRange ? filtered : data;
  const numberLocale = sector && tx.locale === "tr" ? "tr-TR" : "en-US";

  const fillOf = (s: BarSeries, i: number) =>
    s.fill?.[variant] ?? (sector ? t.palette[i % t.palette.length] : FALLBACK_FILLS[i % FALLBACK_FILLS.length][variant]);
  const lineColor =
    line?.color?.[variant] ?? (sector ? t.hero : { light: "#171717", dark: "#ededed" }[variant]);

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
          <span style={{ color: sector ? t.inkMuted : t.axis }}>{tx(name)}</span>
          <span style={{ marginLeft: "auto", paddingLeft: 16, fontVariantNumeric: "tabular-nums" }}>
            {tx(nf(v, decimals, numberLocale))}
            {tx(unit)}
          </span>
        </div>
      );
    };
    return (
      <div style={{ ...tt.contentStyle, minWidth: 200, lineHeight: 1.7, ...(sector ? { fontSize: 14, padding: "12px 14px", fontFamily: "var(--font-sans)" } : {}) }}>
        <div style={tt.labelStyle}>{tx(String(label))}</div>
        {tx(bars.map((s, i) => item(s.key, s.label, fillOf(s, i))))}
        {tx(line && item(line.key, line.label, lineColor, true))}
      </div>
    );
  };

  const csvSeries = line ? [...bars, { key: line.key, label: line.label }] : bars;

  return (
    <>
      <ChartData
        table={wideToTable(
          chartData,
          { key: "x", label: "Period" },
          csvSeries.map((s) => ({ key: s.key, label: s.label })),
        )}
      />
      <div style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart
            data={chartData}
            stackOffset={grouped ? undefined : "sign"}
            margin={{
              top: 10,
              right: line?.rightAxis ? 12 : 20,
              left: PLOT_MARGIN_LEFT,
              bottom: sector ? 20 : 28,
            }}
            barCategoryGap={grouped ? "16%" : "18%"}
          >
            <CartesianGrid vertical={!sector} strokeDasharray={sector ? undefined : "3 3"} stroke={t.grid} />
            <XAxis
              dataKey="x"
              tick={{ fontSize: sector ? 14 : 10, fill: sector ? t.inkMuted : t.axis, ...(sector ? { fontFamily: "var(--font-sans)" } : {}) }}
              tickFormatter={sector ? (value) => tx(String(value)) : undefined}
              tickMargin={sector ? 10 : 6}
              minTickGap={sector ? 42 : 18}
              axisLine={sector ? false : { stroke: t.grid }}
              tickLine={sector ? false : { stroke: t.grid }}
            />
            <YAxis
              yAxisId="left"
              width={Y_AXIS_WIDTH}
              tick={{ fontSize: sector ? 14 : 11, fill: sector ? t.inkMuted : t.axis, ...(sector ? { fontFamily: "var(--font-sans)" } : {}) }}
              tickFormatter={(v) => nf(Number(v), 0, numberLocale)}
              axisLine={sector ? false : { stroke: t.grid }}
              tickLine={sector ? false : { stroke: t.grid }}
            />
            {line?.rightAxis && (
              <YAxis
                yAxisId="right"
                orientation="right"
                tick={{ fontSize: sector ? 14 : 11, fill: sector ? t.inkMuted : t.axis, ...(sector ? { fontFamily: "var(--font-sans)" } : {}) }}
                tickFormatter={(v) => nf(Number(v), 0, numberLocale)}
                axisLine={sector ? false : { stroke: t.grid }}
                tickLine={sector ? false : { stroke: t.grid }}
              />
            )}
            <ReferenceLine y={0} yAxisId="left" stroke={t.reference} />
            <Tooltip cursor={crosshairCursor(t)} content={renderTooltip} />
            <Legend
              wrapperStyle={{ fontSize: sector ? 14 : 11, paddingTop: sector ? 10 : 4, ...(sector ? { fontFamily: "var(--font-sans)" } : {}) }}
              content={() => (
                <ul
                  style={{
                    display: "flex",
                    flexWrap: "wrap",
                    justifyContent: "center",
                    gap: sector ? "6px 18px" : "2px 14px",
                    listStyle: "none",
                    margin: 0,
                    padding: 0,
                  }}
                >
                  {bars.map((s, i) => (
                    <li
                      key={s.key}
                      style={{ display: "inline-flex", alignItems: "center", gap: sector ? 7 : 5, color: sector ? t.inkMuted : t.axis }}
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
                      {tx(s.label)}
                    </li>
                  ))}
                  {line && (
                    <li style={{ display: "inline-flex", alignItems: "center", gap: sector ? 7 : 5, color: sector ? t.inkMuted : t.axis }}>
                      <span
                        style={{
                          display: "inline-block",
                          width: 14,
                          borderTop: `2px ${line.dotted ? "dotted" : "solid"} ${lineColor}`,
                        }}
                      />
                      {tx(line.label)}
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
                name={tx(s.label)}
                stackId={grouped ? undefined : "bop"}
                fill={fillOf(s, i)}
                isAnimationActive={false}
              />
            ))}
            {line && (
              <Line
                yAxisId={line.rightAxis ? "right" : "left"}
                dataKey={line.key}
                name={tx(line.label)}
                stroke={lineColor}
                strokeWidth={2}
                strokeDasharray={line.dotted ? "2 3" : undefined}
                dot={false}
                isAnimationActive={false}
                connectNulls={!sector}
              />
            )}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </>
  );
}
