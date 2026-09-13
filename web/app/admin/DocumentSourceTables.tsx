"use client";

import { useEffect, useRef, useState } from "react";
import type { SourceTable, SourceTables } from "../lib/document-source-tables";
import type { DipnoteLink, NoteTarget } from "../lib/document-dipnotes";

const control = "border-b border-border bg-transparent px-1 py-1.5 text-xs text-foreground focus:outline-primary";
const labels: Record<string, string> = {
  balance_sheet_assets: "Balance sheet — assets", balance_sheet_liabilities: "Balance sheet — liabilities",
  profit_loss: "Income statement", other_comprehensive_income: "Other comprehensive income", equity_change: "Changes in equity",
  cash_flow: "Cash flow", off_balance: "Off-balance sheet", credit_quality: "Credit quality", loans_by_sector: "Loans by sector",
  npl_movement: "NPL movement", capital: "Capital adequacy", liquidity: "Liquidity", fx_position: "FX position",
  repricing: "Interest-rate repricing", profile: "Bank profile", free_provision: "Free provision",
};

export function SourceGrid({ table, onNote }: { table: SourceTable; onNote?: (link: DipnoteLink) => void }) {
  const covered = new Set<string>();
  for (const span of table.merged_spans) for (let r = span.row; r < span.row + span.row_span; r++) for (let c = span.column; c < span.column + span.column_span; c++) {
    if (r !== span.row || c !== span.column) covered.add(`${r}:${c}`);
  }
  return <div className="mt-3 max-h-[65vh] overflow-auto" tabIndex={0} aria-label={`Source table on page ${table.page}`}>
    <table className="w-full border-collapse text-[11px]"><tbody>{table.rows.map(row => <tr key={row.row}>
      {row.cells.map(cell => {
        if (covered.has(`${row.row}:${cell.column}`)) return null;
        const span = table.merged_spans.find(s => s.row === row.row && s.column === cell.column);
        const links = table.dipnote_links.filter(l => l.row === row.row && l.column === cell.column);
        return <td key={cell.column} rowSpan={span?.row_span} colSpan={span?.column_span} data-cell-state={cell.state}
          className={`border-b border-hair px-2 py-1.5 align-top whitespace-pre-wrap ${cell.column === 0 ? "min-w-52" : "min-w-20 text-right font-mono tabular-nums"}`}
          title={cell.source_fragments.map(p => `${p.text} · source word ${p.word_id}, characters ${p.start + 1}–${p.end}`).join("; ")}>
          {cell.state === "absent" ? <span className="text-faint">[no cell]</span> : cell.state === "blank" ? <span className="text-faint">[blank]</span> : cell.text}
          {onNote && links.map((link, i) => <button key={i} type="button" onClick={() => onNote(link)}
            className="mt-1 block text-primary hover:underline" aria-label={`Read dipnote ${link.marker} for row ${row.row}`}>
            {link.status === "resolved" ? "Read note" : link.status === "ambiguous" ? "Competing notes" : "Unresolved note"} {link.marker}
          </button>)}
        </td>;
      })}
    </tr>)}</tbody></table>
  </div>;
}

export function DipnoteReadingView({ note, report, citation }: { note: NoteTarget; report: SourceTables; citation: string }) {
  const passages = report.passages.filter(p => note.passage_ids.includes(p.id));
  const tables = report.tables.filter(t => note.table_ids.includes(t.id) && t.rows.length && t.verification.native_cells === "checked");
  const shownTables = new Set<string>();
  const address = [note.address.section, note.address.group, note.address.item].filter(v => v !== "");
  return <section className="mt-4 border-t-2 border-foreground pt-3" aria-label={`Dipnote ${address.join(".")}`}>
    <div className="flex flex-wrap items-start justify-between gap-3">
      <h5 className="font-semibold">§{address.join("-")} · {note.heading}</h5>
      <a className="shrink-0 text-primary hover:underline" href={`${citation}&artifact=original#page=${note.page_start}`} target="_blank" rel="noreferrer">PDF pp. {note.page_start}–{note.page_end}</a>
    </div>
    <p className="mt-2 text-faint">Matched by the printed note address. The full source interval follows, including table text and qualifications; interpretation remains unreviewed.</p>
    {passages.map(p => {
      const containing = tables.filter(t => t.page === p.page && p.bbox[0] >= t.bbox[0] - 1 && p.bbox[1] >= t.bbox[1] - 1 && p.bbox[2] <= t.bbox[2] + 1 && p.bbox[3] <= t.bbox[3] + 1);
      if (containing.length === 1) {
        const table = containing[0]; if (shownTables.has(table.id)) return null;
        shownTables.add(table.id);
        return <div key={table.id} className="mt-3"><p className="text-faint">Page {table.page} · {table.verification.row_assignments === "named_source_review" ? "Source-reviewed rows" : "Physical rows; logical grouping unverified"}</p><SourceGrid table={table} /></div>;
      }
      return <p key={p.id} className={`mt-2 whitespace-pre-wrap ${p.kind === "table_text" ? "font-mono text-[11px]" : "text-xs"}`}>{p.raw_text}</p>;
    })}
    <details className="mt-3"><summary className="cursor-pointer font-medium">Original note text and {tables.length} table grids</summary>
      <pre className="mt-2 whitespace-pre-wrap text-[11px]">{passages.map(p => p.raw_text).join("\n\n")}</pre>
      {tables.filter(t => !shownTables.has(t.id)).map(t => <SourceGrid key={t.id} table={t} />)}
    </details>
  </section>;
}

