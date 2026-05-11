"use client";

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

export interface StackPoint {
  period: string;
  [series: string]: string | number;
}

type FormatKind = "pct" | "trn" | "bn" | "raw";

interface Props {
  data: StackPoint[];
  series: { key: string; label: string }[];
  title?: string;
  yFormat?: FormatKind;
  decimals?: number;
  height?: number;
  /** Render as percent stack (each point sums to 100%). */
  percentStack?: boolean;
}

const COLORS = ["#7a0d2e", "#a16500", "#0f7b6c", "#1f4068", "#5b1a8c", "#5a5a5a"];

// en-US locale: comma thousands separator + dot decimal (e.g. 1,234,567.89).
const nf = (v: number, d: number) =>
  new Intl.NumberFormat("en-US", {
    minimumFractionDigits: d,
    maximumFractionDigits: d,
  }).format(v);

const formatters: Record<FormatKind, (v: number, d: number) => string> = {
  pct: (v, d) => `${nf(v, d)}%`,
  trn: (v, d) => `₺${nf(v / 1_000_000, d)} trn`,
  bn: (v, d) => `₺${nf(v / 1_000, d)} bn`,
  raw: (v, d) => nf(v, d),
};

export default function StackedArea({
  data,
  series,
  title,
  yFormat = "raw",
  decimals = 1,
  height = 320,
  percentStack = false,
}: Props) {
  const fmt = formatters[percentStack ? "pct" : yFormat];

  return (
    <div className="rounded-lg border bg-white p-4 shadow-sm">
      {title && <div className="text-sm font-medium mb-2">{title}</div>}
      <div style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} stackOffset={percentStack ? "expand" : "none"}
                     margin={{ top: 10, right: 20, left: 60, bottom: 30 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
            <XAxis dataKey="period" tick={{ fontSize: 11 }} minTickGap={30} />
            <YAxis
              tick={{ fontSize: 11 }}
              tickFormatter={(v) =>
                percentStack ? `${(v * 100).toFixed(0)}%` : fmt(v, 0)
              }
            />
            <Tooltip
              contentStyle={{ fontSize: 11, padding: "6px 10px", borderRadius: 4 }}
              formatter={(v) => [v == null ? "—" : fmt(Number(v), decimals), ""]}
              labelFormatter={(l) => String(l)}
            />
            <Legend wrapperStyle={{ fontSize: 11 }} iconType="square" />
            {series.map((s, i) => (
              <Area
                key={s.key}
                type="monotone"
                dataKey={s.key}
                name={s.label}
                stackId="1"
                stroke={COLORS[i % COLORS.length]}
                fill={COLORS[i % COLORS.length]}
                fillOpacity={0.55}
                isAnimationActive={false}
              />
            ))}
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
