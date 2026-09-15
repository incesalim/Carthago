# System map — Carthago in one page

**This is the front door.** It answers *what runs where, which package owns what,
and which script does which job* in under two minutes. For depth:

- `docs/ARCHITECTURE.md` — the full stack, lane model, caching, deploy, mobile.
- `docs/PROJECT_STATE.md` — what is actually in the database **right now**.
- `docs/OPERATIONS.md` — how to run, backfill or repair anything.
- `docs/README.md` — the complete doc index.
- `scripts/README.md` — the exhaustive per-script index (CI-gated).
- `scripts/ORGANIZATION.md` — scripts grouped by pipeline stage and directory.

> Rule of thumb: this page explains the *shape* of the system. When it disagrees
> with `PROJECT_STATE.md`, `PROJECT_STATE` wins; when that disagrees with code,
> the code wins and the doc is a bug (AGENTS.md).

---

## 1. What Carthago is

A read-only analytics platform for the Turkish banking sector. Python ingests
official sources into **Cloudflare D1** (rows) and **R2** (PDFs + SQLite
snapshots); a Next.js dashboard on **Cloudflare Workers** and an Expo app render
it. Everything scheduled runs in **GitHub Actions** — there is no server we own.

**Sources → code → storage → surface**

```
  OFFICIAL SOURCES              PYTHON (src/)                 STORAGE                 SURFACES
 ─────────────────             ─────────────                 ───────                 ────────
  BDDK bulletins   ─┐
  (monthly/weekly)  │
  TCMB EVDS        ─┼──▶  src/scrapers/  ─
                    │                     │
  TBB / TKBB       ─┤   src/tbb, tkbb    │
  KAP / TEFAS      ─┤   src/kap, tefas   │
  TÜİK             ─┤   src/tuik         ├─▶ scripts/* (CLI) ─▶ SQLite      ─┐
  Bank IR news     ─┤   src/news         │   orchestrated by      staging      │  scripts/
  Faaliyet / decks ─┤   src/faaliyet,    │   GitHub Actions       (local)      │  push_to_d1
  Transcripts      ─┤   earnings,        │                                    ▼
  Rates / calendar ─┘   transcripts,     │                          Cloudflare D1 (bddk-data)
                        rates,           │                                    │
  Bank BRSA PDFs ─────▶ release_calendar │                                    ├─▶ web/  Next.js
  (per-bank, R2)        src/audit_reports┘                                    │     on Workers
                                   │                                           └─▶ mobile/ Expo
                                   │  ── second, independent lane ──               (reads /api/app/v1)
                                   ▼
                        R2 bucket `bddk-audit-reports`
                        (PDFs + gzipped SQLite snapshots)
```

Every lane is **acquire → extract → validate → publish**: fetch from the source,
turn it into rows in a local SQLite, check it, then push the changed rows to D1
and re-upload the snapshot to R2.

---

## 2. The two storage lanes

The pipeline is split into two independent lanes so one cannot stall the other.
Each owns its own staging DB, R2 snapshot and concurrency group.

| Lane | Staging DB | R2 snapshot | Lock | Writes |
|---|---|---|---|---|
| **Bulletin / macro** | `data/bddk_data.db` | `state/bddk_data.db.gz` | `bddk-pipeline` | BDDK bulletins, EVDS, TBB/TKBB, KAP, TEFAS, TÜİK, news, earnings, rates, calendar |
| **Audit reports** | `data/bank_audit.db` | `state/bank_audit.db.gz` | `bddk-audit` | `bank_audit_*` tables only |

They share **only** the D1 sink, where they write a disjoint set of tables with
idempotent `INSERT OR REPLACE`. `src/pipeline/registry.py` is the declared table
ownership; `check_publication_contract.py` / `check_schema_contract.py` enforce
it in CI. Beside the two lane snapshots:

| Store | Purpose | Persistence |
|---|---|---|
| `data/bank_audit_capture.db` | full-document capture ledger (every table a filing prints) | own R2 object, never the audit snapshot |
| `data/bank_audit_tables.db` | derived per-table lane + graduated `bank_audit_*_full` tables | local, not D1 (read `scripts/graduations/`) |
| `data/analyst.db` | analyst signals + memo hashes | R2 `state/analyst.db.gz` |
| `data/bank_audit_prose.db` | historical prose backfill | local-only |

---

## 3. Domain catalog — what each `src/` package owns

One package per lane. A package holds the source client/parser/extractor; its
`schema.py` declares the local tables; a thin CLI in `scripts/` drives it.

