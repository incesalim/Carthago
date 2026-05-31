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
import { ChartCard } from "@/app/components/ui/chart-card";
import { useChartTheme, tooltipStyles } from "@/app/lib/chart-theme";

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

export default function TrendChart({
  data,
  seriesLabels,
  title,
  yFormat = "raw",
  decimals = 2,
  zeroLine = false,
  height = 320,
}: Props) {
  const t = useChartTheme();
  const tt = tooltipStyles(t);

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
    <ChartCard title={title}>
      <div style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={wide} margin={{ top: 10, right: 20, left: 60, bottom: 30 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={t.grid} />
            <XAxis
              dataKey="period"
              tick={{ fontSize: 11, fill: t.axis }}
              tickMargin={6}
              minTickGap={30}
              axisLine={{ stroke: t.grid }}
              tickLine={{ stroke: t.grid }}
            />
            <YAxis
              tick={{ fontSize: 11, fill: t.axis }}
              tickFormatter={(v) => fmt(v, 0)}
              axisLine={{ stroke: t.grid }}
              tickLine={{ stroke: t.grid }}
            />
            {zeroLine && <ReferenceLine y={0} stroke={t.reference} strokeDasharray="3 3" />}
            <Tooltip
              {...tt}
              formatter={(v) => [v == null ? "—" : fmt(Number(v), decimals), ""]}
              labelFormatter={(l) => String(l)}
            />
            <Legend
              wrapperStyle={{ fontSize: 11, paddingTop: 4 }}
              iconType="line"
              layout="horizontal"
              align="center"
              verticalAlign="bottom"
            />
            {codes.map((code, i) => (
              <Line
                key={code}
                type="monotone"
                dataKey={code}
                name={seriesLabels[code]}
                stroke={t.palette[i % t.palette.length]}
                strokeWidth={1.75}
                dot={false}
                isAnimationActive={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </ChartCard>
  );
}
