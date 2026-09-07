import { readFileSync } from "node:fs";
import { gzipSync, gunzipSync } from "node:zlib";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { CORPUS_PREFIX, getCorpusRevision, parseCatalog, parseFiling, readVerifiedPage, type CorpusBucket } from "./document-corpus";

const mocks = vi.hoisted(() => ({ gate: vi.fn(), context: vi.fn() }));
vi.mock("@opennextjs/cloudflare", () => ({ getCloudflareContext: mocks.context }));
vi.mock("@/app/lib/admin-auth", () => ({ requireAdminOr403: mocks.gate }));
vi.mock("@/app/lib/document-corpus", () => import("./document-corpus"));
vi.mock("@/app/lib/document-related", () => import("./document-related"));
vi.mock("@/app/lib/document-editions", () => import("./document-editions"));
vi.mock("@/app/lib/document-content-review", () => import("./document-content-review"));
vi.mock("@/app/lib/document-table-review", () => import("./document-table-review"));
vi.mock("@/app/lib/document-prose", () => import("./document-prose"));
import { GET } from "../api/admin/document-corpus/route";

const fixture = JSON.parse(readFileSync(new URL("../../../tests/fixtures/document_corpus_wire.json", import.meta.url), "utf8"));
const sourceHash = fixture.index.current.source.pdf_sha256;
const filing = { bank_ticker: "TEST", period: "2026Q1", kind: "consolidated" as const };
const stream = (bytes: Uint8Array) => new ReadableStream<Uint8Array>({ start(c) { c.enqueue(bytes); c.close(); } });
const body = (kind: "source" | "structure") => stream(Buffer.from(fixture[`${kind}_gzip`], "base64"));
const indexBucket = (value: unknown) => ({ get: vi.fn(async () => ({ size: 100, json: async () => value })) }) as unknown as CorpusBucket;

describe("corpus wire format and provenance", () => {
  it("reads the Python-produced catalog and preserves unknown counts", () => {
    expect(parseCatalog(fixture.catalog).summary).toMatchObject({ registered: 1, structured_candidates: 1, semantically_verified: 0 });
    const unknown = structuredClone(fixture.catalog);
    unknown.filings[0].capture = null;
    unknown.summary.source_preserved = unknown.summary.structured_candidates = 0;
    expect(parseCatalog(unknown).filings[0].capture).toBeNull();
  });
  it("rejects inflated totals, duplicate filings and another filing's source", () => {
    for (const mutation of [
      (v: typeof fixture.catalog) => { v.summary.semantically_verified = 1; },
      (v: typeof fixture.catalog) => { v.filings.push(v.filings[0]); },
      (v: typeof fixture.catalog) => { v.filings[0].capture.source.bank_ticker = "OTHER"; },
      (v: typeof fixture.catalog) => { v.summary.source_preserved = 10; },
    ]) {
      const changed = structuredClone(fixture.catalog);
      mutation(changed);
      expect(() => parseCatalog(changed)).toThrow();
    }
  });
  it.each(["../TEST|2026Q1|consolidated", "TEST|2026Q5|consolidated", "TEST|2026Q1|../original", "TEST|2026Q1|consolidated|extra"])("refuses invalid identity %s", (value) => {
    expect(parseFiling(value)).toBeNull();
  });
  it("accepts the real Python index and refuses a key from another source", async () => {
    expect(await getCorpusRevision(indexBucket(fixture.index), filing)).toMatchObject({ page_count: 2 });
    const changed = structuredClone(fixture.index);
    changed.current.evidence_key = `${CORPUS_PREFIX}sources/${"b".repeat(64)}/${"c".repeat(64)}.jsonl.gz`;
    await expect(getCorpusRevision(indexBucket(changed), filing)).rejects.toThrow("artifact key");
  });
  it.each(["source", "structure"] as const)("verifies exact Python page bytes in %s, including float formatting", async (kind) => {
    const result = await readVerifiedPage(body(kind), 2, sourceHash, 2, kind);
    expect(result.page.page).toBe(2);
    expect(JSON.stringify(result.page)).toContain("do not substitute another filing");
  });
  it("detects changed page text, dropped pages, and mismatched source identity", async () => {
    const original = gunzipSync(Buffer.from(fixture.source_gzip, "base64")).toString("utf8");
    const changed = original.replaceAll("1,000", "9,999");
    await expect(readVerifiedPage(stream(gzipSync(changed)), 1, sourceHash, 2, "source")).rejects.toThrow("checksum");
    const dropped = original.split("\n").slice(0, 2).join("\n") + "\n";
    await expect(readVerifiedPage(stream(gzipSync(dropped)), 2, sourceHash, 2, "source")).rejects.toThrow("absent");
    await expect(readVerifiedPage(body("source"), 1, "b".repeat(64), 2, "source")).rejects.toThrow("manifest");
    await expect(readVerifiedPage(body("source"), 0, sourceHash, 2, "source")).rejects.toThrow("Invalid source page");
  });
});