| Package | Owns | D1 tables | Driven by |
|---|---|---|---|
| `src/scrapers/` | BDDK monthly + weekly bulletins, TCMB EVDS client | `balance_sheet`, `income_statement`, `loans`, `deposits`, `financial_ratios`, `other_data`, `weekly_series`, `evds_series` | `scripts/refresh.py`, `update_monthly.py`, `update_weekly.py` |
| `src/audit_reports/` | Per-bank BRSA PDF → rows. The registry, extractors, validator, triage, source-capture, and the document-corpus subsystem (`document_*.py`) | every `bank_audit_*` table (see `registry.py`), + `bank_audit_expected`, `_statement_types`, `_coverage` | `sync_audit_reports.py`, `reextract_statement.py`, `build_bank_audit_stages.py`, `sync_audit_expected.py`, `backfill_document_capture.py`, `scripts/graduations/` |
| `src/tbb/` | TBB quarterly digital-banking + monthly acquisition workbooks | `tbb_digital_stats`, `tbb_acquisition_stats` | `update_tbb_digital.py`, `update_tbb_acquisition.py` |
| `src/tkbb/` | TKBB participation-bank digital + acquisition (Turboard API) | `tkbb_digital_stats`, `tkbb_acquisition_stats` | `update_tkbb_digital.py`, `update_tkbb_acquisition.py` |
| `src/kap/` | KAP ownership form §5/§7 | `kap_ownership` | `update_kap_ownership.py` |
| `src/tefas/` | TEFAS fund market (sector aggregates; per-fund rows not persisted) | `tefas_manager_daily`, `tefas_category_daily`, `tefas_allocation_daily`, `tefas_top_funds` | `update_tefas.py` |
| `src/tuik/` | TÜİK detail series EVDS lacks | `evds_series` as `TUIK.*` | `update_tuik.py` |
| `src/news/` | KAP/TCMB/BDDK/press news, regulation briefing, "The Read" | `news_items`, `news_item_banks`, `regulation_briefings`, `read_headlines` | `sync_news.py`, `summarize_regulations.py`, `generate_read_headlines.py` |
| `src/earnings/` | Results calendar + IR presentation decks | `bank_earnings` | `update_presentations.py` |
| `src/transcripts/` | Earnings-call transcripts | `bank_call_transcripts` | `update_transcripts.py` |
| `src/faaliyet/` | Annual-report (Faaliyet) franchise stats | `faaliyet_franchise`, `faaliyet_extractions` | `update_faaliyet.py` |
| `src/nonbank/` | BDDK non-bank monthly bulletin (leasing/factoring/financing) | `nonbank_balance_sheet` | `update_nonbank.py` |
| `src/rates/` | Posted loan/deposit rates (the only per-bank rate source) | `bank_advertised_rates` | `python -m src.rates.scraper` |
| `src/release_calendar/` | TCMB release calendar (MPC, reports) | `release_calendar` | `python -m src.release_calendar.scraper` |
| `src/products/` | Product-shelf benchmark | `product_attributes`, `bank_products`, `bank_product_profile` | `python -m src.products.build` |
| `src/analyst/` | Deterministic detectors over the audit snapshot | `analyst_signals`, `analyst_basis_metadata`, `analyst_notes` | `scripts/analyst/detect.py` |
| `src/d1_usage.py` | D1 billing-cycle usage reader (not a lane) | — | by hand |

**Where a package is not a lane:** `src/audit_reports/document_*.py` (51 modules)
is one subsystem — the complete-document corpus — inside the audit package. It
captures native PDF structure first and mints analytical "wide" lanes from it
later (`scripts/graduations/`). The narrow, frozen BS/P&L extractors live beside
it and are not rewritten.

---

## 4. Script lifecycle — what each script *does*

`scripts/` is organised by pipeline stage, not by source. The exhaustive index is
[`scripts/README.md`](../scripts/README.md); the physical layout and this same
taxonomy are in [`scripts/ORGANIZATION.md`](../scripts/ORGANIZATION.md). The six
buckets:

| Stage | Meaning | Representative scripts |
|---|---|---|
| **Acquire** | Fetch external data into local/R2; no analytical rows | `refresh.py`, `update_*.py`, `sync_news.py`, `sync_audit_reports.py --no-extract`, `build_document_corpus.py`, `discover_audit_urls.py`, `python -m src.rates.scraper` |
| **Extract** | Source bytes → structured rows | `sync_audit_reports.py`, `reextract_statement.py`, `reextract_pl.py`, `backfill_extraction.py`, `backfill_document_capture.py`, `build_document_tables.py`, `scripts/graduations/build_*_full.py` |
| **Publish** | Local SQLite → D1 / R2 | `push_to_d1.py` (the one D1 writer), `push_from_scratch.py`, `build_api_catalog.py`, `sync_audit_expected.py --push`, `seed_audit_db.py` |
| **Repair** | Targeted correction of stored rows | `reextract_statement.py`, `purge_partition.py`, `repair_missing_audit_rows.py`, `repair_audit_roles.py`, `repair_loans_zeros.py`, `audit_correct.py`, `apply_overrides.py`, `load_partition.py`, `revalidate_audit_db.py` |
| **Diagnose** | Read-only inspection; writes nothing | `check_*.py` gates, `healthcheck.py`, `audit_narrow_vs_wide.py`, `triage_partitions.py`, `watch_cross_period.py`, `scripts/diagnostics/*`, `scripts/scratch/*` |
| **One-off / archive** | Finished campaigns and by-hand generators | `scripts/archive/*`, `generate_presentation.py`, `make_brand_assets.py`, `fetch_bank_logos.py`, `compute_bank_metrics.py` |

