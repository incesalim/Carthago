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
import { useText } from "@/i18n/use-text";
import {
  Bar,
  BarChart,
  CartesianGrid,
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
  const tx = useText();
  const t = useChartTheme();
  const colors = { worth: t.palette[1], profit: t.hero };
  const tt = tooltipStyles(t);
  const { filtered } = useRangeFilter(data, (r) => r.period);
  const fmt = (v: number) => tx("₺{0} trn", {0: v.toFixed(2)});

  return (
    <ChartCard plain title={tx(title)} description={tx(description)} source={tx(source)}>
      <ChartData
        table={wideToTable(filtered, { key: "period", label: "Month" }, [
          { key: "worth", label: "Free deposits, priced" },
          { key: "profit", label: "Net profit" },
        ])}
      />
      <div className="mb-4 flex flex-wrap gap-x-5 gap-y-2 text-[14px] text-muted-foreground">
        <span className="flex items-center gap-2"><i aria-hidden className="h-2.5 w-2.5" style={{ background: colors.worth }} />{tx("The free deposits, priced at the paid rate")}</span>
        <span className="flex items-center gap-2"><i aria-hidden className="h-2.5 w-2.5" style={{ background: colors.profit }} />{tx("Sector net profit")}</span>
      </div>
      <div data-chart-plot="history" style={{ height: `var(--sector-chart-height, ${height}px)` }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={filtered}
            margin={{ top: 10, right: 12, left: PLOT_MARGIN_LEFT, bottom: 4 }}
          >
            <CartesianGrid vertical={false} stroke={t.grid} />
            <XAxis
              dataKey="period"
              tick={{ fontSize: 14, fill: t.axis }}
              minTickGap={52}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              width={Y_AXIS_WIDTH}
              tick={{ fontSize: 14, fill: t.axis }}
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
            <Bar
              dataKey="worth"
              name={tx("The free deposits, priced at the paid rate")}
              fill={colors.worth}
              isAnimationActive={false}
            />
            <Bar
              dataKey="profit"
              name={tx("Sector net profit")}
              fill={colors.profit}
              isAnimationActive={false}
            />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </ChartCard>
  );
}
