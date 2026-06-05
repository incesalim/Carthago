/**
 * Read environment bindings (vars + secrets) for server code.
 *
 * Merges `process.env` (available under `next dev`) with the Cloudflare Worker
 * env from OpenNext (available in `preview`/production). Cloudflare bindings win.
 * Only string-valued vars/secrets are meant to be read through here — the D1
 * binding still goes through `getDB()` in `db.ts`.
 */
import { getCloudflareContext } from "@opennextjs/cloudflare";

export type StringEnv = Record<string, string | undefined>;

export async function getEnv(): Promise<StringEnv> {
  let cf: StringEnv = {};
  try {
    const { env } = await getCloudflareContext({ async: true });
    cf = env as unknown as StringEnv;
  } catch {
    // Not running inside a Cloudflare context (plain `next dev`) — fall back to
    // process.env only.
  }
  return { ...(process.env as StringEnv), ...cf };
}

/** Truthy check for boolean-ish env flags ("1"/"true"/"yes"). */
export function envFlag(v: string | undefined): boolean {
  if (!v) return false;
  const s = v.toLowerCase();
  return s !== "0" && s !== "false" && s !== "no" && s !== "";
}