**The gates are part of the code, not an afterthought.** `check_*.py` scripts fail
CI when their guarded inventory drifts — the scripts index, the docsworkflows
sync, the pipeline graph, the schema naming, the fitz-only rule, prose claims,
contrast, calendar freshness. Their list and what each guards is in
[`scripts/README.md`](../scripts/README.md) → *CI gates*.

---

## 5. Workflow families

All 39 workflows live in `.github/workflows/`; the full cadence table with inputs
is in [`docs/WORKFLOWS.md`](WORKFLOWS.md) and [`docs/OPERATIONS.md`](OPERATIONS.md).
Grouped by purpose:

| Family | Trigger | Examples |
|---|---|---|
| **Scheduled refresh** | cron | `refresh-data` (Sat full), `refresh-bddk-bulletins`, `refresh-evds-daily`, `refresh-news-daily`, `refresh-audit`, `refresh-advertised-rates`, `refresh-calendar`, `refresh-presentations-weekly`, `summarize-regulations`, `generate-reads` |
| **Acquire / corpus capture** | dispatch | `acquire-audit`, `build-document-corpus`, `recover-document-corpus`, `review-document-origins`, `capture-related-documents`, `capture-document-edition` |
| **Backfill** | dispatch | `backfill-audit`, `backfill-audit-source-capture`, `backfill-document-capture`, `backfill-faaliyet`, `backfill-nonbank`, `backfill-tefas`, `build-products`, `measure-free-provision` |
| **Repair** | dispatch | `reextract-statement`, `repair-audit-roles`, `repair-missing-audit-rows`, `repair-loans-zeros`, `purge-partition` |
| **Diagnose** | dispatch | `audit-triage`, `audit-extraction-gates`, `test-openrouter` |
| **Analyst** | dispatch (cron wired, off) | `analyst-daily`, `analyst-research` |
| **Infrastructure** | cron / CI / dispatch | `ci`, `deploy-cloudflare`, `healthcheck`, `telegram-webhook` |

---

## 6. Docs: active vs reference vs historical

`docs/README.md` is the full index. This is the status map.

| Status | Docs |
|---|---|
| **Active — start here** | `ARCHITECTURE.md`, `PROJECT_STATE.md`, `OPERATIONS.md`, this page |
| **Active — reference** | `METRICS.md`, `BANKING_METRICS.md`, `SCHEMA_CONVENTIONS.md`, `API.md`, `API_MANUAL.md`, `ADMIN.md`, `TELEGRAM_BOT.md`, `ANALYST.md`, `ANALYST_V2.md`, `REPRODUCING_CHARTS.md` |
| **Active — audit lane** | `AUDIT_DOCUMENT_PLAN.md` (**the single active audit plan**), `AUDIT_PIPELINE.md`, `AUDIT_EXTRACTION_GUIDE.md`, `AUDIT_BANK_CATALOG.md` (generated), `MISSING_AUDIT_DATA.md` — indexed in [`docs/audit/README.md`](audit/README.md) |
| **Dated history** | `CHANGELOG.md` (appended per change) |
| **Historical — do not follow** | `AUDIT_REWORK_PLAN.md` (completed rework), `RESUME_AUDIT_FIX.md` (closed 2026-06 ECL fix) |
| **Internal, gitignored** | `docs/knowledge/` — dated investigation notes; on-disk only, never shipped |
| **Design archive** | `docs/design/MOCKUPS.md` + `mockups/` — concepts and what shipped |

> Audit docs are deliberately kept at `docs/` root and **indexed** from
> `docs/audit/README.md` rather than moved: they are cross-referenced from source
> docstrings, skills, migrations and `PROJECT_STATE.md`. Moving them would break
> links faster than it helps navigation. `AUDIT_DOCUMENT_PLAN.md` is the one
> active plan — treat the others as reference.

---

## 7. If you only remember five things

1. **Two lanes, one D1**: bulletin/macro (`bddk-pipeline`) and audit
   (`bddk-audit`) never share a snapshot; they write disjoint tables.
2. **`push_to_d1.py` is the only D1 writer**, and writes are the cost centre —
   compare before stamping.
3. **`null` ≠ `0`** at every layer.
4. **PDF extraction is PyMuPDF (`fitz`) only**; never re-extract a whole lane
   with `--force`.
5. **`scripts/` is stage-organised, `src/` is source-organised**, and change is
   done through a targeted workflow dispatch, not a local full run.