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
| Page + panels + login form | `web/app/admin/{page,PipelinePanel,TrafficPanel,PurgeCacheButton,LoginForm}.tsx` |
| Coverage matrix + drawer | `web/app/admin/coverage/{CoverageMatrix,CoverageDrawer,status}.{tsx,ts}` |
| Coverage queries | `web/app/lib/coverage.ts` |
| Runs / dispatch / coverage / purge-cache endpoints | `web/app/api/admin/{runs,dispatch,coverage,purge-cache}/route.ts` |
| Presentation deck (route + data + HTML builder) | `web/app/api/presentation/route.ts`, `web/app/lib/presentation-data.ts`, `web/app/lib/presentation-deck.ts` |
| Telegram webhook self-register | `web/app/api/admin/telegram-register/route.ts` |
| Telegram bot test harness (gated by `BOT_TEST_KEY`; 404s while unset) | `web/app/api/admin/bot-ask/route.ts` |
| Web Analytics RUM beacon (rendered manually — see §3) | `web/app/components/Beacon.tsx` |

### Managing audit reports (the intended workflow)

Audit extraction is **not scheduled** — you run it from here. `acquire-audit.yml` (weekly)
downloads newly published PDFs into R2 by itself and pings Telegram; they then show up in the
coverage matrix as **missing** for you to extract.

- **Coverage matrix** — a **per-statement-type summary table** plus an **errors & missing
  sidebar**, both fed by one `?summary=1` round-trip (`coverageSummary` + `coverageProblems`).
  Each row is a statement type with its cell counts — **ok / manual / error / missing / N/A**
  (present and valid, hand-corrected, present but failing a structural identity check,
  expected-but-absent, or not expected) — and a coverage bar; rows are grouped **core** vs
  **footnotes & §4** and a `✓` marks a type that has a validator. All 12 statement types have
  validators (assets, liabilities, off-balance, P&L, OCI, credit_quality, stages,
  loans_by_sector, npl_movement, capital, liquidity; profile has presence-only sanity).
  The kind control (**unconsolidated / consolidated / both**) re-aggregates the counts; a
  header tally shows total errors + missing for the current mode. Click a row to filter the
  sidebar to that lane. New quarters fold into the counts automatically when acquired (the
  expected universe is the profile census **∪** the R2 PDF list).
- **Errors & missing sidebar** — lists every `error`/`missing` cell (the actionable ones) as
  `bank · period · kind`, errors first, with a status toggle (**error / missing / both**,
  defaulting to errors) and a bank-substring filter. The list is capped at 300 rendered rows
  (the count badge still shows the true total) so the long missing tail (profile, repricing)
  can't bloat the DOM. Click a cell to open the drawer.
- **Cell drawer** — extraction counts/note, the failing validator identities (`failed_detail`),
  and a context hint: a PDF-present *missing* cell with **no extraction row** says "acquired, not
  yet extracted — click Re-extract"; one that's been extracted but has an empty statement says
  "likely scanned-image — hand-transcribe." The drawer's **Re-extract** dispatches
  `reextract-statement.yml` for just that `bank` + `period` + `kind` + statement.
- **Pipeline panel** — two audit cards: **Acquire audit PDFs** (`acquire-audit.yml`, no inputs)
  and **Extract audit reports** (`refresh-audit.yml`, optional bank).

Data comes from `bank_audit_coverage` / `bank_audit_expected` / `bank_audit_statement_types`,
rebuilt by `scripts/sync_audit_expected.py` (in both the acquire and extract workflows).

Audit **health** in the data-health cards is no longer time-based (extraction isn't scheduled):
it reads `fresh` when every extracted partition succeeded, else `late`.

## Presentation deck (PDF)

The **Presentation** section has two buttons:

- **Generate PDF** — opens `GET /api/presentation?print=1` in a new tab and fires
  the browser print dialog; choose **Save as PDF**.
- **Preview deck** — opens the same deck without auto-printing, to view first.

The route assembles the deck via `web/app/lib/presentation-data.ts` — which
reuses the dashboard's **own** `metrics.ts` functions (the same series the pages
plot) plus the deterministic reads — and renders it with
`web/app/lib/presentation-deck.ts`. The deck is a self-contained 16:9 HTML
document: a dark title slide, a **KPI vitals** slide (stat tiles — assets/loans/
deposits y/y, NPL, CAR, NIM, ROE, LDR), one slide per tab (headline + driver
bullets + an **inline-SVG trend chart**), and a methodology slide. Because every
figure and chart comes straight from the site's metric functions, the deck can't
drift; nothing to configure. The Worker can't run headless Chrome, so the
browser's print-to-PDF is the render step (the CLI `scripts/generate_presentation.py`
just fetches this same HTML and prints it headlessly for an unattended PDF). Query
params: `?tabs=a,b,c` (subset/reorder), `?title=…`, `?print=1`. Not admin-gated —
it returns already-public copy, same as `/api/reads`.

