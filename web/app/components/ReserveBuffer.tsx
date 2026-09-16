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
import { useText } from "@/i18n/use-text";
import { useChartFormat } from "@/i18n/use-chart-format";
import { formatDateLabel } from "@/i18n/format";
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
import {
  useChartTheme,
  crosshairCursor,
  PLOT_MARGIN_LEFT,
  Y_AXIS_WIDTH,
} from "@/app/lib/chart-theme";
import { wideToTable } from "@/app/lib/chart-csv";
import { useRangeFilter } from "@/app/lib/use-date-range";
import styles from "./reserve-buffer.module.css";

// The point shape and the arithmetic behind it live in lib/reserves.ts, so
// /liquidity and /economy draw the same three levels from one derivation.
export type { BufferPoint } from "@/app/lib/reserves";
import { type BufferPoint } from "@/app/lib/reserves";

const KEYS = ["gross", "net", "own"] as const;
const LABELS: Record<(typeof KEYS)[number], string> = {
  gross: "Gross reserves",
  net: "Net reserves",
  own: "Net excl. swaps",
};
const SANS = "var(--font-sans), ui-sans-serif, sans-serif";

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
  const tx = useText();
  const t = useChartTheme();
  const format = useChartFormat();
  const { filtered } = useRangeFilter(data, (r) => r.period);

  // Range areas: Recharts draws a band when the value is a [lo, hi] tuple.
  const rows = filtered.map((r) => ({
    ...r,
    banksBand: [r.net, r.gross] as [number, number],
    swapBand: [r.own, r.net] as [number, number],
  }));

  const fmt = (v: number) => tx(`$${format.raw(v, 1)}bn`);
  const lastRow = rows.at(-1);

  const ink: Record<string, string> = {
    gross: t.contextActive,
    net: t.palette[1],
    own: t.hero,
  };

  return (
    <ChartCard plain title={tx(title)} description={tx(description)} source={tx(source)} bodyClassName={styles.body}>
      <ChartData
        table={wideToTable(
          rows,
          { key: "period", label: "Week" },
          KEYS.map((k) => ({ key: k, label: LABELS[k] })),
        )}
      />
      <div className={styles.readout} aria-label={tx("Latest values")}>
        <div className={styles.readoutHeading}>
          <span>{tx("Latest values")}</span>
          <span>{lastRow ? formatDateLabel(lastRow.period, tx.locale) : "—"}</span>
        </div>
        <dl className={styles.values}>
          {KEYS.map((key) => <div key={key} className={styles.value}>
            <dt><span className={styles.swatch} style={{ borderColor: ink[key], borderTopStyle: key === "gross" ? "dashed" : "solid" }} />{tx(LABELS[key])}</dt>
            <dd>{lastRow && Number.isFinite(lastRow[key]) ? fmt(lastRow[key]) : "—"}</dd>
          </div>)}
        </dl>
      </div>
      <div data-chart-plot="history" className={styles.plot} style={{ height: `var(--sector-chart-height, ${height}px)` }}>
        <ResponsiveContainer width="100%" height="100%" minWidth={0}>
          <ComposedChart
            data={rows}
            margin={{ top: 10, right: 16, left: PLOT_MARGIN_LEFT, bottom: 8 }}
            accessibilityLayer
          >
            <CartesianGrid vertical={false} stroke={t.grid} />
            <XAxis
              dataKey="period"
              tick={{ fontSize: 14, fill: t.inkMuted, fontFamily: SANS }}
              tickFormatter={(period) => formatDateLabel(String(period).slice(0, 7), tx.locale)}
              tickMargin={10}
              minTickGap={60}
              interval="preserveStartEnd"
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              width={Y_AXIS_WIDTH}
              tick={{ fontSize: 14, fill: t.inkMuted, fontFamily: SANS }}
              tickFormatter={(v) => format.raw(Number(v), 0)}
              tickMargin={8}
              axisLine={false}
              tickLine={false}
            />
            {/* The line the CBRT's own net FX spent a year underneath. */}
            <ReferenceLine y={0} stroke={t.reference} strokeDasharray="3 3" />
            <Tooltip
              cursor={crosshairCursor(t)}
              content={({ active, label, payload }) => {
                if (!active || !payload?.length) return null;
                const point = payload[0]?.payload as BufferPoint | undefined;
                if (!point) return null;
                return <div className={styles.tooltip}>
                  <div className={styles.tooltipDate}>{formatDateLabel(String(label ?? ""), tx.locale)}</div>
                  {KEYS.map((key) => <div key={key} className={styles.tooltipRow}>
                    <span className={styles.swatch} style={{ borderColor: ink[key], borderTopStyle: key === "gross" ? "dashed" : "solid" }} />
                    <span>{tx(LABELS[key])}</span>
                    <strong>{Number.isFinite(point[key]) ? fmt(point[key]) : "—"}</strong>
                  </div>)}
                </div>;
              }}
            />
            {/* Gap 1: gross → net = the BANKS' own FX, held at the CBRT. */}
            <Area
              dataKey="banksBand"
              name={tx("Banks' required reserves")}
              stroke="none"
              fill={ink.gross}
              fillOpacity={0.1}
              isAnimationActive={false}
              activeDot={false}
            />
            {/* Gap 2: net → excl-swaps = the swap stock (borrowed FX). */}
            <Area
              dataKey="swapBand"
              name={tx("Swapped in")}
              stroke="none"
              fill={ink.net}
              fillOpacity={0.1}
              isAnimationActive={false}
              activeDot={false}
            />
            {KEYS.map((k) => (
              <Line
                key={k}
                type="monotone"
                dataKey={k}
                name={tx(LABELS[k])}
                stroke={ink[k]}
                strokeWidth={2}
                strokeDasharray={k === "gross" ? "6 4" : undefined}
                strokeLinecap="round"
                strokeLinejoin="round"
                dot={false}
                activeDot={{ r: 3.5, fill: ink[k], stroke: t.tooltipBg, strokeWidth: 1.5 }}
                connectNulls={false}
                isAnimationActive={false}
              />
            ))}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </ChartCard>
  );
}
