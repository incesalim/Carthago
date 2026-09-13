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
import { useText } from "@/i18n/use-text";
import {
  Bar,
  BarChart,
  CartesianGrid,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useChartTheme, tooltipStyles } from "@/app/lib/chart-theme";
import type { RollForwardYear } from "@/app/lib/credit-risk";

const bnf = (v: number) => `₺${Math.round(v).toLocaleString("en-US")}bn`;

export default function FormationBars({
  data,
  height = 300,
}: {
  data: RollForwardYear[];
  height?: number;
}) {
  const tx = useText();
  const t = useChartTheme();
  const tt = tooltipStyles(t);

  if (data.length === 0) {
    return (
      <p className="py-6 text-[14px] leading-relaxed text-muted-foreground">
        {tx("The audited roll-forward has no full year yet.")}
      </p>
    );
  }

  const rows = data.map((y) => ({
    year: y.year,
    Formation: y.additions,
    Exits: y.exits,
    net: y.net,
  }));

  return (
    <div data-npl-formation>
      <div className="mb-4 flex flex-wrap items-center gap-x-5 gap-y-2 text-[13px] text-muted-foreground">
        <span className="flex items-center gap-1.5">
          <span
            className="inline-block h-2 w-2.5"
            style={{ background: t.negative }}
          />
          {tx(" formation")}
        </span>
        <span className="flex items-center gap-1.5">
          <span
            className="inline-block h-2 w-2.5"
            style={{ background: t.context }}
          />
          {tx(" exits")}
        </span>
        <span className="text-faint">
          {tx("₺bn · net formation below each year")}
        </span>
      </div>

      <ResponsiveContainer width="100%" height={height}>
        <BarChart
          data={rows}
          margin={{ top: 24, right: 8, bottom: 8, left: 0 }}
          barGap={5}
        >
          <CartesianGrid stroke={t.grid} strokeWidth={1} vertical={false} />
          <XAxis
            dataKey="year"
            tick={{
              fill: t.axis,
              fontSize: 14,
              fontFamily: "var(--font-sans)",
            }}
            axisLine={{ stroke: t.grid }}
            tickLine={false}
          />
          <YAxis
            tick={{
              fill: t.axis,
              fontSize: 13,
              fontFamily: "var(--font-sans)",
            }}
            axisLine={false}
            tickLine={false}
            width={54}
            tickFormatter={(v: number) => `${Math.round(v)}`}
          />
          <Tooltip
            cursor={{ fill: t.grid, opacity: 0.35 }}
            contentStyle={tt.contentStyle}
            labelStyle={tt.labelStyle}
            itemStyle={tt.itemStyle}
            formatter={(v, name) => [
              typeof v === "number" ? bnf(v) : String(v),
              String(name),
            ]}
          />
          <Bar
            dataKey="Formation"
            name={tx("Formation")}
            fill={t.negative}
            isAnimationActive={false}
            maxBarSize={42}
            radius={[2, 2, 0, 0]}
          >
            <LabelList
              dataKey="Formation"
              position="top"
              formatter={(v) =>
                typeof v === "number" ? String(Math.round(v)) : ""
              }
              style={{
                fill: t.negative,
                fontSize: 13,
                fontWeight: 650,
                fontFamily: "var(--font-sans)",
              }}
            />
          </Bar>
          <Bar
            dataKey="Exits"
            name={tx("Exits")}
            fill={t.context}
            isAnimationActive={false}
            maxBarSize={42}
            radius={[2, 2, 0, 0]}
          >
            <LabelList
              dataKey="Exits"
              position="top"
              formatter={(v) =>
                typeof v === "number" ? String(Math.round(v)) : ""
              }
              style={{
                fill: t.axis,
                fontSize: 13,
                fontWeight: 650,
                fontFamily: "var(--font-sans)",
              }}
            />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <div
        className="mt-3 flex flex-wrap gap-x-7 gap-y-3 border-t border-hair pt-4"
        aria-label={tx("Net NPL formation")}
      >
        <span className="text-[13px] font-medium text-muted-foreground">
          {tx("Net NPL formation")}
        </span>
        {rows.map((row) => (
          <div key={row.year} className="flex gap-2 text-[13px]">
            <span className="text-muted-foreground">{row.year}</span>
            <b className="font-semibold tabular-nums">
              {row.net >= 0 ? "+" : "−"}
              {tx(bnf(Math.abs(row.net)))}
            </b>
          </div>
        ))}
      </div>
    </div>
  );
}
