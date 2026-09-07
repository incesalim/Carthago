import { readFileSync } from "node:fs";
import { gunzipSync, gzipSync } from "node:zlib";
import { createHash } from "node:crypto";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { getRecoveryIndex, readRecoveryPage } from "./document-recovery";
import type { CorpusBucket } from "./document-corpus";

const mocks = vi.hoisted(() => ({ gate: vi.fn(), context: vi.fn() }));
vi.mock("@opennextjs/cloudflare", () => ({ getCloudflareContext: mocks.context }));
vi.mock("@/app/lib/admin-auth", () => ({ requireAdminOr403: mocks.gate }));
vi.mock("@/app/lib/document-corpus", () => import("./document-corpus"));
vi.mock("@/app/lib/document-recovery", () => import("./document-recovery"));
vi.mock("@/app/lib/document-related", () => import("./document-related"));
vi.mock("@/app/lib/document-editions", () => import("./document-editions"));
import { GET } from "../api/admin/document-recovery/route";

const fixture = JSON.parse(readFileSync(new URL("../../../tests/fixtures/document_recovery_wire.json", import.meta.url), "utf8"));
const source = fixture.core_index.current;
const stream = (bytes: Uint8Array) => new ReadableStream<Uint8Array>({ start(c) { c.enqueue(bytes); c.close(); } });
const objects = Object.fromEntries(Object.entries(fixture.objects_gzip).map(([key, value]) =>
  [key, gunzipSync(Buffer.from(value as string, "base64"))]));
function bucket(index = fixture.index, mutate?: (b: Buffer) => Buffer): CorpusBucket {
  return { get: vi.fn(async (key: string) => {
    if (key.includes("/filings/")) return { size: 2000, uploaded: new Date(), body: stream(new Uint8Array()), json: async () => fixture.core_index };
    if (key.includes("/recovery/TEST/")) return { size: 2000, uploaded: new Date(), body: stream(new Uint8Array()), json: async () => index };
    const original = objects[key];
    if (!original) return null;
    const bytes = mutate ? mutate(original) : original;
    return { size: original.length, uploaded: new Date(), body: stream(bytes), json: async () => JSON.parse(bytes.toString()) };
  }) } as unknown as CorpusBucket;
}
const entry = fixture.index.pages["1"].current.artifacts.page;
const url = "https://test/api/admin/document-recovery?filing=TEST%7C2026Q1%7Cconsolidated&page=1";

