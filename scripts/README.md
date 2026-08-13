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
| `push_to_d1.py` | Incremental SQLite→D1 sync (`INSERT OR REPLACE` rows newer than `--hours`); `--db`, `--only-tables`, `--table-set`. The one D1 writer every lane uses. **Full-rebuild tables (`api_series`, the audit spine) are skipped when their content hash is unchanged** — D1 bills rows written and those are ~20k-row DELETE+INSERT cycles; `--force-rebuild` overrides after direct D1 edits. See OPERATIONS §D1 write budget. | every refresh workflow | pipeline |
| `notify.py` | Telegram/Discord alert (lib + CLI). | called by workflows + scripts on failure | pipeline |
| `healthcheck.py` | Daily D1 freshness check + audit-failure count. | `healthcheck.yml` | pipeline |
| `verify_chart_spec.py` | Re-resolve every reproduced chart spec in D1 (regression catch). | `healthcheck.yml` | pipeline |
| `check_amount_integrity.py` | Sweep every audit amount column (ratio columns excluded by name) for a fractional value — BRSA prints whole thousands of TL, so a fraction is a mis-read thousands separator, i.e. a figure stored 1000× too small. `--db` sweeps a snapshot, default is remote D1. Alerts only on that class; marker leakage is reported. | `healthcheck.yml`; by hand | pipeline |
| `_bank_types.py` | BDDK bank-type code taxonomy (library; no `__main__`). | imported by `verify_chart_spec`, tests | pipeline (lib) |
| `check_pipeline_graph_sync.py` | Stdlib-only CI gate: every ingestion workflow ↔ `/pipeline` graph node stays in sync (both directions), and every node `href` resolves to a real route. Scratch lanes that move no production data are exempt via `SCRATCH_WORKFLOWS`, and an exemption naming a deleted workflow fails the gate. | `ci.yml` | pipeline |
| `metric_knowledge.py` | CLI over the banking-metrics knowledge registry (`data/metric_knowledge/registry.json`): list / show / validate. | by hand | operational |

## Bulletin / EVDS lane (BDDK monthly+weekly, EVDS, TBB, TKBB, KAP, TEFAS)
| Script | Purpose | Run by | Class |
|---|---|---|---|
| `refresh.py` | Orchestrator: monthly + weekly + EVDS + TBB + TKBB + KAP + TEFAS → snapshot. `--skip-*`, cadence-aware `--evds-frequencies`, and `--change-file` so workflows skip packaging/D1/R2 when SQLite is unchanged. | `refresh-data.yml`, `refresh-bddk-bulletins.yml`, `refresh-evds-daily.yml` | pipeline |
| `update_monthly.py` | Incremental monthly BDDK bulletin (latest month). | `refresh.py` | pipeline |
| `update_weekly.py` | Rolling 13-week BDDK weekly refresh. | `refresh.py` | pipeline |
| `update_tbb_digital.py` | TBB quarterly digital-banking Excel → `tbb_digital_stats`. | `refresh.py` | pipeline |
| `update_kap_ownership.py` | KAP Genel Bilgi Formu ownership → `kap_ownership`. | `refresh.py` | pipeline |
| `update_tefas.py` | TEFAS fund-market daily / `--backfill`. | `refresh.py`; `backfill-tefas.yml` | pipeline |
| `update_nonbank.py` | BDDK non-bank monthly bulletin (leasing / factoring / financing) → `nonbank_balance_sheet`. | `refresh.py`; `backfill-nonbank.yml` | pipeline |
| `update_tbb_acquisition.py` | TBB monthly remote-vs-branch customer-acquisition stats → `tbb_acquisition_stats`. | `refresh.py` | pipeline |
| `update_tkbb_digital.py` | TKBB participation-bank quarterly digital stats (Turboard JSON API) → `tkbb_digital_stats`; incremental, auto-backfills an empty table. | `refresh.py` | pipeline |
| `update_tkbb_acquisition.py` | TKBB monthly remote-vs-branch acquisition (rolling 12-month window, accumulated) → `tkbb_acquisition_stats`. | `refresh.py` | pipeline |
| `update_tuik.py` | TÜİK veriportali Excel detail (GDP expenditure, PPI MIG) → `evds_series` as `TUIK.*` codes. | `refresh.py` | pipeline |
| `update_faaliyet.py` | Bank annual-report (faaliyet) franchise stats → `faaliyet_franchise`; `--backfill`. | `refresh.py`; `backfill-faaliyet.yml` | pipeline |
| `update_presentations.py` | IR investor-presentation decks (static URLs + auto-discovery) → `bank_earnings`. | `refresh-presentations-weekly.yml` | pipeline |

