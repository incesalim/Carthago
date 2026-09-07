"use client";

import { useEffect, useState } from "react";
import type { ContentReview } from "@/app/lib/document-content-review";

export function ContentReviewList({ findings, filing }: { findings: ContentReview[]; filing: string }) {
  return <div className="mt-3 text-xs">
    <p className="text-muted-foreground">Open analyst notes. Source passages were checked; the differences remain unresolved.</p>
    {findings.map(finding => <details key={finding.id} className="border-b border-border py-3">
      <summary className="cursor-pointer font-medium">{finding.title} · open</summary>
      <p className="mt-2 leading-relaxed">{finding.note}</p>
      {finding.points.map((point, i) => <div key={i} className="mt-3 border-l border-border pl-3">
        <a className="text-primary hover:underline" target="_blank" rel="noreferrer"
          href={`/api/admin/document-corpus?filing=${encodeURIComponent(filing)}&artifact=original#page=${point.page}`}>Original PDF · page {point.page}</a>
        <blockquote className="mt-1 whitespace-pre-wrap leading-relaxed">{point.source_text}</blockquote>
      </div>)}
    </details>)}
    {!findings.length && <p className="mt-2 text-faint">No source-bound content notes are registered for this revision. This does not establish that the report has no discrepancies.</p>}
  </div>;
}

export default function DocumentContentReviews({ filing, sourceHash }: { filing: string; sourceHash: string }) {
  const key = `${filing}:${sourceHash}`;
  const [result, setResult] = useState<{ key: string; findings?: ContentReview[]; error?: string }>();
  useEffect(() => {
    const controller = new AbortController();
    fetch(`/api/admin/document-corpus?filing=${encodeURIComponent(filing)}&artifact=reviews`, { cache: "no-store", signal: controller.signal })
      .then(async response => {
        const data = await response.json();
        if (!response.ok || data.source?.pdf_sha256 !== sourceHash) throw new Error(data.error ?? "The review source changed. Reload this filing.");
        setResult({ key, findings: data.findings });
      })
      .catch(error => { if (!controller.signal.aborted) setResult({ key, error: error.message }); });
    return () => controller.abort();
  }, [filing, sourceHash, key]);
  const current = result?.key === key ? result : null;
  return <details className="mt-4 border-t border-border pt-3">
    <summary className="cursor-pointer text-xs font-semibold">Content review notes{current?.findings?.length ? ` · ${current.findings.length} open` : ""}</summary>
    {!current && <p className="mt-2 text-xs text-faint">Checking source passages…</p>}
    {current?.error && <p className="mt-2 text-xs text-negative" role="alert">{current.error}</p>}
    {current?.findings && <ContentReviewList findings={current.findings} filing={filing} />}
  </details>;
}
