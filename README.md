# BDDK Banking Analytics

Two-layer analytical system for the Turkish banking sector:

1. **Sector aggregates** — monthly + weekly bulletins from **BDDK** (Bankacılık
   Düzenleme ve Denetleme Kurumu), plus EVDS macro/rate series — driving an
   interactive Dash dashboard.
2. **Per-bank quarterly data** — each bank's published BRSA Financial Report
   PDF parsed into structured rows. 32 banks × up to 16 quarters
   (2022Q1 → 2025Q4) covering ~98% of sector assets.

Both layers live in the same SQLite database (`data/bddk_data.db`) and are
designed to reconcile against each other.

## Quick start

```bash
pip install -r requirements.txt
python run.py                       # interactive CLI (dashboard / refresh)
python scripts/refresh.py --push    # refresh BDDK monthly + weekly + EVDS
```

Dashboard runs at `http://localhost:8050`.

## What's in the database

| Table | Granularity | Coverage |
|---|---|---|
| `balance_sheet`, `income_statement`, `loans`, `deposits`, `financial_ratios`, `other_data` | Sector + 5 ownership groups | 2020-01 → 2026-02 (74 months) |
| `weekly_series` | Sector + 6 BDDK banks × 3 currencies × 124 items | 2019-11 → 2026-04 (334 weeks) |
| `bank_audit_balance_sheet` | Per-bank Assets / Liabilities / Off-Balance | 2022Q1 → 2025Q4 (16 quarters × 32 banks) |
| `bank_audit_profit_loss` | Per-bank P&L line items | same |
| `bank_audit_extractions` | One row per ingested PDF (success flag) | same |
| `raw_api_responses`, `raw_weekly_responses` | JSON cache | for re-parsing |
| `download_log`, `bank_types`, `table_definitions` | Metadata | — |

## Project structure

```
bddk_analysis/
├── run.py                        ← interactive CLI entry
├── README.md, requirements.txt, render.yaml, .env(.example)
│
├── src/                          ← code modules
│   ├── config.py
│   ├── scrapers/                 ← BDDK monthly + weekly API scrapers
│   ├── analytics/                ← metrics_catalog, metrics_engine, fci_engine, data_store
│   ├── audit_reports/            ← per-bank PDF → SQLite (extractor + loader + schema)
│   │   └── README.md             ← module-level pipeline docs
│   ├── dashboard/                ← Dash app, sections, charts, EVDS client
│   ├── reports/, data/           ← project-specific helpers
│   └── __init__.py
│
├── scripts/                      ← CLI entry points
│   ├── refresh.py                ← BDDK monthly + weekly + EVDS update + git push
│   ├── update_monthly.py / update_weekly.py / update_db_2026.py
│   ├── backfill_2020_2023.py / backfill_weekly_2y.py / backfill_weekly_2020_2023.py
│   ├── scrape_all_banks.py       ← downloads quarterly BRSA PDFs from bank IR sites
│   ├── extract_all_audit_reports.py  ← parses PDFs into bank_audit_* tables
│   ├── generate_metrics_docs.py
│   └── dev.py                    ← dashboard with hot reload
│
├── data/
│   ├── bddk_data.db              ← SQLite (~370 MB)
│   ├── audit_reports/            ← 32 bank folders, ~1.8 GB of PDFs
│   ├── banks/                    ← URL config + BDDK bank list
│   ├── evds_cache/               ← TCMB EVDS API cache
│   └── external_reports/         ← BBVA / IMF / OECD / TCMB reference PDFs
│
├── docs/                         ← canonical docs (this is the source of truth)
│   ├── PROJECT_STATE.md          ← architectural snapshot — read this first
│   ├── METRICS.md                ← every metric formula + source
│   └── OPERATIONS.md             ← refresh cadence + commands
│
└── logs/                         ← refresh / backfill logs
```

## Daily / weekly cadence

```bash
python scripts/refresh.py --push   # Saturdays after BDDK posts weekly data
```

Runs the monthly + weekly + EVDS pipeline, vacuums the DB, gzips it, and
pushes to GitHub (Render auto-redeploys).

GitHub Actions workflow `refresh-data.yml` runs the same automatically every
Saturday 03:00 UTC.

## Quarterly cadence (per-bank audit reports)

After each quarter-end (~late Apr / Jul / Oct / Feb):

1. Add new period URLs to `data/banks/audit_report_urls.json` (banks rename
   files unpredictably each quarter, so URLs aren't templatable).
2. `python scripts/scrape_all_banks.py` — downloads new PDFs, idempotent.
3. `python scripts/extract_all_audit_reports.py` — parses into DB.

See [`src/audit_reports/README.md`](src/audit_reports/README.md) for details.

## Production

- **Dashboard:** https://turkish-banking-sector.onrender.com
- **Repo:** GitHub (auto-deployed via Render free tier)

## License

Educational / analytical use. Respect BDDK's terms of service.
