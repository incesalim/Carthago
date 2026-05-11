# BDDK Banking Analytics

Turkish banking-sector analytical platform. End-to-end stack:

- **Ingestion** — Python scripts in `scripts/` and `src/`, run by the
  GitHub Actions cron (no laptop required).
- **Storage** — Cloudflare R2 (bank audit-report PDFs) and Cloudflare D1
  (structured rows: monthly + weekly bulletins, EVDS macro, per-bank
  quarterly statements).
- **Dashboard** — Next.js 15 + OpenNext, deployed to Cloudflare Workers.
  Live at <https://turkish-banking-dashboard.incesalim10.workers.dev>.

Two data layers cohabit in D1:

1. **Sector aggregates** — monthly + weekly bulletins from BDDK
   (Bankacılık Düzenleme ve Denetleme Kurumu) plus TCMB EVDS macro/rate
   series.
2. **Per-bank quarterly data** — each bank's published BRSA Financial
   Report PDF parsed into structured rows. 32 banks × up to 16 quarters
   (2022-Q1 → 2026-Q1), ~98% of sector by assets. PDFs live in R2.

## Quick start

```bash
# Python pipeline — only needed for local dev / one-off backfills.
# Production runs in GitHub Actions; nothing to install on your laptop.
pip install -r requirements.txt
python scripts/refresh.py                  # monthly + weekly + EVDS (local SQLite)
python scripts/sync_audit_reports.py       # scrape new PDFs → R2 → extract → SQLite
python scripts/push_to_d1.py --hours 168   # push incremental rows to D1

# Next.js dashboard
cd web
npm install
npm run dev                                # http://localhost:3000
npm run deploy                             # build + deploy to Cloudflare
```

## Project layout

```
bddk_analysis/
├── README.md
├── requirements.txt                ← Python deps (ingestion only)
├── .env, .env.example, .gitignore
│
├── docs/                           ← canonical docs (read these)
│   ├── ARCHITECTURE.md
│   ├── PROJECT_STATE.md
│   ├── METRICS.md
│   └── OPERATIONS.md
│
├── src/                            ← Python — ingestion + extraction
│   ├── config.py
│   ├── scrapers/                   ← BDDK monthly/weekly + EVDS scrapers
│   │   ├── evds_client.py          ← TCMB EVDS HTTP client
│   │   ├── evds_scraper.py         ← scrape EVDS → SQLite
│   │   └── ...                     ← BDDK monthly + weekly scrapers
│   └── audit_reports/              ← per-bank PDF extraction
│       ├── extractor.py            ← pdfplumber + pymupdf with fallback
│       ├── loader.py               ← upsert into bank_audit_* tables
│       ├── schema.py
│       └── r2_storage.py           ← Cloudflare R2 (S3-compat) wrapper
│
├── scripts/                        ← Python CLI entry points
│   ├── refresh.py                  ← monthly + weekly + EVDS + gzip (incremental)
│   ├── sync_audit_reports.py       ← scrape bank IR → R2 → extract → SQLite
│   ├── update_monthly.py / update_weekly.py
│   ├── push_to_d1.py               ← incremental D1 sync (handles every table)
│   ├── migrate_pdfs_to_r2.py       ← one-shot uploader for existing local PDFs
│   ├── generate_d1_migrations.py   ← export local SQLite → D1 import files
│   ├── extract_all_audit_reports.py
│   ├── scrape_all_banks.py
│   └── backfills/
│
├── web/                            ← Next.js 15 + OpenNext (Cloudflare Workers)
│   ├── app/                        ← routes
│   │   ├── components/             ← TrendChart, BarByBank, StackedArea, …
│   │   ├── lib/                    ← db.ts (D1 binding) · metrics.ts (SQL helpers)
│   │   ├── credit/, deposits/, asset-quality/, capital/, profitability/
│   │   ├── weekly/, rates/, banks/, sector/
│   │   └── page.tsx                ← Overview
│   ├── wrangler.jsonc, open-next.config.ts
│   ├── package.json
│   └── migrations/                 ← gitignored · regenerated from local SQLite
│
├── data/                           ← all data (mostly gitignored)
│   ├── bddk_data.db                ← local SQLite (gitignored)
│   ├── bddk_data.db.gz             ← committed snapshot (~55 MB) — cron bootstraps from this
│   ├── banks/                      ← URL config + BDDK bank list
│   └── external_reports/           ← reference PDFs (BBVA, IMF, …)
│
└── .github/workflows/
    ├── refresh-data.yml            ← Sat 03 UTC: monthly + weekly + EVDS + audit + push
    ├── refresh-evds-daily.yml      ← Sun-Fri 05 UTC: EVDS only + push
    └── deploy-cloudflare.yml       ← on web/ push: deploy
```

## Cadences

| | When | Workflow |
|---|---|---|
| **EVDS daily refresh** | Sun–Fri 05:00 UTC | `refresh-evds-daily.yml` |
| **Full weekly refresh** | Saturday 03:00 UTC | `refresh-data.yml` (monthly + weekly + EVDS + audit reports + D1 push) |
| **Audit-report scrape** | Saturday (above) | inside `sync_audit_reports.py` — pulls new bank IR PDFs to R2, extracts, upserts |
| **Cloudflare dashboard deploy** | Every push to `web/` | `deploy-cloudflare.yml` |

All schedules can be triggered manually from **GitHub → Actions → Run workflow**.

See [`docs/OPERATIONS.md`](docs/OPERATIONS.md) for full instructions.

## License

Educational / analytical use. Respect BDDK's and TCMB's terms of service.
