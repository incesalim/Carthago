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
  D1 reads are cached ~1h via a KV-backed data cache. A password-gated
  `/admin` control center (data health, refresh triggers, traffic) lives at
  `/admin` — see [`docs/ADMIN.md`](docs/ADMIN.md).

Two data layers cohabit in D1:

1. **Sector aggregates** — monthly + weekly bulletins from BDDK plus
   TCMB EVDS macro / rate series.
2. **Per-bank quarterly data** — each bank's published BRSA Financial
   Report PDF parsed into structured rows. 38 banks × up to 18 quarters
   (2022-Q1 → 2026-Q2, season in progress — 1,093 extractions as of
   2026-08-13), ~98% of sector by assets. PDFs live in R2.

## Quick start

Production runs in GitHub Actions on a schedule — local installation is
only needed for development or ad-hoc backfills.

```bash
# Python pipeline (ingestion)
pip install -r requirements.txt
python scripts/refresh.py                              # BDDK + EVDS + TBB/TKBB/KAP/TEFAS/… (local SQLite)
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
├── src/                            ← Python — ingestion + extraction (one package per lane)
│   ├── scrapers/                   ← BDDK monthly/weekly + EVDS scrapers
│   ├── audit_reports/              ← per-bank PDF extraction — PyMuPDF (fitz) only —
│   │                                  + registry, validators, R2 (S3-compat) wrapper
│   ├── tbb/, tkbb/                 ← quarterly digital-banking stats (+ acquisition)
│   ├── kap/, tefas/, tuik/         ← ownership, fund market, TÜİK detail series
│   ├── news/                       ← KAP/TCMB/BDDK/press news + free-LLM clients
│   ├── earnings/, transcripts/     ← results calendar + decks, call transcripts
│   ├── faaliyet/, nonbank/         ← annual-report franchise stats, non-bank lenders
│   ├── rates/, release_calendar/   ← advertised rates, TCMB release calendar
│   ├── products/, analyst/         ← product benchmark, analyst detectors
│   └── d1_usage.py                 ← D1 billing-cycle usage reader
│
├── scripts/                        ← Python CLI entry points
│   ├── refresh.py                  ← bulletin-lane orchestrator (BDDK + EVDS + all satellites)
│   ├── sync_audit_reports.py       ← scrape bank IR → R2 → extract → SQLite
│   ├── push_to_d1.py               ← incremental D1 sync (handles every table)
│   ├── update_*.py                 ← one lane each (monthly, weekly, tbb, tefas, kap, …)
│   ├── reextract_statement.py      ← targeted single-statement repair
│   ├── purge_partition.py          ← remove one (bank, period, kind) everywhere
│   ├── check_*.py                  ← the 17 standalone CI gates
│   ├── backfill_*.py, watch_cross_period.py, scratch_*.py  ← backfills + diagnostics
│   └── archive/                    ← retired one-shots (kept for the record)
│
├── web/                            ← Next.js 16 + OpenNext (Cloudflare Workers)
│   ├── app/                        ← routes
│   │   ├── components/             ← TrendChart, BarByBank, StackedArea, …
│   │   ├── lib/                    ← db.ts (D1 binding) · metrics.ts (SQL helpers)
│   │   ├── credit/, deposits/, asset-quality/, capital/, profitability/
│   │   ├── rates/, liquidity/, market-risk/, cross-bank/, banks/, ownership/
│   │   ├── earnings/, funds/, digital/, economy/, news/, regulation/
│   │   ├── non-bank/, disclosures/, pipeline/
│   │   ├── _franchise/             ← parked: the leading _ un-routes it (Next
│   │   │                              private folder). Don't rename without reading why
│   │   ├── admin/, api/admin/      ← password-gated control center
│   │   └── page.tsx                ← Overview
│   ├── wrangler.jsonc, open-next.config.ts
│   ├── package.json
│   ├── migrations/                 ← hand-authored D1 schema migrations (source of truth)
│   └── seeds/                      ← gitignored · bulk data-seed dumps (scripts/archive/generate_d1_migrations.py)
│
├── data/                           ← all data (mostly gitignored)
│   ├── README.md                   ← map of everything in data/ — tracked vs local vs disposable
│   ├── banks/                      ← URL config + BDDK bank list (committed)
│   └── external_reports/           ← reference PDFs (BBVA, IMF, …) [local]
│   # Not in git; live in cloud storage:
│   #   state/bddk_data.db.gz       ← R2 bucket bddk-audit-reports (bulletin/EVDS lane snapshot)
│   #   state/bank_audit.db.gz      ← R2 bucket bddk-audit-reports (audit lane snapshot)
│   #   audit_reports/*.pdf         ← R2 bucket bddk-audit-reports, by ticker
│   #   bddk_data.db / bank_audit.db ← rebuilt in each cron run from the R2 snapshot
│
├── reports/                        ← generated one-off outputs (scripts/generate_presentation.py) [gitignored]
│
└── .github/workflows/              ← 31 workflows — every scheduled job + every manual backfill
    ├── refresh-evds-daily.yml      ← Sun-Fri 05 UTC: daily-frequency EVDS → D1
    ├── refresh-news-daily.yml      ← daily 04 UTC: KAP/TCMB/BDDK news → D1
    ├── refresh-bddk-bulletins.yml  ← month edges + Fridays: BDDK bulletins → D1
    ├── refresh-data.yml            ← Sat 03 UTC: full refresh (BDDK + EVDS + satellites) → D1
    ├── refresh-audit.yml           ← filing windows daily: acquire + extract + one D1 batch
    ├── refresh-advertised-rates.yml / refresh-calendar.yml / refresh-presentations-weekly.yml
    ├── summarize-regulations.yml / generate-reads.yml  ← weekly LLM lanes → D1
    ├── healthcheck.yml             ← daily: D1 freshness → Telegram/Discord alert
    ├── ci.yml                      ← PRs + master: ruff + pytest + eslint + tsc + vitest
    ├── deploy-cloudflare.yml       ← after green CI on master: migrate + build + deploy
    └── + ~18 manual-dispatch workflows (backfills, repairs, purge, triage,
        analyst, acquire, transcripts, telegram-webhook) — docs/OPERATIONS.md has all
# also: pyproject.toml (ruff/pytest), tests/, .github/dependabot.yml
```

