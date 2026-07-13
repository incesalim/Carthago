"use client";

/**
 * The month's P&L, de-cumulated from the year-to-date statement.
 *
 * Every ratio /profitability prints (ROE, ROA, NIM, OPEX) is a YTD figure
 * annualized, so it cannot show what a single month did. This waterfall can:
 * in May 2026 net interest income rose ₺98bn year-on-year and the profit STILL
 * FELL — costs and trading took it.
 *
 * The bars are Recharts *range* bars (`dataKey` returning `[lo, hi]`). The final
 * column is the REPORTED net-profit line, not the sum — and the page only draws
 * this chart when the two reconcile (see lib/profitability.ts).
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
import type { Bridge } from "@/app/lib/profitability";

export default function ProfitBridge({
  bridge,
  prior,
  title,
  description,
  source,
  height = 300,
}: {
  bridge: Bridge;
  /** The same month a year earlier — drives the y/y line under each label. */
  prior?: Bridge | null;
  title?: React.ReactNode;
  description?: React.ReactNode;
  source?: React.ReactNode;
  height?: number;
}) {
  const t = useChartTheme();

  const steps: { key: keyof Bridge; name: string }[] = [
    { key: "nii", name: "Net interest income" },
    { key: "prov", name: "− Provisions" },
    { key: "fees", name: "+ Fees & other" },
    { key: "opex", name: "− Operating costs" },
    { key: "other", name: "± Trading / FX" },
    { key: "tax", name: "− Tax" },
  ];

  let run = 0;
  const data = steps.map((s) => {
    const v = bridge[s.key] as number;
    const from = run;
    run += v;
    const yoy = prior ? v - (prior[s.key] as number) : null;
    return {
      name: s.name,
      range: [Math.min(from, run), Math.max(from, run)] as [number, number],
      value: v,
      yoy,
      kind: v >= 0 ? "up" : "down",
    };
  });
  data.push({
    name: "= Net profit",
    range: [0, bridge.net] as [number, number],
    value: bridge.net,
    yoy: prior ? bridge.net - prior.net : null,
    kind: "total",
  });

  const fill = (k: string) =>
    k === "total" ? t.hero : k === "up" ? "var(--positive)" : "var(--negative)";

  return (
    <ChartCard plain title={title} description={description} source={source}>
      <div style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 24, right: 10, left: 34, bottom: 30 }}>
            <CartesianGrid vertical={false} stroke={t.grid} />
            <XAxis
              dataKey="name"
              tick={{ fontSize: 10, fill: t.axis }}
              interval={0}
              axisLine={false}
              tickLine={false}
              height={44}
            />
            <YAxis
              tick={{ fontSize: 11, fill: t.axis, fontFamily: "var(--font-geist-mono), monospace" }}
              tickFormatter={(v: number) => v.toFixed(2)}
              axisLine={false}
              tickLine={false}
              width={40}
            />
            <ReferenceLine y={0} stroke={t.reference} strokeDasharray="3 3" />
            <Bar dataKey="range" isAnimationActive={false} radius={[2, 2, 0, 0]}>
              {data.map((d) => (
                <Cell key={d.name} fill={fill(d.kind)} fillOpacity={d.kind === "total" ? 0.9 : 0.75} />
              ))}
              <LabelList
                dataKey="value"
                position="top"
                formatter={(v) => {
                  const n = Number(v);
                  return Number.isFinite(n)
                    ? `${n >= 0 ? "+" : "−"}${Math.abs(n).toFixed(3)}`
                    : "";
                }}
                style={{
                  fill: "var(--foreground)",
                  fontSize: 10,
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
