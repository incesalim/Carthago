/**
 * Cross-cutting concerns for the public data API (/api/v1).
 *
 * Distinct from the rest of app/api/, which is admin/monitoring plumbing for our
 * own dashboard: these routes are a documented product surface that third
 * parties may depend on, so they get CORS, a kill switch, and a stable error
 * envelope that never leaks internals.
 */
import { envFlag, getEnv } from "@/app/lib/cf-env";

/**
 * Browser callers need CORS or the API is unusable from any web page. The data
 * is public and read-only, so `*` costs nothing; there are no cookies or
 * credentials to protect.
 */
export const CORS_HEADERS: Record<string, string> = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};

/**
 * Cache at the edge. The underlying data moves monthly (BDDK tables) or weekly
 * (bulletin), so an hour of staleness is invisible to a caller and keeps repeat
 * traffic off D1 entirely.
 */
export const CACHE_HEADERS: Record<string, string> = {
  "Cache-Control": "public, max-age=3600, s-maxage=3600",
};

export function jsonResponse(body: unknown, status = 200): Response {
  return Response.json(body, {
    status,
    headers: { ...CORS_HEADERS, ...(status === 200 ? CACHE_HEADERS : {}) },
  });
}

export function csvResponse(csv: string, filename: string): Response {
  return new Response(csv, {
    headers: {
      ...CORS_HEADERS,
      ...CACHE_HEADERS,
      "Content-Type": "text/csv; charset=utf-8",
      "Content-Disposition": `attachment; filename="${filename}"`,
    },
  });
}

export function errorResponse(message: string, status = 400): Response {
  return jsonResponse({ error: message }, status);
}

/**
 * Whether the API is switched off. Set `PUBLIC_API_DISABLED=1` on the Worker to
 * take it down without a deploy — the escape hatch that lets us publish an
 * unauthenticated endpoint in the first place.
 */
export async function apiDisabled(): Promise<boolean> {
  const env = await getEnv();
  return envFlag(env.PUBLIC_API_DISABLED);
}

export function disabledResponse(): Response {
  return errorResponse(
    "This API is temporarily unavailable. See https://carthago.app for status.",
    503,
  );
}

/** Preflight. Every /api/v1 route re-exports this. */
export function OPTIONS(): Response {
  return new Response(null, { status: 204, headers: CORS_HEADERS });
}
