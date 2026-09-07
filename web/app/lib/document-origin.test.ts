import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { getOriginReview } from "./document-origin";
import type { CorpusBucket } from "./document-corpus";

const mocks = vi.hoisted(() => ({ gate: vi.fn(), context: vi.fn() }));
vi.mock("@opennextjs/cloudflare", () => ({ getCloudflareContext: mocks.context }));
vi.mock("@/app/lib/admin-auth", () => ({ requireAdminOr403: mocks.gate }));
vi.mock("@/app/lib/document-corpus", () => import("./document-corpus"));
vi.mock("@/app/lib/document-origin", () => import("./document-origin"));
vi.mock("@/app/lib/document-recovery", () => import("./document-recovery"));
import { GET } from "../api/admin/document-origin/route";

const fixture = JSON.parse(readFileSync(new URL("../../../tests/fixtures/document_origin_wire.json", import.meta.url), "utf8"));
const objects = () => Object.fromEntries(Object.entries(fixture.objects).map(([key, value]) => [key, Buffer.from(value as string, "base64")]));
const digest = (body: Buffer) => createHash("sha256").update(body).digest("hex");
function bucket(data = objects()): CorpusBucket {
  return { get: vi.fn(async (key: string) => {
    const bytes = data[key];
    if (!bytes) return null;
    return { size: bytes.length, uploaded: new Date(),
      body: new ReadableStream<Uint8Array>({ start(c) { c.enqueue(bytes); c.close(); } }),
      json: async () => JSON.parse(bytes.toString("utf8")) };
  }) } as unknown as CorpusBucket;
}
const indexKey = fixture.review.index_key;
function changedReceipt(mutate: (r: Record<string, unknown>) => void) {
  const data = objects();
  const index = JSON.parse(data[indexKey].toString());
  const review = JSON.parse(data[index.current.key].toString());
  mutate(review);
  const bytes = Buffer.from(JSON.stringify(review));
  index.current = { ...index.current, key: index.current.key.replace(/[a-f0-9]{64}\.json$/, digest(bytes) + ".json"),
    sha256: digest(bytes), bytes: bytes.length };
  index.revisions = [index.current];
  data[index.current.key] = bytes;
  data[indexKey] = Buffer.from(JSON.stringify(index));
  return data;
}
const url = "https://test/api/admin/document-origin?filing=TEST%7C2026Q1%7Cconsolidated";

const listed = JSON.parse(readFileSync(new URL("../../../tests/fixtures/document_origin_listing_wire.json", import.meta.url), "utf8"));
function listedObjects(mutate?: (review: Record<string, unknown>) => void) {
  const data = Object.fromEntries(Object.entries(listed.objects).map(([k, v]) => [k, Buffer.from(v as string, "base64")]));
  const index = JSON.parse(data[listed.review.index_key].toString());
  if (mutate) {
    const review = JSON.parse(data[index.current.key].toString());
    mutate(review);
    const bytes = Buffer.from(JSON.stringify(review));
    index.current = { ...index.current, key: index.current.key.replace(/[a-f0-9]{64}\.json$/, digest(bytes) + ".json"), sha256: digest(bytes), bytes: bytes.length };
    index.revisions = [index.current];
    data[index.current.key] = bytes;
    data[listed.review.index_key] = Buffer.from(JSON.stringify(index));
  }
  return data;
}

describe("retained regulator listing witnesses", () => {
  it("reads the independently produced Python witness", async () => {
    const review = await getOriginReview(bucket(listedObjects()), listed.filing);
    expect(review?.source_listing?.registry_name).toBe("ARAP TÜRK BANKASI A.Ş.");
    expect(review?.source_listing?.download_url).toBe(review?.source_url);
  });
  it.each(["bank", "period", "basis", "source", "host", "target", "key", "approval", "request"])("rejects a substituted %s witness", async mutation => {
    const data = listedObjects(review => {
      const listing = review.source_listing as Record<string, unknown>;
      if (mutation === "bank") listing.registry_name = "Other Bank";
      if (mutation === "period") (listing.row_cells as string[])[1] = "2025";
      if (mutation === "basis") (listing.row_cells as string[])[3] = "KONSOLIDE";
      if (mutation === "source") listing.download_url = "https://other.example/report.pdf";
      if (mutation === "host" || mutation === "target") {
        review.source_url = String(review.source_url).replace(mutation === "host" ? "www.bddk.org.tr" : "2026-06", mutation === "host" ? "other.example" : "2025-06");
        listing.download_url = review.source_url;
      }
      if (mutation === "key") listing.key = "document-corpus/v1/foreign.html";
      if (mutation === "approval") listing.semantically_verified = true;
      if (mutation === "request") (listing.response as Record<string, unknown>).method = "GET";
    });
    await expect(getOriginReview(bucket(data), listed.filing)).rejects.toThrow();
  });
});

