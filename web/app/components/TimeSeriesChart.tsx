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
import { useChartTheme, tooltipStyles, seriesColor } from "@/app/lib/chart-theme";

interface Point {
  period_date: string;
  value: number;
}

interface Props {
  /** Map of seriesLabel → array of {period_date, value}. */
  series: Record<string, Point[]>;
  title?: string;
  yFormat?: "pct" | "rate" | "raw" | "fx";
  decimals?: number;
  height?: number;
}

// en-US locale: comma thousands separator + dot decimal (e.g. 1,234,567.89).
const nf = (v: number, d: number) =>
  new Intl.NumberFormat("en-US", {
    minimumFractionDigits: d,
    maximumFractionDigits: d,
  }).format(v);

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
  decimals = 2,
  height = 320,
}: Props) {
  const t = useChartTheme();
  const tt = tooltipStyles(t);
  const fmt = formatters[yFormat];
  const labels = Object.keys(series);
  // Hovering a legend item emphasises that line and fades the rest.
  const [active, setActive] = useState<string | null>(null);

  // Pivot all series into a wide structure { period_date, label1: v, label2: v }
  const byDate = new Map<string, Record<string, number | string>>();
  for (const label of labels) {
    for (const p of series[label]) {
      if (!byDate.has(p.period_date)) {
        byDate.set(p.period_date, { period_date: p.period_date });
      }
      byDate.get(p.period_date)![label] = p.value;
    }
  }
  const data = Array.from(byDate.values()).sort((a, b) =>
    String(a.period_date).localeCompare(String(b.period_date)),
  );

  return (
    <ChartCard title={title}>
      <div style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 10, right: 20, left: 60, bottom: 30 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={t.grid} />
            <XAxis
              dataKey="period_date"
              tick={{ fontSize: 11, fill: t.axis }}
              minTickGap={40}
              tickFormatter={(v) => String(v).slice(0, 7)}
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
              labelFormatter={(l) => String(l)}
              itemSorter={(item) =>
                typeof item.value === "number" ? -item.value : 0
              }
            />
            <Legend
              wrapperStyle={{ fontSize: 11 }}
              iconType="line"
              onMouseEnter={(o) => setActive(String(o.dataKey ?? ""))}
              onMouseLeave={() => setActive(null)}
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
