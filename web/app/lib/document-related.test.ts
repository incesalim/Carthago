import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { getRelatedRevision } from "./document-related";
import type { CorpusBucket } from "./document-corpus";

const mocks = vi.hoisted(() => ({ gate: vi.fn(), context: vi.fn() }));
vi.mock("@opennextjs/cloudflare", () => ({ getCloudflareContext: mocks.context }));
vi.mock("@/app/lib/admin-auth", () => ({ requireAdminOr403: mocks.gate }));
vi.mock("@/app/lib/document-corpus", () => import("./document-corpus"));
vi.mock("@/app/lib/document-content-review", () => import("./document-content-review"));
vi.mock("@/app/lib/document-related", () => import("./document-related"));
vi.mock("@/app/lib/document-editions", () => import("./document-editions"));
vi.mock("@/app/lib/document-recovery", () => import("./document-recovery"));
import { GET as sourceGET } from "../api/admin/document-corpus/route";
import { GET as recoveryGET } from "../api/admin/document-recovery/route";

const fixture = JSON.parse(readFileSync(new URL("../../../tests/fixtures/document_related_wire.json", import.meta.url), "utf8"));
const identityFixture = JSON.parse(readFileSync(new URL("../../../tests/fixtures/document_related_identity_wire.json", import.meta.url), "utf8"));
const objects = () => Object.fromEntries(Object.entries(fixture.objects).map(([k, v]) => [k, Buffer.from(v as string, "base64")]));
function bucket(data = objects()): CorpusBucket {
  return { get: vi.fn(async (key: string) => {
    const body = data[key];
    if (!body) return null;
    return { size: body.length, uploaded: new Date(),
      body: new ReadableStream<Uint8Array>({ start(c) { c.enqueue(body); c.close(); } }),
      json: async () => JSON.parse(body.toString("utf8")) };
  }) } as unknown as CorpusBucket;
}
const query = `filing=TEST%7C2026Q1%7Cconsolidated&related=${fixture.member.sha256}`;
const url = `https://test/api/admin/document-corpus?${query}`;

