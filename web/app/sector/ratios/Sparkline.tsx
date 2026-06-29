"use client";

import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis } from "recharts";
import { useChartTheme, tooltipStyles } from "@/app/lib/chart-theme";
import { formatters } from "@/app/lib/chart-format";

interface Point {
  period: string;
  value: number;
}

// Sparkline only offers a subset of the shared format kinds.
type FormatKind = "pct" | "trn" | "raw";

interface Props {
  data: Point[];
  /** Override the stroke colour; defaults to the brand chart colour. */
  color?: string;
  /** Tooltip format hint (cannot pass functions across the server/client boundary). */
  format?: FormatKind;
  /** Decimal places for the formatted value. */
  decimals?: number;
}

export default function Sparkline({
  data,
  color,
  format = "raw",
  decimals = 2,
}: Props) {
  const t = useChartTheme();
  const tt = tooltipStyles(t);
  const stroke = color ?? t.palette[0];
  const gradId = `spark-${stroke.replace(/[^a-z0-9]/gi, "")}`;

  if (!data.length) return <div className="h-10" />;
  const fmt = formatters[format];

  return (
    <div className="h-10 -mx-1">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 2, right: 2, left: 2, bottom: 2 }}>
          <defs>
            <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={stroke} stopOpacity={0.12} />
              <stop offset="100%" stopColor={stroke} stopOpacity={0} />
            </linearGradient>
          </defs>
          <XAxis dataKey="period" hide />
          <Tooltip
            contentStyle={tt.contentStyle}
            labelStyle={tt.labelStyle}
            itemStyle={tt.itemStyle}
            formatter={(v) => [fmt(Number(v), decimals), ""]}
            labelFormatter={(l) => String(l)}
            separator=""
          />
          <Area
            type="monotone"
            dataKey="value"
            stroke={stroke}
            strokeWidth={2}
            strokeLinecap="round"
            strokeLinejoin="round"
            fill={`url(#${gradId})`}
            // Small filled dot at the last point only (r=0 elsewhere).
            dot={(props: { cx?: number; cy?: number; index?: number }) => {
              const { cx, cy, index } = props;
              const show = index === data.length - 1 && cx != null && cy != null;
              return (
                <circle
                  key={`s-${index}`}
                  cx={cx}
                  cy={cy}
                  r={show ? 2.5 : 0}
                  fill={stroke}
                />
              );
            }}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
