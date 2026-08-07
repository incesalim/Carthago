# Turkish Banking Sector Analytics

An analytical platform for the Turkish banking sector built around three
official sources:

- **BDDK** (*Bankacılık Düzenleme ve Denetleme Kurumu*) — the Banking
  Regulation and Supervision Agency, publisher of monthly + weekly
  sector bulletins and per-bank quarterly BRSA Financial Reports.
- **TCMB EVDS** (*Türkiye Cumhuriyet Merkez Bankası Elektronik Veri
  Dağıtım Sistemi*) — the Central Bank's macro / interest-rate data
  service.
- **TBB** (*Türkiye Bankalar Birliği*) — the Banks Association of Türkiye,
  publisher of quarterly sector-wide digital / internet / mobile banking
  statistics.

The entire pipeline runs in the cloud: GitHub Actions for ingestion,
Cloudflare for storage and display.

- **Ingestion** — Python scripts in `scripts/` and `src/`, executed by
  scheduled GitHub Actions workflows.
- **Storage** — Cloudflare R2 (bank audit-report PDFs + the SQLite
  staging snapshot) and Cloudflare D1 (structured rows: monthly +
  weekly bulletins, EVDS macro series, per-bank quarterly statements).
- **Dashboard** — Next.js 16 + OpenNext, deployed to Cloudflare Workers.
  Live at <https://carthago.app>.
  D1 reads are cached ~12h via a KV-backed data cache. A password-gated
  `/admin` control center (data health, refresh triggers, traffic) lives at
  `/admin` — see [`docs/ADMIN.md`](docs/ADMIN.md).

Two data layers cohabit in D1:

1. **Sector aggregates** — monthly + weekly bulletins from BDDK plus
   TCMB EVDS macro / rate series.
2. **Per-bank quarterly data** — each bank's published BRSA Financial
   Report PDF parsed into structured rows. 38 banks × up to 17 quarters
   (2022-Q1 → 2026-Q1), 1,050 PDFs, ~98% of sector by assets. PDFs live in R2.

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
carthago/
├── README.md
├── AGENTS.md                       ← repo guide for coding agents (CLAUDE.md imports it)
├── requirements.txt                ← Python deps (ingestion only)
├── .env, .env.example, .gitignore
│
├── docs/                           ← canonical docs — start at docs/README.md
│   ├── README.md                   ← doc index + reading order
│   ├── ARCHITECTURE.md
│   ├── PROJECT_STATE.md            ← current state (dated history → CHANGELOG.md)
│   ├── CHANGELOG.md
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
│   ├── tbb/                        ← TBB quarterly digital-banking .xls/.xlsx → SQLite
│   └── audit_reports/              ← per-bank PDF extraction
│       ├── extractor.py            ← PyMuPDF (fitz) only
│       ├── loader.py               ← upsert into bank_audit_* tables
│       ├── schema.py
│       └── r2_storage.py           ← Cloudflare R2 (S3-compat) wrapper
│
├── scripts/                        ← Python CLI entry points
│   ├── refresh.py                  ← monthly + weekly + EVDS + gzip (incremental)
│   ├── sync_audit_reports.py       ← scrape bank IR → R2 → extract → SQLite
│   ├── update_monthly.py / update_weekly.py
│   ├── update_tbb_digital.py       ← TBB quarterly digital-banking → SQLite
│   ├── push_to_d1.py               ← incremental D1 sync (handles every table)
│   ├── migrate_pdfs_to_r2.py       ← one-shot uploader for existing local PDFs
│   ├── generate_d1_migrations.py   ← export local SQLite → D1 import files
│   ├── extract_all_audit_reports.py
│   ├── scrape_all_banks.py
│   └── backfills/
│
├── web/                            ← Next.js 16 + OpenNext (Cloudflare Workers)
│   ├── app/                        ← routes
│   │   ├── components/             ← TrendChart, BarByBank, StackedArea, …
│   │   ├── lib/                    ← db.ts (D1 binding) · metrics.ts (SQL helpers)
│   │   ├── credit/, deposits/, asset-quality/, capital/, profitability/
│   │   ├── rates/, liquidity/, market-risk/, cross-bank/, banks/, ownership/
│   │   ├── earnings/, funds/, digital/, economy/, news/, regulation/
│   │   ├── non-bank/, disclosures/, pipeline/
│   │   ├── _valuation/, _franchise/  ← parked: the leading _ un-routes them (Next
│   │   │                                private folders). Don't rename without reading why
│   │   ├── admin/, api/admin/      ← password-gated control center
│   │   └── page.tsx                ← Overview
│   ├── wrangler.jsonc, open-next.config.ts
│   ├── package.json
│   ├── migrations/                 ← hand-authored D1 schema migrations (source of truth)
│   └── seeds/                      ← gitignored · bulk data-seed dumps (generate_d1_migrations.py)
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
    ├── refresh-evds-daily.yml      ← Sun-Fri 05 UTC: daily-frequency EVDS → D1
    ├── refresh-bddk-bulletins.yml  ← month edges + Fridays: BDDK bulletins → D1
    ├── refresh-data.yml            ← Sat 03 UTC: monthly + weekly + EVDS + TBB digital → D1
    ├── acquire-audit.yml           ← manual: download audit PDFs without extraction
    ├── refresh-audit.yml           ← filing windows daily: acquire + extract + one D1 batch
    ├── backfill-audit-source-capture.yml ← manual: preserve omitted audit-table source rows
    ├── refresh-news-daily.yml      ← daily: KAP/TCMB/BDDK news → D1
    ├── summarize-regulations.yml   ← weekly: LLM regulation briefing → D1
    ├── healthcheck.yml             ← daily: D1 freshness → Telegram/Discord alert
    ├── ci.yml                      ← PRs: ruff + pytest + eslint + tsc
    └── deploy-cloudflare.yml       ← on web/ push: migrate + build + deploy