## News / regulation lane
| Script | Purpose | Run by | Class |
|---|---|---|---|
| `sync_news.py` | KAP + TCMB + BDDK + press feeds → `news_items`. | `refresh-news-daily.yml` | pipeline |
| `summarize_regulations.py` | LLM (Kimi) weekly regulation briefing → `regulation_briefings`. | `summarize-regulations.yml` | pipeline |
| `ingest_policy_baseline.py` | Ingest TCMB annual Monetary-Policy PDF as briefing baseline. | by hand, ~annually | operational |

## Audit lane — pipeline
One scheduled arrival path plus a manual diagnostic (same `bddk-audit` group). During filing
windows `refresh-audit.yml` runs daily: scrape → extract → derive/revalidate/build coverage
locally → **one** D1 push → snapshot; it stops after discovery when nothing changed.
`acquire-audit.yml` is manual-only acquisition without extraction.
| Script | Purpose | Run by | Class |
|---|---|---|---|
| `sync_audit_reports.py` | THE audit entry: scrape new PDFs → R2 (`--no-extract` = acquire) and/or extract pending → `bank_audit.db`. `--only-bank`, `--latest-period`, `--periods`, `--no-scrape`, `--force`, `--new-count-file`, `--result-file` (machine-readable quiet-run handoff). | `acquire-audit.yml` (manual scrape), `refresh-audit.yml` (scheduled/manual combined path) | pipeline |
| `build_bank_audit_stages.py` | Consolidate credit-quality rows → `bank_audit_stages`. | `refresh-audit.yml` | pipeline |
| `check_audit_quality.py` | 10 alert-only anomaly families (stale/balance/coverage/npl_drop/capital/liquidity/structure/ecl/pl_sign/free-provision); delta-alerts against the R2 baseline. | `refresh-audit.yml`, `backfill-audit.yml`, `reextract-statement.yml` | pipeline |
| `seed_audit_db.py` | Bootstrap `bank_audit.db` from the bulletin snapshot on first run. | both audit workflows (bootstrap) | pipeline |
| `sync_audit_expected.py` | Build `bank_audit_expected` (profile census ∪ R2 PDFs) + `bank_audit_statement_types` + `bank_audit_coverage` (the /admin coverage matrix spine). `--push` = full-rebuild D1 push, no R2 write. | `acquire-audit.yml`, `refresh-audit.yml`; by hand | pipeline |

