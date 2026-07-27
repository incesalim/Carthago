/**
 * CSV export for charts. Charts stamp a `ChartTable` into the card DOM (see
 * `app/components/ui/chart-csv.tsx`) and `ChartExport` reads it back and feeds
 * it to `toCsv` for download — so these helpers are pure and React-free.
 *
 * A `ChartTable` is the chart's underlying data flattened to a matrix: a header
 * row of column labels plus one row per x-value. `wideToTable` builds it from
 * the Recharts wide-row arrays the charts already compute (e.g.
 * `[{ period, "10006": 1.2, … }]`).
 */

export interface ChartTable {
  columns: string[];
  /** One row per x-value; cell order matches `columns`. `null` = empty cell. */
  rows: (string | number | null)[][];
}

export interface Col {
  key: string;
  label: string;
}

/**
 * Pivot a Recharts wide-row array into a `ChartTable`. The x column comes first,
 * then one column per series in the given order. Missing/`undefined`/`NaN`
 * values become `null` (an empty CSV cell).
 */
export function wideToTable(
  rows: ReadonlyArray<Record<string, unknown>>,
  x: Col,
  series: ReadonlyArray<Col>,
): ChartTable {
  const columns = [x.label, ...series.map((s) => s.label)];
  const cell = (v: unknown): string | number | null =>
    v == null || (typeof v === "number" && Number.isNaN(v))
      ? null
      : typeof v === "number" || typeof v === "string"
        ? v
        : String(v);
  const matrix = rows.map((r) => [
    cell(r[x.key]),
    ...series.map((s) => cell(r[s.key])),
  ]);
  return { columns, rows: matrix };
}

/** Quote an RFC-4180 field only when it contains a delimiter, quote, or newline. */
function field(v: string | number | null): string {
  if (v == null) return "";
  const s = String(v);
  return /[",\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

/**
 * Serialize a `ChartTable` to an RFC-4180 CSV string. Numbers are emitted raw
 * (full precision, no thousands separators) so the file holds the real values,
 * not the chart's display formatting. Prepends a UTF-8 BOM so Excel renders
 * Turkish characters / `₺` correctly.
 */
export function toCsv(t: ChartTable): string {
  const lines = [t.columns, ...t.rows].map((row) => row.map(field).join(","));
  return "﻿" + lines.join("\r\n");
}

// ───────────────────────────────────────── text alternative ──
//
// A chart on this site renders ENTIRELY on the client: Recharts'
// `ResponsiveContainer` needs a measured width, so the server ships an empty
// `<div class="recharts-responsive-container">` and nothing else. Assistive
// technology therefore met a chart page and found no chart, no data and no
// description — measured 2026-07-25, and the top accessibility gap on the site.
//
// The same `ChartTable` the CSV button already stamps into the DOM is the fix:
// it is the chart's data, so a summary built from it cannot drift from what the
// chart draws (the failure mode a hand-written alt text has by design).

/** Series listed individually before the summary switches to a count. */
const MAX_SERIES_DESCRIBED = 8;

/**
 * A screen-reader data table is only worth rendering while it is navigable.
 *
 * Measured across /economy: the median chart is 37 rows x 2 columns, which is a
 * genuinely useful table — but one series is 753 rows, and reading 753 rows to
 * someone is not access, it is an obstacle wearing the costume of compliance.
 * Above these bounds the summary carries the shape and says how many points the
 * CSV holds.
 */
const SR_TABLE_MAX_ROWS = 60;
const SR_TABLE_MAX_CELLS = 400;

export function srTableIsUseful(t: ChartTable): boolean {
  const rows = t.rows.length;
  return rows > 0 && rows <= SR_TABLE_MAX_ROWS && rows * t.columns.length <= SR_TABLE_MAX_CELLS;
}

/** Round for speech, not for storage: nobody needs "16.104346" read aloud. */
function speak(v: string | number | null): string | null {
  if (v == null) return null;
  if (typeof v === "string") return v.trim() || null;
  if (!Number.isFinite(v)) return null;
  const abs = Math.abs(v);
  const decimals = abs >= 10_000 ? 0 : abs >= 100 ? 1 : 2;
  return String(Number(v.toFixed(decimals)));
}

/**
 * One sentence per series: where it starts, where it ends, and the band it moved
 * in. Deliberately not a direction WORD — "rose"/"fell" is a claim, and claims
 * on this site are computed next to the series that settles them
 * (`lib/prose.ts`). First and last are the facts; the reader draws the arrow.
 */
export function chartSummary(t: ChartTable): string {
  if (t.columns.length === 0 || t.rows.length === 0) return "";

  const xLabel = t.columns[0] ?? "Category";
  const xFirst = speak(t.rows[0]?.[0]);
  const xLast = speak(t.rows[t.rows.length - 1]?.[0]);
  const span =
    xFirst && xLast && xFirst !== xLast
      ? `${xLabel} from ${xFirst} to ${xLast}`
      : xFirst
        ? `${xLabel} ${xFirst}`
        : xLabel;

  const seriesCols = t.columns.slice(1);
  const described = seriesCols.slice(0, MAX_SERIES_DESCRIBED);
  const parts: string[] = [];

  described.forEach((label, i) => {
    const col = i + 1;
    const values = t.rows
      .map((r) => r[col])
      .filter((v): v is number => typeof v === "number" && Number.isFinite(v));
    if (values.length === 0) {
      parts.push(`${label}: no values`);
      return;
    }
    const first = speak(values[0]);
    const last = speak(values[values.length - 1]);
    const min = speak(Math.min(...values));
    const max = speak(Math.max(...values));
    const range = min === max ? `` : `, ranging ${min} to ${max}`;
    parts.push(
      first === last
        ? `${label}: ${last}${range}`
        : `${label}: ${first} at the start, ${last} at the end${range}`,
    );
  });

  const hidden = seriesCols.length - described.length;
  if (hidden > 0) parts.push(`and ${hidden} more series`);

  const rowNote = `${t.rows.length} ${t.rows.length === 1 ? "row" : "rows"}`;
  const tail = srTableIsUseful(t)
    ? "The full data follows as a table."
    : "The full data is available from this chart's CSV download.";

  return `Chart data: ${rowNote}, ${span}. ${parts.join(". ")}. ${tail}`;
}
