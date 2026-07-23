import Script from "next/script";
import { getEnv } from "@/app/lib/cf-env";

/**
 * Google Analytics 4 tag (gtag.js), injected manually.
 *
 * Mirrors {@link Beacon}: the measurement ID is a non-secret `var`
 * (GA_MEASUREMENT_ID in web/wrangler.jsonc) — a GA4 ID is meant to ship in every
 * page's HTML, so reading it server-side and emitting it here is fine. Renders
 * nothing when unset (e.g. plain `next dev`), so local page loads never pollute
 * the production property. The `/^G-[A-Z0-9]+$/` guard both matches the GA4 ID
 * shape and keeps the value safe to interpolate into the inline config script.
 *
 * `next/script` (default `afterInteractive`) loads the loader after hydration
 * begins and guarantees it runs once across client-side route changes.
 */
export default async function GoogleAnalytics() {
  const env = await getEnv();
  const id = env.GA_MEASUREMENT_ID;
  if (!id || !/^G-[A-Z0-9]+$/.test(id)) return null;
  return (
    <>
      <Script
        src={`https://www.googletagmanager.com/gtag/js?id=${id}`}
        strategy="afterInteractive"
      />
      <Script id="ga-gtag" strategy="afterInteractive">
        {`window.dataLayer = window.dataLayer || [];
function gtag(){dataLayer.push(arguments);}
gtag('js', new Date());
gtag('config', '${id}');`}
      </Script>
    </>
  );
}
