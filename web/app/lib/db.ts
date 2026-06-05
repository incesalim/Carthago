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

/** Default cache window for D1 reads. Data changes daily at most, so a 12h
 *  window keeps pages fresh enough while keeping KV writes well under the free
 *  tier's 1,000 writes/day cap (each cache miss / revalidation = one KV write).
 *  A 1h window risked exceeding that on a busy day, which silently disables the
 *  cache and sends reads back to D1. */
export const DATA_REVALIDATE_SECONDS = 43200; // 12h

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
