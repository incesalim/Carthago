"use client";

/**
 * The reserve buffer, decomposed — gross → net → net excluding swaps, with the
 * two gaps between them shaded.
 *
 * Deliberately NOT a stacked area. The obvious mark for "whose FX is it" is a
 * stack of three components summing to gross (banks' required reserves + the
 * swap stock + the CBRT's own net FX). It would LIE: the CBRT's own net FX is
 * NEGATIVE across a long stretch of this window (−$68.6bn at its worst in March
 * 2024), and a stack cannot draw a negative band without misstating the total.
 *
 * So: three lines, and the gaps drawn as Recharts *range* areas (`dataKey`
 * returning `[lo, hi]`). The gross→net gap is the banks' own FX, held at the
 * CBRT as required reserves; the net→excl-swaps gap is the swap stock. A zero
 * reference line makes the negative stretch legible.
 */
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ChartCard } from "@/app/components/ui/chart-card";
import { ChartData } from "@/app/components/ui/chart-csv";
import { NearestSeriesTooltip } from "@/app/components/nearest-hover";
import { EndLabelLayer, estimateEndLabelWidth } from "@/app/components/chart-end-labels";
import { useChartTheme, crosshairCursor } from "@/app/lib/chart-theme";
import { wideToTable } from "@/app/lib/chart-csv";
import { useRangeFilter } from "@/app/lib/use-date-range";

export interface BufferPoint {
  period: string;
  /** Gross reserves (AB.TOPLAM), USD bn. */
  gross: number;
  /** Derived net international reserves, USD bn. */
  net: number;
  /** Net excluding swaps — the CBRT's own FX, USD bn. May be negative. */
  own: number;
  /** Index signature so the row satisfies the chart helpers' `Row` shape. */
  [k: string]: string | number;
}

const LABELS: Record<string, string> = {
  gross: "Gross",
  net: "Net",
  own: "CBRT's own",
};

export default function ReserveBuffer({
  data,
  title,
  description,
  source,
  height = 300,
}: {
  data: BufferPoint[];
  title?: React.ReactNode;
  description?: React.ReactNode;
  source?: React.ReactNode;
  height?: number;
}) {
  const t = useChartTheme();
  const { filtered } = useRangeFilter(data, (r) => r.period);
  // The swap band + the CBRT's-own line take the plum from the categorical ramp
  // (--chart-5): distinct from the navy hero without inventing a colour.
  const PLUM = t.palette[4];

  // Range areas: Recharts draws a band when the value is a [lo, hi] tuple.
  const rows = filtered.map((r) => ({
    ...r,
    banksBand: [r.net, r.gross] as [number, number],
    swapBand: [r.own, r.net] as [number, number],
  }));

  const fmt = (v: number) => `$${v.toFixed(1)}bn`;
  const keys = ["gross", "net", "own"];
  const lastRow = rows.at(-1);
  const labelWidth = estimateEndLabelWidth(
    lastRow
      ? keys.map((k) => ({ name: LABELS[k], value: fmt(lastRow[k as "gross"]) }))
      : [],
  );

  const ink: Record<string, string> = {
    gross: t.context,
    net: t.hero,
    own: PLUM,
  };

  return (
    <ChartCard plain title={title} description={description} source={source}>
      <ChartData
        table={wideToTable(
          rows,
          { key: "period", label: "Week" },
          keys.map((k) => ({ key: k, label: LABELS[k] })),
        )}
      />
      <div style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={rows} margin={{ top: 10, right: labelWidth, left: 52, bottom: 8 }}>
            <CartesianGrid vertical={false} stroke={t.grid} />
            <XAxis
              dataKey="period"
              tick={{ fontSize: 11, fill: t.axis, fontFamily: "var(--font-geist-mono), monospace" }}
              tickMargin={6}
              minTickGap={40}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              tick={{ fontSize: 11, fill: t.axis, fontFamily: "var(--font-geist-mono), monospace" }}
              tickFormatter={(v) => `${v}`}
              axisLine={false}
              tickLine={false}
            />
            {/* The line the CBRT's own net FX spent a year underneath. */}
            <ReferenceLine y={0} stroke={t.reference} strokeDasharray="3 3" />
            <Tooltip
              cursor={crosshairCursor(t)}
              content={(p) => (
                <NearestSeriesTooltip
                  active={p.active}
                  payload={p.payload?.filter((s) => keys.includes(String(s.dataKey)))}
                  label={p.label}
                  coordinate={p.coordinate}
                  formatValue={(v) => fmt(v)}
                />
              )}
            />
            {/* Gap 1: gross → net = the BANKS' own FX, held at the CBRT. */}
            <Area
              dataKey="banksBand"
              name="Banks' required reserves"
              stroke="none"
              fill={t.context}
              fillOpacity={0.35}
              isAnimationActive={false}
              activeDot={false}
            />
            {/* Gap 2: net → excl-swaps = the swap stock (borrowed FX). */}
            <Area
              dataKey="swapBand"
              name="Swapped in"
              stroke="none"
              fill={PLUM}
              fillOpacity={0.3}
              isAnimationActive={false}
              activeDot={false}
            />
            {keys.map((k) => (
              <Line
                key={k}
                type="monotone"
                dataKey={k}
                name={LABELS[k]}
                stroke={ink[k]}
                strokeWidth={k === "net" ? 2.5 : 1.75}
                strokeLinecap="round"
                strokeLinejoin="round"
                dot={false}
                activeDot={false}
                isAnimationActive={false}
              />
            ))}
            {/* EndLabelLayer reads scalar series only — hand it the three lines,
                not the two [lo, hi] range bands. */}
            <EndLabelLayer
              rows={filtered}
              periodKey="period"
              keys={keys}
              labelFor={(k) => LABELS[k]}
              colorFor={(k) => (k === "gross" ? t.inkMuted : ink[k])}
              lineColorFor={(k) => ink[k]}
              formatValue={fmt}
              heroKey="net"
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </ChartCard>
  );
}
