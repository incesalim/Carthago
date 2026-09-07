"use client";

import { useEffect, useState } from "react";
import type { RelatedRevision } from "@/app/lib/document-related";
import DocumentRecoveryPanel from "./DocumentRecoveryPanel";

export default function DocumentRelatedPanel({ filing, member, observation }: {
  filing: string; member: { name: string; bytes: number; sha256: string }; observation?: string;
}) {
  const [open, setOpen] = useState(false);
  const [page, setPage] = useState(1);
  const [state, setState] = useState<{ key: string; revision?: RelatedRevision; error?: string } | null>(null);
  const query = `filing=${encodeURIComponent(filing)}&related=${member.sha256}${observation ? `&origin=${observation}` : ""}`;
  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    fetch(`/api/admin/document-corpus?${query}`, { cache: "no-store", signal: controller.signal })
      .then(async response => {
        const data = await response.json();
        if (!response.ok) throw new Error(data.error ?? "The related document could not be loaded.");
        setState({ key: query, revision: data.revision });
      }).catch(error => { if (!controller.signal.aborted) setState({ key: query, error: error.message }); });
    return () => controller.abort();
  }, [open, query]);
  const current = state?.key === query ? state : null;
  return <details className="mt-3 border-t border-border pt-3" onToggle={event => setOpen(event.currentTarget.open)}>
    <summary className="cursor-pointer text-xs font-medium">Related PDF: {member.name}</summary>
    {open && <>
      {!current && <p className="mt-2 text-faint">Checking this related document’s capture…</p>}
      {current?.error && <p className="mt-2 text-warning" role="alert">{current.error}</p>}
      {current?.revision && <>
        <p className="mt-2 text-muted-foreground">Separate document in the same official archive · {current.revision.page_count} pages · content review pending.</p>
        <p className="mt-1 text-faint">The archive’s reporting period does not establish this document’s period.</p>
        {current.revision.archive_identity && <div className="mt-2 text-xs">
          <p className={current.revision.archive_identity.status === "source_text_conflict" ? "text-warning" : "text-muted-foreground"}>
            Opening-page identity: {current.revision.archive_identity.status.replaceAll("_", " ")}.</p>
          {current.revision.archive_identity.observed_periods.length > 0 && <p className="mt-1">Source period on page {current.revision.archive_identity.claim_page}: {current.revision.archive_identity.observed_periods.join(", ")}.</p>}
          {current.revision.archive_identity.issues.map(issue => <p key={issue} className="mt-1 text-warning">{issue.replaceAll("_", " ")}</p>)}
        </div>}
        <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-2">
          <label>Related PDF page <select className="ml-2 border-b border-border bg-transparent py-1 text-foreground" value={page} onChange={event => setPage(Number(event.target.value))}>
            {Array.from({ length: current.revision.page_count }, (_, i) => <option key={i} value={i + 1}>{i + 1}</option>)}
          </select></label>
          <a className="text-primary hover:underline" href={`/api/admin/document-corpus?${query}&artifact=original#page=${page}`} target="_blank" rel="noreferrer">Open related original PDF</a>
          <a className="text-primary hover:underline" href={`/api/admin/document-corpus?${query}&artifact=source&page=${page}`} target="_blank" rel="noreferrer">Native page evidence</a>
          {current.revision.structure_current && <a className="text-primary hover:underline" href={`/api/admin/document-corpus?${query}&artifact=structure`}>Download related structure</a>}
        </div>
        <DocumentRecoveryPanel filing={filing} page={page} related={member.sha256} origin={observation} />
      </>}
    </>}
  </details>;
}
