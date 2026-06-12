import type { NextConfig } from "next";
import { initOpenNextCloudflareForDev } from "@opennextjs/cloudflare";

// Make Cloudflare bindings (D1 `DB`, KV) available in `next dev` via the
// local wrangler/miniflare state — getCloudflareContext() throws without it.
// Seed local data with e.g. `npx wrangler d1 execute bddk-data --local --file …`.
initOpenNextCloudflareForDev();

const nextConfig: NextConfig = {
  /* config options here */
};

export default nextConfig;
