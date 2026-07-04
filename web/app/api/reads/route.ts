/**
 * GET /api/reads — the deterministic "The Read" takeaways for every registered
 * tab (headline + bullet text + a content hash), computed server-side via
 * reads.ts. The weekly headline generator (scripts/generate_read_headlines.py)
 * reads this, rewrites each headline with the LLM, and upserts read_headlines.
 *
 * Returns only already-public dashboard copy, so it is not admin-gated. The
 * `det_hash` here is exactly what read-headlines.ts recomputes on render to gate
 * whether a cached rewrite is still fresh.
 */
import { computeReads } from "@/app/lib/reads";
import { takeawayHash } from "@/app/lib/read-headlines";

export const dynamic = "force-dynamic";

export async function GET() {
  const reads = await computeReads();
  return Response.json(
    reads.map((r) => ({
      tab: r.tab,
      headline: r.takeaway.headline,
      items: r.takeaway.items.map((i) => i.text),
      det_hash: takeawayHash(r.takeaway),
    })),
  );
}
