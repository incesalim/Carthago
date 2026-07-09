"use client";

/**
 * Multi-series time-series line/area chart.
 * Designed for showing one metric over time, optionally split by bank type.
 */
import { useState } from "react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
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
import { useRangeFilter } from "@/app/lib/use-date-range";

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

/**
 * End-dot: a small filled circle drawn at the series' last point only (r=0
 * elsewhere so Recharts always gets a valid SVG element). Passed via the
 * element form `dot={<EndDot … />}` — Recharts clones it per point, injecting
 * `cx/cy/index/value`. `dim` mirrors the line opacity so an isolated series
 * fades its dot too.
 */
function EndDot(props: {
  cx?: number;
  cy?: number;
  index?: number;
  value?: number | null;
  color?: string;
  bg?: string;
  lastIndex?: number;
  dim?: number;
}) {
  const { cx, cy, index, value, color, bg, lastIndex, dim = 1 } = props;
  const show =
    index === lastIndex && value != null && cx != null && cy != null;
  return (
    <circle
      cx={cx}
      cy={cy}
      r={show ? 3 : 0}
      fill={color}
      fillOpacity={show ? dim : 0}
      stroke={bg}
      strokeWidth={show ? 1.5 : 0}
    />
  );
}

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

  // Window to the dashboard's global date range (filter rows before pivoting).
  const { filtered } = useRangeFilter(data, (r) => r.period);

  // Pivot long → wide: { period, "10001": v, "10003": v, ... }
  // Order series by BANK_GROUP_ORDER (by label); unknown labels keep their order.
  const rank = (code: string) => {
    const i = BANK_GROUP_ORDER.indexOf(seriesLabels[code]);
    return i === -1 ? Number.MAX_SAFE_INTEGER : i;
  };
  const codes = Object.keys(seriesLabels).sort((a, b) => rank(a) - rank(b));
  type Wide = { period: string; [code: string]: string | number | null };
  const byPeriod = new Map<string, Wide>();
  for (const r of filtered) {
    if (!byPeriod.has(r.period)) byPeriod.set(r.period, { period: r.period });
    byPeriod.get(r.period)![r.bank_type_code] = r.value;
  }
  const wide = Array.from(byPeriod.values()).sort((a, b) =>
    a.period.localeCompare(b.period),
  );

  const fmt = formatters[yFormat];

  const lastIdx = wide.length - 1;

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
          <ComposedChart data={wide} margin={{ top: 10, right: 20, left: 60, bottom: 30 }}>
            {/* Horizontal hairlines only — drop the vertical grid + axis lines. */}
            <CartesianGrid vertical={false} stroke={t.grid} />
            <XAxis
              dataKey="period"
              tick={{ fontSize: 11, fill: t.axis, fontFamily: "var(--font-geist-mono), monospace" }}
              tickMargin={6}
              minTickGap={30}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              tick={{ fontSize: 11, fill: t.axis, fontFamily: "var(--font-geist-mono), monospace" }}
              tickFormatter={(v) => fmt(v, 0)}
              axisLine={false}
              tickLine={false}
            />
            {zeroLine && <ReferenceLine y={0} stroke={t.reference} strokeDasharray="3 3" />}
            <Tooltip
              {...tt}
              // Single hovered series, not the whole date column: resolve to the
              // line nearest the cursor so the box shows one group's point.
              shared={false}
              formatter={(v, name) => [v == null ? "—" : fmt(Number(v), decimals), name]}
              labelFormatter={(l) => String(l)}
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
                            gap: 6,
                            color:
                              seriesLabels[code] === "Sector" ? t.tooltipText : t.axis,
                            opacity: active && active !== code ? 0.4 : 1,
                            fontWeight:
                              pinned === code || seriesLabels[code] === "Sector"
                                ? 600
                                : 400,
                            cursor: "default",
                          }}
                        >
                          <span
                            style={{
                              display: "inline-block",
                              width: 9,
                              height: 9,
                              borderRadius: 9999,
                              background: it.color ?? "currentColor",
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
            {codes.length === 1
              ? (() => {
                  // Lone series → a soft area fill under a primary line.
                  const code = codes[0];
                  const color = seriesColor(t, code, 0);
                  const gid = `trend-area-${code.replace(/[^a-z0-9]/gi, "")}`;
                  return (
                    <>
                      <defs>
                        <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
                          <stop offset="0%" stopColor={color} stopOpacity={0.12} />
                          <stop offset="100%" stopColor={color} stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <Area
                        type="monotone"
                        dataKey={code}
                        name={seriesLabels[code]}
                        stroke={color}
                        strokeWidth={2.5}
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        fill={`url(#${gid})`}
                        dot={<EndDot color={color} bg={t.tooltipBg} lastIndex={lastIdx} />}
                        activeDot={{ r: 4, fill: color, stroke: t.tooltipBg, strokeWidth: 1.5 }}
                        isAnimationActive={false}
                      />
                    </>
                  );
                })()
              : codes.map((code, i) => {
                  const color = seriesColor(t, code, i);
                  // Emphasise the Sector aggregate; fade non-isolated lines.
                  const base = seriesLabels[code] === "Sector" ? 2.5 : 2;
                  const opacity = active && active !== code ? 0.18 : 1;
                  return (
                    <Line
                      key={code}
                      type="monotone"
                      dataKey={code}
                      name={seriesLabels[code]}
                      stroke={color}
                      strokeWidth={active === code ? base + 0.75 : base}
                      strokeOpacity={opacity}
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      dot={<EndDot color={color} bg={t.tooltipBg} lastIndex={lastIdx} dim={opacity} />}
                      activeDot={{ r: 4, fill: color, stroke: t.tooltipBg, strokeWidth: 1.5 }}
                      isAnimationActive={false}
                    />
                  );
                })}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </ChartCard>
  );
}
