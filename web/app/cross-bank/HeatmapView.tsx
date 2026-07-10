"use client";

/**
 * Cross-bank heatmap shell: a small client wrapper that toggles between the
 * Snapshot grid (banks × metrics at the latest common quarter) and the
 * Over-time grid (banks × quarters for one metric). Both datasets are computed
 * server-side and passed in as props; this component only owns the toggle.
 */
import { useState } from "react";
import type { MetricDef } from "@/app/lib/heatmap";
import HeatmapGrid, { type HeatmapBankRow } from "./HeatmapGrid";
import HeatmapOverTime, {
  type HeatmapTimeRow,
  type PanelCell,
} from "./HeatmapOverTime";

interface Props {
  metrics: MetricDef[];
  snapshot: { period: string; rows: HeatmapBankRow[] };
  timePanel: { banks: HeatmapTimeRow[]; periods: string[]; panel: PanelCell[] };
}

type ViewKind = "snapshot" | "time";

export default function HeatmapView({ metrics, snapshot, timePanel }: Props) {
  const [view, setView] = useState<ViewKind>("snapshot");

  const tab = (kind: ViewKind, label: string) => (
    <button
      type="button"
      onClick={() => setView(kind)}
      aria-pressed={view === kind}
      className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
        view === kind
          ? "bg-primary/10 font-semibold text-primary"
          : "text-muted-foreground hover:bg-accent/60 hover:text-foreground"
      }`}
    >
      {label}
    </button>
  );

  return (
    <div className="space-y-4">
      <div className="inline-flex items-center gap-0.5 rounded-[9px] border border-border bg-card p-[3px]">
        {tab("snapshot", "Snapshot")}
        {tab("time", "Over time")}
      </div>

      {view === "snapshot" ? (
        <HeatmapGrid metrics={metrics} rows={snapshot.rows} period={snapshot.period} />
      ) : (
        <HeatmapOverTime
          metrics={metrics}
          banks={timePanel.banks}
          periods={timePanel.periods}
          panel={timePanel.panel}
        />
      )}
    </div>
  );
}
