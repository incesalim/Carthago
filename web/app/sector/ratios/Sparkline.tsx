"use client";

import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis } from "recharts";

interface Point {
  period: string;
  value: number;
}

type FormatKind = "pct" | "trn" | "raw";

interface Props {
  data: Point[];
  color?: string;
  /** Tooltip format hint (cannot pass functions across the server/client boundary). */
  format?: FormatKind;
  /** Decimal places for the formatted value. */
  decimals?: number;
}

const formatters: Record<FormatKind, (v: number, d: number) => string> = {
  pct: (v, d) => `${v.toFixed(d)}%`,
  trn: (v, d) => `₺${(v / 1_000_000).toFixed(d)} trn`,
  raw: (v, d) => v.toFixed(d),
};

export default function Sparkline({
  data,
  color = "#7a0d2e",
  format = "raw",
  decimals = 2,
}: Props) {
  if (!data.length) return <div className="h-10" />;
  const fmt = formatters[format];

  return (
    <div className="h-10 -mx-1">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 2, right: 2, left: 2, bottom: 2 }}>
          <defs>
            <linearGradient id={`grad-${color}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity={0.3} />
              <stop offset="100%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
          <XAxis dataKey="period" hide />
          <Tooltip
            contentStyle={{
              fontSize: 11,
              padding: "4px 8px",
              borderRadius: 4,
              border: "1px solid #e5e5e5",
            }}
            formatter={(v) => [fmt(Number(v), decimals), ""]}
            labelFormatter={(l) => String(l)}
            separator=""
          />
          <Area
            type="monotone"
            dataKey="value"
            stroke={color}
            strokeWidth={1.5}
            fill={`url(#grad-${color})`}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
