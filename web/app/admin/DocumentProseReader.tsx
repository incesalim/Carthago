"use client";

import { useEffect, useMemo, useState } from "react";
import type { StructuredProse } from "@/app/lib/document-prose";
import { nf } from "@/app/lib/chart-format";

const control = "border-b border-border bg-transparent px-1 py-1.5 text-xs text-foreground focus:outline-primary";

export function ProseReadingView({ report, citation, onPage }: {
  report: StructuredProse; citation: string; onPage: (page: number) => void;
}) {
  const [query, setQuery] = useState("");
  const [section, setSection] = useState("");
  const [includeTables, setIncludeTables] = useState(false);
  const [raw, setRaw] = useState(false);
  const [limit, setLimit] = useState(60);
  const matching = useMemo(() => {
    const search = query.toLocaleLowerCase("tr").trim();
    return report.passages.filter(p => (includeTables || !["furniture", "table_text", "heading_marker"].includes(p.kind))
      && (!section || (section === "unknown" ? !p.section : String(p.section?.number) === section))
      && (!search || `${p.heading_marker?.text ?? ""} ${p.text} ${p.heading_path.map(h => `${h.marker ?? ""} ${h.text}`).join(" ")}`.toLocaleLowerCase("tr").includes(search)));
  }, [report, query, section, includeTables]);
  return <div className="mt-3">
    <p className="text-xs text-muted-foreground">Wording checked against {nf(report.verification.source_spans_checked, 0)} native source spans
      across {nf(report.page_count, 0)} pages. Paragraph boundaries, heading relationships and reading order still need review.</p>
    <div className="my-3 flex flex-wrap items-center gap-3">
      <label className="text-xs">Search report <input className={`${control} ml-2`} value={query}
        onChange={e => { setQuery(e.target.value); setLimit(60); }} type="search" /></label>
      <label className="text-xs">Section <select className={`${control} ml-2`} value={section}
        onChange={e => { setSection(e.target.value); setLimit(60); }}>
        <option value="">All sections</option><option value="unknown">Unassigned section</option>
        {report.sections.map(s => <option key={`${s.number}:${s.page_start}`} value={s.number}>{s.number}. {s.title}</option>)}
      </select></label>
      <label className="text-xs"><input type="checkbox" checked={includeTables} onChange={e => setIncludeTables(e.target.checked)} /> Include table text and page furniture</label>
      <label className="text-xs"><input type="checkbox" checked={raw} onChange={e => setRaw(e.target.checked)} /> Original line breaks</label>
      <a className="text-xs text-primary hover:underline" href={`${citation}&artifact=prose&download=1`}>Download structured prose JSON</a>
    </div>
    <p className="text-xs text-faint">{nf(matching.length, 0)} matching passages · short disclosures such as “Bulunmamaktadır” remain included.</p>
    {report.pages_without_native_text.length > 0 && <p className="my-2 text-xs text-warning">No native text on PDF pages {report.pages_without_native_text.join(", ")}. Images on these pages may contain text that this view cannot read.</p>}
    {report.pages_with_issues.length > 0 && <details className="my-2 text-xs text-muted-foreground">
      <summary className="cursor-pointer">Reading and source flags on {nf(report.pages_with_issues.length, 0)} pages</summary>
      {report.pages_with_issues.map(p => <p key={p.page}>Page {p.page}: {p.issues.map(i => i.replaceAll("_", " ")).join(" · ")}</p>)}
    </details>}
    {matching.slice(0, limit).map(p => <article key={p.id} id={`prose-${p.element_id}`} className="border-b border-hair py-3">
      <div className="flex flex-wrap gap-x-3 text-[10px] text-faint">
        <span className="font-mono">{p.kind.replaceAll("_", " ")} · {p.language}</span>
        <button className="text-primary hover:underline" onClick={() => onPage(p.page)}>Inspect page {p.page}</button>
        <a className="text-primary hover:underline" href={`${citation}&artifact=original#page=${p.page}`} target="_blank" rel="noreferrer">Original PDF</a>
        <span>{p.section ? `${p.section.number}. ${p.section.role.replaceAll("_", " ")}` : "Section unassigned"}</span>
      </div>
      {p.heading_path.length > 0 && <p className="mt-1 text-xs text-muted-foreground">{p.heading_path.map(h => h.marker_element_id ? `${h.marker} ${h.text}` : h.text).join(" › ")}</p>}
      <p className={`mt-2 text-sm leading-relaxed ${raw ? "whitespace-pre-wrap" : ""} ${p.kind === "heading" ? "font-semibold" : ""}`}>{p.heading_marker && <span>{p.heading_marker.text}{" "}</span>}{raw ? p.raw_text : p.text}</p>
      {p.continuation_from && <p className="mt-1 text-xs text-warning">Possible continuation of the preceding page’s paragraph; fragments are kept separately.</p>}
      {p.note_links.map(link => <p key={`${link.table_id}:${link.column}`} className="mt-1 text-xs text-muted-foreground">Note {link.marker} · table {link.table_id} · column {link.column}</p>)}
      {p.issues.length > 0 && <p className="mt-1 text-xs text-warning">{p.issues.map(i => i.replaceAll("_", " ")).join(" · ")}</p>}
    </article>)}
    {matching.length === 0 && <p className="py-3 text-xs text-muted-foreground">No passages match these filters.</p>}
    {matching.length > limit && <button className="mt-3 text-xs text-primary hover:underline" onClick={() => setLimit(limit + 60)}>Show next 60 passages</button>}
  </div>;
}

export default function DocumentProseReader({ filing, sourceHash, onPage }: {
  filing: string; sourceHash: string; onPage: (page: number) => void;
}) {
  const [opened, setOpened] = useState(false);
  const [result, setResult] = useState<{ key: string; report?: StructuredProse; error?: string } | null>(null);
  const citation = `/api/admin/document-corpus?filing=${encodeURIComponent(filing)}&source_hash=${sourceHash}`;
  useEffect(() => {
    if (!opened) return;
    const controller = new AbortController();
    fetch(`${citation}&artifact=prose`, { cache: "no-store", signal: controller.signal })
      .then(async response => {
        const data = await response.json();
        if (!response.ok) throw new Error(data.error ?? "Prose could not be verified.");
        if (data.schema_version !== "audit-prose-1" || data.source?.pdf_sha256 !== sourceHash) throw new Error("Prose source differs from this filing.");
        setResult({ key: citation, report: data });
      }).catch(error => { if (!controller.signal.aborted) setResult({ key: citation, error: error.message }); });
    return () => controller.abort();
  }, [opened, citation, sourceHash]);
  const current = result?.key === citation ? result : null;
  return <details className="my-4 border-y border-border py-3" onToggle={e => setOpened(e.currentTarget.open)}>
    <summary className="cursor-pointer text-sm font-semibold">Read and search structured prose across this report</summary>
    {opened && !current && <p className="mt-3 text-xs text-faint" role="status">Reading the report and checking every passage against its source…</p>}
    {opened && current?.error && <p className="mt-3 text-xs text-negative" role="alert">{current.error}</p>}
    {opened && current?.report && <ProseReadingView key={citation} report={current.report} citation={citation} onPage={onPage} />}
  </details>;
}
