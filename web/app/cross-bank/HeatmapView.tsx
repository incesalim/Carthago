"use client";

/**
 * Cross-bank heatmap shell: toggles between the Snapshot grid (banks × metrics
 * at the record quarter) and the Over-time grid (banks × quarters for one
 * metric). Both are scoped to the peer frame chosen upstairs on the scorecard —
 * a grid that ranked a different population than the strips above it would be
 * two answers to the same question.
 */
import { useMemo, useState } from "react";
import type { MetricDef } from "@/app/lib/heatmap";
import type { BoardBank } from "./picks";
import HeatmapGrid from "./HeatmapGrid";
import HeatmapOverTime, { type PanelCell } from "./HeatmapOverTime";

interface Props {
  metrics: MetricDef[];
  /** The framed banks, in display order. */
  banks: BoardBank[];
  periods: string[];
  /** The FULL panel — filtered to the frame here. */
  panel: PanelCell[];
  period: string;
  /** Tickers picked on the scorecard — pinned to the top of the grid. */
  picks: string[];
  frameLabel: string;
}

type ViewKind = "snapshot" | "time";

export default function HeatmapView({
  metrics,
  banks,
  periods,
  panel,
  period,
  picks,
  frameLabel,
}: Props) {
  const [view, setView] = useState<ViewKind>("snapshot");

  const inFrame = useMemo(() => new Set(banks.map((b) => b.ticker)), [banks]);
  const framedPanel = useMemo(
    () => panel.filter((c) => inFrame.has(c.ticker)),
    [panel, inFrame],
  );

  /** Snapshot rows at the record quarter, raw values only — the grid scores
   *  them itself so the population is always exactly what is on screen. */
  const rows = useMemo(() => {
    const raw = new Map<string, (number | null)[]>();
    for (const c of panel) if (c.period === period) raw.set(c.ticker, c.raw);
    return banks
      .filter((b) => raw.has(b.ticker))
      .map((b) => ({ ...b, raw: raw.get(b.ticker)! }));
  }, [banks, panel, period]);

  const tab = (kind: ViewKind, label: string) => (
    <button
      key={kind}
      type="button"
      onClick={() => setView(kind)}
      aria-pressed={view === kind}
      className={`border-b-[1.5px] pb-0.5 font-mono text-[10.5px] transition-colors ${
        view === kind
          ? "border-foreground font-semibold text-foreground"
          : "border-transparent text-muted-foreground hover:text-foreground"
      }`}
    >
      {label}
    </button>
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-baseline gap-x-5 gap-y-1">
        {tab("snapshot", "Snapshot")}
        {tab("time", "Over time")}
        <span className="ml-auto font-mono text-[8.5px] uppercase tracking-[0.07em] text-faint">
          {frameLabel} · {banks.length} banks
        </span>
      </div>

      {view === "snapshot" ? (
        <HeatmapGrid metrics={metrics} rows={rows} picks={picks} />
      ) : (
        <HeatmapOverTime
          metrics={metrics}
          banks={banks}
          periods={periods}
          panel={framedPanel}
        />
      )}
    </div>
  );
}
