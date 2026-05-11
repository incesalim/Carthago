# Project State — verified 2026-05-11

> **Reading order:** [ARCHITECTURE.md](ARCHITECTURE.md) for the end-to-end
> picture (Python ingest in GitHub Actions → R2 → D1 → Cloudflare Workers
> dashboard), then this file for current snapshot, then
> [METRICS.md](METRICS.md) and [OPERATIONS.md](OPERATIONS.md).

> **Render → Cloudflare migration is complete.** The legacy Python Dash
> dashboard, its analytics package, `render.yaml`, `run.py`, and
> `scripts/dev.py` were removed on 2026-05-11. References to
> `src/dashboard/` or `src/analytics/` elsewhere in the docs are
> historical. Production runs only on Cloudflare Workers + D1 + R2.

---

## Entry points

| Command | Purpose |
|---|---|
| `python scripts/dev.py` | Dashboard with hot reload (development) |
| `python scripts/refresh.py --push` | Refresh monthly + weekly data, vacuum, gzip, push to GitHub (triggers Render redeploy) |
| `python run.py` | Simple "just run the dashboard" entry (no reload) |
| `python scripts/scrape_all_banks.py` | Download new quarterly BRSA PDFs (per-bank audit reports) |
| `python scripts/extract_all_audit_reports.py` | Parse downloaded PDFs into `bank_audit_*` tables |

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
| `audit_reports/extractor.py` | pdfplumber-based BRSA Financial Report parser (handles EN/TR, deposit/participation/investment banks) |
| `audit_reports/loader.py` | Inserts a parsed `BankReport` into the 3 `bank_audit_*` tables (idempotent upsert) |
| `audit_reports/schema.py` | DDL for `bank_audit_balance_sheet` / `bank_audit_profit_loss` / `bank_audit_extractions` |

## Database — `data/bddk_data.db` (~370 MB, 50 MB compressed)

### Sector-aggregate tables (BDDK monthly + weekly bulletins)

| Table | Coverage |
|---|---|
| `balance_sheet`, `income_statement`, `loans`, `deposits`, `financial_ratios`, `other_data` | 2020-01 → 2026-02 (74 months), sector + 5 ownership groups |
| `weekly_series` | 2019-11-22 → 2026-04-10 (334 weeks, 124 items × 6 banks × 3 currencies) |
| `raw_api_responses`, `raw_weekly_responses` | Raw JSON cache |
| `download_log`, `bank_types`, `table_definitions` | Metadata |

### Per-bank audit-report tables (NEW — added May 2026)

| Table | Coverage |
|---|---|
| `bank_audit_balance_sheet` | Per-bank Assets / Liabilities / Off-Balance rows. ~144k rows. 31 banks × 16 quarters × {consolidated, unconsolidated}. 6 columns: TL / FC / Total × current period (prior is the previous report's current). |
| `bank_audit_profit_loss` | Per-bank P&L line items. ~56k rows. Single amount column. |
| `bank_audit_extractions` | One row per ingested PDF: `(bank_ticker, period, kind)` + row counts + `success` flag. |

Coverage: 32 banks total in URL config (`data/banks/audit_report_urls.json`); 31 in DB (TAKAS pending manual download — F5 bot mitigation blocks Python scraping). 920 PDFs ingested, 888 fully successful, 32 with partial extraction (one of the four statements has fewer rows than expected).

## Bank-type taxonomy

Sector (10001) = Private Deposit (10003) + State Deposit (10004) + Foreign Deposit (10005) + Participation (10006) + Dev&Inv (10007). Codes 10008–10010 are ownership-only cross-cuts. See METRICS.md §2 + §10 for the weekly-API remap (same numbers, different semantics).

## Data flow

**Layer 1 — sector aggregates (BDDK monthly + weekly bulletins, EVDS macro):**

1. `scripts/refresh.py` → `BDDKAPIScraper` (monthly) + `BDDKWeeklyAPIScraper` (weekly) + EVDS.
2. Raw JSON cached; typed tables populated via `INSERT OR REPLACE`.
3. `data_store.initialize()` runs at app startup, pre-computes 28 DataFrames.
4. Sections import `metrics_ext` (public) + `data_store` (cached series) for chart content.
5. EVDS-backed panels call `evds.fetch_series(code, start, end)` live.

**Layer 2 — per-bank audit reports (quarterly):**

1. URL config in `data/banks/audit_report_urls.json` (one entry per bank → `{consolidated, unconsolidated}` → `{YYYYQn → direct PDF URL}`).
2. `scripts/scrape_all_banks.py` downloads PDFs in parallel into `data/audit_reports/{ticker}/{TICKER}_{period}_{kind}.pdf`. Idempotent (skips files on disk).
3. `scripts/extract_all_audit_reports.py` runs `audit_reports.extractor` over each PDF in parallel, then `audit_reports.loader` upserts rows into `bank_audit_*` tables. Idempotent via the extractions log.
4. The two layers are designed to reconcile: sum of per-bank values should approximate BDDK group/sector aggregates (with caveats for clearing-house banks like Takasbank).

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
- Verify any unfamiliar file against this doc before editing — the codebase has been consolidated (Apr 2026) and audit-reports module added (May 2026).
- **Per-bank audit-report data is in the DB but not yet surfaced in the dashboard.** The `bank_audit_*` tables are queryable but no section uses them yet. Adding a per-bank tab is the natural next step; see `src/audit_reports/README.md` for query examples.
- **TAKAS missing**: Takasbank's IR site has F5 bot mitigation that blocks Python downloads. URL config exists; PDFs need to be downloaded manually into `data/audit_reports/takas/` then `extract_all_audit_reports.py` will pick them up.
- **32 partial extractions** (out of 920) are flagged `success=0` in `bank_audit_extractions`. Mostly ISCTR (10), FIBA (8), VAKBN (8), TFKB (4), AKBNK (2). Each is a layout edge case in `audit_reports/extractor.py` that can be patched bank-by-bank.
