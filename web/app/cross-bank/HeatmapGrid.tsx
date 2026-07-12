"use client";

/**
 * Cross-bank snapshot grid — banks (rows) × metrics (columns) at the record
 * quarter, scored against the peer frame the scorecard is using.
 *
 * This is the EVIDENCE layer: the scorecard above it carries the comparison, so
 * the grid's job is to let you check any bank against any metric, not to shout.
 * Hence:
 *   • one metric FAMILY at a time — all 21 columns at once meant 14 of them
 *     lived behind a horizontal scroll nobody drags;
 *   • the picks pinned to the top, above an ink rule, wearing their scorecard
 *     colour;
 *   • a much quieter colour ramp (see scoreToColor) — the value is always
 *     printed, so colour only sorts the eye.
 *
 * Scores are computed HERE, from the rows actually on screen, so the colour and
 * the rank can never describe a different population than the one displayed.
 */
import { Fragment, useMemo, useState } from "react";
import {
  METRIC_FAMILIES,
  type MetricDef,
  type MetricFamily,
  type MetricKey,
} from "@/app/lib/heatmap";
import {
  formatMetricValue,
  normalizeColumn,
  scoreToColor,
} from "@/app/lib/heatmap-normalize";
import BankTypeBadge from "@/app/components/BankTypeBadge";
import HeatmapLegend from "./HeatmapLegend";
import { PICK_COLORS, type BoardBank } from "./picks";

export interface HeatmapBankRow extends BoardBank {
  /** Raw values, aligned to the full METRIC_DEFS order. */
  raw: (number | null)[];
}

interface Props {
  metrics: MetricDef[];
  rows: HeatmapBankRow[];
  /** Tickers on the scorecard — pinned above the rule, in their pick colour. */
  picks: string[];
}

/** Good-direction arrow shown next to each column label. */
function directionArrow(dir: MetricDef["direction"]): string {
  if (dir === "higher_better") return "↑";
  if (dir === "higher_worse") return "↓";
  return "";
}

