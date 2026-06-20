/**
 * Stamps a chart's underlying data into the card DOM as a hidden JSON payload
 * so `ChartExport`'s CSV button can read it back (via `closest()` →
 * `[data-chart-csv]`) and download it — no prop threading through `ChartCard`,
 * which is sometimes rendered by the page rather than the chart (e.g.
 * `BopFlowChart`). Render `<ChartData>` anywhere inside the card.
 *
 * The table is React text children (not `dangerouslySetInnerHTML`), so labels
 * with `<`/`&` are escaped and `textContent` round-trips to valid JSON.
 * `hidden` keeps it out of view (incl. the Expand modal); `data-chart-no-export`
 * keeps it out of the PNG screenshot.
 */
import type { ChartTable } from "@/app/lib/chart-csv";

export function ChartData({ table }: { table: ChartTable }) {
  return (
    <span hidden data-chart-csv="" data-chart-no-export="">
      {JSON.stringify(table)}
    </span>
  );
}
