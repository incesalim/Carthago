"use client";

/**
 * Sector × quarter NPL-ratio heatmap — a purpose-built, self-contained grid that
 * reuses the cross-bank colour discipline (`normalizeColumn` + `scoreToColor`
 * from lib/heatmap-normalize) without the metric-selector machinery. Cells are
 * ranked over the WHOLE panel (higher NPL = worse = red), so deterioration reads
 * as a left→right green→red drift. The raw ratio is always printed in-cell, so
 * nothing depends on reading the colour (DESIGN.md rule 3: green/red = direction,
 * kept quiet — the ceilings live in scoreToColor).
 */
import { useMemo } from "react";
import { normalizeColumn, scoreToColor } from "@/app/lib/heatmap-normalize";
import type { HeatmapPayload } from "@/app/lib/loans-by-sector";

export default function SectorHeatmap({ rows, periods, cells }: HeatmapPayload) {
  const scoreByKey = useMemo(() => {
    const keys: string[] = [];
    const values: (number | null)[] = [];
    for (const r of rows) {
      for (const p of periods) {
        const k = `${r.key}|${p}`;
        keys.push(k);
        values.push(cells[k] ?? null);
      }
    }
    const scores = normalizeColumn(values, "higher_worse");
    const map = new Map<string, number | null>();
    keys.forEach((k, i) => map.set(k, scores[i]));
    return map;
  }, [rows, periods, cells]);

  const fmt = (v: number | null) => (v == null ? "—" : `${v.toFixed(1)}%`);

  return (
    <div className="space-y-2">
      <p className="text-[11px] text-muted-foreground">
        NPL ratio by sector, quarter-end. Each cell is ranked across the whole grid — green = lower,
        red = higher; the ratio is printed in-cell.
      </p>
      <div className="overflow-auto">
        <div
          className="grid min-w-max"
          style={{
            gridTemplateColumns: `minmax(180px, 1.6fr) repeat(${periods.length}, minmax(54px, 1fr))`,
          }}
        >
          <div className="sticky left-0 top-0 z-30 border-b border-foreground bg-card px-3 py-2 font-mono text-[8.5px] font-semibold uppercase tracking-[0.07em] text-faint">
            Sector
          </div>
          {periods.map((p) => (
            <div
              key={p}
              className="sticky top-0 z-20 border-b border-foreground bg-card px-2 py-2 text-right font-mono text-[8.5px] font-semibold uppercase tracking-[0.07em] tabular-nums text-faint"
            >
              {p}
            </div>
          ))}

          {rows.map((r) => (
            <div key={r.key} className="contents">
              <div className="sticky left-0 z-10 flex items-center border-b border-hair bg-card px-3 py-1.5">
                <span className="truncate text-xs font-medium text-foreground">{r.label}</span>
              </div>
              {periods.map((p) => {
                const key = `${r.key}|${p}`;
                const raw = cells[key] ?? null;
                const score = scoreByKey.get(key) ?? null;
                return (
                  <div
                    key={p}
                    title={`${r.label} · ${p}: ${fmt(raw)} NPL`}
                    style={{ background: scoreToColor(score, false) }}
                    className="flex items-center justify-end border-b border-hair px-1.5 py-1.5 text-right font-mono text-[11px] tabular-nums text-foreground"
                  >
                    {raw == null ? <span className="text-faint">—</span> : fmt(raw)}
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
