# Turkish Banking Sector Analytics

An analytical platform for the Turkish banking sector built around two
official sources:

- **BDDK** (*Bankacılık Düzenleme ve Denetleme Kurumu*) — the Banking
  Regulation and Supervision Agency, publisher of monthly + weekly
  sector bulletins and per-bank quarterly BRSA Financial Reports.
- **TCMB EVDS** (*Türkiye Cumhuriyet Merkez Bankası Elektronik Veri
  Dağıtım Sistemi*) — the Central Bank's macro / interest-rate data
  service.

The entire pipeline runs in the cloud: GitHub Actions for ingestion,
Cloudflare for storage and display.

- **Ingestion** — Python scripts in `scripts/` and `src/`, executed by
  scheduled GitHub Actions workflows.
- **Storage** — Cloudflare R2 (bank audit-report PDFs + the SQLite
  staging snapshot) and Cloudflare D1 (structured rows: monthly +
  weekly bulletins, EVDS macro series, per-bank quarterly statements).
- **Dashboard** — Next.js 15 + OpenNext, deployed to Cloudflare Workers.
  Live at <https://turkish-banking-dashboard.incesalim10.workers.dev>.
  D1 reads are cached ~1h via a KV-backed data cache. A password-gated
  `/admin` control center (data health, refresh triggers, traffic) lives at
  `/admin` — see [`docs/ADMIN.md`](docs/ADMIN.md).

Two data layers cohabit in D1:

1. **Sector aggregates** — monthly + weekly bulletins from BDDK plus
   TCMB EVDS macro / rate series.
2. **Per-bank quarterly data** — each bank's published BRSA Financial
   Report PDF parsed into structured rows. 32 banks × up to 17 quarters
   (2022-Q1 → 2026-Q1), ~98% of sector by assets. PDFs live in R2.

## Quick start

Production runs in GitHub Actions on a schedule — local installation is
only needed for development or ad-hoc backfills.

```bash
# Python pipeline (ingestion)
pip install -r requirements.txt
python scripts/refresh.py                              # monthly + weekly + EVDS (local SQLite)
python scripts/sync_audit_reports.py --db data/bank_audit.db   # audit PDFs → R2 → extract (own DB)
python scripts/push_to_d1.py --hours 168               # push incremental rows to D1

# Next.js dashboard (display)
cd web
npm install
npm run dev                                # http://localhost:3000
npm run deploy                             # build + deploy to Cloudflare
```

Required secrets (in shell env or `.env` for local runs; repo Secrets
for GitHub Actions): `EVDS_API_KEY`, `CLOUDFLARE_API_TOKEN`,
`R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`.

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
│   ├── OPERATIONS.md
│   └── ADMIN.md                    ← /admin control-panel setup
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
│   ├── banks/                      ← URL config + BDDK bank list (committed)
│   └── external_reports/           ← reference PDFs (BBVA, IMF, …) [local]
│   # Not in git; live in cloud storage:
│   #   state/bddk_data.db.gz       ← R2 bucket bddk-audit-reports (bulletin/EVDS lane snapshot)
│   #   state/bank_audit.db.gz      ← R2 bucket bddk-audit-reports (audit lane snapshot)
│   #   audit_reports/*.pdf         ← R2 bucket bddk-audit-reports, by ticker
│   #   bddk_data.db / bank_audit.db ← rebuilt in each cron run from the R2 snapshot
│
└── .github/workflows/
    ├── refresh-evds-daily.yml      ← Sun-Fri 05 UTC: EVDS only → D1
    ├── refresh-bddk-bulletins.yml  ← Sat 02 UTC: monthly + weekly bulletins → D1
    ├── refresh-data.yml            ← Sat 03 UTC: monthly + weekly + EVDS → D1
    ├── refresh-audit.yml           ← Sun 04 UTC: audit PDFs → bank_audit_* → D1 (own lane)
    ├── refresh-news-daily.yml      ← daily: KAP/TCMB/BDDK news → D1
    ├── summarize-regulations.yml   ← weekly: LLM regulation briefing → D1
    └── deploy-cloudflare.yml       ← on web/ push: deploy
```

## Cadences

| | When | Workflow |
|---|---|---|
| **EVDS daily refresh** | Sun–Fri 05:00 UTC | `refresh-evds-daily.yml` |
| **Weekly bulletins** | Saturday 02:00 UTC | `refresh-bddk-bulletins.yml` (monthly + weekly, no EVDS/audit) |
| **Full weekly refresh** | Saturday 03:00 UTC | `refresh-data.yml` (monthly + weekly + EVDS + D1 push) |
| **Audit-report scrape** | Sunday 04:00 UTC | `refresh-audit.yml` — own DB + R2 snapshot; new bank IR PDFs → R2 → extract → D1 |
| **Cloudflare dashboard deploy** | Every push to `web/` | `deploy-cloudflare.yml` |

All schedules can be triggered manually from **GitHub → Actions → Run workflow**.

See [`docs/OPERATIONS.md`](docs/OPERATIONS.md) for full instructions.

## License

Educational / analytical use. Respect BDDK's and TCMB's terms of service.
