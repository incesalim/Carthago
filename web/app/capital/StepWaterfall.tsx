"use client";

/**
 * The twelve-month change in CAR, split into the one-month step and everything
 * else — a four-bar waterfall: the level a year ago, the two moves that made
 * the year, and the level now.
 *
 * This exists because the page used to print a single "−1.2pp over 12m" and
 * extrapolate it. That number is a step (−2.92pp) and a non-step (+1.75pp)
 * averaged together: ex-step the sector ADDED capital. The waterfall is the
 * smallest mark that makes the two visible at once.
 *
 * The floating bars are Recharts *range* bars (`dataKey` returning `[lo, hi]`).
 */
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  ReferenceLine,
  ResponsiveContainer,
  XAxis,
  YAxis,
} from "recharts";
import { ChartCard } from "@/app/components/ui/chart-card";
import { useChartTheme } from "@/app/lib/chart-theme";

const MIN = 12; // the regulatory minimum the buffer is measured against

export default function StepWaterfall({
  fromLabel,
  toLabel,
  from,
  to,
  step,
  rest,
  stepLabel,
  title,
  description,
  source,
  height = 260,
}: {
  fromLabel: string;
  toLabel: string;
  from: number;
  to: number;
  step: number;
  rest: number;
  /** e.g. "The January step". */
  stepLabel: string;
  title?: React.ReactNode;
  description?: React.ReactNode;
  source?: React.ReactNode;
  height?: number;
}) {
  const t = useChartTheme();

  // Bars in the order the year happened: level → the non-step → the step → level.
  // `rest` is drawn from `from` upward, then the step from there.
  const afterRest = from + rest;
  const data = [
    { name: fromLabel, range: [MIN, from] as [number, number], kind: "level", value: from },
    {
      name: "Everything else",
      range: [Math.min(from, afterRest), Math.max(from, afterRest)] as [number, number],
      kind: rest >= 0 ? "up" : "down",
      value: rest,
    },
    {
      name: stepLabel,
      range: [Math.min(afterRest, to), Math.max(afterRest, to)] as [number, number],
      kind: step >= 0 ? "up" : "down",
      value: step,
    },
    { name: toLabel, range: [MIN, to] as [number, number], kind: "level", value: to },
  ];

  const fill = (kind: string) =>
    kind === "level" ? t.hero : kind === "up" ? "var(--positive)" : "var(--negative)";
  const lo = Math.min(MIN, to, from) - 1.5;
  const hi = Math.max(from, to, afterRest) + 1.2;

  return (
    <ChartCard plain title={title} description={description} source={source}>
      <div style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 22, right: 12, left: 8, bottom: 4 }}>
            <CartesianGrid vertical={false} stroke={t.grid} />
            <XAxis
              dataKey="name"
              tick={{ fontSize: 11, fill: t.axis }}
              axisLine={false}
              tickLine={false}
              interval={0}
            />
            <YAxis
              domain={[lo, hi]}
              tick={{ fontSize: 11, fill: t.axis, fontFamily: "var(--font-geist-mono), monospace" }}
              tickFormatter={(v: number) => `${v.toFixed(0)}%`}
              axisLine={false}
              tickLine={false}
              width={42}
            />
            {/* the floor the buffer is measured against */}
            <ReferenceLine
              y={MIN}
              stroke="var(--warning)"
              strokeDasharray="3 3"
              label={{
                value: "12% minimum",
                position: "insideBottomLeft",
                fill: "var(--warning)",
                fontSize: 10,
                fontFamily: "var(--font-geist-mono), monospace",
              }}
            />
            <Bar dataKey="range" isAnimationActive={false} radius={[2, 2, 0, 0]}>
              {data.map((d) => (
                <Cell key={d.name} fill={fill(d.kind)} fillOpacity={d.kind === "level" ? 0.9 : 0.75} />
              ))}
              <LabelList
                dataKey="value"
                position="top"
                // levels print as a ratio, moves print as pp — the two are not
                // the same quantity and must not look like it
                formatter={(v) => {
                  const n = Number(v);
                  if (!Number.isFinite(n)) return "";
                  return n === from || n === to
                    ? `${n.toFixed(2)}%`
                    : `${n >= 0 ? "+" : "−"}${Math.abs(n).toFixed(2)}pp`;
                }}
                style={{
                  fill: "var(--foreground)",
                  fontSize: 11,
                  fontWeight: 600,
                  fontFamily: "var(--font-geist-mono), monospace",
                }}
              />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </ChartCard>
  );
}
