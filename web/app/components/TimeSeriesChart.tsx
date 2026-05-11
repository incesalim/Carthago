"use client";

/**
 * Multi-series line chart for irregular time-series (e.g. EVDS daily series
 * with non-bank-code identification). Simpler than TrendChart since we
 * don't need bank-type pivot.
 */
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

const COLORS = ["#7a0d2e", "#1f4068", "#0f7b6c", "#a16500", "#5b1a8c", "#5a5a5a"];

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
  const fmt = formatters[yFormat];
  const labels = Object.keys(series);

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
    <div className="rounded-lg border bg-white p-4 shadow-sm">
      {title && <div className="text-sm font-medium mb-2">{title}</div>}
      <div style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 10, right: 20, left: 60, bottom: 30 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
            <XAxis dataKey="period_date" tick={{ fontSize: 11 }} minTickGap={40}
                   tickFormatter={(v) => String(v).slice(0, 7)} />
            <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => fmt(v, 0)} />
            <Tooltip
              contentStyle={{ fontSize: 11, padding: "6px 10px", borderRadius: 4 }}
              formatter={(v) => [v == null ? "—" : fmt(Number(v), decimals), ""]}
              labelFormatter={(l) => String(l)}
            />
            <Legend wrapperStyle={{ fontSize: 11 }} iconType="line" />
            {labels.map((label, i) => (
              <Line
                key={label}
                type="monotone"
                dataKey={label}
                name={label}
                stroke={COLORS[i % COLORS.length]}
                strokeWidth={1.75}
                dot={false}
                connectNulls
                isAnimationActive={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
