"use client";

/**
 * Cross-bank snapshot heatmap — banks (rows) × metrics (columns) at one
 * quarter. Each cell is colored by the bank's rank-vs-peers on that metric
 * (green = better, red = worse, --info ramp for neutral size metrics); the raw
 * value is shown in-cell and in the hover title. Scores are precomputed
 * server-side (see cross-bank/page.tsx) and passed in.
 *
 * Two arrangements via a header click:
 *   • default — grouped by BDDK type (same order as /banks, no section
 *     bands — the per-row badge labels the type), banks size-ranked by
 *     total assets within each group.
 *   • sorted  — click a metric header to rank every bank by that column.
 */
import { Fragment, useMemo, useState } from "react";
import type { MetricDef, MetricKey } from "@/app/lib/heatmap";
import { scoreToColor, formatMetricValue } from "@/app/lib/heatmap-normalize";
import BankTypeBadge from "@/app/components/BankTypeBadge";
import HeatmapLegend from "@/app/components/HeatmapLegend";

export interface HeatmapBankRow {
  ticker: string;
  name: string;
  groupCode: string;
  groupLabel: string;
  /** Raw values, aligned to METRIC_DEFS order. */
  raw: (number | null)[];
  /** 0..1 rank scores, aligned to METRIC_DEFS order (null = no data). */
  scores: (number | null)[];
}

interface Props {
  metrics: MetricDef[];
  rows: HeatmapBankRow[];
  period: string;
  groupOrder?: string[];
}

const DEFAULT_GROUP_ORDER = ["10006", "10005", "10007", "10003", "10004"];

/** Good-direction arrow shown next to each column label. */
function directionArrow(dir: MetricDef["direction"]): string {
  if (dir === "higher_better") return "↑";
  if (dir === "higher_worse") return "↓";
  return "";
}

export default function HeatmapGrid({ metrics, rows, groupOrder }: Props) {
  const [sortMetric, setSortMetric] = useState<MetricKey | null>(null);
  const order = groupOrder ?? DEFAULT_GROUP_ORDER;
  const assetIdx = metrics.findIndex((m) => m.key === "total_assets");

  // Per-column "rank N/total" over the non-null scores (best = 1), keyed by
  // ticker so it's independent of render order.
  const ranks = useMemo(
    () =>
      metrics.map((_, ci) => {
        const present = rows
          .map((r) => ({ t: r.ticker, s: r.scores[ci] }))
          .filter((e): e is { t: string; s: number } => e.s != null);
        const total = present.length;
        const byScore = [...present].sort((a, b) => b.s - a.s);
        const m = new Map<string, string>();
        byScore.forEach((e, i) => m.set(e.t, `${i + 1}/${total}`));
        return m;
      }),
    [metrics, rows],
  );

  // Grouped arrangement: bucket by type, sort each bucket by total assets desc.
  const grouped = useMemo(() => {
    const byCode = new Map<string, HeatmapBankRow[]>();
    for (const r of rows) {
      const arr = byCode.get(r.groupCode) ?? [];
      arr.push(r);
      byCode.set(r.groupCode, arr);
    }
    for (const arr of byCode.values())
      arr.sort((a, b) => (b.raw[assetIdx] ?? -1) - (a.raw[assetIdx] ?? -1));
    const codes = [
      ...order.filter((c) => byCode.has(c)),
      ...[...byCode.keys()].filter((c) => !order.includes(c)),
    ];
    return codes.map((code) => {
      const banks = byCode.get(code)!;
      return { code, label: banks[0].groupLabel, banks };
    });
  }, [rows, order, assetIdx]);

  // Sorted arrangement: every bank by the clicked metric's score, nulls last.
  const sortedRows = useMemo(() => {
    if (sortMetric == null) return [];
    const ci = metrics.findIndex((m) => m.key === sortMetric);
    return [...rows].sort((a, b) => {
      const sa = a.scores[ci];
      const sb = b.scores[ci];
      if (sa == null && sb == null) return 0;
      if (sa == null) return 1;
      if (sb == null) return -1;
      return sb - sa;
    });
  }, [rows, metrics, sortMetric]);

  const toggleSort = (key: MetricKey) =>
    setSortMetric((cur) => (cur === key ? null : key));

  const renderRow = (row: HeatmapBankRow) => (
    <Fragment key={row.ticker}>
      <div className="sticky left-0 z-10 flex items-center justify-between gap-2 border-b border-border bg-card px-3 py-1.5">
        <div className="min-w-0">
          <div className="truncate text-xs font-medium text-foreground">{row.name}</div>
          <div className="mt-0.5 flex items-center gap-1.5">
            <span className="text-[10px] tabular-nums text-muted-foreground">{row.ticker}</span>
            <BankTypeBadge code={row.groupCode} label={row.groupLabel} />
          </div>
        </div>
      </div>
      {metrics.map((m, ci) => {
        const raw = row.raw[ci];
        const score = row.scores[ci];
        const text = formatMetricValue(raw, m.unit, m.decimals);
        const rank = score != null ? ranks[ci].get(row.ticker) : null;
        return (
          <div
            key={m.key}
            title={`${row.name} · ${m.label}: ${text}${rank ? ` (rank ${rank})` : ""}`}
            style={{ background: scoreToColor(score, m.direction === "neutral") }}
            className="flex items-center justify-end border-b border-l border-border px-2 py-1.5 text-right text-xs tabular-nums text-foreground"
          >
            {text}
          </div>
        );
      })}
    </Fragment>
  );

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
        <p className="text-[11px] text-muted-foreground">
          {sortMetric == null
            ? "Grouped by bank type, sized by assets · click a metric to rank every bank by it"
            : "Ranked by the highlighted metric · click it again to regroup by type"}
        </p>
        <HeatmapLegend mode="both" />
      </div>
      <div className="overflow-auto rounded-lg border border-border bg-card">
      <div
        className="grid min-w-max"
        style={{
          gridTemplateColumns: `minmax(200px, 1.6fr) repeat(${metrics.length}, minmax(76px, 1fr))`,
        }}
      >
        {/* Header */}
        <div className="sticky left-0 top-0 z-30 border-b border-border bg-muted px-3 py-2 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
          Bank
        </div>
        {metrics.map((m) => {
          const active = sortMetric === m.key;
          return (
            <button
              key={m.key}
              type="button"
              onClick={() => toggleSort(m.key)}
              title={`Sort by ${m.label}${
                m.direction === "neutral" ? "" : ` (${directionArrow(m.direction)} = better)`
              }`}
              className={`sticky top-0 z-20 flex items-center justify-end gap-1 border-b border-l border-border px-2 py-2 text-right text-[11px] font-semibold uppercase tracking-wide transition-colors ${
                active ? "bg-accent text-foreground" : "bg-muted text-muted-foreground hover:text-foreground"
              }`}
            >
              <span className="truncate">{m.short}</span>
              <span className="text-muted-foreground/70">{directionArrow(m.direction)}</span>
              {active && <span aria-hidden>▾</span>}
            </button>
          );
        })}

        {/* Body — grouped order keeps the type buckets, no section bands
            (the per-row type badge already labels each bank). */}
        {(sortMetric == null ? grouped.flatMap((g) => g.banks) : sortedRows).map(
          renderRow,
        )}
      </div>
      </div>
    </div>
  );
}
