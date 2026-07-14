"use client";

/**
 * What the free deposits are worth, against the profit they produce.
 *
 * Two bars a month: the demand book priced at the rate the sector pays its
 * interest-bearing depositors, and the sector's annualized net profit. The gap
 * IS the finding — the free funding is worth roughly three times the profit of
 * the whole banking system — so it is drawn as two bars on one scale rather than
 * a ratio line, which would hide both magnitudes.
 */
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
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
  crosshairCursor,
  PLOT_MARGIN_LEFT,
  Y_AXIS_WIDTH,
} from "@/app/lib/chart-theme";
import { wideToTable } from "@/app/lib/chart-csv";
import { useRangeFilter } from "@/app/lib/use-date-range";

export interface EngineBarPoint {
  period: string;
  worth: number;
  profit: number;
  [k: string]: string | number;
}

export default function EngineBars({
  data,
  title,
  description,
  source,
  height = 280,
}: {
  data: EngineBarPoint[];
  title?: React.ReactNode;
  description?: React.ReactNode;
  source?: React.ReactNode;
  height?: number;
}) {
  const t = useChartTheme();
  const tt = tooltipStyles(t);
  const { filtered } = useRangeFilter(data, (r) => r.period);
  const fmt = (v: number) => `₺${v.toFixed(2)} trn`;

  return (
    <ChartCard plain title={title} description={description} source={source}>
      <ChartData
        table={wideToTable(filtered, { key: "period", label: "Month" }, [
          { key: "worth", label: "Free deposits, priced" },
          { key: "profit", label: "Net profit" },
        ])}
      />
      <div style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={filtered}
            margin={{ top: 10, right: 12, left: PLOT_MARGIN_LEFT, bottom: 4 }}
          >
            <CartesianGrid vertical={false} stroke={t.grid} />
            <XAxis
              dataKey="period"
              tick={{ fontSize: 11, fill: t.axis, fontFamily: "var(--font-geist-mono), monospace" }}
              minTickGap={28}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              width={Y_AXIS_WIDTH}
              tick={{ fontSize: 11, fill: t.axis, fontFamily: "var(--font-geist-mono), monospace" }}
              tickFormatter={(v: number) => `₺${v.toFixed(1)}`}
              axisLine={false}
              tickLine={false}
            />
            <Tooltip
              cursor={crosshairCursor(t)}
              contentStyle={tt.contentStyle}
              labelStyle={tt.labelStyle}
              formatter={(v) => fmt(Number(v))}
            />
            <Legend
              verticalAlign="top"
              align="left"
              height={22}
              wrapperStyle={{ fontSize: 11, color: t.axis }}
              iconType="square"
              iconSize={9}
            />
            <Bar
              dataKey="worth"
              name="The free deposits, priced at the paid rate"
              fill={t.hero}
              fillOpacity={0.9}
              isAnimationActive={false}
            />
            <Bar
              dataKey="profit"
              name="Sector net profit"
              fill={t.palette[3]}
              fillOpacity={0.9}
              isAnimationActive={false}
            />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </ChartCard>
  );
}