describe("private corpus route", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.gate.mockResolvedValue({ identity: { email: "test" } });
  });
  it("requires admin before touching storage, including original downloads", async () => {
    mocks.gate.mockResolvedValue({ response: Response.json({ error: "forbidden" }, { status: 403 }) });
    const response = await GET(new Request("https://test/api/admin/document-corpus?filing=TEST%7C2026Q1%7Cconsolidated&artifact=original"));
    expect(response.status).toBe(403);
    expect(response.headers.get("Cache-Control")).toBe("private, no-store");
    expect(mocks.context).not.toHaveBeenCalled();
  });
  it("requires admin for reviewed table downloads too", async () => {
    mocks.gate.mockResolvedValue({ response: Response.json({ error: "forbidden" }, { status: 403 }) });
    const response = await GET(new Request("https://test/api/admin/document-corpus?filing=TEST%7C2026Q1%7Cconsolidated&artifact=table-reviews&page=1"));
    expect(response.status).toBe(403);
    expect(mocks.context).not.toHaveBeenCalled();
  });
  it("requires an explicit page and returns no reviews for an older capture", async () => {
    mocks.context.mockReturnValue({ env: { AUDIT_DOCUMENTS: indexBucket(fixture.index) } });
    const base = "https://test/api/admin/document-corpus?filing=TEST%7C2026Q1%7Cconsolidated&artifact=table-reviews";
    expect((await GET(new Request(base))).status).toBe(400);
    const response = await GET(new Request(base + "&page=1"));
    expect(response.status).toBe(200);
    expect(response.headers.get("Cache-Control")).toBe("private, no-store");
    expect(await response.json()).toMatchObject({ semantically_verified: false, tables: [] });
  });
  it("never treats a missing binding as zero coverage", async () => {
    mocks.context.mockResolvedValue({ env: {} });
    const response = await GET(new Request("https://test/api/admin/document-corpus"));
    expect(await response.json()).toEqual({ status: "not_connected" });
  });
  it("requires admin for prose before reading any report", async () => {
    mocks.gate.mockResolvedValue({ response: Response.json({ error: "forbidden" }, { status: 403 }) });
    const response = await GET(new Request("https://test/api/admin/document-corpus?filing=TEST%7C2026Q1%7Cconsolidated&artifact=prose"));
    expect(response.status).toBe(403);
    expect(mocks.context).not.toHaveBeenCalled();
  });
  it("refuses a citation after the filing's source changes", async () => {
    const bucket = indexBucket(fixture.index);
    mocks.context.mockResolvedValue({ env: { AUDIT_DOCUMENTS: bucket } });
    const response = await GET(new Request("https://test/api/admin/document-corpus?filing=TEST%7C2026Q1%7Cconsolidated&artifact=original&source_hash=" + "f".repeat(64)));
    expect(response.status).toBe(409);
    expect(bucket.get).toHaveBeenCalledTimes(1);
  });
  it("exports full structured prose privately and never accepts a partial page as a report", async () => {
    const get = vi.fn(async (key: string) => key.endsWith("consolidated.json")
      ? { size: 100, json: async () => fixture.index }
      : { size: 100, body: body(key.includes(".structure.") ? "structure" : "source") });
    mocks.context.mockResolvedValue({ env: { AUDIT_DOCUMENTS: { get } } });
    const base = "https://test/api/admin/document-corpus?filing=TEST%7C2026Q1%7Cconsolidated&artifact=prose";
    expect((await GET(new Request(base + "&page=1"))).status).toBe(400);
    const response = await GET(new Request(base + "&download=1"));
    expect(response.status).toBe(200);
    expect(response.headers.get("Cache-Control")).toBe("private, no-store");
    expect(response.headers.get("Content-Disposition")).toContain(".prose.json");
    expect(await response.json()).toMatchObject({ schema_version: "audit-prose-1", page_count: 2,
      verification: { source_text_verified: true, semantic_verification: "not_performed" } });
  });
  it("serves a verified source page and rejects invalid page numbers before artifact access", async () => {
    const get = vi.fn(async (key: string) => {
      if (key.endsWith("consolidated.json")) return { size: 100, json: async () => fixture.index };
      return { size: 100, body: body("source") };
    });
    mocks.context.mockResolvedValue({ env: { AUDIT_DOCUMENTS: { get } } });
    const base = "https://test/api/admin/document-corpus?filing=TEST%7C2026Q1%7Cconsolidated&artifact=source&page=";
    const response = await GET(new Request(base + "2"));
    expect(response.status).toBe(200);
    expect((await response.json()).page.page).toBe(2);
    expect(response.headers.get("Cache-Control")).toBe("private, no-store");
    get.mockClear();
    expect((await GET(new Request(base + "3"))).status).toBe(400);
    expect(get).toHaveBeenCalledTimes(1);
  });
});
