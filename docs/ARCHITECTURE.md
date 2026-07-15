# Architecture

End-to-end cloud stack. Ingestion runs in GitHub Actions; storage is
Cloudflare R2 + D1; display is Next.js on Cloudflare Workers. No local
machine is involved in the production data flow.

## Data flow

```
              ┌─── BDDK API ────┐    ┌─── Bank IR sites ────┐    ┌─── TCMB EVDS ────┐
              │                 │    │                      │    │                  │
              ▼                 ▼    ▼                      ▼    ▼                  ▼
       monthly bulletin    weekly bulletin            audit-report PDFs        macro / rates
              │                 │                           │                       │
              ├─────────────────┼─────────┐                 │                       │
                                          │                 │                       │
                          (Python scrapers, run in GitHub Actions)                  │
                                          │                 │                       │
                                          ▼                 ▼                       ▼
                              data/bddk_data.db         Cloudflare R2          (same DB)
                              (SQLite, ephemeral             │                       │
                               on the runner —               │  bucket: bddk-audit-reports
                               re-built each cron            │                       │
                               from the R2 .db.gz snapshot)  │                       │
                                          │                 │                       │
                                          ▼                 ▼                       ▼
                                    scripts/push_to_d1.py — incremental sync
                                                    │
                                                    ▼
                                       Cloudflare D1 (bddk-data)
                                                    │
                                                    ▼
                                       web/ — Next.js 16 + OpenNext
                                       Deployed to Cloudflare Workers
```

## Components

| Layer | Path | Tech |
|---|---|---|
| **BDDK scrapers** | `src/scrapers/` | Python — monthly + weekly bulletins |
| **EVDS client + scraper** | `src/scrapers/evds_client.py`, `evds_scraper.py` | TCMB EVDS v3 HTTP client |
| **TBB digital-banking** | `src/tbb/` | Python — quarterly `.xls`/`.xlsx` workbook → tidy `tbb_digital_stats` |
| **TKBB participation digital** | `src/tkbb/` | Python — TKBB Veri Peteği (Turboard JSON API) → `tkbb_digital_stats`, `tkbb_acquisition_stats` |
| **TEFAS fund market** | `src/tefas/` | Python — rate-limited tefas.gov.tr JSON client → per-day sector aggregates in `tefas_*` (per-fund rows not persisted) |
| **KAP ownership** | `src/kap/` | Python — KAP Genel Bilgi Formu §5 + §7 → `kap_ownership` (weekly full replace) |
| **News + regulations** | `src/news/` | Python — KAP / TCMB / BDDK / press / Google News → `news_items`; free-LLM clients (`free_llm.py`, `kimi.py`) for "The Read" + `regulation_briefings` |
| **Earnings calendar** | `src/earnings/` | Python — KAP results filings + IR presentation decks → `bank_earnings` |
| **Franchise (annual reports)** | `src/faaliyet/` | Python — Faaliyet Raporu PDFs → `faaliyet_franchise`, `faaliyet_extractions` |
| **Non-bank lenders** | `src/nonbank/` | Python — BDDK non-bank monthly bulletin → `nonbank_balance_sheet` |
| **Advertised rates** | `src/rates/` | Python — doviz.com (loans) + hangikredi (deposits) → `bank_advertised_rates`; the only **per-bank** rate source (EVDS/BDDK publish rates at sector level only) |
| **TÜİK tables** | `src/tuik/` | Python — veriportali cookie-session → `.xls` downloads (series EVDS lacks) |
| **Audit-report extraction** | `src/audit_reports/` | **PyMuPDF (fitz) only** for every lane — pdfplumber was removed entirely on 2026-07-15 (the frozen BS/P&L `extractor.py`, `profiler.py`, and `src/faaliyet/extractor.py`, the last holdouts, moved to `_fitz_page_text`, a strict superset of the old pdfplumber layout-repair). `_fitz_page_text` is the single text reader; don't add another PDF engine. See `docs/AUDIT_EXTRACTION_GUIDE.md` |
| **R2 wrapper** | `src/audit_reports/r2_storage.py` | boto3 against S3-compatible R2 |
| **D1 sync** | `scripts/push_to_d1.py` | incremental push via wrangler. Audit lanes pass `--table-set audit` — the table list is derived from `src/audit_reports/registry.py`, never hand-written (a hand-written copy is what silently kept `bank_audit_fx_position`/`_repricing` out of D1) |
| **Edge database** | Cloudflare D1 (`bddk-data`) | SQLite at the edge, ~1.6M rows |
| **PDF storage** | Cloudflare R2 (`bddk-audit-reports`) | ~2.2 GB; **1,050 quarterly PDFs** extracted across the 38-bank universe |
| **Dashboard** | `web/` | Next.js 16 + OpenNext + Recharts (charts) + d3-force (/ownership network layout) on Cloudflare Workers |
| **Read cache** | Cloudflare KV (`NEXT_INC_CACHE_KV`) | 12h data cache for D1 reads (`cachedAll` → `unstable_cache`) |
| **Admin panel** | `web/app/admin/`, `web/app/api/admin/` | password-gated control center: data health, refresh triggers, traffic |
| **Quality gates** | `.github/workflows/ci.yml`, `pyproject.toml`, `tests/` | ruff + pytest + eslint + tsc + vitest on every PR |
| **Schema migrations** | `web/migrations/` | hand-authored, version-controlled; applied via `wrangler d1 migrations apply` on deploy |

