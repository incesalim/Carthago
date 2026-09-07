import { requireAdminOr403 } from "@/app/lib/admin-auth";
import { getCorpusBucket, parseFiling } from "@/app/lib/document-corpus";
import { getOriginReview } from "@/app/lib/document-origin";
import { readRecoveryArtifact } from "@/app/lib/document-recovery";

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
  const filing = parseFiling(params.get("filing") ?? "");
  const artifact = params.get("artifact");
  if (!filing || artifact !== null && !["origin_pdf", "transport", "source_listing"].includes(artifact)) {
    return json({ error: "Choose a registered filing and an available source artifact." }, 400);
  }
  const bucket = await getCorpusBucket();
  if (!bucket) return json({ error: "Document storage is not connected." }, 503);
  try {
    const review = await getOriginReview(bucket, filing);
    if (!artifact) return json({ review });
    const entry = artifact === "origin_pdf" ? review?.origin_pdf : artifact === "source_listing" ? review?.source_listing : review?.transport;
    if (!entry) return json({ error: "This source observation has no retained artifact of that kind." }, 404);
    const bytes = await readRecoveryArtifact(bucket, entry);
    return new Response(new Uint8Array(bytes).buffer, { headers: { ...headers,
      "Content-Type": artifact === "origin_pdf" ? "application/pdf" : "application/octet-stream",
      "Content-Length": String(bytes.length),
      "Content-Disposition": `${artifact === "origin_pdf" ? "inline" : "attachment"}; filename="${filing.bank_ticker}_${filing.period}_${filing.kind}.official.${artifact === "origin_pdf" ? "pdf" : "bin"}"`,
    } });
  } catch (error) {
    console.error("Official document origin read failed", error);
    return json({ error: "The retained source comparison could not be verified." }, 503);
  }
}
