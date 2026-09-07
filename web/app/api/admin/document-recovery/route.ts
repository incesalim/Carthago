import { requireAdminOr403 } from "@/app/lib/admin-auth";
import { getCorpusBucket, getCorpusRevision, parseFiling } from "@/app/lib/document-corpus";
import { getRecoveryIndex, readRecoveryArtifact, readRecoveryPage } from "@/app/lib/document-recovery";
import { getRelatedRevision } from "@/app/lib/document-related";
import { getEditionRevision } from "@/app/lib/document-editions";

export const dynamic = "force-dynamic";
const headers = { "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff" };
const json = (v: unknown, status = 200) => Response.json(v, { status, headers });

export async function GET(req: Request) {
  const gate = await requireAdminOr403();
  if ("response" in gate) {
    gate.response.headers.set("Cache-Control", "private, no-store");
    return gate.response;
  }
  const params = new URL(req.url).searchParams;
  const filing = parseFiling(params.get("filing") ?? "");
  const pageText = params.get("page") ?? "";
  const page = Number(pageText);
  const artifact = params.get("artifact") ?? "page";
  const related = params.get("related");
  const edition = params.get("edition");
  const origin = params.get("origin");
  if (edition !== null && (!/^[a-f0-9]{64}$/.test(edition) || related !== null)
      || origin !== null && (!related || !/^[a-f0-9]{64}$/.test(origin))) return json({ error: "Choose one valid document source." }, 400);
  if (related !== null && !/^[a-f0-9]{64}$/.test(related)) return json({ error: "Invalid related document." }, 400);
  if (!filing || !/^\d+$/.test(pageText) || !Number.isSafeInteger(page) || page < 1
      || !["page", "ocr-pdf"].includes(artifact)) return json({ error: "Choose a valid filing, page and recovery artifact." }, 400);
  try {
    const bucket = await getCorpusBucket();
    if (!bucket) return json({ error: "Document storage is not connected." }, 503);
    const source = edition ? await getEditionRevision(bucket, filing, edition)
      : related ? await getRelatedRevision(bucket, filing, related, origin ?? undefined) : await getCorpusRevision(bucket, filing);
    if (!source) return json({ status: "source_not_captured" });
    if (page > source.page_count) return json({ error: "Page is outside this source PDF." }, 400);
    const index = await getRecoveryIndex(bucket, source);
    const row = index?.pages[String(page)];
    if (!row?.current) return json({ status: "not_started", last_attempt: row?.last_attempt });
    if (artifact === "ocr-pdf") {
      const bytes = await readRecoveryArtifact(bucket, row.current.artifacts.ocr_pdf);
      return new Response(new Uint8Array(bytes).buffer, { headers: { ...headers, "Content-Type": "application/pdf",
        "Content-Disposition": `inline; filename="${filing.bank_ticker}_${filing.period}_page${page}.ocr.pdf"` } });
    }
    return json({ status: "ready", page: await readRecoveryPage(bucket, row.current.artifacts.page, source, page),
      last_attempt: row.last_attempt });
  } catch (error) {
    console.error("Recovery read failed", error);
    return json({ error: "The stored recovery could not be verified." }, 503);
  }
}