## Audit lane — operational (backfills + manual corrections)
| Script | Purpose | Run by | Class |
|---|---|---|---|
| `backfill_audit_source_capture.py` | Download existing audit PDFs and add lossless source-line evidence + compact manifests for the 8 normalized/summary lanes, without rewriting analytical facts. Content-idempotent; revalidates touched partitions. | `backfill-audit-source-capture.yml`; by hand | operational |
| `check_capture_reconcile.py` | Reconcile stored analytical figures against the cells the filing printed, using the capture as an **external** anchor. Every per-partition validator is an internal identity, and a uniform unit change scales both sides equally — so this is the only check that sees a partition stored at the wrong reporting scale (the TEB 2026Q2 failure). Reads the declared unit off the captured text via `units.regex_unit`, so it needs no PDF. Reports `unit_scale` / `figures_absent` (errors) and `capture_incomplete` / `unit_unknown` (info); exits 1 on an error. Read-only. | by hand | diagnostic |
| `view_document_capture.py` | Render one captured filing to a standalone HTML page for review — each table as a grid, each footnote under the table it qualifies with the rows it links to. Reads `data/bank_audit_capture.db` only; writes one .html. `--list` shows captured partitions. Read-only. | by hand | diagnostic |
| `backfill_document_capture.py` | Capture EVERY table each filing prints — rows, inferred columns, cells — plus footnotes linked to the rows carrying their marker. Document-scoped, so tables with no parser are captured too; calls no analytical upsert. Raw ledger → `data/bank_audit_capture.db` + `data/audit_capture/*.jsonl` (local, gitignored) and R2 `state/bank_audit_capture.db.gz`; **only** `bank_audit_document_manifest` reaches D1. `--from-r2` streams each PDF then deletes it. | `backfill-document-capture.yml`; by hand | operational |
| `backfill_extraction.py` | Re-extract named banks from R2 → clear D1 partitions → push → snapshot. Shared D1/R2 helpers live in `scripts/audit_d1.py`. | `backfill-audit.yml`; by hand | operational |
| `audit_correct.py` | Unified manual-correction CLI: `overlay-statement` (hand-transcribed `manual_statements.json`), `override-cells` (`audit_overrides.json`), `reextract-pl`. Validate-to-0 → push one partition. | by hand | operational |
| `load_partition.py` | Impl behind `audit_correct overlay-statement`: load a hand-transcribed statement from `data/manual_statements.json` into one partition, validate, push. | via `audit_correct`; by hand | operational |
| `apply_overrides.py` | Impl behind `audit_correct override-cells`: apply curated cell fixes from `data/audit_overrides.json` (BS/OCI/capital/pl_rehier/… types), revalidate, push. | via `audit_correct`; by hand | operational |
| `reextract_statement.py` | Registry-routed re-extract of ONE statement lane; `--only-failing` uses the full relationship gate and `--require-passing` rolls back rejected source + derived + validation rows. Credit-quality rebuilds stages before acceptance; no-op tables are not re-stamped or pushed. | `reextract-statement.yml`; by hand | operational |
| `reextract_pl.py` | Re-extract ONLY `profit_loss` for ONE `(bank, period, kind)` partition — single-PDF repair, not a fleet tool (also exposed as the `audit_correct reextract-pl` sub-command). | by hand | operational |
| `revalidate_audit_db.py` | Recompute `bank_audit_validation` from stored rows for all 19 registered lanes, including cross-table and longitudinal checks; no PDF re-extraction. | by hand after a validator change | operational |
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
| `validate_presentation_discovery.py` | Check IR-deck auto-discovery (GARAN/AKBNK/YKBNK) against the static URL config. | diagnostic |

## Backfills (`scripts/backfills/`)
| Script | Purpose | Class |
|---|---|---|
| `backfill_credit_quality.py` | Re-extract the IFRS-9 credit-quality footnote fleet-wide after a fix. | operational backfill |
| `backfill_npl_history.py` | Re-extract NPL Stage-3 movement history (chunked by period). | operational backfill |

## Archived (`scripts/archive/`) — done, kept for reference
`extract_all_audit_reports.py`, `scrape_all_banks.py` (local-PDF flow, replaced by R2-based
`sync_audit_reports`), `migrate_pdfs_to_r2.py` (one-time R2 migration), `reextract_all.py`
(superseded by `backfill_extraction --banks ALL`), `validate_pl_fix.py` / `audit_extraction.py`
(fix-verification), `generate_d1_migrations.py` (one-time D1 seed), the historical data
backfills `backfill_2020_2023.py` / `backfill_weekly_2020_2023.py` / `backfill_weekly_2y.py` /
`update_db_2026.py`, and the 2026-06 audit-repair one-offs: `_eq_failreport.py`
(equity-change failure listing), `ocr_statement.py` (easyocr experiment for image-only
statements — superseded by the manual-overlay path), `normalize_hierarchy_keys.py` (one-time
trailing-dot hierarchy-key migration; the loader now normalises on write), and
`load_partitions_batch.py` (batch variant of `load_partition` for the manual-transcription
campaign).
