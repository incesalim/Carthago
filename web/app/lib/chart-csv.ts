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
