/**
 * The HTTP client. One `get()`, no dependency, no query builder.
 *
 * Three things a phone client needs that a browser gets for free:
 *
 *   1. A TIMEOUT. `fetch` on a mobile network does not fail on a dead radio, it
 *      hangs — for minutes. Without an abort the screen shows a spinner with no
 *      end state and no retry affordance, which reads as a broken app.
 *   2. A typed ApiError carrying `status`, so a screen can tell "we are offline"
 *      (retry, keep any cached copy) from "this bank does not exist" (don't
 *      retry, say so).
 *   3. An explicit BASE. A native binary has no origin to be relative to, so the
 *      host is compiled in.
 */
import Constants from "expo-constants";

/**
 * API host. `EXPO_PUBLIC_API_BASE` overrides it for local work — point a
 * simulator at `http://<your-lan-ip>:3000` to run against `npm run dev` in
 * web/. `localhost` is the DEVICE's localhost on a phone, so a LAN IP is
 * required; this is the single most common reason a dev build shows no data.
 */
export const API_BASE =
  process.env.EXPO_PUBLIC_API_BASE?.replace(/\/$/, "") ?? "https://carthago.app";

/** This build's number, compared against the server's `minSupportedClient`. */
export const CLIENT_BUILD = Number(
  Constants.expoConfig?.extra?.clientBuild ?? 1,
);

const TIMEOUT_MS = 15_000;

export class ApiError extends Error {
  readonly status: number;
  /** True when the request never reached the server — offline, DNS, timeout.
   *  The distinction matters: this is the only case worth auto-retrying. */
  readonly offline: boolean;

  constructor(message: string, status: number, offline = false) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.offline = offline;
  }
}

export async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);

  // Caller-driven cancellation (screen unmounted, pull-to-refresh superseded)
  // has to compose with the timeout, or an unmount leaves the timer to fire
  // against a dead screen.
  const onAbort = () => controller.abort();
  signal?.addEventListener("abort", onAbort);

  try {
    const res = await fetch(`${API_BASE}${path}`, {
      signal: controller.signal,
      headers: { Accept: "application/json" },
      // These responses carry `max-age=3600`, which is right in production and
      // actively misleading in development: change a route handler, deploy, and
      // the client keeps serving the old payload for up to an hour with nothing
      // on screen to say so. Cost an hour once already. Production keeps the
      // cache; `__DEV__` always goes to the origin.
      cache: __DEV__ ? "no-store" : "default",
    });

    if (!res.ok) {
      // The API's error envelope is `{ error }`. If the body isn't that — a
      // Cloudflare error page, an HTML 502 — fall back to the status rather
      // than surfacing a JSON parse failure, which tells the user nothing.
      let message = `Request failed (${res.status})`;
      try {
        const body = (await res.json()) as { error?: string };
        if (body?.error) message = body.error;
      } catch {
        /* non-JSON error body — keep the status message */
      }
      throw new ApiError(message, res.status);
    }

    return (await res.json()) as T;
  } catch (err) {
    if (err instanceof ApiError) throw err;
    // AbortError covers both the timeout and an explicit cancel. Either way the
    // request never completed, so it is an offline-class failure.
    throw new ApiError(
      "Can't reach Carthago. Check your connection.",
      0,
      true,
    );
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", onAbort);
  }
}

export const endpoints = {
  handshake: () => "/api/app/v1",
  overview: () => "/api/app/v1/overview",
  banks: () => "/api/app/v1/banks",
  bank: (ticker: string) => `/api/app/v1/banks/${encodeURIComponent(ticker)}`,
  economy: () => "/api/app/v1/economy",
  news: (source = "all", limit = 50) =>
    `/api/app/v1/news?source=${encodeURIComponent(source)}&limit=${limit}`,
} as const;