function TableReadingView({ table, report, citation }: { table: SourceTable; report: SourceTables; citation: string }) {
  const [link, setLink] = useState<DipnoteLink | null>(null);
  const [expanded, setExpanded] = useState(table.verification.row_assignments === "named_source_review");
  const notePanel = useRef<HTMLDivElement | null>(null);
  useEffect(() => { if (link) notePanel.current?.focus(); }, [link]);
  const context = report.passages.filter(p => table.context_passage_ids.includes(p.id));
  const units = report.passages.filter(p => table.page_unit_passage_ids.includes(p.id));
  return <details className="mt-4 border-t border-border pt-3" open={expanded} onToggle={e => setExpanded(e.currentTarget.open)}>
    <summary className="cursor-pointer font-semibold">Page {table.page} · {table.rows.length ? `${table.rows.length} rows · ${table.column_count} columns` : "Unassigned table candidate"}
      {table.candidate_lanes.length ? ` · ${table.candidate_lanes.map(l => labels[l] ?? l).join(" / ")}` : ""}
      {table.verification.row_assignments === "named_source_review" ? " · Source-reviewed rows" : " · Unreviewed boundaries"}</summary>
    {expanded && <><div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-faint">
      <span>{table.id} · {table.verification.native_cells === "checked" ? "Cells checked against native text" : "Cell verification incomplete"}</span>
      <a className="text-primary hover:underline" href={`${citation}&artifact=original#page=${table.page}`} target="_blank" rel="noreferrer">Compare original PDF</a>
    </div>
    {context.map(p => <p className="mt-2 whitespace-pre-wrap text-muted-foreground" key={p.id}>{p.raw_text}</p>)}
    {units.map(p => <p className="mt-2 whitespace-pre-wrap text-faint" key={p.id}>Printed page units: {p.raw_text}</p>)}
    {!!table.verification.issues.length && <p className="mt-2 text-warning">Needs review: {table.verification.issues.map(i => i.replaceAll("_", " ")).join("; ")}.</p>}
    {table.rows.length > 0 && <SourceGrid table={table} onNote={setLink} />}
    {table.unresolved_source !== undefined && <details className="mt-3"><summary className="cursor-pointer">Inspect retained evidence with unresolved columns</summary><pre className="mt-2 max-h-72 overflow-auto text-[10px]">{JSON.stringify(table.unresolved_source, null, 2)}</pre></details>}
    {link && <div className="mt-3" ref={notePanel} tabIndex={-1}>
      <button className="text-primary hover:underline" onClick={() => setLink(null)}>Close dipnote {link.marker}</button>
      {link.status !== "resolved" && <p className="mt-2 text-warning">{link.address ? `Printed address: §${[link.address.section, link.address.group, link.address.item].filter(v => v !== "").join("-")}. ` : ""}{link.status === "ambiguous" ? "More than one source interval has this printed address. No interval was selected automatically." : "This reference could not be tied to one closed source interval. Check the original PDF."}</p>}
      {link.target_ids.map(id => report.notes.find(n => n.id === id)).filter((n): n is NoteTarget => !!n).map(note => <DipnoteReadingView key={note.id} note={note} report={report} citation={citation} />)}
    </div>}</>}
  </details>;
}

