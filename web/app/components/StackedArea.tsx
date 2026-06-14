"use client";

import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ChartCard } from "@/app/components/ui/chart-card";
import { useChartTheme, tooltipStyles, seriesColor } from "@/app/lib/chart-theme";

export interface StackPoint {
  // Wide row: the x-axis field (recharts reads it via dataKey="period") plus one
  // value per series. `null` marks a gap and is handled at render time.
  [series: string]: string | number | null;
}

type FormatKind = "pct" | "trn" | "bn" | "raw";

interface Props {
  data: StackPoint[];
  series: { key: string; label: string }[];
  title?: string;
  yFormat?: FormatKind;
  decimals?: number;
  height?: number;
  /** Render as percent stack (each point sums to 100%). */
  percentStack?: boolean;
  /** Colour each series by its key via `seriesColor` (matches TrendChart /
   *  BopFlowChart) instead of the warm/cool layering order. Use when the same
   *  series also appears as a line on the page so colours stay consistent. */
  colorKeys?: boolean;
}

// Stacked areas read best when the brand red leads but warm/cool alternate.
const ORDER = [0, 3, 2, 1, 4, 5];

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

export default function StackedArea({
  data,
  series,
  title,
  yFormat = "raw",
  decimals = 1,
  height = 320,
  percentStack = false,
  colorKeys = false,
}: Props) {
  const t = useChartTheme();
  const tt = tooltipStyles(t);
  const fmt = formatters[percentStack ? "pct" : yFormat];
  const colorAt = (i: number) =>
    colorKeys
      ? seriesColor(t, series[i].key, i)
      : t.palette[ORDER[i % ORDER.length] % t.palette.length];

  return (
    <ChartCard title={title}>
      <div style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} stackOffset={percentStack ? "expand" : "none"}
                     margin={{ top: 10, right: 20, left: 60, bottom: 30 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={t.grid} />
            <XAxis
              dataKey="period"
              tick={{ fontSize: 11, fill: t.axis }}
              minTickGap={30}
              axisLine={{ stroke: t.grid }}
              tickLine={{ stroke: t.grid }}
            />
            <YAxis
              tick={{ fontSize: 11, fill: t.axis }}
              tickFormatter={(v) =>
                percentStack ? `${(v * 100).toFixed(0)}%` : fmt(v, 0)
              }
              axisLine={{ stroke: t.grid }}
              tickLine={{ stroke: t.grid }}
            />
            <Tooltip
              {...tt}
              // Order tooltip rows by `series` (= stack + legend order); Recharts
              // otherwise uses its own internal series order.
              itemSorter={(item) => series.findIndex((s) => s.key === String(item.dataKey))}
              formatter={(value, name, item) => {
                if (value == null) return ["—", name];
                if (percentStack) {
                  // stackOffset="expand" only normalises the drawn areas — the
                  // tooltip value is still the raw level, so compute each
                  // bucket's share of the period total here.
                  const row = (item?.payload ?? {}) as Record<string, number>;
                  const total = series.reduce(
                    (sum, s) => sum + (Number(row[s.key]) || 0),
                    0,
                  );
                  const share = total > 0 ? (Number(value) / total) * 100 : 0;
                  return [`${nf(share, decimals)}%`, name];
                }
                return [fmt(Number(value), decimals), name];
              }}
              labelFormatter={(l) => String(l)}
            />
            <Legend
              wrapperStyle={{ fontSize: 11 }}
              content={() => (
                // Render straight from `series` so the legend order matches the
                // stack (bottom→top); Recharts otherwise reorders it.
                <ul
                  style={{
                    display: "flex",
                    flexWrap: "wrap",
                    justifyContent: "center",
                    gap: "2px 14px",
                    listStyle: "none",
                    margin: 0,
                    padding: 0,
                  }}
                >
                  {series.map((s, i) => (
                    <li
                      key={s.key}
                      style={{
                        display: "inline-flex",
                        alignItems: "center",
                        gap: 5,
                        color: t.axis,
                      }}
                    >
                      <span
                        style={{
                          display: "inline-block",
                          width: 11,
                          height: 11,
                          borderRadius: 2,
                          background: colorAt(i),
                        }}
                      />
                      {s.label}
                    </li>
                  ))}
                </ul>
              )}
            />
            {series.map((s, i) => (
              <Area
                key={s.key}
                type="monotone"
                dataKey={s.key}
                name={s.label}
                stackId="1"
                stroke={colorAt(i)}
                fill={colorAt(i)}
                fillOpacity={0.55}
                isAnimationActive={false}
              />
            ))}
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </ChartCard>
  );
}
