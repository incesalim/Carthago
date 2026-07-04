"use client";

/**
 * PlSankeySection — card shell for the P&L flow Sankey on /banks/[ticker].
 *
 * Server passes the raw P&L rows for the displayed periods; this component
 * owns the period pill row and runs the pure derivation per selection.
 * Kind / annual-quarterly toggles live on the page (searchParams), so a
 * toggle re-renders the server component and fresh rows arrive as props.
 */
import { useMemo, useState } from "react";
import { ChartCard } from "@/app/components/ui/chart-card";
import PlSankeyChart from "./PlSankeyChart";
import { buildPlSankey } from "@/app/lib/pl-sankey";
import type { PlRow } from "@/app/lib/audit";

interface Props {
  rowsByPeriod: Record<string, PlRow[]>;
  /** Display order, latest first (matches the table columns). */
  periods: string[];
}

/** "2025Q4" → "2025 Q4" for the pills. */
const periodLabel = (p: string) => p.replace(/^(\d{4})Q([1-4])$/, "$1 Q$2");

export default function PlSankeySection({ rowsByPeriod, periods }: Props) {
  const [period, setPeriod] = useState(periods[0]);
  const active = periods.includes(period) ? period : periods[0];

  const graph = useMemo(
    () => buildPlSankey(rowsByPeriod[active] ?? []),
    [rowsByPeriod, active],
  );

  if (periods.length === 0) return null;

  return (
    <ChartCard
      className="mb-6"
      title="P&L flow"
      description="Income through expenses to net profit — YTD cumulative as reported, TL thousands. Hover for exact figures."
      action={
        <div className="inline-flex items-center gap-0.5 rounded-lg border border-border bg-card p-0.5">
          {periods.map((p) => (
            <button
              key={p}
              type="button"
              onClick={() => setPeriod(p)}
              aria-pressed={p === active}
              className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                p === active
                  ? "bg-accent text-foreground"
                  : "text-muted-foreground hover:bg-accent/60 hover:text-foreground"
              }`}
            >
              {periodLabel(p)}
            </button>
          ))}
        </div>
      }
    >
      {graph.renderable ? (
        <>
          <PlSankeyChart graph={graph} ariaLabel={`P&L flow, ${periodLabel(active)}`} />
          {graph.notes.length > 0 && (
            <ul className="mt-2 space-y-0.5 text-[11px] text-muted-foreground">
              {graph.notes.map((n, i) => (
                <li key={i}>{n}</li>
              ))}
            </ul>
          )}
        </>
      ) : (
        <div className="flex h-[200px] flex-col items-center justify-center gap-1 text-sm text-muted-foreground">
          <span>Flow chart unavailable for {periodLabel(active)}.</span>
          {graph.notes.map((n, i) => (
            <span key={i} className="text-xs">{n}</span>
          ))}
        </div>
      )}
    </ChartCard>
  );
}
