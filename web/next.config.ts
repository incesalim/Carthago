import type { NextConfig } from "next";
import { initOpenNextCloudflareForDev } from "@opennextjs/cloudflare";

// Make Cloudflare bindings (D1 `DB`, KV) available in `next dev` via the
// local wrangler/miniflare state — getCloudflareContext() throws without it.
// Seed local data with e.g. `npx wrangler d1 execute bddk-data --local --file …`.
initOpenNextCloudflareForDev();

/**
 * Security response headers.
 *
 * The 2026-07-25 re-evaluation measured the site sending NONE of these — not
 * HSTS, not nosniff, not a framing policy. For a read-only dashboard the blast
 * radius is small, but `/admin` sets a session cookie on the same origin, so
 * "read-only" is not the whole story: clickjacking that origin is a real shape.
 *
 * Deliberate omissions, so the next reader knows they were decisions:
 *
 *  - **No `includeSubDomains` on HSTS.** The app is also served from
 *    `carthago.incesalim10.workers.dev` (verified live), and the subdomain
 *    inventory of carthago.app is not something this file can know. Pinning a
 *    subdomain that does not speak HTTPS breaks it with no way to unbreak it
 *    inside `max-age`. Add it — and `preload` — once that inventory is certain;
 *    both are one-way doors, which is exactly why they are not defaults here.
 *  - **No full Content-Security-Policy.** `frame-ancestors` is the half that
 *    needs no allow-listing. A real `script-src` has to cover the next-themes
 *    inline initializer, the JSON-LD blocks and the consent-gated gtag loader,
 *    which means nonces via middleware — worth doing, but that is a change which
 *    breaks pages silently, not a header to bolt on.
 *  - **No Cross-Origin-Resource-Policy.** `/api/v1` deliberately serves
 *    `Access-Control-Allow-Origin: *`; a blanket CORP would fight it.
 */
const SECURITY_HEADERS = [
  // One year is the standard floor. No includeSubDomains / preload — see above.
  { key: "Strict-Transport-Security", value: "max-age=31536000" },
  // Stop the browser second-guessing a Content-Type. The cheapest header there is.
  { key: "X-Content-Type-Options", value: "nosniff" },
  // Nothing here is meant to be embedded, and nothing embeds itself (verified:
  // zero <iframe> in web/app). Both headers, because the legacy one is still
  // what some scanners and older browsers read.
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Content-Security-Policy", value: "frame-ancestors 'none'" },
  // Origin cross-site, full path same-site: referrer analytics keeps working
  // without leaking which bank someone was reading to a third party.
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  // The site asks for no device permissions at all; say so, so an injected
  // script cannot ask either.
  {
    key: "Permissions-Policy",
    value:
      "accelerometer=(), camera=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(), payment=(), usb=()",
  },
];

const nextConfig: NextConfig = {
  async headers() {
    return [{ source: "/:path*", headers: SECURITY_HEADERS }];
  },
};

export default nextConfig;
