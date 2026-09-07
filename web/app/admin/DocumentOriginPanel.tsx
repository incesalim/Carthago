"use client";

import { useEffect, useState } from "react";
import type { OriginReview } from "@/app/lib/document-origin";
import DocumentRelatedPanel from "./DocumentRelatedPanel";

const labels: Record<OriginReview["status"], string> = {
  matches_acquired_bytes: "Fresh official download matches the acquired PDF",
  same_pdf_after_acquisition_wrapper: "The PDF matches after removing its recorded download wrapper",
  different_pdf_revision: "The official download contains a different PDF revision",
  acquisition_missing: "Official source retained; acquired PDF was missing when checked",
  origin_unavailable: "The official URL could not be downloaded",
  origin_needs_review: "The official download requires source review",
};

export default function DocumentOriginPanel({ filing, sourceHash }: { filing: string; sourceHash?: string }) {
  const [state, setState] = useState<{ filing: string; review?: OriginReview | null; error?: string } | null>(null);
  const url = `/api/admin/document-origin?filing=${encodeURIComponent(filing)}`;
  useEffect(() => {
    const controller = new AbortController();
    fetch(`/api/admin/document-origin?filing=${encodeURIComponent(filing)}`, { cache: "no-store", signal: controller.signal })
      .then(async response => {
        const body = await response.json();
        if (!response.ok) throw new Error(body.error ?? "The official-source comparison could not be loaded.");
        setState({ filing, review: body.review });
      }).catch(error => { if (!controller.signal.aborted) setState({ filing, error: error.message }); });
    return () => controller.abort();
  }, [filing]);
  const current = state?.filing === filing ? state : null;
  const review = current?.review;
  return <div className="mt-3 border-y border-border py-3 text-xs">
    <h4 className="font-semibold">Official-source comparison</h4>
    {!current && <p className="mt-1 text-faint">Loading source observation…</p>}
    {current?.error && <p className="mt-1 text-warning" role="alert">{current.error}</p>}
    {current && !current.error && !review && <p className="mt-1 text-muted-foreground">No fresh official-source comparison has been retained for this filing.</p>}
    {review && <>
      <p className="mt-1">{labels[review.status]}.</p>
      <p className="mt-1 text-faint">Observed {review.checked_at} · Text and table verification remains pending.</p>
      {sourceHash && review.acquisition?.sha256 !== sourceHash && <p className="mt-1 text-warning">This observation does not establish agreement with the currently displayed source revision.</p>}
      {review.origin_identity && <p className="mt-1 text-muted-foreground">Opening-page identity: {review.origin_identity.status.replaceAll("_", " ")}.</p>}
      {review.error && <p className="mt-1 text-warning">{review.error}</p>}
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1">
        <a className="text-primary hover:underline" href={review.source_url} target="_blank" rel="noreferrer">{review.source_listing ? "Regulator-listed official URL" : "Registered official URL"}</a>
        {review.source_listing && <a className="text-primary hover:underline" href={`${url}&artifact=source_listing`}>Download retained regulator listing</a>}
        {review.origin_pdf && <a className="text-primary hover:underline" href={`${url}&artifact=origin_pdf`} target="_blank" rel="noreferrer">Open retained official PDF</a>}
        {review.transport && <a className="text-primary hover:underline" href={`${url}&artifact=transport`}>Download original response</a>}
        <a className="text-primary hover:underline" href={url} target="_blank" rel="noreferrer">Comparison evidence</a>
      </div>
      {review.selection?.unselected_pdf_members?.map(member => <DocumentRelatedPanel key={`${member.name}:${member.sha256}`} filing={filing} member={member} />)}
    </>}
  </div>;
}