## Purge cache (making a refresh show up immediately)

The **Purge cache** button in the Data-health section header clears the dashboard's
KV cache so a just-refreshed source appears in the graphs right away.

Why it's needed: D1 reads are cached ~12h in KV (`cachedAll` → `unstable_cache`,
`DATA_REVALIDATE_SECONDS` in `web/app/lib/db.ts`) to keep repeat page views off D1.
So when a manual refresh lands a new bulletin / EVDS / weekly row in D1, the charts
keep serving the pre-refresh render until that window rolls over. The data isn't
missing — only the cached page is stale.

The button drops the cached entries (`POST /api/admin/purge-cache`); pages then
re-read D1 lazily on the next view. The endpoint deletes the `NEXT_INC_CACHE_KV`
namespace in batched, cursor-paginated rounds (the client loops until done) — that
namespace also accumulates orphaned entries from past deploys (OpenNext keys by
build id and never GCs old builds), so a purge can clear thousands of keys and
also cleans that cruft. No tag cache is configured, so `revalidateTag` is a no-op
here; deleting the KV entries directly is the lever. Safe — it only clears a cache,
and the Workers Paid plan has no KV write-cap concern on repopulation. A `web/**`
deploy also busts the cache (new build id → new keys) but needs a code push.

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

> `CF_ANALYTICS_SITE_TAG` is **dual-purpose**: it's the key this panel queries against
> *and* the token of the client RUM beacon. Do not turn on Cloudflare's "automatic"
> (edge) injection expecting it to work — it does **not** fire on the OpenNext Worker
> response, which is why the beacon is rendered by hand in
> `web/app/components/Beacon.tsx`. If RUM reads 0 while the panel works, check that
> component, not the Cloudflare dashboard toggle.

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

### Auto-discovery

Some banks **auto-discover** new quarters straight from their IR page, so you
just trigger and the newest report is found, scraped, and ingested with no
hand-edit. Currently 13 banks: **ALBRK, ANADOLU, EMLAK, EXIM, FIBA, HALKB, ING,
PASHA, TEB, TFKB, TSKB, VAKIFK, ZIRAAT** (`DISCOVERY_BANKS` in
`src/audit_reports/discovery.py`).

The engine (`discovery.py`) is generic and config-anchored: for each bank it
learns the URL's quarter-end date encoding and a filename "skeleton" from that
bank's existing config entries, then matches new links on the page — which picks
the right document (full report vs tables-only / TR vs EN) and assigns the
consolidated/unconsolidated kind. It's fail-safe: any error falls back to the
static config.

The other banks still need a hand-added URL in `audit_report_urls.json` before
triggering: some are JavaScript-rendered (AKBNK, GARAN, YKBNK, ISCTR, VAKBN,
ICBCT, ALNTF), some serve opaque file-id URLs with no date (HSBC, KLNMA, ODEA,
QNBFB), and a few don't validate cleanly yet (AKTIF, BURGAN, KUVEYT, SKBNK).

**Adding / re-checking a bank:** run `python scripts/diagnostics/validate_discovery.py`
(uses the config as a test oracle — a bank passes when it reproduces its latest
period with no recent-period URL mismatch), then add the passing tickers to
`DISCOVERY_BANKS`. Re-run it if a bank redesigns its IR page.

> Note: to re-process an *older* period for one bank, run the script directly
> with `--only-bank TICKER` (no `--latest-period`).

## How health status is derived

Each source reports its latest data period, last ingest timestamp, and a row
count. The colour (Fresh / Late / Stale) compares time-since-last-ingest against
the source's expected cron cadence (daily for EVDS/news, weekly for
bulletins/audit/regulation): `≤1.5×` cadence = Fresh, `≤3×` = Late, else Stale.

Audit extraction success/failure and per-bank structural-validation detail are
**not** separate panels — they're surfaced cell-by-cell in the **coverage
matrix** (extraction status, failing identity checks per `bank × period × kind`,
with the drill-down drawer). The per-row identities checked are TL+FC=Total,
parent = Σ children, TOTAL = Σ roman sections, assets = liabilities+equity; the
same `bank_audit_validation` data drives the ⚠ markers on `/banks/[ticker]`
period columns.
