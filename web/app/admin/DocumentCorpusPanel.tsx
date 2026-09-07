"use client";

import { useEffect, useState } from "react";
import { SecHead } from "@/app/components/desk";
import type { CorpusCatalogResult, CorpusFiling } from "@/app/lib/document-corpus";
import { nf } from "@/app/lib/chart-format";
import DocumentRecoveryPanel from "./DocumentRecoveryPanel";
import DocumentOriginPanel from "./DocumentOriginPanel";
import DocumentContentReviews from "./DocumentContentReviews";
import DocumentNarrativePreview, { type Narrative, type ReadingLayout } from "./DocumentNarrativePreview";

const endpoint = "/api/admin/document-corpus";
const id = (f: CorpusFiling) => `${f.bank_ticker}|${f.period}|${f.kind}`;
const count = (v: number | null | undefined) => v == null ? "—" : nf(v, 0);
const control = "border-b border-border bg-transparent px-1 py-1.5 text-xs text-foreground focus:outline-primary";

type Cell = { text: string | null; col_index?: number | null; column?: number; placement?: string; word_ids: string[] };
type Table = { id: string; method: string; n_cols: number; row_count: number; col_labels?: string[]; word_view?: string;
  rows: { index: number; label?: string; cells: Cell[] }[] };
type TableContext = { table_id: string; heading: { text: string } | null;
  physical_grid: { anchors: { row: number; column: number; row_span: number; column_span: number }[];
    covered_slots: { row: number; column: number; anchor: number[] }[] } | null };
type SourceRows = { table_id: string; split_rows: { source_row: number; column_projection?: { header_row: number };
  lines: { index: number; cells: Cell[] }[] }[] };
type PagePreview = { manifest: { sections: { title: string; page_start: number; page_end: number }[] };
  page: { page: number; text_blocks: { id: string; text: string }[]; tables: Table[];
    table_source_rows?: { tables: SourceRows[] };
    table_context?: { tables: TableContext[]; continuations: { status: string; from_page: number;
      from_table_ids: string[]; to_table_id: string; title: string; column_identifiers: string[] }[] };
    reading_layout?: ReadingLayout;
    narrative_elements?: Narrative[]; issues: { kind: string; count?: number }[] } };

async function fetchJson<T>(url: string, signal: AbortSignal): Promise<T> {
  const response = await fetch(url, { cache: "no-store", signal });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error ?? "The document could not be loaded.");
  return data;
}

function status(row: CorpusFiling) {
  if (row.latest_attempt_failed) return "Capture failed";
  if (row.source_capture_stale || row.structure_stale) return "Capture needs updating";
  if (row.capture?.structure_engine) return "Structure awaiting review";
  if (row.capture?.source) return "Source preserved";
  return row.acquisition_status === "missing" ? "Source missing" : "Not captured";
}

