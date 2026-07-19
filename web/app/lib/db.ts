/**
 * D1 helper for Server Components and Route Handlers.
 *
 * Use `getDB()` inside server components / route handlers / server actions.
 * Returns the bound D1Database instance from the Cloudflare env.
 */
import { getCloudflareContext } from "@opennextjs/cloudflare";
import { unstable_cache } from "next/cache";

export async function getDB() {
  const { env } = await getCloudflareContext({ async: true });
  return env.DB;
}

/** Default cache window for D1 reads. Each cache miss / revalidation costs one
 *  KV write, so this is bounded by the KV write allowance, not by how fast the
 *  data moves.
 *
 *  This was 12h to stay under the Workers FREE tier's 1,000 KV writes/day —
 *  exceeding it silently disables the cache and sends every read back to D1. On
 *  the paid plan the allowance is 1,000,000 writes/month (~33k/day), so the
 *  binding constraint is gone: ~400–800 distinct cache keys at a 1h window is
 *  ~14k writes/day ≈ 430k/month, comfortably inside the included quota. */
export const DATA_REVALIDATE_SECONDS = 3600; // 1h

/**
 * Run a `SELECT … .all()` through Next's data cache (KV-backed via OpenNext),
 * keyed by the SQL text + bound params. Identical queries then hit D1 at most
 * once per revalidate window instead of on every page render.
 *
 * Pages stay dynamic (no build-time prerender of D1 data); only the *data* is
 * cached. The function reads the D1 binding via getDB(), which uses the async
 * Cloudflare context that is valid inside the cache callback.
 */
export async function cachedAll<T>(
  sql: string,
  binds: unknown[] = [],
  revalidate: number = DATA_REVALIDATE_SECONDS,
): Promise<T[]> {
  return unstable_cache(
    async () => {
      const db = await getDB();
      const { results } = await db
        .prepare(sql)
        .bind(...binds)
        .all<T>();
      return results;
    },
    ["d1all", sql, JSON.stringify(binds)],
    { revalidate },
  )();
}

export interface BalanceSheetRow {
  year: number;
  month: number;
  currency: string;
  bank_type_code: string;
  item_order: number;
  item_name: string;
  is_subtotal: number | null;
  amount_tl: number | null;
  amount_fx: number | null;
  amount_total: number | null;
}
