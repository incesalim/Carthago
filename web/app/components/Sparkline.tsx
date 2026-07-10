"use client";

/**
 * KPI-tile sparkline. Not purely decorative (redesign phase B3): a faint
 * dashed baseline at the window minimum plus min/max markers give it a range
 * reference, so it shows level AND turn — not just a squiggle.
 */
import {
  Area,
  AreaChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
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

  // Range references: min/max indices for the markers + the min baseline.
  let iMin = 0;
  let iMax = 0;
  for (let i = 1; i < data.length; i++) {
    if (data[i].value < data[iMin].value) iMin = i;
    if (data[i].value > data[iMax].value) iMax = i;
  }
  const lastIdx = data.length - 1;

  return (
    <div className="h-10 -mx-1">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 3, right: 2, left: 2, bottom: 3 }}>
          <defs>
            <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={stroke} stopOpacity={0.12} />
              <stop offset="100%" stopColor={stroke} stopOpacity={0} />
            </linearGradient>
          </defs>
          <XAxis dataKey="period" hide />
          {/* Hidden axis pins the domain to the data range (matches the
              implicit-axis look) and lets the baseline ReferenceLine resolve. */}
          <YAxis hide domain={["dataMin", "dataMax"]} />
          <ReferenceLine
            y={data[iMin].value}
            stroke={t.grid}
            strokeDasharray="2 3"
          />
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
            // Filled dot at the last point; faint markers at the window
            // min/max (end-dot styling wins when they coincide).
            dot={(props: { cx?: number; cy?: number; index?: number }) => {
              const { cx, cy, index } = props;
              if (cx == null || cy == null || index == null)
                return <circle key={`s-${index}`} r={0} />;
              if (index === lastIdx)
                return <circle key={`s-${index}`} cx={cx} cy={cy} r={2.5} fill={stroke} />;
              if (index === iMin || index === iMax)
                return <circle key={`s-${index}`} cx={cx} cy={cy} r={1.8} fill={t.axis} />;
              return <circle key={`s-${index}`} cx={cx} cy={cy} r={0} />;
            }}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