describe("retained official-origin evidence", () => {
  it("reads the Python-produced receipt and keeps semantic verification false", async () => {
    const expected = { ...fixture.review };
    delete expected.review_key; delete expected.index_key;
    expect(await getOriginReview(bucket(), fixture.filing)).toEqual(expected);
  });
  it("treats absent comparison separately from success", async () => {
    expect(await getOriginReview(bucket({}), fixture.filing)).toBeNull();
  });
  it.each(["filing", "path", "history", "approval"])("rejects invalid %s index bindings", async change => {
    const data = objects();
    const index = JSON.parse(data[indexKey].toString());
    if (change === "filing") index.filing.period = "2026Q2";
    if (change === "path") index.current.key = "unrelated/private.json";
    if (change === "history") index.revisions = [];
    if (change === "approval") index.semantically_verified = true;
    data[indexKey] = Buffer.from(JSON.stringify(index));
    await expect(getOriginReview(bucket(data), fixture.filing)).rejects.toThrow();
  });
  it.each(["filing", "path", "status", "approval", "different_hash", "identity", "acquisition"])(
    "rejects %s receipt mutation even with a recomputed checksum", async change => {
      const data = changedReceipt(r => {
        if (change === "filing") (r.filing as Record<string, unknown>).period = "2026Q2";
        if (change === "path") (r.origin_pdf as Record<string, unknown>).key = "private/unrelated.pdf";
        if (change === "status") r.status = "different_pdf_revision";
        if (change === "approval") r.semantically_verified = true;
        if (change === "different_hash") {
          const pdf = r.origin_pdf as Record<string, unknown>;
          pdf.sha256 = "a".repeat(64); pdf.key = `document-corpus/v1/sources/${pdf.sha256}/original.pdf`;
        }
        if (change === "identity") r.origin_identity = { status: true };
        if (change === "acquisition") r.acquisition = null;
      });
      await expect(getOriginReview(bucket(data), fixture.filing)).rejects.toThrow();
    });
  it("rejects changed receipt bytes without reading arbitrary source objects", async () => {
    const data = objects();
    data[fixture.review.review_key] = Buffer.from("corrupt");
    await expect(getOriginReview(bucket(data), fixture.filing)).rejects.toThrow();
  });
});

describe("private official-origin route", () => {
  beforeEach(() => { vi.clearAllMocks(); mocks.gate.mockResolvedValue({}); mocks.context.mockResolvedValue({ env: { AUDIT_DOCUMENTS: bucket() } }); });
  it("blocks anonymous access before reading storage", async () => {
    mocks.gate.mockResolvedValue({ response: Response.json({ error: "Forbidden" }, { status: 403 }) });
    const response = await GET(new Request(url));
    expect(response.status).toBe(403); expect(response.headers.get("Cache-Control")).toBe("private, no-store");
    expect(mocks.context).not.toHaveBeenCalled();
  });
  it("serves observed origin evidence without requiring a core capture", async () => {
    const response = await GET(new Request(url));
    expect(response.status).toBe(200);
    expect((await response.json()).review.status).toBe("matches_acquired_bytes");
    expect(response.headers.get("Cache-Control")).toBe("private, no-store");
  });
  it("verifies downloaded source bytes and refuses corruption", async () => {
    const response = await GET(new Request(url + "&artifact=origin_pdf"));
    expect(response.status).toBe(200);
    expect(digest(Buffer.from(await response.arrayBuffer()))).toBe(fixture.review.origin_pdf.sha256);
    const data = objects(); data[fixture.review.origin_pdf.key] = Buffer.from("corrupt");
    mocks.context.mockResolvedValue({ env: { AUDIT_DOCUMENTS: bucket(data) } });
    expect((await GET(new Request(url + "&artifact=origin_pdf"))).status).toBe(503);
  });
  it("rejects a user-supplied artifact key", async () => {
    expect((await GET(new Request(url + "&artifact=private/secret"))).status).toBe(400);
  });
});
