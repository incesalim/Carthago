"use client";

/**
 * Multi-series time-series line/area chart.
 * Designed for showing one metric over time, optionally split by bank type.
 *
 * At-rest legibility (redesign phase B): on wide plots every series carries a
 * direct end-of-line label (`Name 16.4%`) and the bottom legend is dropped;
 * hovering a label isolates its line, right-click pins. When a "Sector" series
 * is present (or `hero` is passed) the chart renders hero-vs-context: Sector
 * as the navy hero line, the other groups as thin grey — identity moves to the
 * labels. Below ~500px the legend returns and lines keep their series colours
 * (grey context without labels would lose identity on mobile).
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
import { NearestActiveDot, NearestSeriesTooltip } from "@/app/components/nearest-hover";
import {
  EndLabelLayer,
  estimateEndLabelWidth,
  lastPoint,
  renderAnnotations,
  type ChartAnnotation,
} from "@/app/components/chart-end-labels";
import {
  useChartTheme,
  seriesColor,
  crosshairCursor,
  PLOT_MARGIN_LEFT,
  Y_AXIS_WIDTH,
} from "@/app/lib/chart-theme";
import { wideToTable } from "@/app/lib/chart-csv";
import { formatters, type FormatKind } from "@/app/lib/chart-format";
import { useRangeFilter } from "@/app/lib/use-date-range";

export interface TrendPoint {
  period: string;
  bank_type_code: string;
  value: number | null;
}

export type { ChartAnnotation };

interface Props {
  /** Long-form rows {period, bank_type_code, value}. */
  data: TrendPoint[];
  /** Map of bank_type_code → label shown in legend. */
  seriesLabels: Record<string, string>;
  /** Card headline — a finding sentence on lead charts (chart-findings.ts). */
  title?: string;
  /** Card subtitle — the metric, units, period (when title is a finding). */
  description?: React.ReactNode;
  /** Mono source footer, e.g. "Source: BDDK monthly bulletin". */
  source?: React.ReactNode;
  /** Render on the sheet without card chrome (Desk evidence layer). */
  plain?: boolean;
  yFormat?: FormatKind;
  decimals?: number;
  /** Show a horizontal line at y=0 (useful for growth rates). */
  zeroLine?: boolean;
  height?: number;
  /**
   * Series code to emphasise as the hero line (navy) with the rest as grey
   * context. Defaults to the series labelled "Sector" when one exists.
   */
  hero?: string;
  /** On-chart annotations (dashed line + optional band + mono note). */
  annotations?: ChartAnnotation[];
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
  description,
  source,
  plain = false,
  yFormat = "raw",
  decimals = 2,
  zeroLine = false,
  height = 320,
  hero,
  annotations,
}: Props) {
  const t = useChartTheme();
  // Hovering an end-label (or legend item on narrow plots) emphasises that
  // line and fades the rest; right-clicking pins the isolation.
  const [hovered, setHovered] = useState<string | null>(null);
  const [pinned, setPinned] = useState<string | null>(null);
  const active = hovered ?? pinned;

  // Direct end-labels on wide plots; narrow plots fall back to the legend.
  // Hysteresis (520 on / 490 off) so a border-straddling width doesn't flap.
  const [labelsOn, setLabelsOn] = useState(true);
  const handleResize = (w: number) => {
    if (w >= 520) setLabelsOn(true);
    else if (w < 490) setLabelsOn(false);
  };

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

  // Hero-vs-context applies only with end-labels on (grey lines without
  // labels would leave the mobile legend with five identical swatches).
  const heroKey =
    hero ?? codes.find((c) => seriesLabels[c] === "Sector") ?? null;
  const heroMode = labelsOn && heroKey != null && codes.length > 1;

  const lineColor = (code: string, i: number): string =>
    heroMode
      ? code === heroKey
        ? t.hero
        : active === code
          ? t.contextActive
          : t.context
      : seriesColor(t, code, i);

  // Label-name ink: hero navy / muted for context / the series colour.
  const labelInk = (code: string): string =>
    heroMode
      ? code === heroKey
        ? t.hero
        : active === code
          ? t.contextActive
          : t.inkMuted
      : seriesColor(t, code, codes.indexOf(code));

  const valueOnly = codes.length === 1;
  const labelWidth = estimateEndLabelWidth(
    codes
      .map((c) => {
        const lp = lastPoint(wide, "period", c);
        return lp
          ? { name: seriesLabels[c], value: fmt(lp.value, decimals) }
          : null;
      })
      .filter((e): e is { name: string; value: string } => e != null),
    valueOnly,
  );

  return (
    <ChartCard title={title} description={description} source={source} plain={plain}>
      <ChartData
        table={wideToTable(
          wide,
          { key: "period", label: "Period" },
          codes.map((c) => ({ key: c, label: seriesLabels[c] })),
        )}
      />
      {/* Right-click is a pin/unpin gesture here — keep the browser menu out. */}
      <div style={{ height }} onContextMenu={(e) => e.preventDefault()}>
        <ResponsiveContainer width="100%" height="100%" onResize={handleResize}>
          <ComposedChart
            data={wide}
            margin={{
              top: 10,
              right: labelsOn ? labelWidth : 20,
              left: PLOT_MARGIN_LEFT,
              bottom: labelsOn ? 8 : 30,
            }}
          >
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
              width={Y_AXIS_WIDTH}
              tick={{ fontSize: 11, fill: t.axis, fontFamily: "var(--font-geist-mono), monospace" }}
              tickFormatter={(v) => fmt(v, 0)}
              axisLine={false}
              tickLine={false}
            />
            {zeroLine && <ReferenceLine y={0} stroke={t.reference} strokeDasharray="3 3" />}
            {renderAnnotations(annotations, wide, "period", t)}
            {/* Nearest-series tooltip: one group's point, not the whole date
                column (see nearest-hover.tsx on why `shared` can't do this). */}
            <Tooltip
              cursor={crosshairCursor(t)}
              content={(p) => (
                <NearestSeriesTooltip
                  active={p.active}
                  payload={p.payload}
                  label={p.label}
                  coordinate={p.coordinate}
                  formatValue={(v) => fmt(v, decimals)}
                />
              )}
            />
            {!labelsOn && (
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
            )}
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
                        activeDot={false}
                        isAnimationActive={false}
                      />
                    </>
                  );
                })()
              : codes.map((code, i) => {
                  const color = lineColor(code, i);
                  const opacity = active && active !== code ? 0.18 : 1;
                  const width = heroMode
                    ? code === heroKey
                      ? 2.5
                      : active === code
                        ? 2.25
                        : 1.75
                    : (seriesLabels[code] === "Sector" ? 2.5 : 2) +
                      (active === code ? 0.75 : 0);
                  return (
                    <Line
                      key={code}
                      type="monotone"
                      dataKey={code}
                      name={seriesLabels[code]}
                      stroke={color}
                      strokeWidth={width}
                      strokeOpacity={opacity}
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      dot={<EndDot color={color} bg={t.tooltipBg} lastIndex={lastIdx} dim={opacity} />}
                      activeDot={false}
                      isAnimationActive={false}
                    />
                  );
                })}
            {labelsOn && (
              <EndLabelLayer
                rows={wide}
                periodKey="period"
                keys={codes}
                labelFor={(c) => seriesLabels[c]}
                colorFor={labelInk}
                lineColorFor={(c) => lineColor(c, codes.indexOf(c))}
                formatValue={(v) => fmt(v, decimals)}
                heroKey={heroMode ? heroKey : null}
                active={active}
                pinned={pinned}
                onHover={setHovered}
                onPinToggle={(c) => setPinned((p) => (p === c ? null : c))}
                valueOnly={valueOnly}
              />
            )}
            {/* Single hover point on the nearest line. */}
            <NearestActiveDot
              rows={wide}
              periodKey="period"
              keys={codes}
              colorFor={(k) => lineColor(k, codes.indexOf(k))}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </ChartCard>
  );
}