export default function HeatmapGrid({ metrics, rows, picks }: Props) {
  const [family, setFamily] = useState<MetricFamily>("Asset quality");
  const [sortMetric, setSortMetric] = useState<MetricKey | null>(null);

  const shown = useMemo(
    () => metrics.filter((m) => m.family === family),
    [metrics, family],
  );

  /** Per-column scores + ranks over the rows on screen (full metric order). */
  const { scores, ranks } = useMemo(() => {
    const s = metrics.map((m, ci) =>
      normalizeColumn(rows.map((r) => r.raw[ci]), m.direction),
    );
    const rk = s.map((col) => {
      const present = rows
        .map((r, i) => ({ t: r.ticker, v: col[i] }))
        .filter((e): e is { t: string; v: number } => e.v != null);
      const m = new Map<string, string>();
      for (const e of present) {
        const better = present.filter((o) => o.v > e.v + 1e-12).length;
        m.set(e.t, `${better + 1}/${present.length}`);
      }
      return m;
    });
    return { scores: s, ranks: rk };
  }, [metrics, rows]);

  /** Picks first (in pick order), then the rest — sorted by the clicked metric
   *  if there is one, otherwise left in the order the page supplied (group,
   *  then size). */
  const ordered = useMemo(() => {
    const pinned = picks
      .map((t) => rows.find((r) => r.ticker === t))
      .filter((r): r is HeatmapBankRow => r != null);
    let rest = rows.filter((r) => !picks.includes(r.ticker));
    if (sortMetric != null) {
      const ci = metrics.findIndex((m) => m.key === sortMetric);
      rest = [...rest].sort((a, b) => {
        const ia = rows.indexOf(a);
        const ib = rows.indexOf(b);
        const sa = scores[ci][ia];
        const sb = scores[ci][ib];
        if (sa == null && sb == null) return 0;
        if (sa == null) return 1;
        if (sb == null) return -1;
        return sb - sa;
      });
    }
    return { pinned, rest };
  }, [rows, picks, sortMetric, metrics, scores]);

  const toggleSort = (key: MetricKey) =>
    setSortMetric((cur) => (cur === key ? null : key));

  const renderRow = (row: HeatmapBankRow, pinIndex: number | null, last: boolean) => {
    const i = rows.indexOf(row);
    const pinned = pinIndex != null;
    return (
      <Fragment key={row.ticker}>
        <div
          className={`sticky left-0 z-10 flex items-center gap-2 bg-card px-3 py-1.5 ${
            last ? "border-b border-foreground" : "border-b border-hair"
          }`}
          style={
            pinned ? { boxShadow: `inset 3px 0 0 ${PICK_COLORS[pinIndex]}` } : undefined
          }
        >
          <div className="min-w-0">
            <div
              className={`truncate text-xs ${pinned ? "font-semibold" : "font-medium"} text-foreground`}
            >
              {row.name}
            </div>
            <div className="mt-0.5 flex items-center gap-1.5">
              <span className="font-mono text-[10px] tabular-nums text-faint">{row.ticker}</span>
              <BankTypeBadge code={row.groupCode} label={row.groupLabel} />
            </div>
          </div>
        </div>
        {shown.map((m) => {
          const ci = metrics.findIndex((x) => x.key === m.key);
          const raw = row.raw[ci];
          const score = scores[ci][i];
          const text = formatMetricValue(raw, m.unit, m.decimals);
          const rank = score != null ? ranks[ci].get(row.ticker) : null;
          return (
            <div
              key={m.key}
              title={`${row.name} · ${m.label}: ${text}${rank ? ` (rank ${rank})` : ""}`}
              style={{ background: scoreToColor(score, m.direction === "neutral") }}
              className={`flex items-center justify-end px-2 py-1.5 text-right font-mono text-[11.5px] tabular-nums text-foreground ${
                last ? "border-b border-foreground" : "border-b border-hair"
              }`}
            >
              {raw == null ? <span className="text-faint">—</span> : text}
            </div>
          );
        })}
      </Fragment>
    );
  };

  return (
    <div className="space-y-3">
      {/* metric family chooser */}
      <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1.5 border-b border-hair pb-1.5">
        {METRIC_FAMILIES.map((f) => {
          const n = metrics.filter((m) => m.family === f).length;
          if (!n) return null;
          return (
            <button
              key={f}
              type="button"
              onClick={() => {
                setFamily(f);
                setSortMetric(null);
              }}
              aria-pressed={family === f}
              className={`border-b-[1.5px] pb-0.5 font-mono text-[10.5px] transition-colors ${
                family === f
                  ? "border-foreground font-semibold text-foreground"
                  : "border-transparent text-muted-foreground hover:text-foreground"
              }`}
            >
              {f} <span className="text-faint">{n}</span>
            </button>
          );
        })}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
        <p className="text-[11px] text-muted-foreground">
          {sortMetric == null
            ? "Your picks are pinned to the top; the rest keep their type order. Click a metric to rank every bank by it."
            : "Ranked by the highlighted metric — click it again to restore the type order."}
        </p>
        <HeatmapLegend mode="both" />
      </div>

      <div className="overflow-auto">
        <div
          className="grid min-w-max"
          style={{
            gridTemplateColumns: `minmax(200px, 1.6fr) repeat(${shown.length}, minmax(84px, 1fr))`,
          }}
        >
          {/* header */}
          <div className="sticky left-0 top-0 z-30 border-b border-foreground bg-card px-3 py-2 font-mono text-[8.5px] font-semibold uppercase tracking-[0.07em] text-faint">
            Bank
          </div>
          {shown.map((m) => {
            const active = sortMetric === m.key;
            return (
              <button
                key={m.key}
                type="button"
                onClick={() => toggleSort(m.key)}
                title={`${m.rule}${
                  m.direction === "neutral" ? "" : ` · ${directionArrow(m.direction)} = better`
                }`}
                className={`sticky top-0 z-20 flex items-center justify-end gap-1 border-b border-foreground bg-card px-2 py-2 text-right font-mono text-[8.5px] font-semibold uppercase tracking-[0.07em] transition-colors ${
                  active ? "text-foreground" : "text-faint hover:text-foreground"
                }`}
              >
                <span className="truncate">{m.short}</span>
                <span className="text-faint">{directionArrow(m.direction)}</span>
                {active && <span aria-hidden>▾</span>}
              </button>
            );
          })}

          {ordered.pinned.map((row, i) =>
            renderRow(row, i, i === ordered.pinned.length - 1),
          )}
          {ordered.rest.map((row) => renderRow(row, null, false))}
        </div>
      </div>
    </div>
  );
}
