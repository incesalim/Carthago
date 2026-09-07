/** Private source evidence, addressed by validated filing identity, never by user-supplied storage keys. */
import { requireAdminOr403 } from "@/app/lib/admin-auth";
import { getCorpusBucket, getCorpusCatalog, getCorpusRevision, parseFiling, readVerifiedPage } from "@/app/lib/document-corpus";
import { getRelatedRevision } from "@/app/lib/document-related";
import { getContentReviews } from "@/app/lib/document-content-review";

export const dynamic = "force-dynamic";
const headers = { "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff" };
const json = (value: unknown, status = 200) => Response.json(value, { status, headers });

export async function GET(req: Request) {
  const gate = await requireAdminOr403();
  if ("response" in gate) {
    gate.response.headers.set("Cache-Control", "private, no-store");
    return gate.response;
  }
  const params = new URL(req.url).searchParams;
  if (!params.has("filing")) return json(await getCorpusCatalog());
  const filing = parseFiling(params.get("filing") ?? "");
  if (!filing) return json({ error: "Use BANK|YYYYQn|consolidated or unconsolidated." }, 400);
  const artifact = params.get("artifact");
  const related = params.get("related");
  if (related !== null && !/^[a-f0-9]{64}$/.test(related)) return json({ error: "Invalid related document." }, 400);
  if (artifact !== null && !["original", "source", "structure", "reviews"].includes(artifact)) {
    return json({ error: "Unknown document artifact." }, 400);
  }
  const bucket = await getCorpusBucket();
  if (!bucket) return json({ error: "Document storage is not connected." }, 503);
  try {
    const revision = related ? await getRelatedRevision(bucket, filing, related) : await getCorpusRevision(bucket, filing);
    if (!revision) return json({ error: related ? "This related PDF has not been captured yet."
      : "This filing has no successful source capture yet." }, 404);
    if (!artifact) return json({ revision });
    if (artifact === "reviews") {
      if (related) return json({ error: "Content notes for related attachments are not registered here." }, 400);
      return json({ source: revision.source, scope: "registered_open_notes_only",
        semantically_verified: false, findings: await getContentReviews(bucket, filing, revision) });
    }
    const pageText = params.get("page");
    const page = Number(pageText);
    if (pageText !== null && (!/^\d+$/.test(pageText) || !Number.isSafeInteger(page) || page < 1 || page > revision.page_count)) {
      return json({ error: `Page must be between 1 and ${revision.page_count}.` }, 400);
    }
    const key = artifact === "original" ? revision.original_key
      : artifact === "source" ? revision.evidence_key : revision.structure_current?.key;
    if (!key) return json({ error: "Structure has not been captured for this source revision." }, 404);
    if (pageText !== null && artifact !== "original" && !key.endsWith(".jsonl.gz")) {
      return json({ error: "This older capture needs updating before page preview is available." }, 409);
    }
    const object = await bucket.get(key);
    if (!object) return json({ error: "The indexed artifact is missing from storage." }, 503);
    if (pageText !== null && artifact !== "original") {
      return json(await readVerifiedPage(object.body, page, revision.source.pdf_sha256, revision.page_count,
        artifact === "source" ? "source" : "structure"));
    }
    const name = `${filing.bank_ticker}_${filing.period}_${filing.kind}`;
    return new Response(object.body, { headers: { ...headers,
      "Content-Type": artifact === "original" ? "application/pdf" : "application/gzip",
      "Content-Length": String(object.size),
      "Content-Disposition": artifact === "original" ? `inline; filename="${name}.pdf"`
        : `attachment; filename="${name}.${artifact}.${key.endsWith('.jsonl.gz') ? 'jsonl' : 'json'}.gz"`,
    } });
  } catch (error) {
    console.error("Document corpus read failed", error);
    return json({ error: "The stored document could not be verified. Review the capture before using it." }, 503);
  }
}
