# Project State — verified 2026-04-23

> **See also:** [METRICS.md](METRICS.md) for every metric formula,
> [OPERATIONS.md](OPERATIONS.md) for the refresh/deploy cadence.

Authoritative snapshot of the repo's current shape. Older Dec-2025 notes
referenced here in earlier versions have been deleted.

---

## Entry points

| Command | Purpose |
|---|---|
| `python scripts/dev.py` | Dashboard with hot reload (development) |
| `python scripts/refresh.py --push` | Refresh monthly + weekly data, vacuum, gzip, push to GitHub (triggers Render redeploy) |
| `python run.py` | Simple "just run the dashboard" entry (no reload) |

## Source layout (`src/`)

| Path | Purpose |
|---|---|
| `analytics/metrics_catalog.py` | Metric definitions + `BANK_TYPES` taxonomy |
| `analytics/metrics_engine.py` | Class-based SQL access + base calculations (internal) |
| `analytics/metrics_ext.py` | **Public metric layer** — sections import from here |
| `analytics/data_store.py` | In-memory cache, initialized at app startup |
| `dashboard/app.py` | Dash entry + layout + tab routing |
| `dashboard/series.py` | Canonical series registry (EVDS/BDDK codes → short keys) |
| `dashboard/evds.py` | TCMB EVDS v3 client with auto-chunking |
| `dashboard/charts.py` | Plotly helpers (trend, bar, stacked area, KPI card, narrative card) |
| `dashboard/panel_factory.py` | Config-driven panel renderer (new, opt-in) |
| `dashboard/theme.py` | Meridian design tokens (oxblood accent, warm neutrals, fonts) |
| `dashboard/weekly_ext.py` | Weekly-series query helpers + 4w/13w/YoY growth transforms |
| `dashboard/sections/*.py` | One file per dashboard tab |
| `dashboard/assets/*.css` | Meridian CSS auto-loaded by Dash |
| `scrapers/bddk_api_scraper.py` | Monthly bulletin scraper (JSON API) |
| `scrapers/weekly_api_scraper.py` | Weekly bulletin scraper (KiyaslamaJsonGetir) |

## Database — `data/bddk_data.db` (~340 MB, 45 MB compressed)

| Table | Coverage |
|---|---|
| `balance_sheet`, `income_statement`, `loans`, `deposits`, `financial_ratios`, `other_data` | 2020-01 → 2026-02 (74 months) |
| `weekly_series` | 2019-11-22 → 2026-04-10 (334 weeks, 124 items × 6 banks × 3 currencies) |
| `raw_api_responses`, `raw_weekly_responses` | Raw JSON cache |
| `download_log`, `bank_types`, `table_definitions` | Metadata |

## Bank-type taxonomy

Sector (10001) = Private Deposit (10003) + State Deposit (10004) + Foreign Deposit (10005) + Participation (10006) + Dev&Inv (10007). Codes 10008–10010 are ownership-only cross-cuts. See METRICS.md §2 + §10 for the weekly-API remap (same numbers, different semantics).

## Data flow

1. `scripts/refresh.py` → `BDDKAPIScraper` (monthly) + `BDDKWeeklyAPIScraper` (weekly) + EVDS.
2. Raw JSON cached; typed tables populated via `INSERT OR REPLACE`.
3. `data_store.initialize()` runs at app startup, pre-computes 28 DataFrames.
4. Sections import `metrics_ext` (public) + `data_store` (cached series) for chart content.
5. EVDS-backed panels call `evds.fetch_series(code, start, end)` live.

## Deployment

- **Local:** `python scripts/dev.py` → http://localhost:8050
- **Production:** https://turkish-banking-sector.onrender.com (Render free tier, redeploys on every git push)
- **Auto-refresh:** GitHub Actions workflow `refresh-data.yml` runs every Saturday 03:00 UTC → commits new DB snapshot → Render picks it up

## Entry-point layering (sections → metrics)

```
section code  →  metrics_ext (public API)
                       ↓  (internally)
                 MetricsEngine + data_store (cache)
                       ↓
                   SQLite DB + EVDS live
```

Rule: sections must import only from `metrics_ext`, never `metrics_engine` directly.

## For the next session

- Panel factory ([panel_factory.py](../src/dashboard/panel_factory.py)) is opt-in; existing section files still use direct Plotly. Migrate panels to factory specs incrementally when adding new ones.
- Verify any unfamiliar file against this doc before editing — the codebase has been consolidated recently (Apr 2026).
