# Architecture

End-to-end Cloudflare stack. No laptop required for production data
flow — everything runs from GitHub Actions, R2, and D1.

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
                               from committed .db.gz)        │                       │
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
| **Audit-report extraction** | `src/audit_reports/` | pdfplumber + pymupdf with fallback |
| **R2 wrapper** | `src/audit_reports/r2_storage.py` | boto3 against S3-compatible R2 |
| **D1 sync** | `scripts/push_to_d1.py` | incremental push via wrangler |
| **Edge database** | Cloudflare D1 (`bddk-data`) | SQLite at the edge, ~1.6M rows |
| **PDF storage** | Cloudflare R2 (`bddk-audit-reports`) | ~2.2 GB, 949 quarterly PDFs |
| **Dashboard** | `web/` | Next.js 15 + OpenNext + Recharts on Cloudflare Workers |

## Workflows

### Daily — `.github/workflows/refresh-evds-daily.yml`
Sun–Fri 05:00 UTC. EVDS scraper only — fresh FX / rates / sterilization
data in D1 within 24h. Saturday is skipped because the weekly workflow
already includes EVDS.

### Weekly — `.github/workflows/refresh-data.yml`
Saturday 03:00 UTC. Full pipeline:
1. Decompress `data/bddk_data.db.gz` → `data/bddk_data.db`
2. `scripts/refresh.py` — monthly + weekly + EVDS scrapes into SQLite
3. `scripts/sync_audit_reports.py` — scrape any new bank IR PDFs to R2,
   pull pending PDFs from R2, extract, upsert
4. `scripts/push_to_d1.py --hours 168` — push everything from the last
   week to D1 (idempotent via INSERT OR REPLACE)
5. Re-gzip + git commit + push the snapshot

### Deploy — `.github/workflows/deploy-cloudflare.yml`
On push touching `web/**`. Builds OpenNext bundle and deploys to
Cloudflare Workers.

## Why the local `.db.gz` still exists

The cron pipeline uses a local SQLite as a staging area between scrapers
and D1 (it's cheap to query, supports complex SQL the scrapers expect,
and gives us a backup of the canonical numbers). After each run the
gzipped snapshot (`data/bddk_data.db.gz`, ~55 MB) is committed back to
git so the next cron starts from the last known state without
re-scraping from scratch. Production reads go to D1, not this file.
