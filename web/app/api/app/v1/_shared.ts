/**
 * Cross-cutting concerns for the mobile-app read API (/api/app/v1).
 *
 * Deliberately NOT part of /api/v1. That namespace is a published product
 * surface: a documented series contract that third parties build against, so its
 * shapes can only ever be added to. This one is the private wire format between
 * our own Worker and our own Expo client — screen-oriented, denormalised, and
 * free to change the moment a screen changes. Keeping them apart is what lets
 * the mobile app iterate without freezing the public API, and vice versa.
 *
 * The client pins a namespace version (`/v1`) rather than a build date, so a
 * breaking reshape means minting `/api/app/v2` and leaving v1 serving the old
 * binaries in the wild until the store rollout catches up. See
 * docs/ARCHITECTURE.md § "Mobile app".
 */
import { envFlag, getEnv } from "@/app/lib/cf-env";

/**
 * A native client is not a browser and sends no Origin, so CORS is irrelevant
 * to the shipped app. It exists for `expo start --web`, which runs the very same
 * client code from a localhost origin — without this, every screen is blank in
 * the one environment where the debugger works.
 */
export const CORS_HEADERS: Record<string, string> = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};

/**
 * Edge cache. Underlying data moves monthly (BDDK tables), weekly (bulletin) or
 * quarterly (audited filings), so an hour of staleness is invisible — and it
 * keeps a cold-start app launch off D1 entirely.
 *
 * `stale-while-revalidate` matters more here than on the website: a phone on a
 * bad connection would otherwise block the first paint on a full origin round
 * trip. Serving the last good payload instantly and refreshing behind it is the
 * difference between a snappy launch and a spinner.
 */
export const CACHE_HEADERS: Record<string, string> = {
  "Cache-Control": "public, max-age=3600, s-maxage=3600, stale-while-revalidate=86400",
};

/** The contract version the client negotiates against. Bump only for a
 *  BREAKING reshape — additive fields don't need it, since the client reads
 *  fields it knows and ignores the rest. */
export const APP_API_VERSION = 1;

/**
 * Oldest client build this API still serves happily. The app compares its own
 * build number against this on launch (`GET /api/app/v1`) and shows a soft
 * upgrade prompt when it falls behind.
 *
 * Raise this ONLY when an older build would actively misread a payload — a
 * renamed field, a changed unit. It is not a marketing nag: every raise strands
 * users who cannot or will not update until the store rollout reaches them.
 */
export const MIN_SUPPORTED_CLIENT = 1;

export function jsonResponse(body: unknown, status = 200): Response {
  return Response.json(body, {
    status,
    headers: { ...CORS_HEADERS, ...(status === 200 ? CACHE_HEADERS : {}) },
  });
}

export function errorResponse(message: string, status = 400): Response {
  return jsonResponse({ error: message }, status);
}

/**
 * Whether the mobile API is switched off. `APP_API_DISABLED=1` on the Worker
 * takes it down without a deploy.
 *
 * Deliberately a SEPARATE flag from `PUBLIC_API_DISABLED`. That one exists to
 * shed unauthenticated third-party load in an incident; using it here would
 * black out every installed app at the same moment — the users least able to
 * work around it, since they can't just open the website instead.
 */
export async function appApiDisabled(): Promise<boolean> {
  const env = await getEnv();
  return envFlag(env.APP_API_DISABLED);
}

export function disabledResponse(): Response {
  return errorResponse(
    "Carthago is temporarily unavailable. Please try again shortly.",
    503,
  );
}

/** Preflight. Every /api/app/v1 route re-exports this. */
export function OPTIONS(): Response {
  return new Response(null, { status: 204, headers: CORS_HEADERS });
}

/** A time series as the client wants it: parallel-free, JSON-small. */
export interface WirePoint {
  t: string;
  v: number | null;
}

/**
 * Trim a series to its last `n` points and strip it to `{t,v}`.
 *
 * Payload size is a real constraint on a phone: the overview screen carries six
 * sparklines, and shipping full history for each turns a ~12KB response into
 * ~400KB over a mobile connection for pixels that render 13 points wide.
 */
export function wireSeries(
  rows: ReadonlyArray<{ period?: string; period_date?: string; value: number | null }>,
  n = 13,
): WirePoint[] {
  return rows.slice(-n).map((r) => ({
    t: r.period ?? r.period_date ?? "",
    v: r.value,
  }));
}