export function SourceTablesReadingView({ report, filing, initialPage, initialLane }: { report: SourceTables; filing: string; initialPage?: number; initialLane?: string }) {
  const preferred = initialLane === "stages" ? "credit_quality" : initialLane;
  const [lane, setLane] = useState(preferred && report.tables.some(t => t.candidate_lanes.includes(preferred)) ? preferred : "all");
  const [page, setPage] = useState(initialPage ?? 0);
  const [alternatives, setAlternatives] = useState(false);
  const citation = `/api/admin/document-corpus?filing=${encodeURIComponent(filing)}&source_hash=${report.source.pdf_sha256}`;
  const matching = report.tables.filter(t => (lane === "all" || t.candidate_lanes.includes(lane)) && (!page || t.page === page));
  const shown = matching.filter(t => alternatives || t.unresolved_source === undefined);
  const pages = [...new Set(report.tables.map(t => t.page))];
  return <div className="mt-3 text-xs">
    <p className="text-muted-foreground">Printed columns, amounts and cell states are retained. Notes open from their table references. A checked cell is not proof that every table in the report has been captured.</p>
    {initialLane === "stages" && <p className="mt-2 text-muted-foreground">IFRS-9 stages are derived from credit-quality disclosures; inspect those source tables here.</p>}
    <div className="my-3 flex flex-wrap items-center gap-3">
      <label>Table family <select className={control} value={lane} onChange={e => { setLane(e.target.value); setPage(0); }}>
        <option value="all">All source candidates</option>
        {Object.entries(labels).filter(([key]) => report.tables.some(t => t.candidate_lanes.includes(key))).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
      </select></label>
      <label>Page <select className={control} value={page} onChange={e => setPage(Number(e.target.value))}><option value={0}>All pages</option>{pages.map(p => <option key={p} value={p}>{p}</option>)}</select></label>
      <label className="flex items-center gap-1"><input type="checkbox" checked={alternatives} onChange={e => setAlternatives(e.target.checked)} />Show candidates with unassigned columns</label>
      <a className="text-primary hover:underline" href={`${citation}&artifact=tables&download=1`}>Download tables with dipnotes JSON</a>
    </div>
    <p className="text-faint">{shown.length} of {matching.length} matching candidates shown · {report.notes.length} indexed note intervals. Table families are suggested by source headings; choose all candidates to inspect other tables.</p>
    {!shown.length && <p className="mt-3 text-warning">No aligned candidate matches this selection. This does not establish that the source contains no table.</p>}
    {shown.map(table => <TableReadingView key={table.id} table={table} report={report} citation={citation} />)}
  </div>;
}

export default function DocumentSourceTables({ filing, sourceHash, initialPage, initialLane, onRead }: { filing: string; sourceHash?: string; initialPage?: number; initialLane?: string; onRead?: () => void }) {
  const [result, setResult] = useState<SourceTables | null>(null), [error, setError] = useState<string | null>(null), [busy, setBusy] = useState(false);
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);
  async function load() {
    onRead?.();
    controller.current?.abort();
    const request = new AbortController(); controller.current = request;
    setBusy(true); setError(null);
    try {
      const response = await fetch(`/api/admin/document-corpus?filing=${encodeURIComponent(filing)}&artifact=tables${sourceHash ? `&source_hash=${sourceHash}` : ""}`, { cache: "no-store", signal: request.signal });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error ?? "Tables could not be read.");
      if (data.schema_version !== "audit-source-tables-1" || `${data.source?.bank_ticker}|${data.source?.period}|${data.source?.kind}` !== filing
          || (sourceHash && data.source.pdf_sha256 !== sourceHash)) throw new Error("Source changed. Reload the filing before reading its tables.");
      if (!request.signal.aborted) setResult(data);
    } catch (e) { if (!request.signal.aborted) setError(e instanceof Error ? e.message : "Tables could not be read."); }
    finally { if (!request.signal.aborted) setBusy(false); }
  }
  return <section className="my-4 border-t-2 border-foreground pt-3">
    <h4 className="text-sm font-semibold">Source tables and dipnotes</h4>
    {!result && <button className="mt-2 text-xs text-primary hover:underline disabled:opacity-50" onClick={load} disabled={busy}>Read source tables and dipnotes</button>}
    {busy && <p className="mt-2 text-xs text-faint" role="status">Checking source pages and linking printed note references across the report…</p>}
    {error && <p className="mt-2 text-xs text-negative" role="alert">{error}</p>}
    {result && <SourceTablesReadingView report={result} filing={filing} initialPage={initialPage} initialLane={initialLane} />}
  </section>;
}
