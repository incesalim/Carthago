import { readFileSync } from "node:fs";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { getEditionRevision } from "./document-editions";
import { getOriginObservations, getOriginReview } from "./document-origin";
import type { CorpusBucket } from "./document-corpus";

const mocks = vi.hoisted(() => ({ gate: vi.fn(), context: vi.fn() }));
vi.mock("@opennextjs/cloudflare", () => ({ getCloudflareContext: mocks.context }));
vi.mock("@/app/lib/admin-auth", () => ({ requireAdminOr403: mocks.gate }));
vi.mock("@/app/lib/document-corpus", () => import("./document-corpus"));
vi.mock("@/app/lib/document-related", () => import("./document-related"));
vi.mock("@/app/lib/document-editions", () => import("./document-editions"));
vi.mock("@/app/lib/document-origin", () => import("./document-origin"));
vi.mock("@/app/lib/document-recovery", () => import("./document-recovery"));
vi.mock("@/app/lib/document-content-review", () => import("./document-content-review"));
import { GET as corpusGet } from "../api/admin/document-corpus/route";
import { GET as recoveryGet } from "../api/admin/document-recovery/route";
import { GET as originGet } from "../api/admin/document-origin/route";

const fixture = JSON.parse(readFileSync(new URL("../../../tests/fixtures/document_edition_wire.json", import.meta.url), "utf8"));
const objects = () => Object.fromEntries(Object.entries(fixture.objects).map(([key, value]) => [key, Buffer.from(value as string, "base64")]));
function bucket(data = objects()): CorpusBucket {
  return { get: vi.fn(async (key: string) => {
    const bytes = data[key];
    if (!bytes) return null;
    return { size: bytes.length, uploaded: new Date(), body: new ReadableStream<Uint8Array>({ start(c) { c.enqueue(bytes); c.close(); } }),
      json: async () => JSON.parse(bytes.toString("utf8")) };
  }) } as unknown as CorpusBucket;
}
const query = `filing=TEST%7C2026Q1%7Cconsolidated&edition=${fixture.observation}`;

describe("separately captured official PDF editions", () => {
  it("retains both a different edition and a later exact match", async () => {
    const observations = await getOriginObservations(bucket(), fixture.filing);
    expect(observations.map(o => o.review.status)).toEqual(["matches_acquired_bytes", "different_pdf_revision"]);
    expect(observations.map(o => o.current)).toEqual([true, false]);
    expect((await getOriginReview(bucket(), fixture.filing, fixture.observation))?.status).toBe("different_pdf_revision");
    const revision = await getEditionRevision(bucket(), fixture.filing, fixture.observation);
    expect(revision?.source.pdf_sha256).toBe(fixture.different_review.origin_pdf.sha256);
    expect(revision?.page_count).toBe(1);
  });
  it("reports an edition with no capture separately from source absence", async () => {
    const data = objects(); delete data[fixture.edition_key];
    expect(await getEditionRevision(bucket(data), fixture.filing, fixture.observation)).toBeNull();
  });
  it.each(["binding", "pdf", "url", "approval", "reference", "reference_bytes", "foreign_reference", "history"])("rejects substituted %s", async mutation => {
    const data = objects(); const index = JSON.parse(data[fixture.edition_key].toString());
    if (mutation === "binding") index.edition.filing.period = "2026Q2";
    if (mutation === "pdf") index.edition.pdf_sha256 = "a".repeat(64);
    if (mutation === "url") index.current.source.source_url = "https://invented.example/pdf";
    if (mutation === "approval") index.current.semantic_verification = "verified";
    if (mutation === "reference") index.origin_observations = [];
    if (mutation === "reference_bytes") index.origin_observations[0].bytes += 1;
    if (mutation === "foreign_reference") index.origin_observations[0].key = "private/foreign.json";
    if (mutation === "history") {
      const origins = JSON.parse(data[fixture.different_review.index_key].toString());
      origins.revisions = [origins.current]; data[fixture.different_review.index_key] = Buffer.from(JSON.stringify(origins));
    }
    data[fixture.edition_key] = Buffer.from(JSON.stringify(index));
    await expect(getEditionRevision(bucket(data), fixture.filing, fixture.observation)).rejects.toThrow();
  });
  it("does not treat the later matching observation as a different edition", async () => {
    const latest = fixture.latest_review.review_key.split("/").at(-1).replace(".json", "");
    await expect(getEditionRevision(bucket(), fixture.filing, latest)).rejects.toThrow();
    await expect(getOriginReview(bucket(), fixture.filing, "a".repeat(64))).rejects.toThrow();
  });
});

describe("private edition and historical-origin routes", () => {
  beforeEach(() => { vi.clearAllMocks(); mocks.gate.mockResolvedValue({}); mocks.context.mockResolvedValue({ env: { AUDIT_DOCUMENTS: bucket() } }); });
  it("denies anonymous access before reading edition storage", async () => {
    mocks.gate.mockResolvedValue({ response: Response.json({ error: "Forbidden" }, { status: 403 }) });
    expect((await corpusGet(new Request(`https://test/?${query}`))).status).toBe(403);
    expect(mocks.context).not.toHaveBeenCalled();
  });
  it("serves edition native and structure pages without a main filing index", async () => {
    for (const artifact of ["source", "structure"]) {
      const response = await corpusGet(new Request(`https://test/?${query}&artifact=${artifact}&page=1`));
      expect(response.status).toBe(200);
      expect(response.headers.get("Cache-Control")).toBe("private, no-store");
      const value = await response.json(); expect(value.page.page).toBe(1);
    }
    expect((await recoveryGet(new Request(`https://test/?${query}&page=1`))).status).toBe(200);
  });
  it("serves all origin observations and exact historical source bytes", async () => {
    const url = "https://test/?filing=TEST%7C2026Q1%7Cconsolidated";
    const all = await (await originGet(new Request(url))).json();
    expect(all.observations).toHaveLength(2);
    const pdf = await originGet(new Request(`${url}&observation=${fixture.observation}&artifact=origin_pdf`));
    expect(Buffer.from(await pdf.arrayBuffer())).toEqual(objects()[fixture.different_review.origin_pdf.key]);
  });
  it.each(["&related=" + "a".repeat(64), "&origin=" + "a".repeat(64)])("rejects ambiguous source selectors %s", async suffix => {
    expect((await corpusGet(new Request(`https://test/?${query}${suffix}`))).status).toBe(400);
    expect((await recoveryGet(new Request(`https://test/?${query}${suffix}&page=1`))).status).toBe(400);
  });
  it("does not attach main-filing review notes to an edition", async () => {
    expect((await corpusGet(new Request(`https://test/?${query}&artifact=reviews`))).status).toBe(400);
  });
});
