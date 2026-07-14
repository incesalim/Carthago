"use client";

/**
 * Stacked composition chart.
 *
 * BEFORE reaching for this: read "Choosing the mark" in ../../DESIGN.md. A stack
 * answers ONE question — "who holds the book" — and answers it badly in nominal
 * ₺: the shape is mostly the deflator (deposits: nominal ×2.86 since May 2023,
 * real ×0.91), only the bottom band has a flat baseline, and a weekly Δ named in
 * the title is smaller than the axis can draw. If the question is a trend, a
 * change, or a real-terms level, the mark is a share stack, a Δ strip, small
 * multiples or a nominal-vs-real index — not this.
 *
 * The redesign this component is measured against (real rows, the arithmetic,
 * the rules it sets): docs/design/mockups/2026-07-12-composition-chart.html.
 */

import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ChartCard } from "@/app/components/ui/chart-card";
import { ChartData } from "@/app/components/ui/chart-csv";
import {
  useChartTheme,
  tooltipStyles,
  seriesColor,
  crosshairCursor,
  PLOT_MARGIN_LEFT,
  Y_AXIS_WIDTH,
} from "@/app/lib/chart-theme";
import { wideToTable } from "@/app/lib/chart-csv";
import { nf, formatters, type FormatKind } from "@/app/lib/chart-format";
import { useRangeFilter } from "@/app/lib/use-date-range";

export interface StackPoint {
  // Wide row: the x-axis field (recharts reads it via dataKey="period") plus one
  // value per series. `null` marks a gap and is handled at render time.
  [series: string]: string | number | null;
}

interface Props {
  data: StackPoint[];
  series: { key: string; label: string }[];
  /** Card headline — a finding sentence on lead charts (chart-findings.ts). */
  title?: string;
  /** Card subtitle — the metric, units, period (when title is a finding). */
  description?: React.ReactNode;
  /** Mono source footer, e.g. "Source: BDDK weekly bulletin". */
  source?: React.ReactNode;
  /** Render on the sheet without card chrome (Desk evidence layer). */
  plain?: boolean;
  yFormat?: FormatKind;
  decimals?: number;
  height?: number;
  /** Render as percent stack (each point sums to 100%). */
  percentStack?: boolean;
  /** Colour each series by its key via `seriesColor` (matches TrendChart /
   *  BopFlowChart) instead of the warm/cool layering order. Use when the same
   *  series also appears as a line on the page so colours stay consistent. */
  colorKeys?: boolean;
}

// Stacked areas read best when the brand red leads but warm/cool alternate.
const ORDER = [0, 3, 2, 1, 4, 5];


