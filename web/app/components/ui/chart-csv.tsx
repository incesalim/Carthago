/**
 * Stamps a chart's underlying data into the card DOM twice, for two different
 * readers.
 *
 * 1. A hidden JSON payload, so `ChartExport`'s CSV button can read it back (via
 *    `closest()` → `[data-chart-csv]`) and download it — no prop threading
 *    through `ChartCard`, which is sometimes rendered by the page rather than
 *    the chart (e.g. `BopFlowChart`). Render `<ChartData>` anywhere in the card.
 *    The payload is React text children (not `dangerouslySetInnerHTML`), so
 *    labels with `<`/`&` are escaped and `textContent` round-trips to valid JSON.
 *
 * 2. A screen-reader text alternative, added 2026-07-25. Every chart here
 *    renders ENTIRELY on the client — Recharts' `ResponsiveContainer` needs a
 *    measured width, so the served HTML holds an empty container div and nothing
 *    else. Assistive technology met a page of charts and found no chart, no data
 *    and no description. Since all eight chart components already stamp this
 *    component, building the alternative from the SAME table fixes every chart
 *    type at once — and it cannot drift from what is drawn, which is the defect
 *    hand-written alt text has by construction.
 *
 * The JSON stays `hidden` (out of the a11y tree — it is machine data, and
 * reading raw JSON aloud helps nobody). The alternative uses `sr-only`, which is
 * visually clipped but present for a screen reader. Both carry
 * `data-chart-no-export` so neither lands in the PNG screenshot.
 */
import { chartSummary, srTableIsUseful, type ChartTable } from "@/app/lib/chart-csv";

export function ChartData({ table }: { table: ChartTable }) {
  const summary = chartSummary(table);
  const withTable = srTableIsUseful(table);

  return (
    <>
      <span hidden data-chart-csv="" data-chart-no-export="">
        {JSON.stringify(table)}
      </span>
      {summary && (
        <div className="sr-only" data-chart-no-export="">
          <p>{summary}</p>
          {withTable && (
            <table>
              <caption>{table.columns.join(", ")}</caption>
              <thead>
                <tr>
                  {table.columns.map((c, i) => (
                    <th key={`${c}-${i}`} scope="col">
                      {c}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {table.rows.map((row, r) => (
                  <tr key={r}>
                    {row.map((cell, c) =>
                      // The x value heads its own row, so a cell read in
                      // isolation still announces which period or bank it
                      // belongs to.
                      c === 0 ? (
                        <th key={c} scope="row">
                          {cell ?? ""}
                        </th>
                      ) : (
                        <td key={c}>{cell ?? ""}</td>
                      ),
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </>
  );
}
