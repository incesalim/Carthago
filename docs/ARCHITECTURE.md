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
| **TEFAS fund market** | `src/tefas/` | Python — rate-limited tefas.gov.tr JSON client → per-day sector aggregates in `tefas_*` (per-fund rows not persisted) |
| **Audit-report extraction** | `src/audit_reports/` | pdfplumber + pymupdf with fallback |
| **R2 wrapper** | `src/audit_reports/r2_storage.py` | boto3 against S3-compatible R2 |
| **D1 sync** | `scripts/push_to_d1.py` | incremental push via wrangler |
| **Edge database** | Cloudflare D1 (`bddk-data`) | SQLite at the edge, ~1.6M rows |
| **PDF storage** | Cloudflare R2 (`bddk-audit-reports`) | ~2.2 GB, ~970 quarterly PDFs |
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
within 24h) plus the non-critical TBB / KAP / TEFAS steps of `refresh.py`
(TEFAS re-fetches a trailing 7-day window daily). Saturday is skipped because
the weekly workflow already covers everything.

### Weekly bulletins — `.github/workflows/refresh-bddk-bulletins.yml`
Saturday 02:00 UTC. Isolated BDDK-only refresh (monthly + weekly bulletins,
`--skip-evds`, no audit). Catches the new week before `refresh-data.yml`.

### Weekly full — `.github/workflows/refresh-data.yml`
Saturday 03:00 UTC. BDDK bulletins + EVDS + TBB digital + KAP + TEFAS:
1. Decompress `state/bddk_data.db.gz` (pulled from R2) → `data/bddk_data.db`
2. `scripts/refresh.py` — monthly + weekly + EVDS scrapes + TBB quarterly
   digital-banking refresh + KAP ownership + TEFAS fund market into SQLite
   (TBB/KAP/TEFAS are non-critical steps; an outage in one won't abort the
   BDDK refresh)
3. `scripts/push_to_d1.py --hours 168` — push the week's rows to D1
   (idempotent via INSERT OR REPLACE; covers `tbb_digital_stats`,
   `kap_ownership` and the `tefas_*` tables too)
4. VACUUM + re-gzip + upload the snapshot back to R2

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
4. `push_to_d1.py --only-tables bank_audit_*` + `sync_audit_expected.py --push`
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
