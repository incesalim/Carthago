// Generated/manual binding types. Regenerate with `npm run cf-typegen` after Node 22.

interface CloudflareEnv {
  DB: D1Database;
  ASSETS: Fetcher;

  // --- Admin panel (all optional; the panel degrades gracefully when unset) ---
  // Cloudflare Access JWT verification (set as wrangler `vars`).
  CF_ACCESS_TEAM_DOMAIN?: string; // e.g. "yourname.cloudflareaccess.com"
  CF_ACCESS_AUD?: string; // the Access application's AUD tag
  // Bypass auth for local dev only — NEVER set in production.
  ADMIN_DEV_BYPASS?: string;

  // GitHub Actions control (set as a wrangler `secret`).
  GITHUB_DISPATCH_TOKEN?: string; // fine-grained PAT, Actions: read+write

  // Cloudflare Web Analytics (traffic panel). Token is a `secret`, the rest `vars`.
  CF_ANALYTICS_TOKEN?: string; // account API token with Analytics: Read
  CF_ANALYTICS_SITE_TAG?: string; // Web Analytics site tag
  CF_ACCOUNT_TAG?: string; // Cloudflare account id/tag
}
