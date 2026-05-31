"use client";

/**
 * Client component: renders the time series via Recharts.
 * Server fetches data from D1, passes it down, this just paints.
 */
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useChartTheme, tooltipStyles } from "@/app/lib/chart-theme";

interface Row {
  period: string;
  total: number;
}

export default function TotalAssetsChart({ data }: { data: Row[] }) {
  const t = useChartTheme();
  const tt = tooltipStyles(t);
  // DB stores values in million TL → display as trillion TL
  const formatted = data.map((d) => ({ ...d, total_trn: d.total / 1_000_000 }));
  const stroke = t.palette[0];

  return (
    <div className="h-[420px]">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={formatted} margin={{ top: 10, right: 30, left: 60, bottom: 30 }}>
          <defs>
            <linearGradient id="total-assets-fill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={stroke} stopOpacity={0.22} />
              <stop offset="100%" stopColor={stroke} stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke={t.grid} />
          <XAxis
            dataKey="period"
            tickMargin={8}
            angle={-30}
            textAnchor="end"
            height={60}
            tick={{ fontSize: 11, fill: t.axis }}
            axisLine={{ stroke: t.grid }}
            tickLine={{ stroke: t.grid }}
          />
          <YAxis
            tickFormatter={(v) => `₺${v.toFixed(0)} trn`}
            domain={["auto", "auto"]}
            tick={{ fontSize: 11, fill: t.axis }}
            axisLine={{ stroke: t.grid }}
            tickLine={{ stroke: t.grid }}
          />
          <Tooltip
            {...tt}
            formatter={(v) => [`₺${Number(v).toFixed(2)} trn`, "Total Assets"]}
            labelFormatter={(l) => `Period: ${l}`}
          />
          <Area
            type="monotone"
            dataKey="total_trn"
            stroke={stroke}
            strokeWidth={1.75}
            fill="url(#total-assets-fill)"
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
