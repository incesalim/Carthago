# Architecture

The project has two parallel stacks during the Render → Cloudflare migration.
This document explains how the pieces fit.

## Two stacks, one database

```
                ┌────────────── BDDK API ──────────────┐
                │                                       │
                ▼                                       ▼
         monthly bulletin                       weekly bulletin
                │                                       │
                ├───────────────┬───────────────────────┤
                                │
                          (Python scrapers)
                                │
                                ▼
                  ┌─────────────────────────┐
                  │   data/bddk_data.db     │  ← local SQLite (source of truth)
                  └────────┬────────┬───────┘
                           │        │
              ┌────────────┘        └────────────┐
              │                                  │
              ▼                                  ▼
     bddk_data.db.gz (committed)         scripts/push_to_d1.py
              │                                  │
              ▼                                  ▼
      Render (legacy)                   Cloudflare D1 (new)
              │                                  │
              ▼                                  ▼
     src/dashboard/ (Dash)              web/ (Next.js + OpenNext)
     turkish-banking-sector             turkish-banking-dashboard
       .onrender.com                      .workers.dev
```

## Layers

| Layer | Path | Tech |
|---|---|---|
| **Data ingestion** | `src/scrapers/` | Python — scrapes BDDK monthly + weekly APIs |
| **Audit-report extraction** | `src/audit_reports/` | Python + pdfplumber — per-bank quarterly reports |
| **Local database** | `data/bddk_data.db` | SQLite (~370 MB) |
| **Analytics (legacy)** | `src/analytics/` | Python — metrics, FCI, in-memory cache |
| **Legacy dashboard** | `src/dashboard/` | Dash + Plotly, deployed to Render |
| **D1 sync** | `scripts/push_to_d1.py` | Python + wrangler — incremental push of new rows |
| **Edge database** | Cloudflare D1 (`bddk-data`) | SQLite at the edge, 1.6M rows |
| **New dashboard** | `web/` | Next.js 15 + OpenNext + Recharts, deployed to Cloudflare Workers |

## Refresh flow (Saturday cron)

`.github/workflows/refresh-data.yml`:
1. Decompress `data/bddk_data.db.gz` → `data/bddk_data.db`
2. Run `scripts/refresh.py` — scrapes new BDDK data into local DB
3. Run `scripts/push_to_d1.py --hours 168` — pushes recent rows to D1
4. Re-gzip → commit → push → Render auto-redeploys

## Deploy flow

| Target | Trigger |
|---|---|
| **Render** (legacy) | Auto on git push (any commit to master) |
| **Cloudflare Workers** | `.github/workflows/deploy-cloudflare.yml` — auto on push when `web/**` changes |

## Migration status

Dashboard ports complete:
- Overview · Credit · Deposits · Asset Quality · Capital · Profitability

Still on Render only:
- FCI (Financial Conditions Index)
- Weekly trends (4w/13w/YoY transforms)
- Rates/EVDS macro panels

When the remaining three are ported, the legacy stack can be retired:
1. Delete `src/dashboard/` and `src/analytics/` (or keep `analytics` for offline use)
2. Stop committing `data/bddk_data.db.gz`
3. Remove `render.yaml`
4. Drop the gzip+push step from the refresh workflow
