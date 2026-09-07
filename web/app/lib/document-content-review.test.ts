import { readFileSync } from "node:fs";
import { describe, expect, it, vi } from "vitest";
import { getContentReviews } from "./document-content-review";
import { parseCorpusRevision, type CorpusBucket, type FilingIdentity } from "./document-corpus";

vi.mock("@opennextjs/cloudflare", () => ({ getCloudflareContext: vi.fn() }));
const fixture = JSON.parse(readFileSync(new URL("../../../tests/fixtures/document_corpus_wire.json", import.meta.url), "utf8"));
const receipt = JSON.parse(readFileSync(new URL("../../../tests/fixtures/document_content_review_wire.json", import.meta.url), "utf8"));
const filing: FilingIdentity = { bank_ticker: "TEST", period: "2026Q1", kind: "consolidated" };
const revision = parseCorpusRevision(fixture.index, filing)!;
const bucketFor = (value: unknown) => ({ get: vi.fn(async (key: string) => {
  const bytes = Buffer.from(fixture.source_gzip, "base64");
  return key === revision.evidence_key ? { size: bytes.length, uploaded: new Date(0),
    body: new ReadableStream<Uint8Array>({ start(c) { c.enqueue(bytes); c.close(); } }), json: async (): Promise<unknown> => null }
    : { size: 100, uploaded: new Date(0), json: async (): Promise<unknown> => value };
}) }) as unknown as CorpusBucket;

describe("source-bound content notes", () => {
  it("rechecks the Python receipt against both native source pages", async () => {
    const index = { ...structuredClone(fixture.index), resume_receipt: receipt };
    expect(await getContentReviews(bucketFor(index), filing, revision)).toEqual(receipt.source_benchmark.checks[0].content_reviews);
  });
  it("returns no registered notes for older captures", async () => {
    expect(await getContentReviews(bucketFor(fixture.index), filing, revision)).toEqual([]);
  });
  it.each(["pdf", "native", "receipt", "figure", "page", "span", "duplicate", "bbox", "page_hash", "approval", "status", "benchmark"])("rejects invalid %s binding", async mutation => {
    const index = { ...structuredClone(fixture.index), resume_receipt: structuredClone(receipt) };
    const check = index.resume_receipt.source_benchmark.checks[0];
    const review = check.content_reviews[0];
    const point = review.points[0];
    if (mutation === "pdf") index.current.source.pdf_sha256 = "0".repeat(64);
    if (mutation === "native") index.resume_receipt.evidence_artifact_sha256 = "0".repeat(64);
    if (mutation === "receipt") index.resume_receipt.schema_version = "other";
    if (mutation === "figure") point.source_text += " invented";
    if (mutation === "page") point.page = 2;
    if (mutation === "span") point.source_span_ids = [999];
    if (mutation === "duplicate") point.source_span_ids.push(point.source_span_ids[0]);
    if (mutation === "bbox") point.bbox[2] = point.bbox[0] + 1;
    if (mutation === "page_hash") point.source_page_artifact_sha256 = "0".repeat(64);
    if (mutation === "approval") review.semantic_verification = "verified";
    if (mutation === "status") review.status = "resolved";
    if (mutation === "benchmark") check.passed = false;
    await expect(getContentReviews(bucketFor(index), filing, revision)).rejects.toThrow();
  });
});
