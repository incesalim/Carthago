"use client";

import { useEffect, useState } from "react";
import type { ReviewedTable } from "@/app/lib/document-table-review";

export function ReviewedTableList({ tables, filing, page }: { tables: ReviewedTable[]; filing: string; page: number }) {
  const query = `filing=${encodeURIComponent(filing)}&artifact=table-reviews&page=${page}`;
  return <div className="mb-5 border-t border-border pt-3 text-xs">
    <div className="flex flex-wrap items-center justify-between gap-2">
      <h4 className="font-semibold">Source-reviewed tables · {tables.length}</h4>
      {!!tables.length && <a className="text-primary hover:underline" href={`/api/admin/document-corpus?${query}`} target="_blank" rel="noreferrer">Download reviewed tables and source references</a>}
    </div>
    {!tables.length && <p className="mt-2 text-faint">No complete-table review is registered for this page.</p>}
    {!!tables.length && <p className="mt-2 text-muted-foreground">These named tables were checked against the source. Financial interpretation and review of the complete report remain separate.</p>}
    {tables.map(table => {
      const covered = new Set<string>();
      for (const span of table.merged_spans) for (let r = span.row; r < span.row + span.row_span; r++) for (let c = span.column; c < span.column + span.column_span; c++) {
        if (r !== span.row || c !== span.column) covered.add(`${r}:${c}`);
      }
      return <details className="mt-3 border-b border-border pb-3" key={table.review_id} open>
        <summary className="cursor-pointer font-medium">{table.rows.length} rows · {table.physical_table.n_cols} columns · {table.table_id}</summary>
        {table.rows.some(r => r.reviewed_assignment) && <p className="mt-2 text-muted-foreground">Includes source-reviewed row and column assignments. The original physical cells remain available below and in the download.</p>}
        <div className="mt-3 overflow-x-auto">
          <table className="w-full border-collapse text-[11px]">
            <tbody>{table.rows.map(row => <tr key={row.row} data-reviewed-assignment={row.reviewed_assignment || undefined}>
              {row.cells.map(cell => {
                if (covered.has(`${row.row}:${cell.column}`)) return null;
                const span = table.merged_spans.find(s => s.row === row.row && s.column === cell.column);
                return <td key={cell.column} rowSpan={span?.row_span} colSpan={span?.column_span}
                  className={`border-b border-border px-2 py-1.5 align-top whitespace-pre-wrap ${cell.column === 0 ? "min-w-48" : "text-right font-mono tabular-nums"}`}
                  title={cell.source_fragments.map(p => `${p.text} · source word ${p.word_id}, characters ${p.start + 1}–${p.end}`).join("; ")}>
                  {cell.text === null ? <span className="text-faint">[no physical cell]</span> : cell.text === "" ? <span className="text-faint">[empty source cell]</span> : cell.text}
                </td>;
              })}
            </tr>)}</tbody>
          </table>
        </div>
        {table.source_context.map((context, i) => <p key={i} className="mt-2 whitespace-pre-wrap text-muted-foreground">{context.text}</p>)}
        <p className="mt-2 text-muted-foreground">Source review: {table.source_review}</p>
      </details>;
    })}
  </div>;
}

export default function DocumentReviewedTables({ filing, page, sourceHash, pageHash }: { filing: string; page: number; sourceHash: string; pageHash: string }) {
  const key = `${filing}:${sourceHash}:${pageHash}:${page}`;
  const [result, setResult] = useState<{ key: string; tables?: ReviewedTable[]; error?: string }>();
  useEffect(() => {
    const controller = new AbortController();
    fetch(`/api/admin/document-corpus?filing=${encodeURIComponent(filing)}&artifact=table-reviews&page=${page}`, { cache: "no-store", signal: controller.signal })
      .then(async response => {
        const data = await response.json();
        if (!response.ok || data.source?.pdf_sha256 !== sourceHash || !Array.isArray(data.tables)
            || data.tables.some((t: ReviewedTable) => t.structure_page_sha256 !== pageHash)) throw new Error(data.error ?? "The captured page changed. Reload the filing to inspect its review.");
        setResult({ key, tables: data.tables });
      })
      .catch(error => { if (!controller.signal.aborted) setResult({ key, error: error.message }); });
    return () => controller.abort();
  }, [filing, page, sourceHash, pageHash, key]);
  const current = result?.key === key ? result : null;
  if (!current) return <p className="mb-3 text-xs text-faint" role="status">Checking registered table reviews…</p>;
  if (current.error) return <p className="mb-3 text-xs text-negative" role="alert">{current.error}</p>;
  return <ReviewedTableList tables={current.tables ?? []} filing={filing} page={page} />;
}
