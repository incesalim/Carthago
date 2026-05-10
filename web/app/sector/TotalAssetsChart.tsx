"use client";

/**
 * Client component: renders the time series via Recharts.
 * Server fetches data from D1, passes it down, this just paints.
 */
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

interface Row {
  period: string;
  total: number;
}

export default function TotalAssetsChart({ data }: { data: Row[] }) {
  // DB stores values in million TL → display as trillion TL
  const formatted = data.map((d) => ({ ...d, total_trn: d.total / 1_000_000 }));

  return (
    <div className="h-[420px]">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={formatted} margin={{ top: 10, right: 30, left: 60, bottom: 30 }}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="period" tickMargin={8} angle={-30} textAnchor="end" height={60} />
          <YAxis
            tickFormatter={(v) => `₺${v.toFixed(0)} trn`}
            domain={["auto", "auto"]}
          />
          <Tooltip
            formatter={(v) => [`₺${Number(v).toFixed(2)} trn`, "Total Assets"]}
            labelFormatter={(l) => `Period: ${l}`}
          />
          <Area type="monotone" dataKey="total_trn" stroke="#7a0d2e" fill="#7a0d2e22" />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
