"use client";

import { useEffect, useState } from "react";
import type { RecoveryPage } from "@/app/lib/document-recovery";

type Result = { status: "ready"; page: RecoveryPage; last_attempt?: { status: string; error?: string } }
  | { status: "not_started" | "source_not_captured"; last_attempt?: { status: string; error?: string } };

export default function DocumentRecoveryPanel({ filing, page, related, origin, edition }: {
  filing: string; page: number; related?: string; origin?: string; edition?: string;
}) {
  const query = `filing=${encodeURIComponent(filing)}&page=${page}${related ? `&related=${related}` : ""}${origin ? `&origin=${origin}` : ""}${edition ? `&edition=${edition}` : ""}`;
  const key = query;
  const [state, setState] = useState<{ key: string; value?: Result; error?: string } | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    fetch(`/api/admin/document-recovery?${query}`, { signal: controller.signal, cache: "no-store" })
      .then(async r => { const body = await r.json(); if (!r.ok) throw new Error(body.error); return body as Result; })
      .then(value => setState({ key, value }))
      .catch(error => { if (!controller.signal.aborted) setState({ key, error: error.message }); });
    return () => controller.abort();
  }, [query, key]);
  const current = state?.key === key ? state : null;
  const value = current?.value;
  const recovered = value?.status === "ready" ? value.page : null;
  const differences = recovered?.view.vector_comparisons.filter(c => c.status !== "exact_agreement") ?? [];
  const sourceTextDifferences = recovered?.benchmarks?.text_regions?.checks.filter(c => !c.passed) ?? [];
  return <details className="my-4 border-y border-border py-3" open={Boolean(recovered)}>
    <summary className="cursor-pointer text-xs font-semibold">Text recovered from page images, outlines and fonts</summary>
    {!current && <p className="mt-2 text-xs text-faint">Checking recovery records…</p>}
    {current?.error && <p className="mt-2 text-xs text-negative" role="alert">{current.error}</p>}
    {value?.last_attempt?.error && <p className="mt-2 text-xs text-negative">Latest attempt: {value.last_attempt.error}</p>}
    {value && !recovered && <p className="mt-2 text-xs text-faint">No recovered text is stored for this source page yet.</p>}
    {recovered && <>
      <p className="my-2 text-xs text-warning">Recognition and reading order need review. Raw readings retain punctuation and possible errors; matching readings are not approval of a value.</p>
      <div className="flex flex-wrap gap-4 text-xs">
        <a className="text-primary hover:underline" href={`/api/admin/document-recovery?${query}&artifact=ocr-pdf`} target="_blank" rel="noreferrer">Open source image with recovered text</a>
        <a className="text-primary hover:underline" href={`/api/admin/document-recovery?${query}`} target="_blank" rel="noreferrer">Full recovery evidence</a>
      </div>
      {sourceTextDifferences.length > 0 && <details className="mt-3" open>
        <summary className="cursor-pointer text-xs text-warning">{sourceTextDifferences.length} text passages differ from source transcription</summary>
        {sourceTextDifferences.map(c => <div key={c.id} className="border-b border-border/60 py-3 text-xs">
          <p className="font-mono text-[10px] text-faint">Source region: {c.source_bbox.map(n => n.toFixed(1)).join(", ")}</p>
          <p className="mt-1">Source transcription: {c.source_transcription}</p>
          <p className="mt-1 text-warning">Image reading: {c.observed_text || "[no text recovered]"}</p>
          {recovered.benchmarks?.font_text_regions?.checks.filter(f => f.id === c.id).map(f =>
            <p key={f.id} className="mt-1">Font reading: {f.observed_text || "[no text recovered]"} · {f.passed ? "matches this source transcription" : "differs from this source transcription"}</p>)}
        </div>)}
      </details>}
      {recovered.font_mapping && <details className="mt-3" open>
        <summary className="cursor-pointer text-xs font-semibold">Text recovered from embedded fonts · {recovered.font_mapping.mapped_characters} characters</summary>
        <p className="my-2 text-xs text-faint">Character shapes are linked to the PDF’s embedded fonts. Known native text is retained. {recovered.font_mapping.unresolved_characters} missing characters remain unresolved. Paragraph boundaries and reading order need review.</p>
        <div className="max-h-96 overflow-auto">{recovered.font_mapping.blocks.map(block => <div key={block.id} className="border-b border-border/60 py-2">
          <span className="font-mono text-[10px] text-faint" title={`Source spans: ${block.source_span_ids.join(", ")}`}>{block.id}</span>
          <p className="whitespace-pre-wrap text-xs leading-relaxed">{block.text}</p>
        </div>)}</div>
        <details className="mt-2"><summary className="cursor-pointer text-xs">Original and font-derived text</summary>
          {recovered.font_mapping.spans.filter(s => s.native_text !== s.candidate_text).map(s => <div key={s.id} className="border-b border-border/60 py-2 text-xs">
            <p>Original text: {s.native_text}</p><p>Font reading: {s.candidate_text}</p>
          </div>)}
        </details>
      </details>}
      {recovered.view.vector_comparisons.length > 0 && <details className="mt-3" open={differences.length > 0}>
        <summary className="cursor-pointer text-xs">{differences.length} differing or missing OCR readings · {recovered.view.vector_comparisons.length} outline comparisons</summary>
        <div className="mt-2 max-h-80 overflow-auto"><table className="w-full text-left text-[11px]">
          <thead><tr className="border-b border-border"><th className="p-2">Source region</th><th className="p-2">Outline reading</th><th className="p-2">Image reading</th></tr></thead>
          <tbody>{differences.map(c => <tr key={c.drawing_id} className="border-b border-border/60">
            <td className="p-2 font-mono">{c.bbox.map(n => n.toFixed(1)).join(", ")}</td>
            <td className="p-2 font-mono">{c.vector_text}</td><td className="p-2 font-mono">{c.ocr_text ?? "[no matching OCR word]"}</td>
          </tr>)}</tbody>
        </table></div>
      </details>}
      {recovered.view.table_layout?.tables.map(table => <details className="mt-4" key={table.id} open>
        <summary className="cursor-pointer text-xs font-semibold">Recovered table candidate · {table.row_count} rows · {table.n_cols} columns</summary>
        <p className="my-2 text-xs text-faint">{table.method === "ocr_repeated_amount_alignment"
          ? "Columns follow repeated amount alignment; wrapped lines remain separate physical rows."
          : "Columns follow printed rules; row boundaries are inferred."} Header associations and financial meaning remain unreviewed.</p>
        {table.header_text && <p className="my-2 whitespace-pre-wrap text-xs">{table.header_text}</p>}
        <div className="max-h-96 overflow-auto"><table className="w-full border-collapse text-[11px]">
          <thead><tr className="border-b border-border text-left">{Array.from({ length: table.n_cols }, (_, i) =>
            <th key={i} className="p-2 font-normal">Source column {i + 1}</th>)}</tr></thead>
          <tbody>{table.rows.map(row => <tr key={row.index} className="border-b border-border/60 align-top">
            {row.cells.map(cell => <td key={cell.column} className="min-w-24 whitespace-pre-wrap p-2" title={`OCR words: ${cell.ocr_word_ids.join(", ")} · source outlines: ${cell.drawing_ids.join(", ")}`}>
              <span className={cell.candidate_method === "ocr" ? "" : "font-mono"}>{cell.candidate_text ?? (cell.candidate_method === "unobserved" ? "[no text observed]" : "[unresolved outline]")}</span>
              {cell.candidate_method !== "ocr" && <span className="mt-1 block text-[9px] text-faint">{cell.candidate_method === "outline" ? "Outline reading" : "Reading unresolved"}</span>}
              {cell.candidate_method !== "ocr" && cell.ocr_text !== cell.candidate_text && <span className="mt-1 block text-[10px] text-warning">Image reading: {cell.ocr_text || "[empty]"}</span>}
            </td>)}
          </tr>)}</tbody>
        </table></div>
      </details>)}
      {recovered.view.text_blocks && <details className="mt-3" open>
        <summary className="cursor-pointer text-xs">Recovered text blocks · {recovered.view.text_blocks.length} groups</summary>
        <p className="my-2 text-xs text-faint">Original OCR grouping. Paragraph boundaries and reading order need review.</p>
        <div className="max-h-96 overflow-auto">{recovered.view.text_blocks.map(block => <div key={block.id} className="border-b border-border/60 py-2">
          <span className="font-mono text-[10px] text-faint" title={`Source words: ${block.ocr_word_ids.join(", ")}`}>{block.id}{block.table_associations.length > 0 ? " · includes table text" : ""}</span>
          <p className="whitespace-pre-wrap text-xs leading-relaxed">{block.text}</p>
        </div>)}</div>
      </details>}
      <details className="mt-3" open><summary className="cursor-pointer text-xs">All recovered text · {recovered.view.lines.length} source-linked lines</summary>
        <div className="mt-2 max-h-96 overflow-auto">{recovered.view.lines.map(line => <div key={line.id} className="border-b border-border/60 py-2">
          <span className="font-mono text-[10px] text-faint" title={`Source words: ${line.word_ids.join(", ")}`}>{line.id}</span>
          <p className="whitespace-pre-wrap text-xs leading-relaxed">{line.text}</p>
        </div>)}</div>
      </details>
    </>}
  </details>;
}
