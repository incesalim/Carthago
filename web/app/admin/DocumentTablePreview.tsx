"use client";

import { useState } from "react";

type Cell = { text: string | null; col_index?: number | null; column?: number; placement?: string; word_ids: (number | string)[] };
export type Table = { id: string; method: string; n_cols: number; row_count: number; col_labels?: string[]; word_view?: string;
  rows: { index: number; label?: string; cells: Cell[] }[] };
export type TableContext = { table_id: string; heading: { text: string } | null;
  physical_grid: { anchors: { row: number; column: number; row_span: number; column_span: number }[];
    covered_slots: { row: number; column: number; anchor: number[] }[] } | null };
export type SourceRows = { table_id: string; split_rows: { source_row: number; column_projection?: { header_row: number };
  row_group?: { source_rows: number[] };
  lines: { index: number; cells: Cell[] }[] }[] };
export type TableNotes = { table_id: string; links: { label: string; column: number; text: string;
  header_word_ids: (number | string)[]; marker_span_ids: (number | string)[]; text_span_ids: (number | string)[] }[] };
export default function DocumentTablePreview({ table, context, sourceRows, notes }: { table: Table; context?: TableContext; sourceRows?: SourceRows; notes?: TableNotes }) {
  const [expandLines, setExpandLines] = useState(true);
  const positioned = table.method === "native_image_replacement_geometry";
  const numeric = table.method === "legacy_numeric_geometry" || positioned;
  const unplaced = table.rows.some((r) => r.cells.some((c) => c.placement === "unplaced"));
  const grid = !numeric ? context?.physical_grid : null;
  const covered = new Set(grid?.covered_slots.map((slot) => `${slot.row}:${slot.column}`));
  const rows = table.rows.flatMap((row) => {
    if (expandLines && sourceRows?.split_rows.some(s => s.source_row !== row.index && s.row_group?.source_rows.includes(row.index))) return [];
    const split = expandLines && sourceRows?.split_rows.find((s) => s.source_row === row.index);
    return split ? split.lines.map((line) => ({ ...row, cells: line.cells, key: `${row.index}:${line.index}`, sourceLine: true, projected: !!split.column_projection || !!split.row_group }))
      : [{ ...row, key: String(row.index), sourceLine: false, projected: false }];
  });
  return <details className="border-b border-border py-3" open>
    <summary className="cursor-pointer text-xs font-medium">
      Candidate {table.id} · {table.row_count} rows · {table.n_cols} value/text columns
      <span className="ml-2 font-normal text-faint">{positioned ? "PDF-linked label positions" : numeric ? "Numeric layout" : table.method === "segmented_rules_and_source_lines" ? "Printed rules and text positions" : "Ruled layout"} · unreviewed</span>
    </summary>
    {context?.heading && <p className="mt-2 text-xs font-medium">{context.heading.text}</p>}
    {sourceRows && <div className="mt-2 text-xs text-muted-foreground">
      <label><input type="checkbox" checked={expandLines} onChange={(e) => setExpandLines(e.target.checked)} className="mr-2" />Show separate source lines inside tall cells</label>
      <p className="mt-1">Original columns and header cells are retained. Wrapped labels may span several lines; these lines are not verified accounting rows.</p>
      {sourceRows.split_rows.some(r => r.column_projection) && <p className="mt-1">Some merged body columns are separated using the printed headings and borders. Switch this option off to inspect the original merged cells. Isolated amounts or dashes keep their source line and are not assigned to a neighbouring label.</p>}
      {sourceRows.split_rows.some(r => r.row_group) && <p className="mt-1">A cell spans several physical rows here. This view keeps their text together in its original columns and shows each source line once. Switch this option off to inspect the original cell spans.</p>}
    </div>}
    <div className="mt-2 overflow-x-auto">
      <table className="w-full border-collapse text-[11px]">
        <thead><tr className="border-b border-border text-left text-muted-foreground">
          {numeric && <th className="p-2 font-normal">Source row label</th>}
          {Array.from({ length: table.n_cols }, (_, c) => <th key={c} className="p-2 font-normal">{table.col_labels?.[c] || `Column ${c + 1}`}</th>)}
          {unplaced && <th className="p-2 font-normal text-warning">Unplaced text</th>}
        </tr></thead>
        <tbody>{rows.map((row) => <tr key={row.key} className="border-b border-border/60 align-top">
          {numeric && <td className="min-w-48 whitespace-pre-wrap p-2">{row.label}</td>}
          {Array.from({ length: table.n_cols }, (_, c) => {
            if (!row.projected && covered.has(`${row.index}:${c}`)) return null;
            const anchor = !row.projected ? grid?.anchors.find((a) => a.row === row.index && a.column === c) : undefined;
            return <td key={c} rowSpan={anchor?.row_span} colSpan={anchor?.column_span} className="min-w-20 whitespace-pre-wrap p-2 font-mono">
            {row.cells.filter((cell) => (numeric ? cell.placement === "data" && cell.col_index === c : cell.column === c))
              .map((cell, i) => <div key={i} title={`${positioned ? "Positioned source pieces" : "Source words"}: ${cell.word_ids.join(", ")}`}>{cell.text || (row.sourceLine ? "[no text on this line]" : "[empty source cell]")}</div>)}
          </td>;
          })}
          {unplaced && <td className="p-2 font-mono text-warning">{row.cells.filter((c) => c.placement === "unplaced").map((c) => c.text).join("\n")}</td>}
        </tr>)}</tbody>
      </table>
    </div>
    {notes && notes.links.length > 0 && <div className="mt-3 text-xs">
      <p className="font-medium">Numbered source explanations</p>
      <p className="mt-1 text-faint">Suggested links follow the printed column numbers and adjacent notes. Source wording is retained; interpretation still needs review.</p>
      <ol className="mt-2 space-y-2">{notes.links.map((link) => <li key={link.column}
        title={`Header source words: ${link.header_word_ids.join(", ")}; note source spans: ${[...link.marker_span_ids, ...link.text_span_ids].join(", ")}`}>
        <span className="mr-2 font-mono">{link.label}.</span><span className="whitespace-pre-wrap leading-relaxed">{link.text.trim()}</span>
        <span className="ml-2 text-faint">Column {link.column + 1}</span>
      </li>)}</ol>
    </div>}
  </details>;
}
