"use client";

/**
 * Multi-series line chart for irregular time-series (e.g. EVDS daily series
 * with non-bank-code identification). Simpler than TrendChart since we
 * don't need bank-type pivot.
 *
 * At-rest legibility (redesign phase B): wide plots carry direct end-of-line
 * labels and drop the bottom legend; hover a label to isolate, right-click to
 * pin. Lines keep their series colours by default — these series have no
 * natural aggregate — but a `hero` prop can single one out as the navy hero
 * over grey context. Narrow plots keep the legend.
 */
import { useState } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
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
import { useChartTheme, seriesColor, crosshairCursor } from "@/app/lib/chart-theme";
import { wideToTable } from "@/app/lib/chart-csv";
import { formatters, fmtQuarter, type FormatKind } from "@/app/lib/chart-format";
import { useRangeFilter } from "@/app/lib/use-date-range";

interface Point {
  period_date: string;
  value: number;
}

interface Props {
  /** Map of seriesLabel → array of {period_date, value}. */
  series: Record<string, Point[]>;
  /** Card headline — a finding sentence on lead charts (chart-findings.ts). */
  title?: string;
  /** Card subtitle — the metric, units, period (when title is a finding). */
  description?: React.ReactNode;
  /** Mono source footer, e.g. "Source: TCMB EVDS". */
  source?: React.ReactNode;
  yFormat?: Extract<FormatKind, "pct" | "rate" | "raw" | "fx">;
  /** x-axis tick/tooltip label style. "date" → YYYY-MM (default), "quarter" → YYYY-Qn. */
  xFormat?: "date" | "quarter";
  decimals?: number;
  height?: number;
  /** Series label to emphasise as the navy hero over grey context (opt-in —
   *  economy series have no natural aggregate, unlike bank groups). */
  hero?: string;
  /** On-chart annotations (dashed line + optional band + mono note). */
  annotations?: ChartAnnotation[];
  /** Render the plot WITHOUT the ChartCard chrome — for composed cards that
   *  already provide a surface/heading (no export pills in this mode). */
  bare?: boolean;
}