export default function StackedArea({
  data,
  series,
  title,
  description,
  source,
  plain = false,
  yFormat = "raw",
  decimals = 1,
  height = 320,
  percentStack = false,
  colorKeys = false,
}: Props) {
  const t = useChartTheme();
  const tt = tooltipStyles(t);
  const fmt = formatters[percentStack ? "pct" : yFormat];

  // Window to the dashboard's global date range. Everything below (near-zero
  // hide, percent-stack totals, the rendered chart and the CSV payload) is
  // computed over `filtered`, so the window re-derives consistently — a series
  // near-zero only in old years correctly reappears when zoomed in.
  const { filtered } = useRangeFilter(data, (r) => String(r.period));

  // Drop series that are effectively zero everywhere (e.g. Dev&Inv deposits) so
  // they don't clutter the legend with an invisible sliver. Relative threshold
  // keeps it scale-/format-independent; fall back to all series if every one
  // would be filtered (all-zero data).
  const maxAbs = filtered.reduce(
    (m, d) => series.reduce((mm, s) => Math.max(mm, Math.abs(Number(d[s.key]) || 0)), m),
    0,
  );
  const visible = series.filter((s) =>
    filtered.some((d) => Math.abs(Number(d[s.key]) || 0) > maxAbs * 1e-6),
  );
  const shown = visible.length > 0 ? visible : series;

  const colorAt = (i: number) =>
    colorKeys
      ? seriesColor(t, shown[i].key, i)
      : t.palette[ORDER[i % ORDER.length] % t.palette.length];

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
    const row = payload[0]?.payload ?? {};
    const total = shown.reduce((sum, s) => sum + (Number(row[s.key]) || 0), 0);
    return (
      <div style={{ ...tt.contentStyle, minWidth: 180, lineHeight: 1.7 }}>
        <div style={tt.labelStyle}>{String(label)}</div>
        {shown.map((s, i) => {
          const v = Number(row[s.key]) || 0;
          const display = percentStack
            ? `${nf(total > 0 ? (v / total) * 100 : 0, decimals)}%`
            : fmt(v, decimals);
          return (
            <div key={s.key} style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span
                style={{
                  display: "inline-block",
                  width: 9,
                  height: 9,
                  borderRadius: 2,
                  background: colorAt(i),
                  flex: "none",
                }}
              />
              <span style={{ color: t.axis }}>{s.label}</span>
              <span style={{ marginLeft: "auto", paddingLeft: 16, fontVariantNumeric: "tabular-nums" }}>
                {display}
              </span>
            </div>
          );
        })}
        {!percentStack && (
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 6,
              marginTop: 3,
              paddingTop: 3,
              borderTop: `1px solid ${t.tooltipBorder}`,
              fontWeight: 600,
            }}
          >
            <span style={{ width: 9, flex: "none" }} />
            <span style={{ color: t.tooltipText }}>Total</span>
            <span style={{ marginLeft: "auto", paddingLeft: 16, fontVariantNumeric: "tabular-nums" }}>
              {fmt(total, decimals)}
            </span>
          </div>
        )}
      </div>
    );
  };

  return (
    <ChartCard title={title} description={description} source={source} plain={plain}>
      <ChartData
        table={wideToTable(filtered, { key: "period", label: "Period" }, shown)}
      />
      <div style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={filtered} stackOffset={percentStack ? "expand" : "none"}
                     margin={{ top: 10, right: 20, left: PLOT_MARGIN_LEFT, bottom: 30 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={t.grid} />
            <XAxis
              dataKey="period"
              tick={{ fontSize: 11, fill: t.axis }}
              minTickGap={30}
              axisLine={{ stroke: t.grid }}
              tickLine={{ stroke: t.grid }}
            />
            <YAxis
              width={Y_AXIS_WIDTH}
              tick={{ fontSize: 11, fill: t.axis }}
              tickFormatter={(v) =>
                percentStack ? `${(v * 100).toFixed(0)}%` : fmt(v, 0)
              }
              axisLine={{ stroke: t.grid }}
              tickLine={{ stroke: t.grid }}
            />
            <Tooltip cursor={crosshairCursor(t)} content={renderTooltip} />
            <Legend
              wrapperStyle={{ fontSize: 11 }}
              content={() => (
                // Render straight from `shown` so the legend order matches the
                // stack (bottom→top); Recharts otherwise reorders it.
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
                  {shown.map((s, i) => (
                    <li
                      key={s.key}
                      style={{
                        display: "inline-flex",
                        alignItems: "center",
                        gap: 5,
                        color: t.axis,
                      }}
                    >
                      <span
                        style={{
                          display: "inline-block",
                          width: 11,
                          height: 11,
                          borderRadius: 2,
                          background: colorAt(i),
                        }}
                      />
                      {s.label}
                    </li>
                  ))}
                </ul>
              )}
            />
            {shown.map((s, i) => (
              <Area
                key={s.key}
                type="monotone"
                dataKey={s.key}
                name={s.label}
                stackId="1"
                stroke={colorAt(i)}
                fill={colorAt(i)}
                fillOpacity={0.55}
                isAnimationActive={false}
              />
            ))}
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </ChartCard>
  );
}
