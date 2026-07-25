import { getEnv } from "@/app/lib/cf-env";
import AnalyticsConsent from "./AnalyticsConsent";

/**
 * Google Analytics 4 (gtag.js) — **behind consent since 2026-07-25**.
 *
 * This component no longer emits the tag. It resolves the measurement ID on the
 * server and hands it to {@link AnalyticsConsent}, which requests `gtag.js` only
 * after the visitor opts in. Between 2026-07-23 and 2026-07-25 the tag loaded
 * for every visitor, unannounced and with no privacy page; both are fixed.
 *
 * The ID stays a non-secret `var` (GA_MEASUREMENT_ID in web/wrangler.jsonc) — a
 * GA4 ID is meant to ship in the page. Renders nothing when unset (e.g. plain
 * `next dev`), so local page loads never pollute the production property, and
 * nothing when it fails the `/^G-[A-Z0-9]+$/` shape guard, which also keeps the
 * value safe to interpolate into the inline config script.
 *
 * Mirrors {@link Beacon} in how it reads config — but NOT in gating: Cloudflare
 * Web Analytics is cookieless and identifier-free, so it raises no consent
 * question and is not routed through here.
 */
export default async function GoogleAnalytics() {
  const env = await getEnv();
  const id = env.GA_MEASUREMENT_ID;
  if (!id || !/^G-[A-Z0-9]+$/.test(id)) return null;
  return <AnalyticsConsent measurementId={id} />;
}
