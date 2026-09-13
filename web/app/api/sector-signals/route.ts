import { loadSignalSnapshot } from "@/app/lib/sector-signals";

export const dynamic = "force-dynamic";

/** Read-only research input. No analyst runs, editorial writes or publication. */
export async function GET() {
  const snapshot = await loadSignalSnapshot();
  return Response.json(snapshot, {
    status: snapshot.signals.length === 0 && snapshot.failedSectors.length > 0 ? 503 : 200,
    headers: { "Cache-Control": "no-store" },
  });
}
