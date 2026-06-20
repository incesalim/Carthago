"use client";

/**
 * Multi-series time-series line/area chart.
 * Designed for showing one metric over time, optionally split by bank type.
 */
import { useState } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ChartCard } from "@/app/components/ui/chart-card";
import { ChartData } from "@/app/components/ui/chart-csv";
import { useChartTheme, tooltipStyles, seriesColor } from "@/app/lib/chart-theme";
import { wideToTable } from "@/app/lib/chart-csv";
import { formatters, type FormatKind } from "@/app/lib/chart-format";

export interface TrendPoint {
  period: string;
  bank_type_code: string;
  value: number | null;
}

interface Props {
  /** Long-form rows {period, bank_type_code, value}. */
  data: TrendPoint[];
  /** Map of bank_type_code → label shown in legend. */
  seriesLabels: Record<string, string>;
  title?: string;
  yFormat?: FormatKind;
  decimals?: number;
  /** Show a horizontal line at y=0 (useful for growth rates). */
  zeroLine?: boolean;
  height?: number;
}


// Fixed display order for the bank-group series (Sector, then the deposit-
// ownership trio, then participation/dev). Series whose label isn't listed keep
// their original order (single-series, TL/FX, consumer-segment charts, …).
const BANK_GROUP_ORDER = ["Sector", "State", "Domestic", "Foreign", "Participation", "Dev & Inv"];

export default function TrendChart({
  data,
  seriesLabels,
  title,
  yFormat = "raw",
  decimals = 2,
  zeroLine = false,
  height = 320,
}: Props) {
  const t = useChartTheme();
  const tt = tooltipStyles(t);
  // Hovering a legend item emphasises that line and fades the rest;
  // right-clicking pins the isolation until right-clicked again.
  const [hovered, setHovered] = useState<string | null>(null);
  const [pinned, setPinned] = useState<string | null>(null);
  const active = hovered ?? pinned;

  // Pivot long → wide: { period, "10001": v, "10003": v, ... }
  // Order series by BANK_GROUP_ORDER (by label); unknown labels keep their order.
  const rank = (code: string) => {
    const i = BANK_GROUP_ORDER.indexOf(seriesLabels[code]);
    return i === -1 ? Number.MAX_SAFE_INTEGER : i;
  };
  const codes = Object.keys(seriesLabels).sort((a, b) => rank(a) - rank(b));
  type Wide = { period: string; [code: string]: string | number | null };
  const byPeriod = new Map<string, Wide>();
  for (const r of data) {
    if (!byPeriod.has(r.period)) byPeriod.set(r.period, { period: r.period });
    byPeriod.get(r.period)![r.bank_type_code] = r.value;
  }
  const wide = Array.from(byPeriod.values()).sort((a, b) =>
    a.period.localeCompare(b.period),
  );

  const fmt = formatters[yFormat];

  return (
    <ChartCard title={title}>
      <ChartData
        table={wideToTable(
          wide,
          { key: "period", label: "Period" },
          codes.map((c) => ({ key: c, label: seriesLabels[c] })),
        )}
      />
      {/* Right-click is a pin/unpin gesture here — keep the browser menu out. */}
      <div style={{ height }} onContextMenu={(e) => e.preventDefault()}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={wide} margin={{ top: 10, right: 20, left: 60, bottom: 30 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={t.grid} />
            <XAxis
              dataKey="period"
              tick={{ fontSize: 11, fill: t.axis }}
              tickMargin={6}
              minTickGap={30}
              axisLine={{ stroke: t.grid }}
              tickLine={{ stroke: t.grid }}
            />
            <YAxis
              tick={{ fontSize: 11, fill: t.axis }}
              tickFormatter={(v) => fmt(v, 0)}
              axisLine={{ stroke: t.grid }}
              tickLine={{ stroke: t.grid }}
            />
            {zeroLine && <ReferenceLine y={0} stroke={t.reference} strokeDasharray="3 3" />}
            <Tooltip
              {...tt}
              formatter={(v, name) => [v == null ? "—" : fmt(Number(v), decimals), name]}
              labelFormatter={(l) => String(l)}
              itemSorter={(item) =>
                typeof item.value === "number" ? -item.value : 0
              }
            />
            <Legend
              verticalAlign="bottom"
              align="center"
              layout="horizontal"
              wrapperStyle={{ fontSize: 11, paddingTop: 4 }}
              content={({ payload }) => {
                // Recharts 3 auto-sorts the legend alphabetically; render it
                // ourselves so it follows BANK_GROUP_ORDER.
                const items = [...(payload ?? [])].sort(
                  (a, b) => rank(String(a.dataKey)) - rank(String(b.dataKey)),
                );
                return (
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
                    {items.map((it) => {
                      const code = String(it.dataKey);
                      return (
                        <li
                          key={code}
                          onMouseEnter={() => setHovered(code)}
                          onMouseLeave={() => setHovered(null)}
                          onContextMenu={(e) => {
                            e.preventDefault();
                            setPinned((p) => (p === code ? null : code));
                          }}
                          style={{
                            display: "inline-flex",
                            alignItems: "center",
                            gap: 5,
                            color: t.axis,
                            opacity: active && active !== code ? 0.4 : 1,
                            fontWeight: pinned === code ? 600 : 400,
                            cursor: "default",
                          }}
                        >
                          <span
                            style={{
                              display: "inline-block",
                              width: 14,
                              borderTop: `2px solid ${it.color ?? "currentColor"}`,
                            }}
                          />
                          {it.value}
                        </li>
                      );
                    })}
                  </ul>
                );
              }}
            />
            {codes.map((code, i) => (
              <Line
                key={code}
                type="monotone"
                dataKey={code}
                name={seriesLabels[code]}
                stroke={seriesColor(t, code, i)}
                strokeWidth={active === code ? 2.75 : 1.75}
                strokeOpacity={active && active !== code ? 0.18 : 1}
                dot={false}
                isAnimationActive={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </ChartCard>
  );
}
