import { defineCloudflareConfig } from "@opennextjs/cloudflare";
import kvIncrementalCache from "@opennextjs/cloudflare/overrides/incremental-cache/kv-incremental-cache";

// KV-backed incremental cache enables ISR: pages with `export const revalidate`
// are served from KV and re-rendered in the background at most once per window,
// instead of querying D1 on every request. Backed by the NEXT_INC_CACHE_KV
// namespace bound in wrangler.jsonc.
export default defineCloudflareConfig({
  incrementalCache: kvIncrementalCache,
});