describe("source-bound recovery wire format", () => {
  it("reads the Python-produced packet and retains disclosed zero", async () => {
    expect(await getRecoveryIndex(bucket(), source)).toEqual(fixture.index);
    const value = await readRecoveryPage(bucket(), entry, source, 1);
    expect(value.view.lines[0].text).toBe("Disclosed zero 0 and unknown");
    expect(value.semantically_verified).toBe(false);
  });
  it("rejects another source's index, page number and arbitrary storage keys", async () => {
    const index = structuredClone(fixture.index);
    index.source.pdf_sha256 = "b".repeat(64);
    await expect(getRecoveryIndex(bucket(index), source)).rejects.toThrow("source mismatch");
    const wrong = structuredClone(fixture.index);
    wrong.pages["1"].current.artifacts.page.key = "private/unrelated.json";
    await expect(getRecoveryIndex(bucket(wrong), source)).rejects.toThrow("outside");
    await expect(readRecoveryPage(bucket(), entry, source, 2)).rejects.toThrow("source mismatch");
  });
  it("rejects changed bytes and source identity even if a new checksum is supplied", async () => {
    await expect(readRecoveryPage(bucket(fixture.index, b => Buffer.concat([b, Buffer.from("changed")])), entry, source, 1)).rejects.toThrow();
    const packet = JSON.parse(gunzipSync(objects[entry.key]).toString());
    packet.source.pdf_sha256 = "a".repeat(64);
    const bytes = gzipSync(JSON.stringify(packet));
    const bad = { ...entry, bytes: bytes.length, sha256: createHash("sha256").update(bytes).digest("hex") };
    const mocked = { get: async () => ({ size: bytes.length, body: stream(bytes) }) } as unknown as CorpusBucket;
    await expect(readRecoveryPage(mocked, bad, source, 1)).rejects.toThrow("source mismatch");
  });
  it("keeps an unresolved cell distinct from OCR zero and rejects a false resolved value", async () => {
    const packet = JSON.parse(gunzipSync(objects[entry.key]).toString());
    const cell = { column: 0, candidate_text: null as string | null, candidate_method: "unresolved_outline",
      ocr_text: "0", outline_text: null, ocr_word_ids: [2], drawing_ids: [], unresolved_drawing_ids: [1], recognition_verified: false };
    packet.view.table_layout = { tables: [{ id: "p1:grid0", row_count: 1, n_cols: 1, header_text: "",
      header_association_verified: false, table_structure_verified: false, rows: [{ index: 0, cells: [cell] }] }] };
    const read = () => {
      const bytes = gzipSync(JSON.stringify(packet));
      const ref = { ...entry, bytes: bytes.length, sha256: createHash("sha256").update(bytes).digest("hex") };
      const store = { get: async () => ({ size: bytes.length, body: stream(bytes) }) } as unknown as CorpusBucket;
      return readRecoveryPage(store, ref, source, 1);
    };
    expect((await read()).view.table_layout?.tables[0].rows[0].cells[0].candidate_text).toBeNull();
    cell.candidate_text = "0";
    await expect(read()).rejects.toThrow("contradicts");
    cell.candidate_text = null;
    cell.candidate_method = "unobserved";
    cell.ocr_text = "";
    cell.ocr_word_ids = [];
    cell.unresolved_drawing_ids = [];
    expect((await read()).view.table_layout?.tables[0].rows[0].cells[0].candidate_text).toBeNull();
    cell.ocr_text = "0";
    await expect(read()).rejects.toThrow("contradicts");
  });
  it("retains source transcription disagreements without approving the image reading", async () => {
    const packet = JSON.parse(gunzipSync(objects[entry.key]).toString());
    const check = { id: "bank", source_bbox: [10, 20, 100, 40], source_transcription: "İstanbul",
      observed_text: "Istanbul", passed: false };
    packet.benchmarks = { text_regions: { status: "source_disagreement", checks: [check] } };
    const read = () => {
      const bytes = gzipSync(JSON.stringify(packet));
      const ref = { ...entry, bytes: bytes.length, sha256: createHash("sha256").update(bytes).digest("hex") };
      const store = { get: async () => ({ size: bytes.length, body: stream(bytes) }) } as unknown as CorpusBucket;
      return readRecoveryPage(store, ref, source, 1);
    };
    expect((await read()).benchmarks?.text_regions?.checks[0]).toEqual(check);
    check.source_bbox = [10, 20];
    await expect(read()).rejects.toThrow("Invalid source text comparison");
  });
  it("keeps font readings source-bound and rejects a fabricated approval or count", async () => {
    const packet = JSON.parse(gunzipSync(objects[entry.key]).toString());
    const font = { schema_version: "embedded-font-mapping-page-1", source: structuredClone(packet.source),
      page: 1, coordinate_space: "display", mapped_characters: 1, bound_characters: 1,
      missing_unicode_trace_characters: 1, unresolved_characters: 0, unbound_missing_trace_characters: 0,
      replacements: [{ native_text: "x", candidate_text: "İ" }],
      spans: [{ id: 0, native_text: "xstanbul", candidate_text: "İstanbul" }],
      blocks: [{ id: "p1:font_block0", text: "İstanbul", source_span_ids: [0], font_word_ids: [0],
        recognition_verified: false, reading_order_verified: false, paragraph_boundaries_verified: false }],
      recognition_verified: false, reading_order_verified: false };
    packet.font_mapping = font;
    const read = () => {
      const bytes = gzipSync(JSON.stringify(packet));
      const ref = { ...entry, bytes: bytes.length, sha256: createHash("sha256").update(bytes).digest("hex") };
      const store = { get: async () => ({ size: bytes.length, body: stream(bytes) }) } as unknown as CorpusBucket;
      return readRecoveryPage(store, ref, source, 1);
    };
    expect((await read()).font_mapping?.blocks[0].text).toBe("İstanbul");
    font.recognition_verified = true;
    await expect(read()).rejects.toThrow("Invalid source font mapping");
    font.recognition_verified = false;
    font.mapped_characters = 2;
    await expect(read()).rejects.toThrow("Invalid source font mapping");
    font.mapped_characters = 1;
    font.source.pdf_sha256 = "0".repeat(64);
    await expect(read()).rejects.toThrow("Invalid source font mapping");
  });
});

describe("private recovery route", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.gate.mockResolvedValue({ identity: { email: "test" } });
    mocks.context.mockResolvedValue({ env: { AUDIT_DOCUMENTS: bucket() } });
  });
  it("blocks anonymous reads before accessing storage", async () => {
    mocks.gate.mockResolvedValue({ response: Response.json({}, { status: 403 }) });
    const r = await GET(new Request(url));
    expect(r.status).toBe(403);
    expect(r.headers.get("Cache-Control")).toBe("private, no-store");
    expect(mocks.context).not.toHaveBeenCalled();
  });
  it("serves a verified page and its retained image-bearing PDF privately", async () => {
    const r = await GET(new Request(url));
    expect(r.status).toBe(200);
    expect((await r.json()).page.view.lines[0].text).toContain("zero 0");
    const pdf = await GET(new Request(url + "&artifact=ocr-pdf"));
    expect(pdf.headers.get("Content-Type")).toBe("application/pdf");
    expect(pdf.headers.get("Cache-Control")).toBe("private, no-store");
    expect(Buffer.from(await pdf.arrayBuffer()).subarray(0, 5).toString()).toBe("%PDF-");
  });
  it("does not reuse another PDF revision or treat missing recovery as zero text", async () => {
    mocks.context.mockResolvedValue({ env: { AUDIT_DOCUMENTS: bucket({ ...fixture.index, pages: {} }) } });
    expect(await (await GET(new Request(url))).json()).toEqual({ status: "not_started" });
    const index = structuredClone(fixture.index);
    index.source.pdf_sha256 = "b".repeat(64);
    mocks.context.mockResolvedValue({ env: { AUDIT_DOCUMENTS: bucket(index) } });
    expect((await GET(new Request(url))).status).toBe(503);
  });
});