# also: pyproject.toml (ruff/pytest), tests/, .github/dependabot.yml
```

## Cadences

| | When | Workflow |
|---|---|---|
| **EVDS daily refresh** | Sun–Fri 05:00 UTC | `refresh-evds-daily.yml` (daily/workday series only) |
| **BDDK bulletins** | First/last five days + Friday publication window | `refresh-bddk-bulletins.yml` (no EVDS/audit) |
| **Full weekly refresh** | Saturday 03:00 UTC | `refresh-data.yml` (monthly + weekly + EVDS + TBB digital + D1 push) |
| **Audit-report arrival** | Daily in quarterly filing windows | `refresh-audit.yml` — discover → R2 → extract/validate/coverage → one D1 batch → snapshot; quiet checks write nothing |
| **Acquisition-only diagnostic** | Manual / admin only | `acquire-audit.yml` — download a PDF without extracting it |
| **Health check** | Daily 06:00 UTC | `healthcheck.yml` — D1 freshness → alert if stale |
| **CI quality gates** | Every PR | `ci.yml` — ruff + pytest + eslint + tsc |
| **Cloudflare dashboard deploy** | Every push to `web/` | `deploy-cloudflare.yml` (migrate + build + deploy) |

All schedules can be triggered manually from **GitHub → Actions → Run workflow**.

See [`docs/OPERATIONS.md`](docs/OPERATIONS.md) for full instructions.

## License

The **code** in this repository is licensed under the [GNU Affero General
Public License v3.0](LICENSE).

    Carthago — analytics for the Turkish banking sector
    Copyright (C) 2026 Salim İnce

You may use, study, modify and redistribute it. If you run a modified
version as a network service, AGPL §13 requires you to offer that
service's users the corresponding source. For a commercial licence
without that obligation, contact <incesalim10@gmail.com>.

### The data is not covered by this licence

The AGPL grants rights to *this codebase only*. It grants no rights to the
underlying data, which is derived from third parties — BDDK, TCMB EVDS,
TBB, KAP, TEFAS, TKBB and BIST market data — each carrying its own terms
of use. Redistribution of that data, including through the public
[`/api/v1`](docs/API.md) endpoints, remains subject to those terms
regardless of anything stated here. Third-party reports under
`data/external_reports/` are deliberately not redistributed.

What each source actually permits — and what changes if this is ever
monetised — is recorded in
[`docs/knowledge/data-source-terms-audit-2026-07-25.md`](docs/knowledge/data-source-terms-audit-2026-07-25.md).
