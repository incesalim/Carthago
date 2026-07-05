import { getEnv } from "@/app/lib/cf-env";

/**
 * Cloudflare Web Analytics RUM beacon, injected manually.
 *
 * Cloudflare's "automatic" (edge) injection does not fire on the OpenNext Worker
 * response — verified the beacon was absent from the live HTML while RUM stayed
 * at 0 — so we render the snippet ourselves. The token is the non-secret site
 * tag (CF_ANALYTICS_SITE_TAG, the same value the /admin Traffic panel queries
 * against); it's already public in the page, so reading it server-side and
 * emitting it here is fine. Renders nothing when unset (e.g. plain `next dev`),
 * so local page loads never pollute production analytics.
 */
export default async function Beacon() {
  const env = await getEnv();
  const token = env.CF_ANALYTICS_SITE_TAG;
  if (!token) return null;
  return (
    <script
      defer
      src="https://static.cloudflareinsights.com/beacon.min.js"
      data-cf-beacon={JSON.stringify({ token })}
    />
  );
}