export default function TimeSeriesChart({
  series,
  title,
  description,
  source,
  yFormat = "raw",
  xFormat = "date",
  decimals = 2,
  height = 320,
  hero,
  annotations,
  bare = false,
}: Props) {
  const t = useChartTheme();
  const fmt = formatters[yFormat];

  // Window to the dashboard's global date range. Series are per-label arrays,
  // so we apply the shared predicate to each one during the pivot below.
  const { predicate } = useRangeFilter(
    Object.values(series).flat(),
    (p) => p.period_date,
  );
  // x-axis ticks are always YYYY-MM (or the quarter); the tooltip label is
  // resolved below once we can inspect the data's cadence.
  const isQuarter = xFormat === "quarter";
  const fmtTick = isQuarter ? fmtQuarter : (v: string) => v.slice(0, 7);
  const labels = Object.keys(series);
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

  // Pivot all series into a wide structure { period_date, label1: v, label2: v }
  const byDate = new Map<string, Record<string, number | string>>();
  for (const label of labels) {
    for (const p of series[label]) {
      if (!predicate(p.period_date)) continue;
      if (!byDate.has(p.period_date)) {
        byDate.set(p.period_date, { period_date: p.period_date });
      }
      byDate.get(p.period_date)![label] = p.value;
    }
  }
  const data = Array.from(byDate.values()).sort((a, b) =>
    String(a.period_date).localeCompare(String(b.period_date)),
  );

  // Tooltip label: quarters in "quarter" mode; otherwise the full date for a
  // genuinely daily series (FX, share price), but collapsed to YYYY-MM when
  // every point sits on a month-start — the "-01" day is redundant noise on
  // monthly/quarterly series.
  const allMonthStart =
    data.length > 0 &&
    data.every((d) => String(d.period_date).slice(8, 10) === "01");
  const fmtLabel = isQuarter
    ? fmtQuarter
    : allMonthStart
      ? (v: string) => v.slice(0, 7)
      : (v: string) => v;

  // Hero-vs-context is opt-in here (no auto "Sector" — see header comment) and
  // only with end-labels on, so the mobile legend keeps distinct colours.
  const heroMode = labelsOn && hero != null && labels.length > 1;

  const lineColor = (label: string, i: number): string =>
    heroMode
      ? label === hero
        ? t.hero
        : active === label
          ? t.contextActive
          : t.context
      : seriesColor(t, label, i);

  const labelInk = (label: string): string =>
    heroMode
      ? label === hero
        ? t.hero
        : active === label
          ? t.contextActive
          : t.inkMuted
      : seriesColor(t, label, labels.indexOf(label));

  const valueOnly = labels.length === 1;
  const labelWidth = estimateEndLabelWidth(
    labels
      .map((l) => {
        const lp = lastPoint(data, "period_date", l);
        return lp ? { name: l, value: fmt(lp.value, decimals) } : null;
      })
      .filter((e): e is { name: string; value: string } => e != null),
    valueOnly,
  );

  const body = (
    <>
      <ChartData
        table={wideToTable(
          data,
          { key: "period_date", label: "Date" },
          labels.map((l) => ({ key: l, label: l })),
        )}
      />
      {/* Right-click is a pin/unpin gesture here — keep the browser menu out. */}
      <div style={{ height }} onContextMenu={(e) => e.preventDefault()}>
        <ResponsiveContainer width="100%" height="100%" onResize={handleResize}>
          <LineChart
            data={data}
            margin={{
              top: 10,
              right: labelsOn ? labelWidth : 20,
              left: 60,
              bottom: labelsOn ? 8 : 30,
            }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke={t.grid} />
            <XAxis
              dataKey="period_date"
              tick={{ fontSize: 11, fill: t.axis }}
              minTickGap={40}
              tickFormatter={(v) => fmtTick(String(v))}
              axisLine={{ stroke: t.grid }}
              tickLine={{ stroke: t.grid }}
            />
            <YAxis
              tick={{ fontSize: 11, fill: t.axis }}
              tickFormatter={(v) => fmt(v, 0)}
              axisLine={{ stroke: t.grid }}
              tickLine={{ stroke: t.grid }}
            />
            {renderAnnotations(annotations, data, "period_date", t)}
            {/* Nearest-series tooltip: one line's point, not every series at the
                hovered date (see nearest-hover.tsx on why `shared` can't do this). */}
            <Tooltip
              cursor={crosshairCursor(t)}
              content={(p) => (
                <NearestSeriesTooltip
                  active={p.active}
                  payload={p.payload}
                  label={p.label}
                  coordinate={p.coordinate}
                  formatValue={(v) => fmt(v, decimals)}
                  formatLabel={(l) => fmtLabel(String(l))}
                />
              )}
            />
            {!labelsOn && (
              <Legend
                wrapperStyle={{ fontSize: 11 }}
                content={({ payload }) => (
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
                    {(payload ?? []).map((it) => {
                      const label = String(it.dataKey);
                      return (
                        <li
                          key={label}
                          onMouseEnter={() => setHovered(label)}
                          onMouseLeave={() => setHovered(null)}
                          onContextMenu={(e) => {
                            e.preventDefault();
                            setPinned((p) => (p === label ? null : label));
                          }}
                          style={{
                            display: "inline-flex",
                            alignItems: "center",
                            gap: 5,
                            color: t.axis,
                            opacity: active && active !== label ? 0.4 : 1,
                            fontWeight: pinned === label ? 600 : 400,
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
                )}
              />
            )}
            {labels.map((label, i) => (
              <Line
                key={label}
                type="monotone"
                dataKey={label}
                name={label}
                stroke={lineColor(label, i)}
                strokeWidth={
                  heroMode
                    ? label === hero
                      ? 2.5
                      : active === label
                        ? 2.25
                        : 1.75
                    : active === label
                      ? 2.75
                      : 1.75
                }
                strokeOpacity={active && active !== label ? 0.18 : 1}
                dot={false}
                activeDot={false}
                connectNulls
                isAnimationActive={false}
              />
            ))}
            {labelsOn && (
              <EndLabelLayer
                rows={data}
                periodKey="period_date"
                keys={labels}
                labelFor={(l) => l}
                colorFor={labelInk}
                lineColorFor={(l) => lineColor(l, labels.indexOf(l))}
                formatValue={(v) => fmt(v, decimals)}
                heroKey={heroMode ? hero : null}
                active={active}
                pinned={pinned}
                onHover={setHovered}
                onPinToggle={(l) => setPinned((p) => (p === l ? null : l))}
                valueOnly={valueOnly}
              />
            )}
            {/* Single hover point on the nearest line. */}
            <NearestActiveDot
              rows={data}
              periodKey="period_date"
              keys={labels}
              colorFor={(k) => lineColor(k, labels.indexOf(k))}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </>
  );

  if (bare) return body;
  return (
    <ChartCard title={title} description={description} source={source}>
      {body}
    </ChartCard>
  );
}