describe("related-document provenance", () => {
  it("reads the Python-produced identity receipt while keeping the container separate", async () => {
    const data = objects();
    const index = JSON.parse(data[fixture.index_key].toString());
    index.current.related_identity_review = identityFixture.reference;
    data[fixture.index_key] = Buffer.from(JSON.stringify(index));
    data[identityFixture.reference.key] = Buffer.from(identityFixture.body, "base64");
    const revision = await getRelatedRevision(bucket(data), fixture.filing, fixture.member.sha256);
    expect(revision?.archive_identity).toEqual({ status: "unresolved", claim_page: null,
      observed_periods: [], issues: ["no_complete_identity_claim_on_one_leading_page"] });
  });
  it.each(["pdf", "native", "container", "approval", "checksum", "key"])("rejects altered identity %s bindings", async change => {
    const data = objects();
    const index = JSON.parse(data[fixture.index_key].toString());
    const packet = structuredClone(identityFixture.packet);
    if (change === "pdf") packet.source.pdf_sha256 = "a".repeat(64);
    if (change === "native") packet.evidence_artifact_sha256 = "a".repeat(64);
    if (change === "container") packet.container_filing.period = "2026Q2";
    if (change === "approval") packet.semantic_verification = "verified";
    const body = Buffer.from(JSON.stringify(packet));
    const sha256 = createHash("sha256").update(body).digest("hex");
    const key = `document-corpus/v1/sources/${fixture.member.sha256}/related-identity/${sha256}.json`;
    index.current.related_identity_review = { key, sha256, bytes: body.length };
    data[key] = body;
    if (change === "checksum") data[key][0] = 0;
    if (change === "key") index.current.related_identity_review.key = "private/unrelated.json";
    data[fixture.index_key] = Buffer.from(JSON.stringify(index));
    await expect(getRelatedRevision(bucket(data), fixture.filing, fixture.member.sha256)).rejects.toThrow();
  });
  it("reads the Python-produced archive-bound index without accessing the primary filing index", async () => {
    const store = bucket();
    expect(await getRelatedRevision(store, fixture.filing, fixture.member.sha256)).toEqual(fixture.index.current);
    expect(vi.mocked(store.get).mock.calls.every(([key]) => !key.includes("/filings/"))).toBe(true);
  });
  it("keeps a missing related capture distinct from an absent archive member", async () => {
    const data = objects(); delete data[fixture.index_key];
    expect(await getRelatedRevision(bucket(data), fixture.filing, fixture.member.sha256)).toBeNull();
    await expect(getRelatedRevision(bucket(), fixture.filing, "a".repeat(64))).rejects.toThrow("absent or ambiguous");
  });
  it.each(["member", "transport", "primary", "filing", "path", "approval"])("rejects changed %s bindings", async change => {
    const data = objects();
    const index = JSON.parse(data[fixture.index_key].toString());
    if (change === "member") index.relationship.member.name = "another.pdf";
    if (change === "transport") index.relationship.transport_sha256 = "a".repeat(64);
    if (change === "primary") index.relationship.primary_pdf_sha256 = "a".repeat(64);
    if (change === "filing") index.relationship.filing.period = "2026Q2";
    if (change === "path") index.current.original_key = "private/unrelated.pdf";
    if (change === "approval") index.current.semantic_verification = "verified";
    data[fixture.index_key] = Buffer.from(JSON.stringify(index));
    await expect(getRelatedRevision(bucket(data), fixture.filing, fixture.member.sha256)).rejects.toThrow();
  });
  it("rejects damaged origin receipts before following attachment references", async () => {
    const data = objects(); data[fixture.origin_review_key] = Buffer.from("changed");
    await expect(getRelatedRevision(bucket(data), fixture.filing, fixture.member.sha256)).rejects.toThrow();
  });
  it("cannot borrow a valid primary revision under an otherwise valid attachment relationship", async () => {
    const data = objects();
    const index = JSON.parse(data[fixture.index_key].toString());
    const oldHash = index.current.source.pdf_sha256;
    const primaryHash = index.relationship.primary_pdf_sha256;
    index.current = JSON.parse(JSON.stringify(index.current).replaceAll(oldHash, primaryHash));
    data[fixture.index_key] = Buffer.from(JSON.stringify(index));
    await expect(getRelatedRevision(bucket(data), fixture.filing, fixture.member.sha256)).rejects.toThrow("matched directly");
  });
});

describe("related source and recovery routes", () => {
  beforeEach(() => { vi.clearAllMocks(); mocks.gate.mockResolvedValue({}); mocks.context.mockResolvedValue({ env: { AUDIT_DOCUMENTS: bucket() } }); });
  it("previews the attachment's native page without borrowing the primary source", async () => {
    const response = await sourceGET(new Request(url + "&artifact=source&page=1"));
    expect(response.status).toBe(200);
    const value = await response.json();
    expect(value.manifest.source.pdf_sha256).toBe(fixture.index.current.source.pdf_sha256);
    expect(value.page.spans.some((s: { text: string }) => s.text.includes("Signed responsibility"))).toBe(true);
  });
  it("uses the related source hash for recovery and reports missing recovery separately", async () => {
    const store = bucket(); mocks.context.mockResolvedValue({ env: { AUDIT_DOCUMENTS: store } });
    const response = await recoveryGET(new Request(`https://test/api/admin/document-recovery?${query}&page=1`));
    expect(response.status).toBe(200); expect((await response.json()).status).toBe("not_started");
    expect(vi.mocked(store.get).mock.calls.at(-1)?.[0]).toContain(fixture.index.current.source.pdf_sha256);
  });
  it("rejects arbitrary related keys and out-of-range related pages", async () => {
    expect((await sourceGET(new Request(url.replace(fixture.member.sha256, "../private")))).status).toBe(400);
    expect((await recoveryGET(new Request(`https://test/api/admin/document-recovery?${query}&page=2`))).status).toBe(400);
  });
  it("requires authentication on both related routes", async () => {
    for (const handler of [sourceGET, recoveryGET]) {
      mocks.gate.mockResolvedValue({ response: Response.json({ error: "Forbidden" }, { status: 403 }) });
      const response = await handler(new Request(url + "&page=1"));
      expect(response.status).toBe(403); expect(response.headers.get("Cache-Control")).toBe("private, no-store");
    }
    expect(mocks.context).not.toHaveBeenCalled();
  });
});
