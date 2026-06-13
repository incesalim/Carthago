/**
 * GET /api/market-ticker — JSON for the live ticker strip's client-side poll
 * (every ~60s). Backed by the same edge-cached spark fetch as the server
 * render, so repeated polls don't re-hit Yahoo.
 */
import { getMarketTicker } from "@/app/lib/market-ticker";

export const dynamic = "force-dynamic";

export async function GET() {
  const items = await getMarketTicker();
  return Response.json(
    { items },
    { headers: { "Cache-Control": "public, max-age=60" } },
  );
}
