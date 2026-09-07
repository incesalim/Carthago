"use client";

import { useEffect, useState } from "react";
import type { CorpusRevision } from "@/app/lib/document-corpus";
import DocumentRecoveryPanel from "./DocumentRecoveryPanel";

export default function DocumentEditionPanel({ filing, observation }: { filing: string; observation: string }) {
  const [open, setOpen] = useState(false);
  const [page, setPage] = useState(1);
  const [state, setState] = useState<{ key: string; revision?: CorpusRevision; error?: string } | null>(null);
  const query = `filing=${encodeURIComponent(filing)}&edition=${observation}`;
  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    fetch(`/api/admin/document-corpus?${query}`, { cache: "no-store", signal: controller.signal })
      .then(async response => {
        const body = await response.json();
        if (!response.ok) throw new Error(body.error ?? "This edition could not be loaded.");
        setState({ key: query, revision: body.revision });
      }).catch(error => { if (!controller.signal.aborted) setState({ key: query, error: error.message }); });
    return () => controller.abort();
  }, [open, query]);
  const current = state?.key === query ? state : null;
  return <details className="mt-3 border-t border-border pt-3" onToggle={event => setOpen(event.currentTarget.open)}>
    <summary className="cursor-pointer font-medium">Browse this observed PDF edition</summary>
    {open && <>
      {!current && <p className="mt-2 text-faint">Checking this edition’s capture…</p>}
      {current?.error && <p className="mt-2 text-warning" role="alert">{current.error}</p>}
      {current?.revision && <>
        <p className="mt-2 text-muted-foreground">{current.revision.page_count} pages · retained separately · content review pending.</p>
        <p className="mt-1 text-faint">The difference has not been classified as a correction, translation or replacement.</p>
        <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-2">
          <label>Edition PDF page <select className="ml-2 border-b border-border bg-transparent py-1 text-foreground" value={page} onChange={event => setPage(Number(event.target.value))}>
            {Array.from({ length: current.revision.page_count }, (_, i) => <option key={i} value={i + 1}>{i + 1}</option>)}
          </select></label>
          <a className="text-primary hover:underline" href={`/api/admin/document-corpus?${query}&artifact=original#page=${page}`} target="_blank" rel="noreferrer">Open edition PDF</a>
          <a className="text-primary hover:underline" href={`/api/admin/document-corpus?${query}&artifact=source&page=${page}`} target="_blank" rel="noreferrer">Native page evidence</a>
          {current.revision.structure_current && <>
            <a className="text-primary hover:underline" href={`/api/admin/document-corpus?${query}&artifact=structure&page=${page}`} target="_blank" rel="noreferrer">Page structure</a>
            <a className="text-primary hover:underline" href={`/api/admin/document-corpus?${query}&artifact=structure`}>Download full edition structure</a>
          </>}
        </div>
        <DocumentRecoveryPanel filing={filing} page={page} edition={observation} />
      </>}
    </>}
  </details>;
}