## Cadences

| | When | Workflow |
|---|---|---|
| **EVDS daily refresh** | Sun–Fri 05:00 UTC | `refresh-evds-daily.yml` (daily/workday series only) |
| **News refresh** | Daily 04:00 UTC | `refresh-news-daily.yml` → `news_items` |
| **BDDK bulletins** | First/last five days + Friday publication window | `refresh-bddk-bulletins.yml` (no EVDS/audit) |
| **Full weekly refresh** | Saturday 03:00 UTC | `refresh-data.yml` (BDDK + EVDS + TBB/TKBB + KAP + TEFAS + Faaliyet + D1 push) |
| **Audit-report arrival** | Daily in quarterly filing windows | `refresh-audit.yml` — discover → R2 → extract/validate/coverage → one D1 batch → snapshot; quiet checks write nothing |
| **Advertised rates** | Monday 06:00 UTC | `refresh-advertised-rates.yml` → `bank_advertised_rates` |
| **Release calendar** | 1st of month 06:00 UTC | `refresh-calendar.yml` → `release_calendar` |
| **IR presentation decks** | Saturday 06:00 UTC | `refresh-presentations-weekly.yml` → `bank_earnings` |
| **Regulation briefing** | Sunday 06:00 UTC | `summarize-regulations.yml` → `regulation_briefings` (LLM) |
| **Read headlines** | Sunday 07:30 UTC | `generate-reads.yml` → `read_headlines` (LLM, number-validated) |
| **Acquisition-only diagnostic** | Manual / admin only | `acquire-audit.yml` — download a PDF without extracting it |
| **Health check** | Daily 06:00 UTC | `healthcheck.yml` — D1 freshness → alert if stale |
| **CI quality gates** | Every PR | `ci.yml` — ruff + pytest + eslint + tsc + vitest |
| **Cloudflare dashboard deploy** | After green CI on `master` | `deploy-cloudflare.yml` (migrate + build + deploy) |

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
