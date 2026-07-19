// Generated/manual binding types. Regenerate with `npm run cf-typegen` after Node 22.

interface CloudflareEnv {
  DB: D1Database;
  ASSETS: Fetcher;

  // --- Admin panel (all optional; the panel degrades gracefully when unset) ---
  // Password mode (default for workers.dev): the shared /admin password (secret).
  ADMIN_PASSWORD?: string;
  // Cloudflare Access mode (custom-domain setups only): set as wrangler `vars`.
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

  // --- Telegram Q&A bot (all `secret`s; see docs/TELEGRAM_BOT.md) ---
  TELEGRAM_BOT_TOKEN?: string; // BotFather token
  TELEGRAM_WEBHOOK_SECRET?: string; // matched against the setWebhook secret_token
  // Free OpenAI-compatible LLM keys (same providers as the Python reads lane).
  CEREBRAS_KEY?: string;
  CEREBRAS_API_KEY?: string;
  GROQ_API_KEY?: string;
  GROQ_API_TOKEN?: string;
  // Optional usage-cap overrides (defaults: 20 per chat, 300 global, per UTC day).
  BOT_PER_CHAT_DAILY?: string;
  BOT_GLOBAL_DAILY?: string;
  // Enables the /api/admin/bot-ask test harness when set (else it 404s).
  BOT_TEST_KEY?: string;

  // --- Public data API (/api/v1; see docs/API.md) ---
  // Kill switch. Set to 1/true (as a wrangler `secret` or `var`) to take the
  // public API down without a deploy — every /api/v1 route then returns 503.
  // This is what makes it safe to publish an unauthenticated endpoint.
  PUBLIC_API_DISABLED?: string;
}