## Workflows

The ingestion workflows split along **two independent storage lanes**, so a
failure in one can't stall the other:

| Lane | Staging DB | R2 snapshot | Concurrency group |
|---|---|---|---|
| BDDK bulletins + EVDS | `data/bddk_data.db` | `state/bddk_data.db.gz` | `bddk-pipeline` |
| Bank audit reports | `data/bank_audit.db` | `state/bank_audit.db.gz` | `bddk-audit` |

> The whole topology — sources → these workflows → D1/R2/KV → dashboard pages,
> with the two lanes banded apart — is visualized interactively on the **`/pipeline`**
> tab (React Flow; storage nodes show live D1 row counts + freshness, workflow nodes
> their last GitHub Actions run). Source of truth: `web/app/lib/pipeline-graph.ts`.

The two lanes share no snapshot, so the audit workflow runs in parallel with
the bulletin/EVDS workflows. Their only shared sink is D1, where they write a
**disjoint** set of tables (`bank_audit_*` vs everything else) with idempotent
`INSERT OR REPLACE`.

**Most tables sync incrementally** (a time-windowed `INSERT OR REPLACE`), but the
coverage-matrix **spine** — `bank_audit_coverage` / `bank_audit_expected` /
`bank_audit_statement_types` — is **full-rebuild**: `push_to_d1.py` emits
`DELETE FROM <t>; INSERT …` from the local copy, because those rows are computed
wholesale by `sync_audit_expected.py` (no per-row timestamp). This is the one place
the shared-D1 design has a footgun: the spine tables are only populated in
`bank_audit.db`; in `bddk_data.db` they're created-but-empty, so a daily news/EVDS
push from the bulletin lane would `DELETE` the spine and insert nothing — **wiping
the /admin coverage matrix** even though the audit lane never ran. The guard:
`push_to_d1.fetch_recent` **skips a full-rebuild table whose local copy is empty**,
so a push can never wipe a table it has no rows for. (Recovery recipe in
[OPERATIONS.md](OPERATIONS.md) → Troubleshooting.)

One audit table is **derived, not extracted**: `bank_audit_stages` is built from
`bank_audit_credit_quality` (Stage-1/2 loan amounts + the BRSA NPL Stage-3 +
ECLs) by `scripts/build_bank_audit_stages.py`. So re-extracting `credit_quality`
must **rebuild stages** afterward — the audit + reextract workflows do this.

### Daily — `.github/workflows/refresh-evds-daily.yml`
Sun–Fri 05:00 UTC. EVDS scraper (fresh FX / rates / sterilization data in D1
within 24h) plus the non-critical BIST / TBB / TKBB / KAP / TEFAS / Faaliyet steps
of `refresh.py` (BIST re-fetches a trailing 35-day window daily, TEFAS a trailing
7-day window). Saturday is skipped because the weekly workflow already covers
everything. A separate daily job, `refresh-news-daily.yml` (04:00 UTC), refreshes
`news_items`.

### BDDK bulletins — `.github/workflows/refresh-bddk-bulletins.yml`
Isolated BDDK-only refresh (`--skip-evds`, no audit), split by schedule via
`github.event.schedule`:
- **Daily 07:00 UTC** (10:00 Turkey) — monthly check. The monthly bulletin lands
  mid-month on no fixed day, so `update_monthly.py` probes daily and scrapes only
  when BDDK has published a new month (cheap otherwise).
- **Friday 13:30 + 15:30 UTC** (16:30 & 18:30 Turkey) — weekly. BDDK publishes the
  weekly bulletin Friday afternoon; two runs bracket the window (~30 min).
- **Saturday 02:00 UTC** — weekly backstop.

