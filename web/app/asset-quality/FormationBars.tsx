"use client";

/**
 * NPL formation vs exits, by year — the pipeline behind the tip.
 *
 * Four discrete annual flows. The page used to draw them as LINES (TrendChart),
 * which implies a continuum between year-ends that does not exist. There is no
 * grouped-bar component in the library (BarByBank is horizontal-by-bank), so
 * this is it.
 *
 * The net figure is printed under each year, and formation carries the hero mark,
 * because the finding is that formation is running away from exits.
 */
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  useChartTheme,
  tooltipStyles,
  PLOT_MARGIN_LEFT,
  Y_AXIS_WIDTH,
} from "@/app/lib/chart-theme";
import type { RollForwardYear } from "@/app/lib/credit-risk";

const bnf = (v: number) => `₺${Math.round(v).toLocaleString("en-US")}bn`;

export default function FormationBars({
  data,
  height = 260,
}: {
  data: RollForwardYear[];
  height?: number;
}) {
  const t = useChartTheme();
  const tt = tooltipStyles(t);

  if (data.length === 0) {
    return <p className="py-6 text-[12px] text-faint">The audited roll-forward has no full year yet.</p>;
  }

  const rows = data.map((y) => ({
    year: y.year,
    Formation: y.additions,
    Exits: y.exits,
    net: y.net,
  }));

  return (
    <div>
      <div className="mb-1 flex items-center gap-3 font-mono text-[9px] text-muted-foreground">
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-2 w-2.5" style={{ background: t.negative }} /> formation
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-2 w-2.5" style={{ background: t.context }} /> exits
        </span>
        <span className="text-faint">₺bn · net formation below each year</span>
      </div>

      <ResponsiveContainer width="100%" height={height}>
        <BarChart
          data={rows}
          margin={{ top: 14, right: 4, bottom: 22, left: PLOT_MARGIN_LEFT }}
          barGap={3}
        >
          <CartesianGrid stroke={t.grid} strokeWidth={1} vertical={false} />
          <XAxis
            dataKey="year"
            tick={{ fill: t.axis, fontSize: 10, fontFamily: "var(--font-mono)" }}
            axisLine={{ stroke: t.grid }}
            tickLine={false}
          />
          <YAxis
            tick={{ fill: t.axis, fontSize: 9, fontFamily: "var(--font-mono)" }}
            axisLine={false}
            tickLine={false}
            width={Y_AXIS_WIDTH}
            tickFormatter={(v: number) => `${Math.round(v)}`}
          />
          <Tooltip
            cursor={{ fill: t.grid, opacity: 0.35 }}
            contentStyle={tt.contentStyle}
            labelStyle={tt.labelStyle}
            itemStyle={tt.itemStyle}
            formatter={(v, name) => [typeof v === "number" ? bnf(v) : String(v), String(name)]}
          />
          <Bar dataKey="Formation" fill={t.negative} isAnimationActive={false} maxBarSize={30}>
            <LabelList
              dataKey="Formation"
              position="top"
              formatter={(v) => (typeof v === "number" ? String(Math.round(v)) : "")}
              style={{
                fill: t.negative,
                fontSize: 9,
                fontWeight: 650,
                fontFamily: "var(--font-mono)",
              }}
            />
          </Bar>
          <Bar dataKey="Exits" fill={t.context} isAnimationActive={false} maxBarSize={30}>
            {rows.map((r) => (
              <Cell key={r.year} fill={t.context} />
            ))}
            <LabelList
              dataKey="net"
              position="bottom"
              offset={12}
              formatter={(v) =>
                typeof v === "number" ? `${v >= 0 ? "+" : "−"}${Math.abs(Math.round(v))}` : ""
              }
              style={{
                fill: t.negative,
                fontSize: 9,
                fontWeight: 650,
                fontFamily: "var(--font-mono)",
              }}
            />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
