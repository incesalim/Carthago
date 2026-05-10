"use client";

/**
 * Multi-series time-series line/area chart.
 * Designed for showing one metric over time, optionally split by bank type.
 */
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export interface TrendPoint {
  period: string;
  bank_type_code: string;
  value: number | null;
}

type FormatKind = "pct" | "trn" | "bn" | "raw";

interface Props {
  /** Long-form rows {period, bank_type_code, value}. */
  data: TrendPoint[];
  /** Map of bank_type_code → label shown in legend. */
  seriesLabels: Record<string, string>;
  title?: string;
  yFormat?: FormatKind;
  decimals?: number;
  /** Show a horizontal line at y=0 (useful for growth rates). */
  zeroLine?: boolean;
  height?: number;
}

const COLORS = ["#7a0d2e", "#1f4068", "#0f7b6c", "#a16500", "#5b1a8c", "#5a5a5a"];

const formatters: Record<FormatKind, (v: number, d: number) => string> = {
  pct: (v, d) => `${v.toFixed(d)}%`,
  trn: (v, d) => `₺${(v / 1_000_000).toFixed(d)} trn`,
  bn: (v, d) => `₺${(v / 1_000).toFixed(d)} bn`,
  raw: (v, d) => v.toFixed(d),
};

export default function TrendChart({
  data,
  seriesLabels,
  title,
  yFormat = "raw",
  decimals = 2,
  zeroLine = false,
  height = 320,
}: Props) {
  // Pivot long → wide: { period, "10001": v, "10003": v, ... }
  const codes = Object.keys(seriesLabels);
  type Wide = { period: string; [code: string]: string | number | null };
  const byPeriod = new Map<string, Wide>();
  for (const r of data) {
    if (!byPeriod.has(r.period)) byPeriod.set(r.period, { period: r.period });
    byPeriod.get(r.period)![r.bank_type_code] = r.value;
  }
  const wide = Array.from(byPeriod.values()).sort((a, b) =>
    a.period.localeCompare(b.period),
  );

  const fmt = formatters[yFormat];

  return (
    <div className="rounded-lg border bg-white p-4 shadow-sm">
      {title && <div className="text-sm font-medium mb-2">{title}</div>}
      <div style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={wide} margin={{ top: 10, right: 20, left: 60, bottom: 30 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
            <XAxis
              dataKey="period"
              tick={{ fontSize: 11 }}
              tickMargin={6}
              minTickGap={30}
            />
            <YAxis
              tick={{ fontSize: 11 }}
              tickFormatter={(v) => fmt(v, 0)}
            />
            {zeroLine && <ReferenceLine y={0} stroke="#999" strokeDasharray="3 3" />}
            <Tooltip
              contentStyle={{ fontSize: 11, padding: "6px 10px", borderRadius: 4 }}
              formatter={(v) => [v == null ? "—" : fmt(Number(v), decimals), ""]}
              labelFormatter={(l) => String(l)}
            />
            <Legend wrapperStyle={{ fontSize: 11 }} iconType="line" />
            {codes.map((code, i) => (
              <Line
                key={code}
                type="monotone"
                dataKey={code}
                name={seriesLabels[code]}
                stroke={COLORS[i % COLORS.length]}
                strokeWidth={1.75}
                dot={false}
                isAnimationActive={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
