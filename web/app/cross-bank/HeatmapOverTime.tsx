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
import HeatmapLegend from "./HeatmapLegend";

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

// How the color rank is computed — the same raw values, ranked over a
// different population. "panel" ranks every bank-quarter together (good for
// "who is worst overall"); "bank" ranks each bank against its OWN history so a
// single bank's trajectory uses the full ramp (good for spotting that bank
// deteriorating); "period" ranks banks within each quarter (a clean
// cross-section per column).
type ScaleMode = "panel" | "bank" | "period";

const SCALE_LABELS: Record<ScaleMode, string> = {
  panel: "Whole panel",
  bank: "Per bank",
  period: "Per quarter",
};

export default function HeatmapOverTime({ metrics, banks, periods, panel }: Props) {
  const [metricKey, setMetricKey] = useState<MetricKey>("npl_ratio");
  const [scaleMode, setScaleMode] = useState<ScaleMode>("panel");
  const metric = metrics.find((m) => m.key === metricKey) ?? metrics[0];
  const ci = metrics.findIndex((m) => m.key === metric.key);

  // Raw value + 0..1 score per (ticker|period). The score's population depends
  // on scaleMode: the whole panel, or per-bank / per-quarter groups normalized
  // independently so each group spans the full color range.
  const { rawByKey, scoreByKey } = useMemo(() => {
    const rawMap = new Map<string, number | null>();
    const scoreMap = new Map<string, number | null>();
    panel.forEach((c) => rawMap.set(`${c.ticker}|${c.period}`, c.raw[ci]));

    if (scaleMode === "panel") {
      const scores = normalizeColumn(panel.map((c) => c.raw[ci]), metric.direction);
      panel.forEach((c, i) => scoreMap.set(`${c.ticker}|${c.period}`, scores[i]));
    } else {
      const groups = new Map<string, PanelCell[]>();
      for (const c of panel) {
        const g = scaleMode === "bank" ? c.ticker : c.period;
        (groups.get(g) ?? groups.set(g, []).get(g)!).push(c);
      }
      for (const cells of groups.values()) {
        const scores = normalizeColumn(cells.map((c) => c.raw[ci]), metric.direction);
        cells.forEach((c, i) => scoreMap.set(`${c.ticker}|${c.period}`, scores[i]));
      }
    }
    return { rawByKey: rawMap, scoreByKey: scoreMap };
  }, [panel, ci, metric.direction, scaleMode]);

  const dirWord =
    metric.direction === "neutral" ? "higher = darker" : "green = better, red = worse";
  const caption = {
    panel: `Each cell ranked against every bank-quarter — ${dirWord}.`,
    bank: `Each bank ranked against its own history — ${dirWord}.`,
    period: `Banks ranked within each quarter — ${dirWord}.`,
  }[scaleMode];

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
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

        <span className="mx-1 hidden h-5 w-px bg-border sm:block" />

        <span className="text-xs font-medium text-muted-foreground">Color scale</span>
        <div className="inline-flex items-center gap-0.5 rounded-lg border border-border bg-card p-0.5">
          {(["panel", "bank", "period"] as ScaleMode[]).map((mode) => (
            <button
              key={mode}
              type="button"
              onClick={() => setScaleMode(mode)}
              aria-pressed={scaleMode === mode}
              className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                scaleMode === mode
                  ? "bg-primary/10 font-semibold text-primary"
                  : "text-muted-foreground hover:bg-accent/60 hover:text-foreground"
              }`}
            >
              {SCALE_LABELS[mode]}
            </button>
          ))}
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
        <span className="text-[11px] text-muted-foreground">{caption}</span>
        <HeatmapLegend mode={metric.direction === "neutral" ? "neutral" : "directional"} />
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
