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
 * the rules it sets): 2026-07-12-composition-chart.html, in the local design
 * archive (docs/design/ — kept on disk, not versioned). The rules it sets are
 * restated in web/DESIGN.md, which is versioned.
 */

import { useChartFormat } from "@/i18n/use-chart-format";
import { useText } from "@/i18n/use-text";
import { formatDateLabel } from "@/i18n/format";
import {
  Area,
  AreaChart,
  CartesianGrid,
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
import { type FormatKind } from "@/app/lib/chart-format";
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
  /** Retained for callers; all stacks now use stable series identities. */
  colorKeys?: boolean;
}

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
}: Props) {
  const tx = useText();
  const t = useChartTheme();
  const tt = tooltipStyles(t);
  const formatters = useChartFormat();
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

  // Resolve against the authored series before the selected range hides empty
  // components. The same entity keeps its line/bar/area colour at every range.
  const colorAt = (i: number) => seriesColor(t, shown[i].key,
    series.findIndex(s => s.key === shown[i].key), shown[i].label);

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
        <div style={tt.labelStyle}>{tx(String(label))}</div>
        {shown.map((s, i) => {
          const v = Number(row[s.key]) || 0;
          const display = percentStack
            ? fmt(total > 0 ? (v / total) * 100 : 0, decimals)
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
              <span style={{ color: t.axis }}>{tx(s.label)}</span>
              <span style={{ marginLeft: "auto", paddingLeft: 16, fontVariantNumeric: "tabular-nums" }}>
                {tx(display)}
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
            <span style={{ color: t.tooltipText }}>{tx("Total")}</span>
            <span style={{ marginLeft: "auto", paddingLeft: 16, fontVariantNumeric: "tabular-nums" }}>
              {tx(fmt(total, decimals))}
            </span>
          </div>
        )}
      </div>
    );
  };

  return (
    <ChartCard title={tx(title)} description={tx(description)} source={tx(source)} plain={plain}>
      <ChartData
        table={wideToTable(filtered, { key: "period", label: "Period" }, shown)}
      />
      <ul style={{ display: "flex", flexWrap: "wrap", gap: "8px 20px", listStyle: "none", margin: "0 0 16px", padding: 0, fontSize: 14 }}>
        {shown.map((s, i) => (
          <li key={s.key} style={{ display: "inline-flex", alignItems: "center", gap: 6, color: t.axis }}>
            <span aria-hidden style={{ width: 10, height: 10, flex: "none", background: colorAt(i) }} />
            {tx(s.label)}
          </li>
        ))}
      </ul>
      <div data-chart-plot="history" style={{ height: `var(--sector-chart-height, ${height}px)` }}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={filtered} stackOffset={percentStack ? "expand" : "none"}
                     margin={{ top: 10, right: 20, left: PLOT_MARGIN_LEFT, bottom: 4 }}>
            <CartesianGrid vertical={false} stroke={t.grid} />
            <XAxis
              dataKey="period"
              tickFormatter={(value) => formatDateLabel(String(value).slice(0, 7), tx.locale)}
              tick={{ fontSize: 14, fill: t.axis }}
              minTickGap={52}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              width={Y_AXIS_WIDTH}
              tick={{ fontSize: 14, fill: t.axis }}
              tickFormatter={(v) =>
                percentStack ? formatters.pct(v * 100, 0) : fmt(v, 0)
              }
              axisLine={false}
              tickLine={false}
            />
            <Tooltip cursor={crosshairCursor(t)} content={renderTooltip} />
            {shown.map((s, i) => (
              <Area
                key={s.key}
                type="monotone"
                dataKey={s.key}
                name={tx(s.label)}
                stackId="1"
                stroke={t.tooltipBg}
                strokeWidth={1.5}
                fill={colorAt(i)}
                fillOpacity={1}
                isAnimationActive={false}
              />
            ))}
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </ChartCard>
  );
}
