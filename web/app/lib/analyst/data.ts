/**
 * The analyst layer's database seam.
 *
 * Every analyst module takes a `Queryable` instead of touching `getDB()` so the
 * SAME assembly code runs in two places: the Worker (D1 via `cachedAll`) and
 * the CI generation script (`web/scripts/analyst-run.mjs`, node:sqlite over the
 * R2-pulled snapshot with the bulletin DB attached). There is no local
 * miniflare seed in this repo — injection is the only portable seam.
 */
import { cachedAll } from "../db";

export interface Queryable {
  all<T = Record<string, unknown>>(sql: string, binds?: unknown[]): Promise<T[]>;
}

/** Worker-side adapter. KV-cached like every dashboard read. */
export function d1Queryable(revalidate?: number): Queryable {
  return {
    all: <T>(sql: string, binds: unknown[] = []) => cachedAll<T>(sql, binds, revalidate),
  };
}

/** One row or null — the `.first()` idiom over the seam. */
export async function firstRow<T>(
  db: Queryable,
  sql: string,
  binds: unknown[] = [],
): Promise<T | null> {
  const rows = await db.all<T>(sql, binds);
  return rows.length ? rows[0] : null;
}
