"use client";

import { useState } from "react";

type SourceFragment = { word_id: number | string; start: number; end: number; text: string };
type Cell = { text: string | null; col_index?: number | null; column?: number; placement?: string; word_ids: (number | string)[]; source_fragments?: SourceFragment[] };
export type Table = { id: string; method: string; n_cols: number; row_count: number; col_labels?: string[]; word_view?: string;
  word_boundary_observations?: { word_id: number | string; text: string; review_status: string;
    cells: { row: number; column: number; start: number; end: number }[] }[];
  rows: { index: number; label?: string; cells: Cell[] }[] };
export type TableContext = { table_id: string; heading: { text: string } | null;
  physical_grid: { anchors: { row: number; column: number; row_span: number; column_span: number }[];
    covered_slots: { row: number; column: number; anchor: number[] }[] } | null };
export type SourceRows = { table_id: string; split_rows: { source_row: number; column_projection?: { header_row: number };
  row_group?: { source_rows: number[] };
  lines: { index: number; cells: Cell[] }[] }[] };
export type TableNotes = { table_id: string; links: { label: string; column: number; text: string;
  header_word_ids: (number | string)[]; header_source_fragments?: SourceFragment[]; marker_span_ids: (number | string)[]; text_span_ids: (number | string)[] }[] };
export type PeriodHeaders = { table_id: string; status: string; bands: { source_row: number;
  columns: { column: number; text: string; source_fragments: SourceFragment[] }[] }[] };

function sourceReference(cell: Pick<Cell, "word_ids" | "source_fragments">, positioned = false) {
  return cell.source_fragments?.length
    ? cell.source_fragments.map(p => `${p.text} (source word ${p.word_id}, characters ${p.start + 1}-${p.end})`).join("; ")
    : `${positioned ? "Positioned source pieces" : "Source words"}: ${cell.word_ids.join(", ")}`;
}

export default function DocumentTablePreview({ table, context, sourceRows, notes, periodHeaders }: { table: Table; context?: TableContext; sourceRows?: SourceRows; notes?: TableNotes; periodHeaders?: PeriodHeaders }) {
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
    {periodHeaders && <div className="mt-2 text-xs">
      <p className="font-medium">Printed period headings</p>
      <p className="mt-1 text-muted-foreground">These labels follow the words&apos; positions above the columns. The original cells are shown below.</p>
      {periodHeaders.status === "competing_printed_bands" && <p className="mt-1 text-warning">More than one heading band is present. Check which applies before interpreting the amounts.</p>}
      {periodHeaders.bands.map(band => <ul key={band.source_row} className="mt-1 space-y-1">
        {band.columns.filter(column => column.column > 0).map(column => <li key={column.column}
          title={sourceReference({ word_ids: [], source_fragments: column.source_fragments })}>
          <span className="mr-2 text-faint">Column {column.column + 1}</span>
          <span className="whitespace-pre-wrap">{column.text}</span>
        </li>)}
      </ul>)}
    </div>}
    {!!table.word_boundary_observations?.length && <details className="mt-2 text-xs text-muted-foreground">
      <summary className="cursor-pointer">Boundary review: {table.word_boundary_observations.length} source {table.word_boundary_observations.length === 1 ? "word spans" : "words span"} more than one cell</summary>
      <p className="mt-1">Exact character references are retained. Check these boundaries against the original report before interpreting the cells.</p>
      <ul className="mt-1 space-y-1">{table.word_boundary_observations.map(word => <li key={word.word_id}>
        <span className="font-mono">{word.text}</span>: {word.cells.map(cell => `row ${cell.row + 1}, column ${cell.column + 1}`).join("; ")}
      </li>)}</ul>
    </details>}
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
              .map((cell, i) => <div key={i} title={sourceReference(cell, positioned)}>{cell.text === null ? "[no physical cell]" : cell.text || (row.sourceLine ? "[no text on this line]" : "[empty source cell]")}</div>)}
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
        title={`Header ${sourceReference({ word_ids: link.header_word_ids, source_fragments: link.header_source_fragments })}; note source spans: ${[...link.marker_span_ids, ...link.text_span_ids].join(", ")}`}>
        <span className="mr-2 font-mono">{link.label}.</span><span className="whitespace-pre-wrap leading-relaxed">{link.text.trim()}</span>
        <span className="ml-2 text-faint">Column {link.column + 1}</span>
      </li>)}</ol>
    </div>}
  </details>;
}
