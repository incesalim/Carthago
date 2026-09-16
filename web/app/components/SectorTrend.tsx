"use client";

import { useMemo, useState, type ReactNode } from "react";
import {
  CartesianGrid, Line, LineChart, ReferenceArea, ReferenceLine,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { ChartCard } from "@/app/components/ui/chart-card";
import { ChartData } from "@/app/components/ui/chart-csv";
import { type ChartAnnotation } from "@/app/components/chart-end-labels";
import { crosshairCursor, PLOT_MARGIN_LEFT, seriesColor, useChartTheme, Y_AXIS_WIDTH } from "@/app/lib/chart-theme";
import { type FormatKind } from "@/app/lib/chart-format";
import { wideToTable } from "@/app/lib/chart-csv";
import { useRangeFilter } from "@/app/lib/use-date-range";
import {
  pivotSectorTrend, sectorLatestValues, sectorSeriesCodes,
  sectorTrendScale, type SectorTrendPoint, type SectorTrendReference,
} from "@/app/lib/sector-trend";
import { useChartFormat } from "@/i18n/use-chart-format";
import { useText } from "@/i18n/use-text";
import styles from "./sector-trend.module.css";

export interface SectorTrendProps {
  data: SectorTrendPoint[];
  seriesLabels?: Record<string, string>;
  title?: ReactNode;
  description?: ReactNode;
  source?: ReactNode;
  yFormat?: FormatKind;
  decimals?: number;
  zeroLine?: boolean;
  height?: number;
  hero?: string;
  references?: SectorTrendReference[];
  deltaPeriods?: number;
  deltaLabel?: string;
  /** Preserve a pre-existing comparison's published-observation lookback. */
  deltaBasis?: "periods" | "published";
  deltaFromFullHistory?: boolean;
  /** Combined trends for direct comparisons; facets for individual group histories. */
  mode?: "trend" | "groups";
  plain?: boolean;
  annotations?: ChartAnnotation[];
  referencePeriod?: string;
  referenceLabel?: string;
}

const SANS = "var(--font-sans), ui-sans-serif, sans-serif";
const NO_LABELS: Record<string, string> = {};
const NO_REFERENCES: SectorTrendReference[] = [];

function EndPoint({ cx, cy, index, value, lastIndex, color, background, opacity = 1 }: {
  cx?: number; cy?: number; index?: number; value?: number | null;
  lastIndex: number; color: string; background: string; opacity?: number;
}) {
  const visible = index === lastIndex && typeof value === "number" && cx != null && cy != null;
  return <circle cx={cx} cy={cy} r={visible ? 3.5 : 0} fill={color} stroke={background}
    strokeWidth={visible ? 1.5 : 0} opacity={visible ? opacity : 0} />;
}

/** Sector charts pair readable histories with a current, precisely labelled comparison. */
export default function SectorTrend({
  data, seriesLabels = NO_LABELS, title, description, source,
  yFormat = "raw", decimals = 1, zeroLine = false, height, hero,
  references = NO_REFERENCES, deltaPeriods, deltaLabel, deltaBasis = "periods", deltaFromFullHistory = false, mode = "trend", plain = true,
  annotations, referencePeriod, referenceLabel,
}: SectorTrendProps) {
  const tx = useText();
  const theme = useChartTheme();
  const formatters = useChartFormat();
  const formatValue = (value: number) => formatters[yFormat](value, decimals);
  const { filtered } = useRangeFilter(data, (row) => row.period);
  const codes = useMemo(() => sectorSeriesCodes(data, seriesLabels), [data, seriesLabels]);
  const wide = useMemo(() => pivotSectorTrend(filtered, codes), [filtered, codes]);
  const latest = useMemo(() => {
    const current = sectorLatestValues(filtered, codes, deltaPeriods, deltaBasis);
    if (!deltaFromFullHistory) return current;
    const history = sectorLatestValues(data, codes, deltaPeriods, deltaBasis);
    return current.map((entry) => ({ ...entry, delta: history.find((row) => row.code === entry.code && row.period === entry.period)?.delta ?? null }));
  }, [filtered, codes, deltaPeriods, deltaBasis, deltaFromFullHistory, data]);
  const scale = useMemo(() => sectorTrendScale(filtered.map((row) => row.value), references, zeroLine), [filtered, references, zeroLine]);
  const heroCode = hero ?? codes.find((code) => seriesLabels[code] === "Sector") ?? null;
  const latestPeriod = wide.at(-1)?.period ?? null;
  const groups = mode === "groups" && codes.length > 1;
  const compact = !groups && codes.length <= 3;
  const [hovered, setHovered] = useState<string | null>(null);
  const [pinned, setPinned] = useState<string | null>(null);
  const selected = hovered ?? pinned;
  const name = (code: string) => tx(seriesLabels[code] ?? code);
  const color = (code: string) => seriesColor(theme, code, codes.indexOf(code), seriesLabels[code]);
  const toggle = (code: string) => setPinned((previous) => previous === code ? null : code);
  const finiteValues = latest.filter((entry) => entry.value != null);
  const railEntries = groups ? [...latest].sort((a, b) => {
    if (a.code === heroCode) return -1;
    if (b.code === heroCode) return 1;
    return (b.value ?? -Infinity) - (a.value ?? -Infinity);
  }) : latest;
  const lastIndexes = new Map(latest.map((entry) => [entry.code, wide.findIndex((row) => row.period === entry.period)]));
  const tickUnit = yFormat === "trn" ? 1_000_000 : yFormat === "bn" ? 1_000 : 1;
  const axisStep = scale.step / tickUnit;
  const tickDecimals = [0, 1, 2, 3, 4, 5, 6].find((places) => Math.abs(axisStep * 10 ** places - Math.round(axisStep * 10 ** places)) < 1e-8) ?? 6;
  const formatTick = (value: number) => formatters[yFormat](value, tickDecimals);
  const formatDelta = (value: number) => {
    const signed = `${value < 0 ? "−" : "+"}${formatters.raw(Math.abs(value), decimals)}`;
    return yFormat === "pct" || yFormat === "rate" ? tx("{0} pp", { 0: signed })
      : `${value < 0 ? "−" : "+"}${formatters[yFormat](Math.abs(value), decimals)}`;
  };
  const markerEvents = [
    ...(annotations ?? []),
    ...(referencePeriod ? [{ period: referencePeriod, label: referenceLabel }] : []),
  ].filter((event) => wide.length > 0 && event.period >= wide[0].period && event.period <= wide[wide.length - 1].period);

  const referenceMarks = (small: boolean) => <>
    {zeroLine && !references.some((reference) => reference.value === 0) && <ReferenceLine y={0} stroke={theme.reference} strokeDasharray="4 4" />}
    {references.filter((reference) => Number.isFinite(reference.value)).map((reference, i) => <ReferenceLine
      key={`ref-${i}`} y={reference.value} stroke={theme.warning} strokeDasharray="5 4" strokeWidth={1.5}
      label={{ value: formatValue(reference.value), position: "insideTopRight", fill: theme.inkMuted, fontSize: small ? 12 : 14, fontFamily: SANS }}
    />)}
    {markerEvents.flatMap((event, i) => {
      const start = wide.find((row) => row.period >= event.period)?.period;
      const end = event.endPeriod ? wide.find((row) => row.period >= event.endPeriod!)?.period ?? latestPeriod : null;
      return [
        ...(end ? [<ReferenceArea key={`event-area-${i}`} x1={start} x2={end} fill={theme.cursor} stroke="none" />] : []),
        <ReferenceLine key={`event-${i}`} x={start} stroke={theme.reference} strokeDasharray="4 4"
          label={!small && event.label ? { value: tx(event.label), position: "insideTopLeft", fill: theme.inkMuted, fontSize: 12, fontFamily: SANS } : undefined} />,
      ];
    })}
  </>;

  const plot = (visibleCodes: string[], small = false) => <ResponsiveContainer width="100%" height="100%" minWidth={0}>
    <LineChart data={wide} margin={{ top: references.length || markerEvents.length ? 24 : 14, right: 18, bottom: 8, left: PLOT_MARGIN_LEFT }} accessibilityLayer>
      <CartesianGrid vertical={false} stroke={theme.grid} />
      <XAxis dataKey="period" axisLine={false} tickLine={false} tickMargin={12}
        interval="preserveStartEnd" minTickGap={small ? 64 : 78}
        tick={{ fontFamily: SANS, fontSize: small ? 12 : 14, fill: theme.inkMuted }}
        tickFormatter={(period) => tx(String(period).slice(0, 7))} />
      <YAxis width={Y_AXIS_WIDTH} domain={scale.domain} ticks={scale.ticks} allowDataOverflow
        tickMargin={9} axisLine={false} tickLine={false}
        tick={{ fontFamily: SANS, fontSize: small ? 12 : 14, fill: theme.inkMuted }}
        tickFormatter={formatTick} />
      {referenceMarks(small)}
      <Tooltip cursor={crosshairCursor(theme)}
        content={({ active, label, payload }) => {
          if (!active || !payload?.length) return null;
          const entries = payload.filter((entry) => typeof entry.value === "number" && Number.isFinite(entry.value));
          return <div className={styles.tooltip}>
            <div className={styles.tooltipDate}>{tx(String(label ?? ""))}</div>
            {entries.map((entry) => <div key={String(entry.dataKey)} className={styles.tooltipRow}>
              <span className={styles.keyMark} style={{ background: entry.color }} />
              <span>{name(String(entry.dataKey))}</span><strong>{formatValue(Number(entry.value))}</strong>
            </div>)}
          </div>;
        }} />
      {small && heroCode && !visibleCodes.includes(heroCode) && <Line
        dataKey={heroCode} name={name(heroCode)} type="linear" stroke={theme.contextActive} strokeWidth={1.5}
        strokeOpacity={0.48} strokeDasharray="4 4" connectNulls={false} dot={false} activeDot={false} isAnimationActive={false} />}
      {visibleCodes.map((code) => {
        const opacity = selected && selected !== code ? 0.24 : 1;
        return <Line key={code} dataKey={code} name={name(code)} type="linear"
          stroke={color(code)} strokeWidth={code === heroCode || selected === code ? 3 : 2}
          strokeOpacity={opacity} strokeLinecap="round" strokeLinejoin="round"
          connectNulls={false} isAnimationActive={false} onClick={() => toggle(code)}
          dot={<EndPoint lastIndex={lastIndexes.get(code) ?? -1} color={color(code)} background={theme.tooltipBg} opacity={opacity} />}
          activeDot={{ r: 4, fill: color(code), stroke: theme.tooltipBg, strokeWidth: 2 }} />;
      })}
    </LineChart>
  </ResponsiveContainer>;

  return <ChartCard title={title} description={description} source={source} plain={plain}
    className={styles.card} bodyClassName={styles.body}>
    <ChartData table={wideToTable(wide, { key: "period", label: "Period" }, codes.map((code) => ({ key: code, label: seriesLabels[code] ?? code })))} />
    {references.length > 0 && <div className={styles.references}>
      {references.map((reference, i) => <span key={i}><i style={{ borderColor: theme.warning }} />{tx(reference.label)} <strong>{formatValue(reference.value)}</strong></span>)}
    </div>}
    {groups && heroCode && <p className={styles.comparisonNote}><i />{tx("Sector reference")} · {tx("Shared scale")}</p>}
    {finiteValues.length === 0 ? <p className={styles.empty}>{tx("No published observations in the selected period.")}</p> :
      <div className={styles.layout} data-sector-trend-mode={groups ? "groups" : "trend"} data-compact={compact || undefined}
        onKeyDown={(event) => { if (event.key === "Escape") { setPinned(null); setHovered(null); } }}>
        <div className={styles.histories}>
          {groups ? <div className={styles.facets}>
            {codes.map((code) => <section className={styles.facet} key={code} data-hero={code === heroCode || undefined}>
              <button className={styles.facetTitle} type="button" aria-pressed={pinned === code}
                onMouseEnter={() => setHovered(code)} onMouseLeave={() => setHovered(null)}
                onFocus={() => setHovered(code)} onBlur={() => setHovered(null)} onClick={() => toggle(code)}>
                <span className={styles.keyMark} style={{ background: color(code) }} />{name(code)}
              </button>
              <div className={styles.facetPlot} data-chart-plot="facet" style={{ height: "var(--sector-chart-height, 180px)" }}>{plot([code], true)}</div>
            </section>)}
          </div> : <div className={styles.plot} data-chart-plot="history" style={{ height: `var(--sector-chart-height, ${height ?? 320}px)` }}>{plot(codes)}</div>}
        </div>
        <aside className={styles.rail} aria-label={tx("Latest values")}>
          <div className={styles.railHeading}>
            <span>{tx("Latest values")}</span>
            <span>{latestPeriod ? tx(latestPeriod) : "—"}</span>
          </div>
          <div className={styles.entries}>
            {railEntries.map((entry) => <button key={entry.code} type="button" className={styles.entry}
              data-hero={entry.code === heroCode || undefined} data-muted={selected != null && selected !== entry.code || undefined}
              aria-pressed={pinned === entry.code} onClick={() => toggle(entry.code)}
              onMouseEnter={() => setHovered(entry.code)} onMouseLeave={() => setHovered(null)}
              onFocus={() => setHovered(entry.code)} onBlur={() => setHovered(null)}>
              <span className={styles.entryHeading}><span className={styles.keyMark} style={{ background: color(entry.code) }} />
                <span className={styles.entryName}>{name(entry.code)}</span>
                <strong className={styles.entryValue}>{entry.value == null ? "—" : formatValue(entry.value)}</strong>
              </span>
              {!compact && <span className={styles.dotTrack} aria-hidden="true">
                {references.map((reference, i) => <i className={styles.referenceTick} key={i}
                  style={{ left: `${(reference.value - scale.domain[0]) / (scale.domain[1] - scale.domain[0]) * 100}%`, borderColor: theme.warning }} />)}
                {entry.value != null && <i className={styles.dot} style={{ left: `${(entry.value - scale.domain[0]) / (scale.domain[1] - scale.domain[0]) * 100}%`, background: color(entry.code) }} />}
              </span>}
              {(deltaPeriods != null || (entry.period && entry.period !== latestPeriod)) && <span className={styles.entryNote}>
                {deltaPeriods != null && <span>{entry.delta == null ? "—" : formatDelta(entry.delta)}{deltaLabel ? ` · ${tx(deltaLabel)}` : ""}</span>}
                {entry.period && entry.period !== latestPeriod && <span>{tx(entry.period)}</span>}
              </span>}
            </button>)}
          </div>
          {!compact && <div className={styles.railScale} aria-hidden="true"><span>{formatTick(scale.domain[0])}</span><span>{formatTick(scale.domain[1])}</span></div>}
          {pinned && <button className={styles.reset} onClick={() => { setPinned(null); setHovered(null); }}>{tx("Reset selection")}</button>}
        </aside>
      </div>}
  </ChartCard>;
}
