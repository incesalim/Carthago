"use client";

/**
 * Color key for the cross-bank heatmaps. Renders the same `scoreToColor` ramp
 * the cells use, so the legend can never drift from the encoding.
 *  - "directional" — green→red good/bad ramp (most ratio metrics).
 *  - "neutral"     — single --info ramp for size / no-good-or-bad metrics.
 *  - "both"        — the snapshot grid mixes directional + neutral columns.
 * Always includes the "no data" chip (transparent cell + muted "—").
 */
import { useText } from "@/i18n/use-text";
import { scoreToColor } from "@/app/lib/heatmap-normalize";

type Mode = "directional" | "neutral" | "both";

function Ramp({ scores, neutral }: { scores: number[]; neutral?: boolean }) {
  return (
    <div className="flex">
      {scores.map((s, i) => (
        <span
          key={i}
          style={{ background: scoreToColor(s, neutral) }}
          className="h-3 w-4 border-y border-border first:rounded-l-sm first:border-l last:rounded-r-sm last:border-r"
        />
      ))}
    </div>
  );
}

export default function HeatmapLegend({ mode }: { mode: Mode }) {
  const tx = useText();
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-[11px] text-muted-foreground">
      {(mode === "directional" || mode === "both") && (
        <span className="flex items-center gap-1.5">
          <span>{tx("Worse")}</span>
          <Ramp scores={[0, 0.2, 0.4, 0.5, 0.6, 0.8, 1]} />
          <span>{tx("Better")}</span>
        </span>
      )}
      {(mode === "neutral" || mode === "both") && (
        <span className="flex items-center gap-1.5">
          <span>{tx("Low")}</span>
          <Ramp scores={[0, 0.25, 0.5, 0.75, 1]} neutral />
          <span>{tx("High")}</span>
        </span>
      )}
      <span className="flex items-center gap-1.5">
        <span className="h-3 w-4 rounded-sm border border-dashed border-border" />
        <span>{tx("No data")}</span>
      </span>
    </div>
  );
}
