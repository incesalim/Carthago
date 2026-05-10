# BDDK Banking Analytics

Turkish banking-sector analytical platform. Two parallel stacks during the
Render → Cloudflare migration; see [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
for the full picture.

**Two data layers:**

1. **Sector aggregates** — monthly + weekly bulletins from BDDK (Bankacılık
   Düzenleme ve Denetleme Kurumu) plus EVDS macro/rate series.
2. **Per-bank quarterly data** — each bank's published BRSA Financial Report
   PDF parsed into structured rows. 32 banks × up to 16 quarters (2022-Q1 →
   2025-Q4), ~98% of sector by assets.

Both live in the same SQLite (`data/bddk_data.db`), and selected tables are
mirrored to **Cloudflare D1** for the new edge dashboard.

**Two dashboards (during migration):**

| Dashboard | Stack | URL |
|---|---|---|
| Legacy | Python · Dash · Plotly · Render | <https://turkish-banking-sector.onrender.com> |
| New | Next.js 15 · OpenNext · D1 · Cloudflare Workers | <https://turkish-banking-dashboard.incesalim10.workers.dev> |

## Quick start

```bash
# Python pipeline (ingestion + legacy dashboard)
pip install -r requirements.txt
python run.py                       # interactive CLI
python scripts/refresh.py --push    # full refresh → push → Render redeploys

# Next.js dashboard (Cloudflare side)
cd web
npm install
npm run dev                         # local: http://localhost:3000
npm run deploy                      # build + deploy to Cloudflare
```

## Project layout

```
bddk_analysis/
├── README.md                       ← this file
├── requirements.txt                ← Python deps
├── run.py                          ← Python CLI entry
├── render.yaml                     ← Render service config (legacy)
├── .env, .env.example, .gitignore
│
├── docs/                           ← canonical docs (read these)
│   ├── ARCHITECTURE.md             ← dual-stack overview · start here
│   ├── PROJECT_STATE.md            ← current snapshot of code + DB
│   ├── METRICS.md                  ← every metric's formula + source
│   └── OPERATIONS.md               ← refresh + deploy cadence
│
├── src/                            ← Python — ingestion + legacy dashboard
│   ├── config.py
│   ├── scrapers/                   ← BDDK monthly + weekly API scrapers
│   ├── analytics/                  ← metrics, FCI, in-memory cache
│   ├── audit_reports/              ← per-bank PDF extraction (extractor + loader)
│   ├── dashboard/                  ← Render Dash app · marked _LEGACY.md
│   ├── reports/, data/             ← project-specific helpers
│   └── __init__.py
│
├── scripts/                        ← Python CLI entry points
│   ├── refresh.py                  ← MAIN: full refresh + git push (Render)
│   ├── update_monthly.py / update_weekly.py
│   ├── scrape_all_banks.py         ← bank IR PDF download (parallel)
│   ├── extract_all_audit_reports.py ← PDF → bank_audit_* tables
│   ├── generate_d1_migrations.py   ← export local SQLite → D1 import files
│   ├── push_to_d1.py               ← incremental D1 sync
│   ├── generate_metrics_docs.py
│   ├── dev.py                      ← legacy Dash hot-reload
│   └── backfills/                  ← historical / one-off scripts
│
├── web/                            ← Next.js 15 + OpenNext (Cloudflare Workers)
│   ├── app/                        ← routes (overview / credit / deposits / …)
│   │   ├── components/             ← TrendChart, BarByBank, StackedArea, Nav
│   │   ├── lib/                    ← db.ts (D1 binding) · metrics.ts (SQL helpers)
│   │   ├── sector/                 ← sector total-assets + key-ratios pages
│   │   ├── credit/, deposits/, asset-quality/, capital/, profitability/
│   │   └── weekly/, rates/         ← placeholders
│   ├── wrangler.jsonc, open-next.config.ts
│   ├── package.json
│   └── migrations/                 ← gitignored · regenerated from local SQLite
│
├── data/                           ← all data (mostly gitignored)
│   ├── bddk_data.db                ← SQLite source of truth (~370 MB, gitignored)
│   ├── bddk_data.db.gz             ← compressed snapshot (~55 MB, in git for Render)
│   ├── backups/                    ← old DB snapshots before risky migrations
│   ├── audit_reports/              ← bank PDFs (~2 GB, gitignored)
│   ├── banks/                      ← URL config + BDDK bank list
│   ├── evds_cache/                 ← TCMB EVDS API cache
│   └── external_reports/           ← reference PDFs (BBVA, IMF, …)
│
├── logs/                           ← runtime logs (gitignored)
│
└── .github/workflows/
    ├── refresh-data.yml            ← Saturday cron: scrape → push to D1 + Render
    └── deploy-cloudflare.yml       ← Push trigger: Cloudflare deploy
```

## Cadences

| | When | Command / trigger |
|---|---|---|
| **BDDK weekly + monthly refresh** | Saturday 03:00 UTC (auto) or manual | `python scripts/refresh.py --push` |
| **Cloudflare D1 sync** | Auto, runs after refresh | `python scripts/push_to_d1.py --hours 168` |
| **Render redeploy** | Every git push to master | (auto via Render) |
| **Cloudflare deploy** | Every push that touches `web/` | `.github/workflows/deploy-cloudflare.yml` |
| **Quarterly audit-report scrape** | After each quarter (manual) | `scripts/scrape_all_banks.py` then `extract_all_audit_reports.py` |

See [`docs/OPERATIONS.md`](docs/OPERATIONS.md) for full instructions.

## License

Educational / analytical use. Respect BDDK's terms of service.
