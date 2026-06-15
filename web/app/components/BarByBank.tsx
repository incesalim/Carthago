"use client";

/**
 * Horizontal bar chart comparing the latest value per bank type.
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
import { ChartCard } from "@/app/components/ui/chart-card";
import { useChartTheme, tooltipStyles } from "@/app/lib/chart-theme";
import { formatters, type FormatKind } from "@/app/lib/chart-format";

interface Row {
  bank_type_code: string;
  value: number;
}

interface Props {
  data: Row[];
  labels: Record<string, string>;
  title?: string;
  format?: FormatKind;
  decimals?: number;
  height?: number;
}


export default function BarByBank({
  data,
  labels,
  title,
  format = "raw",
  decimals = 2,
  height = 320,
}: Props) {
  const t = useChartTheme();
  const tt = tooltipStyles(t);
  const fmt = formatters[format];
  const ordered = data
    .filter((r) => labels[r.bank_type_code] && r.value != null && !Number.isNaN(r.value))
    .map((r) => ({ ...r, label: labels[r.bank_type_code], value: Number(r.value) }))
    .sort((a, b) => Math.abs(b.value) - Math.abs(a.value));

  // Domain padding so even small bars stay visible.
  const maxAbs = ordered.reduce((m, r) => Math.max(m, Math.abs(r.value)), 0);
  const domain: [number, number] = [
    Math.min(0, ...ordered.map((r) => r.value)) * 1.1,
    Math.max(0, ...ordered.map((r) => r.value)) * 1.1 || maxAbs * 1.1 || 1,
  ];
  const labelFmt = (v: React.ReactNode) =>
    v == null ? "" : fmt(Number(v), decimals);

  return (
    <ChartCard title={title}>
      <div style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={ordered}
            layout="vertical"
            margin={{ top: 5, right: 60, left: 10, bottom: 5 }}
            barCategoryGap="20%"
          >
            <CartesianGrid strokeDasharray="3 3" stroke={t.grid} horizontal={false} />
            <XAxis
              type="number"
              tick={{ fontSize: 11, fill: t.axis }}
              tickFormatter={(v) => fmt(v, 0)}
              domain={domain}
              axisLine={{ stroke: t.grid }}
              tickLine={{ stroke: t.grid }}
            />
            <YAxis
              type="category"
              dataKey="label"
              tick={{ fontSize: 11, fill: t.axis }}
              width={90}
              axisLine={false}
              tickLine={false}
            />
            <Tooltip
              {...tt}
              formatter={(v) => [fmt(Number(v), decimals), ""]}
              cursor={{ fill: t.cursor }}
            />
            <Bar dataKey="value" radius={[0, 4, 4, 0]} isAnimationActive={false}>
              {ordered.map((row, i) => (
                <Cell
                  key={`bar-${row.bank_type_code}`}
                  fill={t.palette[i % t.palette.length]}
                />
              ))}
              <LabelList
                dataKey="value"
                position="right"
                formatter={labelFmt}
                style={{ fontSize: 11, fill: t.axis }}
              />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </ChartCard>
  );
}
