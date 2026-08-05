import { getEnv } from "@/app/lib/cf-env";

/**
 * Cloudflare Web Analytics RUM beacon, injected manually.
 *
 * Cloudflare's "automatic" (edge) injection does not fire on the OpenNext Worker
 * response — verified the beacon was absent from the live HTML while RUM stayed
 * at 0 — so we render the snippet ourselves. Cloudflare's site token is public
 * by design, but it is NOT the GraphQL site tag used by the /admin Traffic
 * panel; keeping separate env keys prevents a valid query from returning an
 * empty dataset. Renders nothing when unset (e.g. plain `next dev`), so local
 * page loads never pollute production analytics.
 */
export default async function Beacon() {
  const env = await getEnv();
  const token = env.CF_ANALYTICS_SITE_TOKEN;
  if (!token) return null;
  return (
    <script
      type="module"
      defer
      src="https://static.cloudflareinsights.com/beacon.min.js"
      data-cf-beacon={JSON.stringify({ token })}
    />
  );
}
