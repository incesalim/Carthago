/**
 * POST /api/admin/purge-cache — clear the OpenNext incremental-cache KV
 * namespace (NEXT_INC_CACHE_KV) so the dashboard re-reads D1 on the next view.
 *
 * D1 reads are cached ~12h via KV (see `web/app/lib/db.ts`), so a freshly
 * ingested bulletin / EVDS week lands in D1 but doesn't surface in the graphs
 * until that window rolls over. Dropping the cached entries (they repopulate
 * lazily from D1 on the next page view) makes a manual /admin refresh visible
 * immediately. No tag cache is configured, so `revalidateTag` is a no-op here —
 * we delete the KV entries directly via the bound namespace.
 *
 * Batched + cursor-paginated: each call lists up to BATCH keys, deletes them,
 * and returns a cursor; the client loops until `done`. Bounding the per-request
 * work keeps us well under the Worker subrequest cap — the namespace also
 * accumulates orphaned entries from past deploys (OpenNext keys by build id and
 * never GCs old builds), so it can hold thousands of keys. Admin-gated.
 */
import { getCloudflareContext } from "@opennextjs/cloudflare";
import { requireAdminOr403 } from "@/app/lib/admin-auth";

export const dynamic = "force-dynamic";

const BATCH = 500; // keys listed + deleted per request
const CONCURRENCY = 50; // concurrent kv.delete() calls per round

export async function POST(req: Request) {
  const gate = await requireAdminOr403();
  if ("response" in gate) return gate.response;

  let env: CloudflareEnv;
  try {
    ({ env } = await getCloudflareContext({ async: true }));
  } catch {
    return Response.json({ error: "no Cloudflare context (local dev?)" }, { status: 409 });
  }
  const kv = env.NEXT_INC_CACHE_KV;
  if (!kv) {
    return Response.json({ error: "NEXT_INC_CACHE_KV not bound" }, { status: 409 });
  }

  let cursor: string | undefined;
  const body = (await req.json().catch(() => ({}))) as { cursor?: unknown };
  if (typeof body.cursor === "string" && body.cursor) cursor = body.cursor;

  const list = await kv.list({ limit: BATCH, cursor });
  // NEXT_INC_CACHE_KV resolves to `any` (workers-types KVNamespace isn't a
  // checked dependency), so annotate to satisfy noImplicitAny.
  const names: string[] = list.keys.map((k: { name: string }) => k.name);
  // Delete in bounded-concurrency rounds (kv.delete is per-key).
  for (let i = 0; i < names.length; i += CONCURRENCY) {
    await Promise.all(names.slice(i, i + CONCURRENCY).map((n) => kv.delete(n)));
  }

  const done = list.list_complete;
  return Response.json({
    ok: true,
    deleted: names.length,
    cursor: done ? null : list.cursor,
    done,
  });
}
