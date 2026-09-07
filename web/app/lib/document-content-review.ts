/** Open analyst notes with source passages rechecked before display. */
import { CORPUS_PREFIX, parseCorpusRevision, readVerifiedPage, type CorpusBucket, type CorpusRevision, type FilingIdentity } from "./document-corpus";

const record = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);
const box = (v: unknown): v is number[] => Array.isArray(v) && v.length === 4 && v.every(n => typeof n === "number" && Number.isFinite(n)) && v[0] < v[2] && v[1] < v[3];
export type ContentReview = { id: string; kind: "source_review"; title: string; note: string; status: "open";
  semantic_verification: "not_performed"; points: { page: number; bbox: number[]; source_span_ids: number[];
    source_text: string; source_page_artifact_sha256: string }[] };

export async function getContentReviews(bucket: CorpusBucket, filing: FilingIdentity, revision: CorpusRevision): Promise<ContentReview[]> {
  const object = await bucket.get(`${CORPUS_PREFIX}filings/${filing.bank_ticker}/${filing.period}/${filing.kind}.json`);
  if (!object || object.size > 8_000_000) throw new Error("Missing or oversized review index");
  const index: unknown = await object.json();
  const current = parseCorpusRevision(index, filing);
  if (!current || current.source.pdf_sha256 !== revision.source.pdf_sha256 || current.evidence_key !== revision.evidence_key) {
    throw new Error("Source changed while loading its content reviews");
  }
  const receipt = record(index) && record(index.resume_receipt) ? index.resume_receipt : null;
  const benchmark = receipt && record(receipt.source_benchmark) ? receipt.source_benchmark : null;
  if (!benchmark) return [];
  if (!Array.isArray(benchmark.checks) || benchmark.checks.length > 100) throw new Error("Invalid review checks");
  const findings: unknown[] = [];
  for (const check of benchmark.checks) {
    if (!record(check)) throw new Error("Invalid review check");
    if (check.content_reviews === undefined) continue;
    if (check.passed !== true || !Array.isArray(check.content_reviews)) throw new Error("Unverified review references");
    findings.push(...check.content_reviews);
  }
  if (!findings.length) return [];
  if (!receipt || receipt.schema_version !== "corpus-receipt-1" || benchmark.status !== "passed"
      || benchmark.scope !== "annotated_cases_only" || findings.length > 100
      || revision.evidence_key !== `${CORPUS_PREFIX}sources/${revision.source.pdf_sha256}/${receipt.evidence_artifact_sha256}.jsonl.gz`) {
    throw new Error("Content reviews differ from the current native source");
  }
  const pages = new Map<number, Awaited<ReturnType<typeof readVerifiedPage>>>();
  const ids = new Set<string>();
  for (const finding of findings) {
    if (!record(finding) || finding.kind !== "source_review" || finding.status !== "open"
        || finding.semantic_verification !== "not_performed"
        || !["id", "title", "note"].every(k => typeof finding[k] === "string" && finding[k].trim())
        || !Array.isArray(finding.points) || finding.points.length < 2 || finding.points.length > 20
        || ids.has(String(finding.id))) throw new Error("Invalid open content review");
    ids.add(String(finding.id));
    for (const point of finding.points) {
      if (!record(point) || typeof point.page !== "number" || !Number.isSafeInteger(point.page)
          || point.page < 1 || point.page > revision.page_count || !box(point.bbox)
          || typeof point.source_text !== "string" || !Array.isArray(point.source_span_ids)
          || !point.source_span_ids.length || !point.source_span_ids.every((n, i, all) => typeof n === "number"
            && Number.isSafeInteger(n) && n >= 0 && (i === 0 || n > all[i - 1]))) throw new Error("Invalid review source point");
      if (!pages.has(point.page)) {
        const source = await bucket.get(revision.evidence_key);
        if (!source) throw new Error("Missing native review evidence");
        pages.set(point.page, await readVerifiedPage(source.body, point.page, revision.source.pdf_sha256, revision.page_count, "source"));
      }
      const saved = pages.get(point.page)!;
      if (!Array.isArray(saved.manifest.page_sha256) || saved.manifest.page_sha256[point.page - 1] !== point.source_page_artifact_sha256
          || !Array.isArray(saved.page.spans)) throw new Error("Review page checksum mismatch");
      const spans = point.source_span_ids.map(id => (saved.page.spans as unknown[]).filter(s => record(s) && s.id === id));
      const bounds = point.bbox;
      if (spans.some(s => s.length !== 1) || spans.some(([s]) => !record(s) || !box(s.bbox)
          || s.bbox[0] < bounds[0] || s.bbox[1] < bounds[1] || s.bbox[2] > bounds[2] || s.bbox[3] > bounds[3])
          || spans.map(([s]) => (s as Record<string, unknown>).text).join("\n") !== point.source_text) {
        throw new Error("Review passage differs from retained source spans");
      }
    }
  }
  return findings as ContentReview[];
}
