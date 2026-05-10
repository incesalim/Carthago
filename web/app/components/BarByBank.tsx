"use client";

/**
 * Horizontal bar chart comparing the latest value per bank type.
 */
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

interface Row {
  bank_type_code: string;
  value: number;
}

type FormatKind = "pct" | "trn" | "bn" | "raw";

interface Props {
  data: Row[];
  labels: Record<string, string>;
  title?: string;
  format?: FormatKind;
  decimals?: number;
  height?: number;
}

const COLORS = ["#7a0d2e", "#1f4068", "#0f7b6c", "#a16500", "#5b1a8c", "#5a5a5a"];

const formatters: Record<FormatKind, (v: number, d: number) => string> = {
  pct: (v, d) => `${v.toFixed(d)}%`,
  trn: (v, d) => `₺${(v / 1_000_000).toFixed(d)} trn`,
  bn: (v, d) => `₺${(v / 1_000).toFixed(d)} bn`,
  raw: (v, d) => v.toFixed(d),
};

export default function BarByBank({
  data,
  labels,
  title,
  format = "raw",
  decimals = 2,
  height = 320,
}: Props) {
  const fmt = formatters[format];
  const ordered = data
    .filter((r) => labels[r.bank_type_code])
    .map((r) => ({ ...r, label: labels[r.bank_type_code] }))
    .sort((a, b) => Math.abs(b.value) - Math.abs(a.value));

  return (
    <div className="rounded-lg border bg-white p-4 shadow-sm">
      {title && <div className="text-sm font-medium mb-2">{title}</div>}
      <div style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={ordered} layout="vertical" margin={{ top: 5, right: 30, left: 70, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#eee" horizontal={false} />
            <XAxis type="number" tick={{ fontSize: 11 }} tickFormatter={(v) => fmt(v, 0)} />
            <YAxis type="category" dataKey="label" tick={{ fontSize: 11 }} width={70} />
            <Tooltip
              contentStyle={{ fontSize: 11, padding: "6px 10px", borderRadius: 4 }}
              formatter={(v) => [fmt(Number(v), decimals), ""]}
              cursor={{ fill: "#f5f5f5" }}
            />
            <Bar dataKey="value" radius={[0, 4, 4, 0]}>
              {ordered.map((_, i) => (
                <Cell key={i} fill={COLORS[i % COLORS.length]} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