function TablePreview({ table, context, sourceRows }: { table: Table; context?: TableContext; sourceRows?: SourceRows }) {
  const [expandLines, setExpandLines] = useState(true);
  const positioned = table.method === "native_image_replacement_geometry";
  const numeric = table.method === "legacy_numeric_geometry" || positioned;
  const unplaced = table.rows.some((r) => r.cells.some((c) => c.placement === "unplaced"));
  const grid = !numeric ? context?.physical_grid : null;
  const covered = new Set(grid?.covered_slots.map((slot) => `${slot.row}:${slot.column}`));
  const rows = table.rows.flatMap((row) => {
    const split = expandLines && sourceRows?.split_rows.find((s) => s.source_row === row.index);
    return split ? split.lines.map((line) => ({ ...row, cells: line.cells, key: `${row.index}:${line.index}`, sourceLine: true, projected: !!split.column_projection }))
      : [{ ...row, key: String(row.index), sourceLine: false, projected: false }];
  });
  return <details className="border-b border-border py-3" open>
    <summary className="cursor-pointer text-xs font-medium">
      Candidate {table.id} · {table.row_count} rows · {table.n_cols} value/text columns
      <span className="ml-2 font-normal text-faint">{positioned ? "PDF-linked label positions" : numeric ? "Numeric layout" : "Ruled layout"} · unreviewed</span>
    </summary>
    {context?.heading && <p className="mt-2 text-xs font-medium">{context.heading.text}</p>}
    {sourceRows && <div className="mt-2 text-xs text-muted-foreground">
      <label><input type="checkbox" checked={expandLines} onChange={(e) => setExpandLines(e.target.checked)} className="mr-2" />Show separate source lines inside tall cells</label>
      <p className="mt-1">Original columns and header cells are retained. Wrapped labels may span several lines; these lines are not verified accounting rows.</p>
      {sourceRows.split_rows.some(r => r.column_projection) && <p className="mt-1">Some merged body columns are separated using the printed headings and borders. Switch this option off to inspect the original merged cells. Isolated amounts or dashes keep their source line and are not assigned to a neighbouring label.</p>}
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
  </details>;
}

function FilingPreview({ filing }: { filing: CorpusFiling }) {
  const [page, setPage] = useState(1);
  const [result, setResult] = useState<{ key: string; value?: PagePreview; error?: string } | null>(null);
  const key = `${id(filing)}:${page}`;
  const query = `filing=${encodeURIComponent(id(filing))}`;
  useEffect(() => {
    const controller = new AbortController();
    if (filing.capture?.structure_engine) {
      fetchJson<PagePreview>(`${endpoint}?filing=${encodeURIComponent(id(filing))}&artifact=structure&page=${page}`, controller.signal)
        .then((value) => setResult({ key, value }))
        .catch((error) => { if (!controller.signal.aborted) setResult({ key, error: error.message }); });
    }
    return () => controller.abort();
  }, [filing, key, page]);
  const current = result?.key === key ? result : null;
  const source = filing.capture?.source;
  const preview = current?.value;
  return <div className="mt-4 border-t border-border pt-4">
    <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-xs">
      <strong>{filing.bank_ticker} · {filing.period} · {filing.kind === "consolidated" ? "Consolidated" : "Solo"}</strong>
      <span className="text-muted-foreground">{status(filing)} · {count(filing.capture?.page_count)} pages</span>
      {source && <a className="text-primary hover:underline" href={`${endpoint}?${query}&artifact=original#page=${page}`} target="_blank" rel="noreferrer">Open original PDF at page {page}</a>}
    </div>
    {filing.capture?.last_error && <p className="mt-2 text-xs text-negative">{filing.capture.last_error}</p>}
    {source && <p className="mt-2 break-all font-mono text-[10px] text-faint">Source SHA-256: {source.pdf_sha256}</p>}
    <DocumentOriginPanel filing={id(filing)} sourceHash={source?.pdf_sha256} />
    {source && <DocumentContentReviews filing={id(filing)} sourceHash={source.pdf_sha256} />}
    {filing.capture?.structure_engine && <>
      <div className="my-4 flex flex-wrap items-center gap-3 text-xs">
        <button className={control} disabled={page === 1} onClick={() => setPage(page - 1)}>Previous</button>
        <label>PDF page <select className={`${control} ml-1`} value={page} onChange={(e) => setPage(Number(e.target.value))}>
          {Array.from({ length: filing.capture?.page_count ?? 0 }, (_, i) => <option key={i} value={i + 1}>{i + 1}</option>)}
        </select></label>
        <button className={control} disabled={page === filing.capture?.page_count} onClick={() => setPage(page + 1)}>Next</button>
        <a className="text-primary hover:underline" href={`${endpoint}?${query}&artifact=source&page=${page}`} target="_blank" rel="noreferrer">Page evidence JSON</a>
        <a className="text-primary hover:underline" href={`${endpoint}?${query}&artifact=structure`}>Download full structured report</a>
      </div>
      {!current && <p className="text-xs text-faint" role="status">Loading and checking page evidence…</p>}
      {current?.error && <p className="text-xs text-negative" role="alert">{current.error}</p>}
      {preview && <>
        <p className="mb-3 text-xs text-muted-foreground">{preview.manifest.sections.filter((s) => s.page_start <= page && page <= s.page_end).map((s) => s.title).join(" · ") || "Section not yet identified"}</p>
        <p className="mb-3 text-xs text-warning">Semantic review pending. Alternative table detections may overlap. Reading order and header associations are unverified.</p>
        {preview.page.issues.length > 0 && <details className="mb-3 text-xs text-muted-foreground">
          <summary className="cursor-pointer">{preview.page.issues.length} review flags on this page</summary>
          <ul className="mt-2 list-disc pl-5">{preview.page.issues.map((issue, i) => <li key={i}>{issue.kind.replaceAll("_", " ")}{issue.count != null ? ` (${count(issue.count)})` : ""}</li>)}</ul>
        </details>}
        <DocumentRecoveryPanel filing={id(filing)} page={page} />
        {preview.page.table_context?.continuations.map((link) => <div key={link.to_table_id} className="my-3 border-l border-border pl-3 text-xs">
          <p>{link.status === "unique_source_evidence" ? "Source indicates a table continuation" : "Possible continuation has competing earlier tables"}: {link.title}</p>
          <p className="mt-1 text-muted-foreground">Repeated column identifiers: {link.column_identifiers.join(" · ")}. Original fragments remain separate; association needs review.</p>
          <button className="mt-1 text-primary hover:underline" onClick={() => setPage(link.from_page)}>Inspect earlier fragment on page {link.from_page}</button>
        </div>)}
        <h4 className="border-b border-border py-2 text-xs font-semibold">Table candidates · {count(preview.page.tables.length)}</h4>
        {preview.page.tables.map((table) => <TablePreview key={table.id} table={table}
          sourceRows={preview.page.table_source_rows?.tables.find((rows) => rows.table_id === table.id)}
          context={preview.page.table_context?.tables.find((context) => context.table_id === table.id)} />)}
        {preview.page.tables.length === 0 && <p className="py-3 text-xs text-faint">No table detected. This does not establish that the source page contains no table.</p>}
        {preview.page.narrative_elements && <DocumentNarrativePreview elements={preview.page.narrative_elements} layout={preview.page.reading_layout} />}
        <details className="mt-5" open={!preview.page.narrative_elements}><summary className="cursor-pointer text-xs font-semibold">All page text · {count(preview.page.text_blocks.length)} source blocks</summary>
          <p className="my-2 text-xs text-faint">Includes table text. Paragraph roles and reading order still require review.</p>
          {preview.page.text_blocks.map((block) => <div key={block.id} className="border-b border-border py-3">
            <span className="font-mono text-[10px] text-faint">{block.id}</span>
            <p className="mt-1 whitespace-pre-wrap text-xs leading-relaxed">{block.text}</p>
          </div>)}
        </details>
      </>}
    </>}
  </div>;
}

export default function DocumentCorpusPanel() {
  const [result, setResult] = useState<CorpusCatalogResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [bank, setBank] = useState("");
  const [selected, setSelected] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    fetchJson<CorpusCatalogResult>(endpoint, controller.signal).then(setResult)
      .catch((e) => { if (!controller.signal.aborted) setError(e.message); });
    return () => controller.abort();
  }, []);
  const catalog = result?.status === "ready" ? result.catalog : null;
  const active = catalog?.filings.filter((f) => f.in_current_inventory) ?? [];
  const currentBank = bank || active.find((f) => f.capture?.structure_engine)?.bank_ticker || active[0]?.bank_ticker || "";
  const choices = active.filter((f) => f.bank_ticker === currentBank).sort((a, b) => b.period.localeCompare(a.period) || a.kind.localeCompare(b.kind));
  const filing = choices.find((f) => id(f) === selected) ?? choices.find((f) => f.capture?.structure_engine) ?? choices[0];
  const unavailable = result && result.status !== "ready" ? {
    not_connected: "Document storage is not connected to this admin deployment.",
    not_started: "The corpus inventory has not been published yet.",
    unavailable: "The corpus inventory could not be read or verified.",
  }[result.status] : null;
  return <div>
    <SecHead title="Complete audit documents" meta="source coverage · tables and text · independent of analytical lanes" className="mb-3" />
    {error && <p className="text-xs text-negative" role="alert">{error}</p>}
    {!result && !error && <p className="text-xs text-faint">Loading document inventory…</p>}
    {unavailable && <p className="text-xs text-warning">{unavailable}</p>}
    {catalog && <>
      <dl className="grid grid-cols-2 gap-4 border-y border-border py-4 sm:grid-cols-4 lg:grid-cols-8">
        {([ ["Registered", catalog.summary.registered], ["Acquired", catalog.summary.acquired],
          ["Source preserved", catalog.summary.source_preserved], ["Structure captured", catalog.summary.structured_candidates],
          ["Fully verified", catalog.summary.semantically_verified], ["Failed", catalog.summary.failed],
          ["Needs updating", catalog.summary.stale], ["Inventory filings", catalog.summary.filings] ] as const).map(([label, value]) =>
          <div key={label}><dt className="text-[10px] text-muted-foreground">{label}</dt><dd className="mt-1 font-mono text-xl">{count(value)}</dd></div>)}
      </dl>
      <p className="my-3 text-xs text-muted-foreground">Counts are filings, including both reporting bases. Captured structure remains unreviewed; zero fully verified is an explicit quality status.</p>
      <div className="flex flex-wrap items-center gap-4">
        <label className="text-xs">Bank <select className={`${control} ml-2`} value={currentBank} onChange={(e) => { setBank(e.target.value); setSelected(""); }}>
          {[...new Set(active.map((f) => f.bank_ticker))].sort().map((ticker) => <option key={ticker}>{ticker}</option>)}
        </select></label>
        {filing && <label className="text-xs">Report <select className={`${control} ml-2`} value={id(filing)} onChange={(e) => setSelected(e.target.value)}>
          {choices.map((f) => <option key={id(f)} value={id(f)}>{f.period} · {f.kind === "consolidated" ? "Consolidated" : "Solo"} · {status(f)}</option>)}
        </select></label>}
      </div>
      {filing && <FilingPreview key={id(filing)} filing={filing} />}
    </>}
  </div>;
}
