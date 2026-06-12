# `scripts/` — what each script is and when it runs

This is the index for the Python entry points. Each row says **what** the script does,
**who runs it** (a cron/CI workflow, the `/admin` panel, or by hand), the **lane** it
belongs to, and its **class**:

- **pipeline** — load-bearing; invoked by a scheduled workflow. Don't break these.
- **operational** — run by hand or `/admin` for an ongoing purpose (backfills, repairs).
- **diagnostic** — inspection / profiling only; in `scripts/diagnostics/`.
- **archived** — one-off campaign / migration that's done; in `scripts/archive/` for reference.

The lanes themselves are described in [`docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md); the
audit lane and its repair playbook are in [`docs/AUDIT_PIPELINE.md`](../docs/AUDIT_PIPELINE.md).

## Shared / infrastructure
| Script | Purpose | Run by | Class |
|---|---|---|---|
| `push_to_d1.py` | Incremental SQLite→D1 sync (`INSERT OR REPLACE` rows newer than `--hours`); `--db`, `--only-tables`. The one D1 writer every lane uses. | every refresh workflow | pipeline |
| `notify.py` | Telegram/Discord alert (lib + CLI). | called by workflows + scripts on failure | pipeline |
| `healthcheck.py` | Daily D1 freshness check + audit-failure count. | `healthcheck.yml` | pipeline |
| `verify_chart_spec.py` | Re-resolve every reproduced chart spec in D1 (regression catch). | `healthcheck.yml` | pipeline |
| `_bank_types.py` | BDDK bank-type code taxonomy (library; no `__main__`). | imported by `verify_chart_spec`, tests | pipeline (lib) |

## Bulletin / EVDS lane (BDDK monthly+weekly, EVDS, TBB, KAP, TEFAS)
| Script | Purpose | Run by | Class |
|---|---|---|---|
| `refresh.py` | Orchestrator: monthly + weekly + EVDS + TBB + KAP + TEFAS → snapshot → R2. `--skip-*` flags. | `refresh-data.yml`, `refresh-bddk-bulletins.yml`, `refresh-evds-daily.yml` | pipeline |
| `update_monthly.py` | Incremental monthly BDDK bulletin (latest month). | `refresh.py` | pipeline |
| `update_weekly.py` | Rolling 13-week BDDK weekly refresh. | `refresh.py` | pipeline |
| `update_tbb_digital.py` | TBB quarterly digital-banking Excel → `tbb_digital_stats`. | `refresh.py` | pipeline |
| `update_kap_ownership.py` | KAP Genel Bilgi Formu ownership → `kap_ownership`. | `refresh.py` | pipeline |
| `update_tefas.py` | TEFAS fund-market daily / `--backfill`. | `refresh.py`; `backfill-tefas.yml` | pipeline |

## News / regulation lane
| Script | Purpose | Run by | Class |
|---|---|---|---|
| `sync_news.py` | KAP + TCMB + BDDK + press feeds → `news_items`. | `refresh-news-daily.yml` | pipeline |
| `summarize_regulations.py` | LLM (Kimi) weekly regulation briefing → `regulation_briefings`. | `summarize-regulations.yml` | pipeline |
| `ingest_policy_baseline.py` | Ingest TCMB annual Monetary-Policy PDF as briefing baseline. | by hand, ~annually | operational |

## Audit lane — pipeline (the cron path)
The weekly path is: **`sync_audit_reports` → `build_bank_audit_stages` → `check_audit_quality` → `push_to_d1` → snapshot**.
| Script | Purpose | Run by | Class |
|---|---|---|---|
| `sync_audit_reports.py` | THE audit entry: scrape new PDFs → R2 → extract pending → `bank_audit.db`. `--only-bank`, `--latest-period`, `--periods`, `--no-scrape`. | `refresh-audit.yml` | pipeline |
| `build_bank_audit_stages.py` | Consolidate credit-quality rows → `bank_audit_stages`. | `refresh-audit.yml` | pipeline |
| `check_audit_quality.py` | 8 alert-only anomaly checks (stale/balance/coverage/npl_drop/capital/liquidity/structure/ecl). | `refresh-audit.yml`, `backfill-audit.yml` | pipeline |
| `seed_audit_db.py` | Bootstrap `bank_audit.db` from the bulletin snapshot on first run. | `refresh-audit.yml` (bootstrap) | pipeline |
| `sync_audit_expected.py` | Build `bank_audit_expected` + `bank_audit_statement_types` + `bank_audit_coverage` (the /admin coverage matrix spine). | `refresh-audit.yml` | pipeline |

## Audit lane — operational (backfills + manual corrections)
| Script | Purpose | Run by | Class |
|---|---|---|---|
| `backfill_extraction.py` | Re-extract named banks from R2 → clear D1 partitions → push → snapshot. Shared D1/R2 helpers live in `scripts/audit_d1.py`. | `backfill-audit.yml`; by hand | operational |
| `audit_correct.py` | Unified manual-correction CLI: `overlay-statement` (hand-transcribed `manual_statements.json`), `override-cells` (`audit_overrides.json`), `reextract-pl`. Validate-to-0 → push one partition. | by hand | operational |
| `revalidate_audit_db.py` | Recompute `bank_audit_validation` from stored rows (balance sheet + P&L, no re-extraction); push validation only. | by hand after a validator change | operational |
| `sync_audit_expected.py` | Build the coverage spine (`bank_audit_expected` / `bank_audit_statement_types` / `bank_audit_coverage`) from the profile census + stored rows; `--push` rebuilds the three tables on D1 (no R2 snapshot). Feeds the `/admin` coverage matrix. | `refresh-audit.yml`; by hand | pipeline |
| `push_from_scratch.py` | Push pre-extracted rows from `fleet_scratch.db` → D1 (no re-extraction). | by hand (large repair) | operational |
| `discover_audit_urls.py` | Scan bank IR pages for new quarterly report URLs. | by hand, quarterly | operational |
| `compute_bank_metrics.py` | Derive a per-bank KPI snapshot from audit data. | by hand | operational |
| `fleet_evidence.py` | Dry-run full re-extraction to `fleet_scratch.db`; bucket improved/unchanged/regressed (the non-regression gate). Never writes prod/D1/R2. | by hand before a backfill | operational |
| `run_phase3_batches.py` | Gated batchwise re-extraction (aborts on regression). | by hand (large repair) | operational |

## Audit lane — diagnostics (`scripts/diagnostics/`)
| Script | Purpose | Class |
|---|---|---|
| `profile_audit_corpus.py` | Profile every R2 PDF → `data/audit_profiles.json` (format census; feeds the coverage matrix's expected universe). | diagnostic |
| `catalog_audit_templates.py` | Catalog NPL/§4/§5 label variants per bank. | diagnostic |
| `summarize_audit_catalog.py` | Render the template catalog to summary + registry. | diagnostic |
| `generate_audit_census.py` | Render the census + drift into `docs/AUDIT_BANK_CATALOG.md`. | diagnostic |
| `diag_partition.py` | Dump one `(bank, period, kind)` statement + PDF line matches; show identity breaks. | diagnostic |
| `validate_discovery.py` | Check IR-page auto-discovery against the hand-maintained config. | diagnostic |
| `verify_stage_coverage.py` | Audit IFRS-9 stage coverage completeness. | diagnostic |

## Backfills (`scripts/backfills/`)
| Script | Purpose | Class |
|---|---|---|
| `backfill_credit_quality.py` | Re-extract the IFRS-9 credit-quality footnote fleet-wide after a fix. | operational backfill |
| `backfill_npl_history.py` | Re-extract NPL Stage-3 movement history (chunked by period). | operational backfill |

## Archived (`scripts/archive/`) — done, kept for reference
`extract_all_audit_reports.py`, `scrape_all_banks.py` (local-PDF flow, replaced by R2-based
`sync_audit_reports`), `migrate_pdfs_to_r2.py` (one-time R2 migration), `reextract_all.py`
(superseded by `backfill_extraction --banks ALL`), `validate_pl_fix.py` / `audit_extraction.py`
(fix-verification), `generate_d1_migrations.py` (one-time D1 seed), and the historical data
backfills `backfill_2020_2023.py` / `backfill_weekly_2020_2023.py` / `backfill_weekly_2y.py` /
`update_db_2026.py`.
