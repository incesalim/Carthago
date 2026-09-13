import { loadSignalSnapshot } from "../../../lib/sector-signals";
import { requireAdminOr403 } from "../../../lib/admin-auth";

export const dynamic = "force-dynamic";

/** Read-only research input. No analyst runs, editorial writes or publication. */
export async function GET() {
  const gate = await requireAdminOr403();
  if ("response" in gate) {
    gate.response.headers.set("Cache-Control", "private, no-store");
    gate.response.headers.set("X-Robots-Tag", "noindex, nofollow");
    return gate.response;
  }
  const snapshot = await loadSignalSnapshot();
  return Response.json(snapshot, {
    status: snapshot.signals.length === 0 && snapshot.failedSectors.length > 0 ? 503 : 200,
    headers: { "Cache-Control": "private, no-store", "X-Robots-Tag": "noindex, nofollow" },
  });
}
