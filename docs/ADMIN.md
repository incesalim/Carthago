# Admin control center

A protected `/admin` page in the dashboard that consolidates **pipeline/data
health**, **manual refresh triggers**, and **site traffic** into one view.

- URL: `https://<dashboard-host>/admin` (not linked from the public nav).
- **Safe-by-default**: until an auth method is configured the page is locked —
  it is never publicly readable.
- Two auth modes (auto-selected): **password** (default, works on the free
  `workers.dev` URL) and **Cloudflare Access** (only when on a custom domain).
- Everything degrades gracefully: health works as soon as you can log in; the
  Pipeline and Traffic panels show a "not configured" hint until their tokens
  are added.

## Code map

| Piece | File |
|---|---|
| Auth (password session + Access JWT) | `web/app/lib/admin-auth.ts` |
| Login / logout endpoints | `web/app/api/admin/{login,logout}/route.ts` |
| Env reader | `web/app/lib/cf-env.ts` |
| D1 health queries | `web/app/lib/admin-health.ts` |
| GitHub Actions client | `web/app/lib/github.ts` |
| Web Analytics client | `web/app/lib/cf-analytics.ts` |
| Page + panels + login form | `web/app/admin/{page,PipelinePanel,TrafficPanel,LoginForm}.tsx` |
| Runs / dispatch endpoints | `web/app/api/admin/{runs,dispatch}/route.ts` |

## Setup

### 1. Set the admin password (unlocks the page)

This is all that's needed to open `/admin` on the current `workers.dev` URL.

Cloudflare dashboard → **Workers & Pages → `turkish-banking-dashboard` →
Settings → Variables and Secrets → Add** → name `ADMIN_PASSWORD`, type **Secret**,
value = a password you choose → **Save**. (Or CLI: `cd web && npx wrangler secret
put ADMIN_PASSWORD`.)

Then visit `/admin`, enter the password, and you're in. The session lasts ~12h;
"Sign out" clears it.

### 2. GitHub token (enables run status + trigger buttons)

Fine-grained PAT scoped to `incesalim/turkish-banking-sector`, **Actions: Read
and write** → add as a secret named `GITHUB_DISPATCH_TOKEN` (same Variables and
Secrets screen, or `npx wrangler secret put GITHUB_DISPATCH_TOKEN`).

### 3. Cloudflare Web Analytics (optional — traffic panel)

Enable Web Analytics for the site, create an account API token with **Analytics:
Read**, then set:
- vars `CF_ANALYTICS_SITE_TAG`, `CF_ACCOUNT_TAG` (in `web/wrangler.jsonc`)
- secret `CF_ANALYTICS_TOKEN`

### 4. Cloudflare Access (optional — only on a custom domain)

On `workers.dev`, Cloudflare Access can only gate the **whole** subdomain, which
would lock the public dashboard too — so we use the password instead. If you
later put the dashboard on a **custom domain**, you can switch to Access:
create a self-hosted Access app over `/admin` + `/api/admin`, allow your email,
then set vars `CF_ACCESS_TEAM_DOMAIN` + `CF_ACCESS_AUD`. When both are present
the panel uses Access automatically (and ignores the password).

Local dev: set `ADMIN_DEV_BYPASS=1` (e.g. in `web/.dev.vars`) to skip auth.

## Per-bank audit trigger

The **Audit reports** card has a bank dropdown. Leave it on **All banks** for
the normal full sweep (every bank, every quarter — idempotent), or pick a single
ticker to scrape + extract just that bank's **latest published quarter** — handy
the moment a bank publishes a new report instead of waiting for the Sunday cron.

It forwards a `bank` input to `refresh-audit.yml`. Because a per-bank trigger
means "grab the quarter this bank just published", the workflow also adds
`--latest-period`, so it runs `sync_audit_reports.py --only-bank TICKER
--latest-period` (newest quarter only, not the bank's full history). The ticker
list mirrors `data/banks/audit_report_urls.json` (`AUDIT_BANKS` in
`web/app/lib/github.ts`) and is validated server-side in the dispatch route, so
only a known ticker can ever reach the workflow.

> Note: the scraper fetches URLs from `audit_report_urls.json`, so the new
> quarter's URL must already be in that file for the trigger to pick it up. To
> re-process an *older* period for one bank, run the script directly with
> `--only-bank TICKER` (no `--latest-period`).

## How health status is derived

Each source reports its latest data period, last ingest timestamp, and a row
count. The colour (Fresh / Late / Stale) compares time-since-last-ingest against
the source's expected cron cadence (daily for EVDS/news, weekly for
bulletins/audit/regulation): `≤1.5×` cadence = Fresh, `≤3×` = Late, else Stale.
Audit extraction failures come straight from `bank_audit_extractions` where
`success = 0`, with the recorded `note`.
