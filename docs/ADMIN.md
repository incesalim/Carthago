# Admin control center

A protected `/admin` page in the dashboard that consolidates **pipeline/data
health**, **manual refresh triggers**, and **site traffic** into one view.

- URL: `https://<dashboard-host>/admin` (not linked from the public nav).
- Gated by **Cloudflare Access** (email allowlist). **Safe-by-default**: until
  Access is configured the page returns a Forbidden card — it is never publicly
  readable.
- Everything degrades gracefully: the health view works with no extra setup; the
  Pipeline and Traffic panels show a "not configured" hint until their tokens are
  added.

## Code map

| Piece | File |
|---|---|
| Auth (Access JWT verify, WebCrypto) | `web/app/lib/admin-auth.ts` |
| Env reader (vars + secrets) | `web/app/lib/cf-env.ts` |
| D1 health queries | `web/app/lib/admin-health.ts` |
| GitHub Actions client | `web/app/lib/github.ts` |
| Web Analytics client | `web/app/lib/cf-analytics.ts` |
| Page + panels | `web/app/admin/{page,PipelinePanel,TrafficPanel}.tsx` |
| Route handlers | `web/app/api/admin/{runs,dispatch}/route.ts` |

## One-time setup

### 1. Cloudflare Access (required to open `/admin`)

1. Cloudflare dashboard → **Zero Trust → Access → Applications → Add → Self-hosted**.
2. Application domain: the dashboard host, **path** `/admin` (add a second app or
   path for `/api/admin` so the API is gated too).
3. Policy: **Allow**, include your Google email (`incesalim10@gmail.com`).
4. Copy two values into `web/wrangler.jsonc` → `vars`:
   - `CF_ACCESS_TEAM_DOMAIN` — e.g. `yourname.cloudflareaccess.com`
   - `CF_ACCESS_AUD` — the application's **Application Audience (AUD) Tag**
5. Redeploy (push to `web/**`).

Local dev bypass: set `ADMIN_DEV_BYPASS=1` (e.g. in `web/.dev.vars`) to skip auth.

### 2. GitHub token (enables run status + trigger buttons)

1. GitHub → **Settings → Developer settings → Fine-grained tokens** → new token
   scoped to `incesalim/turkish-banking-sector`, **Actions: Read and write**.
2. Store it as a Worker secret (you paste it; it's never committed):
   ```
   cd web && npx wrangler secret put GITHUB_DISPATCH_TOKEN
   ```

### 3. Cloudflare Web Analytics (optional — traffic panel)

1. Cloudflare → **Web Analytics** → add/enable the site → copy the **site tag**.
2. Create an **account API token** with **Analytics: Read**.
3. Set:
   - `web/wrangler.jsonc` vars: `CF_ANALYTICS_SITE_TAG`, `CF_ACCOUNT_TAG`
   - secret: `cd web && npx wrangler secret put CF_ANALYTICS_TOKEN`

## How health status is derived

Each source reports the latest data period, last ingest timestamp, and a row
count. The colour (Fresh / Late / Stale) compares time-since-last-ingest against
the source's expected cron cadence (daily for EVDS/news, weekly for
bulletins/audit/regulation): `≤1.5×` cadence = Fresh, `≤3×` = Late, else Stale.
Audit extraction failures come straight from `bank_audit_extractions` where
`success = 0`, with the recorded `note`.
