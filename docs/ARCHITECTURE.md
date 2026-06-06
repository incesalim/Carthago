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
                                       web/ — Next.js 15 + OpenNext
                                       Deployed to Cloudflare Workers
```

## Components

| Layer | Path | Tech |
|---|---|---|
| **BDDK scrapers** | `src/scrapers/` | Python — monthly + weekly bulletins |
| **EVDS client + scraper** | `src/scrapers/evds_client.py`, `evds_scraper.py` | TCMB EVDS v3 HTTP client |
| **TBB digital-banking** | `src/tbb/` | Python — quarterly `.xls`/`.xlsx` workbook → tidy `tbb_digital_stats` |
| **Audit-report extraction** | `src/audit_reports/` | pdfplumber + pymupdf with fallback |
| **R2 wrapper** | `src/audit_reports/r2_storage.py` | boto3 against S3-compatible R2 |
| **D1 sync** | `scripts/push_to_d1.py` | incremental push via wrangler |
| **Edge database** | Cloudflare D1 (`bddk-data`) | SQLite at the edge, ~1.6M rows |
| **PDF storage** | Cloudflare R2 (`bddk-audit-reports`) | ~2.2 GB, ~970 quarterly PDFs |
| **Dashboard** | `web/` | Next.js 15 + OpenNext + Recharts on Cloudflare Workers |
| **Read cache** | Cloudflare KV (`NEXT_INC_CACHE_KV`) | 12h data cache for D1 reads (`cachedAll` → `unstable_cache`) |
| **Admin panel** | `web/app/admin/`, `web/app/api/admin/` | password-gated control center: data health, refresh triggers, traffic |
| **Quality gates** | `.github/workflows/ci.yml`, `pyproject.toml`, `tests/` | ruff + pytest + eslint + tsc on every PR |
| **Schema migrations** | `web/migrations/` | hand-authored, version-controlled; applied via `wrangler d1 migrations apply` on deploy |

## Workflows

The ingestion workflows split along **two independent storage lanes**, so a
failure in one can't stall the other:

| Lane | Staging DB | R2 snapshot | Concurrency group |
|---|---|---|---|
| BDDK bulletins + EVDS | `data/bddk_data.db` | `state/bddk_data.db.gz` | `bddk-pipeline` |
| Bank audit reports | `data/bank_audit.db` | `state/bank_audit.db.gz` | `bddk-audit` |

The two lanes share no snapshot, so the audit workflow runs in parallel with
the bulletin/EVDS workflows. Their only shared sink is D1, where they write a
**disjoint** set of tables (`bank_audit_*` vs everything else) with idempotent
`INSERT OR REPLACE`.

### Daily — `.github/workflows/refresh-evds-daily.yml`
Sun–Fri 05:00 UTC. EVDS scraper only — fresh FX / rates / sterilization
data in D1 within 24h. Saturday is skipped because the weekly workflow
already includes EVDS.

### Weekly bulletins — `.github/workflows/refresh-bddk-bulletins.yml`
Saturday 02:00 UTC. Isolated BDDK-only refresh (monthly + weekly bulletins,
`--skip-evds`, no audit). Catches the new week before `refresh-data.yml`.

### Weekly full — `.github/workflows/refresh-data.yml`
Saturday 03:00 UTC. BDDK bulletins + EVDS + TBB digital:
1. Decompress `state/bddk_data.db.gz` (pulled from R2) → `data/bddk_data.db`
2. `scripts/refresh.py` — monthly + weekly + EVDS scrapes + TBB quarterly
   digital-banking refresh into SQLite (TBB is a non-critical step:
   `scripts/update_tbb_digital.py`, latest 2 reports; a TBB outage won't abort
   the BDDK refresh)
3. `scripts/push_to_d1.py --hours 168` — push the week's rows to D1
   (idempotent via INSERT OR REPLACE; covers `tbb_digital_stats` too)
4. VACUUM + re-gzip + upload the snapshot back to R2

### Audit reports — `.github/workflows/refresh-audit.yml`
Sunday 04:00 UTC. Standalone audit pipeline on its own DB + snapshot:
1. Pull `state/bank_audit.db.gz` from R2 (first run: bootstrap
   `data/bank_audit.db` from the bulletin snapshot via `seed_audit_db.py`,
   so it doesn't re-extract every PDF)
2. `scripts/sync_audit_reports.py --db data/bank_audit.db` — scrape new bank
   IR PDFs to R2, pull pending PDFs, extract, upsert. URLs come from
   `data/banks/audit_report_urls.json`; 13 banks also auto-discover new quarters
   from their IR page (`src/audit_reports/discovery.py`). Accepts
   `--only-bank TICKER` / `--latest-period` for targeted runs (the /admin
   per-bank trigger passes these via the workflow's `bank` input)
3. `scripts/build_bank_audit_stages.py --db data/bank_audit.db` — rebuild the
   derived Stage 1/2/3 table
4. `scripts/push_to_d1.py --db data/bank_audit.db --only-tables bank_audit_*`
5. VACUUM + re-gzip + upload `state/bank_audit.db.gz` back to R2

### Deploy — `.github/workflows/deploy-cloudflare.yml`
On push touching `web/**`. Applies D1 migrations (`wrangler d1 migrations
apply`), builds the OpenNext bundle, and deploys to Cloudflare Workers.

### Health check — `.github/workflows/healthcheck.yml`
Daily 06:00 UTC. Queries D1 freshness per source + audit failure count and
alerts (`scripts/notify.py` → Telegram/Discord) when data is stale or
extractions spike.

### CI — `.github/workflows/ci.yml`
On every PR (and master push): Python `ruff` + `pytest` and web `eslint` +
`tsc`. Dependency updates come via `.github/dependabot.yml` (pip / npm /
github-actions, weekly).

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

## Admin control center

A password-gated `/admin` route (see [ADMIN.md](ADMIN.md)) surfaces data-freshness
per source, audit-extraction failures, GitHub workflow run status + manual
triggers, and Cloudflare Web Analytics — reading D1 plus the GitHub/Cloudflare
APIs through route handlers under `web/app/api/admin/`.
