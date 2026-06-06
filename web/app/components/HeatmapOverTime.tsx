"use client";

/**
 * Cross-bank over-time heatmap — banks (rows) × quarters (columns) for ONE
 * selected metric. Cells are colored from a single normalizeColumn over the
 * whole bank×period panel, so the color scale is comparable across quarters
 * (spots deterioration as a left-to-right green→red gradient). The raw value
 * shows on hover; the selected period's value renders in-cell.
 */
import { useMemo, useState } from "react";
import type { MetricDef, MetricKey } from "@/app/lib/heatmap";
import {
  normalizeColumn,
  scoreToColor,
  formatMetricValue,
} from "@/app/lib/heatmap-normalize";
import BankTypeBadge from "@/app/components/BankTypeBadge";

export interface HeatmapTimeRow {
  ticker: string;
  name: string;
  groupCode: string;
  groupLabel: string;
}

/** One (bank, period) panel cell with raw values aligned to METRIC_DEFS. */
export interface PanelCell {
  ticker: string;
  period: string;
  raw: (number | null)[];
}

interface Props {
  metrics: MetricDef[];
  banks: HeatmapTimeRow[];
  /** Quarters ascending, e.g. ["2022Q1", …, "2026Q1"]. */
  periods: string[];
  panel: PanelCell[];
}

/** "2025Q4" → "Q4 ’25" compact column label. */
function shortPeriod(p: string): string {
  const m = /^(\d{4})Q([1-4])$/.exec(p);
  if (!m) return p;
  return `Q${m[2]} ’${m[1].slice(2)}`;
}

export default function HeatmapOverTime({ metrics, banks, periods, panel }: Props) {
  const [metricKey, setMetricKey] = useState<MetricKey>("npl_ratio");
  const metric = metrics.find((m) => m.key === metricKey) ?? metrics[0];
  const ci = metrics.findIndex((m) => m.key === metric.key);

  // Raw value + 0..1 score per (ticker|period), scored across the whole panel.
  const { rawByKey, scoreByKey } = useMemo(() => {
    const values = panel.map((c) => c.raw[ci]);
    const scores = normalizeColumn(values, metric.direction);
    const rawMap = new Map<string, number | null>();
    const scoreMap = new Map<string, number | null>();
    panel.forEach((c, i) => {
      const key = `${c.ticker}|${c.period}`;
      rawMap.set(key, c.raw[ci]);
      scoreMap.set(key, scores[i]);
    });
    return { rawByKey: rawMap, scoreByKey: scoreMap };
  }, [panel, ci, metric.direction]);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <label htmlFor="heatmap-metric" className="text-xs font-medium text-muted-foreground">
          Metric
        </label>
        <select
          id="heatmap-metric"
          value={metricKey}
          onChange={(e) => setMetricKey(e.target.value as MetricKey)}
          className="rounded-md border border-border bg-card px-2 py-1 text-xs text-foreground"
        >
          {metrics.map((m) => (
            <option key={m.key} value={m.key}>
              {m.label}
            </option>
          ))}
        </select>
        <span className="text-[11px] text-muted-foreground">
          Color compares each cell against the whole panel — darker = more extreme.
        </span>
      </div>

      <div className="overflow-auto rounded-lg border border-border bg-card">
        <div
          className="grid min-w-max"
          style={{
            gridTemplateColumns: `minmax(200px, 1.6fr) repeat(${periods.length}, minmax(60px, 1fr))`,
          }}
        >
          {/* Header */}
          <div className="sticky left-0 top-0 z-30 border-b border-border bg-muted px-3 py-2 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
            Bank
          </div>
          {periods.map((p) => (
            <div
              key={p}
              className="sticky top-0 z-20 border-b border-l border-border bg-muted px-2 py-2 text-right text-[11px] font-medium tabular-nums text-muted-foreground"
            >
              {shortPeriod(p)}
            </div>
          ))}

          {/* Rows */}
          {banks.map((bank) => (
            <div key={bank.ticker} className="contents">
              <div className="sticky left-0 z-10 flex items-center justify-between gap-2 border-b border-border bg-card px-3 py-1.5">
                <div className="min-w-0">
                  <div className="truncate text-xs font-medium text-foreground">{bank.name}</div>
                  <div className="mt-0.5 flex items-center gap-1.5">
                    <span className="text-[10px] tabular-nums text-muted-foreground">{bank.ticker}</span>
                    <BankTypeBadge code={bank.groupCode} label={bank.groupLabel} />
                  </div>
                </div>
              </div>
              {periods.map((p) => {
                const key = `${bank.ticker}|${p}`;
                const raw = rawByKey.get(key) ?? null;
                const score = scoreByKey.get(key) ?? null;
                const text = formatMetricValue(raw, metric.unit, metric.decimals);
                return (
                  <div
                    key={p}
                    title={`${bank.name} · ${metric.label} · ${shortPeriod(p)}: ${text}`}
                    style={{ background: scoreToColor(score, metric.direction === "neutral") }}
                    className="flex items-center justify-end border-b border-l border-border px-1.5 py-1.5 text-right text-[11px] tabular-nums text-foreground"
                  >
                    {text}
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