A positive Telegram ping ("published & fetched", `notify_new_bddk.py`) fires when
a weekly/monthly period newly lands; quiet otherwise.

### Weekly full — `.github/workflows/refresh-data.yml`
Saturday 03:00 UTC. BDDK bulletins + EVDS + BIST + TBB digital + TKBB participation
digital + KAP + TEFAS + Faaliyet franchise:
1. Decompress `state/bddk_data.db.gz` (pulled from R2) → `data/bddk_data.db`
2. `scripts/refresh.py` — monthly + weekly + EVDS scrapes + TBB quarterly
   digital-banking refresh + KAP ownership + TEFAS fund market into SQLite
   (TBB/KAP/TEFAS are non-critical steps; an outage in one won't abort the
   BDDK refresh)
3. `scripts/push_to_d1.py --hours 168` — push the week's rows to D1
   (idempotent via INSERT OR REPLACE; covers `tbb_digital_stats`,
   `kap_ownership` and the `tefas_*` tables too)
4. VACUUM + re-gzip + upload the snapshot back to R2

### The satellite lanes — small, scheduled, one table each
Four crons ride the bulletin lane's snapshot and concurrency group, each writing a
single table. They're listed here because a lane nobody documents is a lane nobody
knows is running:

| Workflow | When | Writes |
|---|---|---|
| `refresh-advertised-rates.yml` | Mon 06:00 UTC | `python -m src.rates.scraper` → `bank_advertised_rates` (per-bank posted loan/deposit rates; the sources only expose "today", so history accretes forward) |
| `refresh-calendar.yml` | 1st of month 06:00 UTC | `python -m src.release_calendar.scraper` → `release_calendar` (TCMB's published calendar — MPC decisions/minutes, Inflation Report, Financial Stability Report; feeds the Ahead strips, retires the hand-typed `MPC_DATES`) |
| `refresh-presentations-weekly.yml` | Sat 06:00 UTC | `update_presentations.py` → `bank_earnings` (IR presentation decks) |
| `summarize-regulations.yml` | Sun 06:00 UTC | `summarize_regulations.py` → `regulation_briefings` (weekly Kimi briefing; needs `KIMI_API_TOKEN`) |
| `generate-reads.yml` | Sun 07:30 UTC | `generate_read_headlines.py` → `read_headlines` (free-LLM rewrite of the one-sentence lead on each T1 tab; number-validated, and shown only while its `det_hash` matches the live page) |

Four more workflows are **manual dispatch only** and exist to load history, not to
keep it fresh: `backfill-audit.yml`, `backfill-faaliyet.yml`, `backfill-nonbank.yml`
and `backfill-tefas.yml` (recipes in [OPERATIONS.md](OPERATIONS.md)).

### Audit reports — two workflows, one `bddk-audit` lane
Standalone audit pipeline on its own DB + snapshot. **Acquisition is automated;
extraction is admin-triggered** (they share the concurrency group, so never overlap).

**`acquire-audit.yml`** (Sunday 04:00 UTC) — the only scheduled part:
1. Pull `state/bank_audit.db.gz` (read-only, for coverage row counts)
2. `scripts/sync_audit_reports.py --no-extract` — scrape new bank IR PDFs to R2.
   URLs from `data/banks/audit_report_urls.json`; 13 banks also auto-discover new
   quarters from their IR page (`src/audit_reports/discovery.py`)
3. `scripts/sync_audit_expected.py --push` — refresh the coverage matrix (new PDFs
   appear as `missing`); notify Telegram on new reports. **Never writes the snapshot.**

**`refresh-audit.yml`** (dispatch-only, from /admin) — extraction:
1. Pull/seed `data/bank_audit.db`
2. `scripts/sync_audit_reports.py` — extract pending PDFs from R2 (or `--only-bank`
   / `--periods … --force` for a targeted re-extract, passed via the workflow's
   `bank`/`period` inputs from the /admin coverage matrix)
3. `build_bank_audit_stages.py` → `revalidate_audit_db.py` → `check_audit_quality.py`
4. `push_to_d1.py --table-set audit` + `sync_audit_expected.py --push` (the table
   list is derived from the statement registry — never hand-listed)
5. VACUUM + re-gzip + upload `state/bank_audit.db.gz` (the snapshot WRITER)

**`reextract-statement.yml`** (dispatch-only) — targeted **single-statement** fix
on the same lane. Re-extracts one statement (`oci` / `cash_flow` / `equity_change`
/ `npl_movement` / `loans_by_sector` / `bank_profile` / `credit_quality`) for the
selected banks/periods via `scripts/reextract_statement.py`, inline-validates, and
pushes only that table + `bank_audit_validation` + a fresh snapshot. The
**non-destructive guard** leaves passing partitions untouched (`only_failing=true`
re-touches only the not-passing ones); `force=true` overrides it for
derived-table defects (a partition can pass `credit_quality` yet fail the derived
`bank_audit_stages`). This is how OCI/CF/NPL/loans_by_stage were fixed fleet-wide
without re-running the frozen BS/P&L extraction.

### Deploy — `.github/workflows/deploy-cloudflare.yml`
On push touching `web/**`. Applies D1 migrations (`wrangler d1 migrations
apply`), builds the OpenNext bundle, and deploys to Cloudflare Workers.

### Health check — `.github/workflows/healthcheck.yml`
Daily 06:00 UTC. Queries D1 freshness per source + audit failure count and
alerts (`scripts/notify.py` → Telegram/Discord) when data is stale or
extractions spike.

### CI — `.github/workflows/ci.yml`
On every PR (and master push): Python `ruff` + `pytest` and web `eslint` +
`tsc` + `vitest` (`npm run test` — unit tests for pure lib code, e.g.
`app/lib/pl-sankey.test.ts`). Dependency updates come via
`.github/dependabot.yml` (pip / npm / github-actions, weekly).

## Why the SQLite snapshot exists

The cron pipeline uses a local SQLite as a staging area between scrapers
and D1 (it's cheap to query, supports complex SQL the scrapers expect,
and gives us a backup of the canonical numbers). After each run the
gzipped snapshot is uploaded to R2 so the next cron starts from the last
known state without re-scraping from scratch.

There are **two** snapshots, one per lane: the bulletin/EVDS lane persists
`state/bddk_data.db.gz` (~55 MB) and the audit lane persists
`state/bank_audit.db.gz` (the `bank_audit_*` tables only). The audit lane
bootstraps its snapshot on first run by seeding from the bulletin snapshot
(`scripts/seed_audit_db.py`) rather than re-extracting every PDF.

Production dashboard reads go to D1, not this snapshot — the R2 copy is
purely pipeline state.

**Backups & recovery (free):** each run also writes a dated copy
`state/history/<lane>-YYYYMMDD.db.gz` and keeps the last 7, so a corrupt run
can't destroy the only snapshot. For the serving DB, D1 **Time Travel** gives a
7-day point-in-time restore. See [OPERATIONS.md](OPERATIONS.md) → Disaster recovery.

## Dashboard read caching

Dashboard pages are dynamic (server-rendered per request), but the D1 queries
behind them are cached: `web/app/lib/db.ts` `cachedAll()` wraps reads in
`unstable_cache` (12h TTL — data changes daily at most, and a longer TTL keeps
KV writes under the free 1,000/day cap), keyed by SQL + params and backed by the
`NEXT_INC_CACHE_KV` namespace via OpenNext's incremental cache
(`open-next.config.ts`). The hot `metrics.ts` query helpers route through it, so
identical queries hit D1 at most once per 12h instead of on every page view —
cutting D1 rows-read sharply.

Pages stay dynamic on purpose: page-level ISR (`export const revalidate`) would
prerender the data pages at build time, which queries D1 against the empty
build-time DB and fails. Caching the *data* (not the page) avoids that. `/admin`
is intentionally uncached (auth-gated + shows live pipeline status).

The `/ownership` sector graph is built server-side off two cached queries
(`sectorOwnership()` in `web/app/lib/kap.ts` for the graph, `bankSummaries()`
for asset-based node sizing — fail-soft to uniform sizes). The force-directed
layout (d3-force, `web/app/lib/ownership-force.ts`) runs synchronously in a
`useMemo` with seeded positions and a seeded random source, so the server
render and client hydration agree; all interaction (zoom, ego-highlighting,
focus, tooltips) is client-side on the serialized graph, so clicking around
costs zero extra D1 reads.

For local dev, `web/next.config.ts` calls `initOpenNextCloudflareForDev()` so
`next dev` resolves the D1/KV bindings against the local wrangler/miniflare
state — seed tables with `npx wrangler d1 execute bddk-data --local --file …`
to work on data pages offline.

## Admin control center

A password-gated `/admin` route (see [ADMIN.md](ADMIN.md)) surfaces data-freshness
per source, audit-extraction failures, GitHub workflow run status + manual
triggers, and Cloudflare Web Analytics — reading D1 plus the GitHub/Cloudflare
APIs through route handlers under `web/app/api/admin/`.
