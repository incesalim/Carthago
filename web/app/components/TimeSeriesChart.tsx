"use client";

/**
 * Multi-series line chart for irregular time-series (e.g. EVDS daily series
 * with non-bank-code identification). Simpler than TrendChart since we
 * don't need bank-type pivot.
 */
import { useState } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ChartCard } from "@/app/components/ui/chart-card";
import { ChartData } from "@/app/components/ui/chart-csv";
import { useChartTheme, tooltipStyles, seriesColor } from "@/app/lib/chart-theme";
import { wideToTable } from "@/app/lib/chart-csv";
import { nf, fmtQuarter } from "@/app/lib/chart-format";
import { useRangeFilter } from "@/app/lib/use-date-range";

interface Point {
  period_date: string;
  value: number;
}

interface Props {
  /** Map of seriesLabel → array of {period_date, value}. */
  series: Record<string, Point[]>;
  title?: string;
  yFormat?: "pct" | "rate" | "raw" | "fx";
  /** x-axis tick/tooltip label style. "date" → YYYY-MM (default), "quarter" → YYYY-Qn. */
  xFormat?: "date" | "quarter";
  decimals?: number;
  height?: number;
}

const formatters = {
  pct: (v: number, d: number) => `${nf(v, d)}%`,
  rate: (v: number, d: number) => nf(v, d),
  fx: (v: number, d: number) => `₺${nf(v, d)}`,
  raw: (v: number, d: number) => nf(v, d),
};

export default function TimeSeriesChart({
  series,
  title,
  yFormat = "raw",
  xFormat = "date",
  decimals = 2,
  height = 320,
}: Props) {
  const t = useChartTheme();
  const tt = tooltipStyles(t);
  const fmt = formatters[yFormat];

  // Window to the dashboard's global date range. Series are per-label arrays,
  // so we apply the shared predicate to each one during the pivot below.
  const { predicate } = useRangeFilter(
    Object.values(series).flat(),
    (p) => p.period_date,
  );
  // x-axis ticks are always YYYY-MM (or the quarter); the tooltip label is
  // resolved below once we can inspect the data's cadence.
  const isQuarter = xFormat === "quarter";
  const fmtTick = isQuarter ? fmtQuarter : (v: string) => v.slice(0, 7);
  const labels = Object.keys(series);
  // Hovering a legend item emphasises that line and fades the rest;
  // right-clicking pins the isolation until right-clicked again.
  const [hovered, setHovered] = useState<string | null>(null);
  const [pinned, setPinned] = useState<string | null>(null);
  const active = hovered ?? pinned;

  // Pivot all series into a wide structure { period_date, label1: v, label2: v }
  const byDate = new Map<string, Record<string, number | string>>();
  for (const label of labels) {
    for (const p of series[label]) {
      if (!predicate(p.period_date)) continue;
      if (!byDate.has(p.period_date)) {
        byDate.set(p.period_date, { period_date: p.period_date });
      }
      byDate.get(p.period_date)![label] = p.value;
    }
  }
  const data = Array.from(byDate.values()).sort((a, b) =>
    String(a.period_date).localeCompare(String(b.period_date)),
  );

  // Tooltip label: quarters in "quarter" mode; otherwise the full date for a
  // genuinely daily series (FX, share price), but collapsed to YYYY-MM when
  // every point sits on a month-start — the "-01" day is redundant noise on
  // monthly/quarterly series.
  const allMonthStart =
    data.length > 0 &&
    data.every((d) => String(d.period_date).slice(8, 10) === "01");
  const fmtLabel = isQuarter
    ? fmtQuarter
    : allMonthStart
      ? (v: string) => v.slice(0, 7)
      : (v: string) => v;

  return (
    <ChartCard title={title}>
      <ChartData
        table={wideToTable(
          data,
          { key: "period_date", label: "Date" },
          labels.map((l) => ({ key: l, label: l })),
        )}
      />
      {/* Right-click is a pin/unpin gesture here — keep the browser menu out. */}
      <div style={{ height }} onContextMenu={(e) => e.preventDefault()}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 10, right: 20, left: 60, bottom: 30 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={t.grid} />
            <XAxis
              dataKey="period_date"
              tick={{ fontSize: 11, fill: t.axis }}
              minTickGap={40}
              tickFormatter={(v) => fmtTick(String(v))}
              axisLine={{ stroke: t.grid }}
              tickLine={{ stroke: t.grid }}
            />
            <YAxis
              tick={{ fontSize: 11, fill: t.axis }}
              tickFormatter={(v) => fmt(v, 0)}
              axisLine={{ stroke: t.grid }}
              tickLine={{ stroke: t.grid }}
            />
            <Tooltip
              {...tt}
              formatter={(v, name) => [v == null ? "—" : fmt(Number(v), decimals), name]}
              labelFormatter={(l) => fmtLabel(String(l))}
              itemSorter={(item) =>
                typeof item.value === "number" ? -item.value : 0
              }
            />
            <Legend
              wrapperStyle={{ fontSize: 11 }}
              content={({ payload }) => (
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
                  {(payload ?? []).map((it) => {
                    const label = String(it.dataKey);
                    return (
                      <li
                        key={label}
                        onMouseEnter={() => setHovered(label)}
                        onMouseLeave={() => setHovered(null)}
                        onContextMenu={(e) => {
                          e.preventDefault();
                          setPinned((p) => (p === label ? null : label));
                        }}
                        style={{
                          display: "inline-flex",
                          alignItems: "center",
                          gap: 5,
                          color: t.axis,
                          opacity: active && active !== label ? 0.4 : 1,
                          fontWeight: pinned === label ? 600 : 400,
                          cursor: "default",
                        }}
                      >
                        <span
                          style={{
                            display: "inline-block",
                            width: 14,
                            borderTop: `2px solid ${it.color ?? "currentColor"}`,
                          }}
                        />
                        {it.value}
                      </li>
                    );
                  })}
                </ul>
              )}
            />
            {labels.map((label, i) => (
              <Line
                key={label}
                type="monotone"
                dataKey={label}
                name={label}
                stroke={seriesColor(t, label, i)}
                strokeWidth={active === label ? 2.75 : 1.75}
                strokeOpacity={active && active !== label ? 0.18 : 1}
                dot={false}
                connectNulls
                isAnimationActive={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </ChartCard>
  );
}
