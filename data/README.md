# data/ — what every file and directory here is

Mostly gitignored. The committed part is hand-curated configuration and
reference data; everything else is local pipeline state, PDF caches, or
run evidence. R2 and D1 hold the authoritative copies of anything that
matters — nothing in this directory is the only copy of a published number.

When a directory is added or retired, move its row here in the same change.
For anything not listed, the commented `.gitignore` is the authority.

## Committed (in git)

| Path | What it is |
|---|---|
| `banks/` | Bank URL config + BDDK bank list + per-lane source configs (audit reports, faaliyet, transcripts). Hand-edited; what makes the pipeline reproducible from scratch |
| `product_benchmark/` | Per-bank product-benchmark JSONs (32 banks × 100 attributes) + the explorer page. Loaded by `src.products.build` |
| `metric_knowledge/` | The 162-metric banking-knowledge registry ([docs/BANKING_METRICS.md](../docs/BANKING_METRICS.md); CLI `scripts/metric_knowledge.py`) |
| `dashboard_rationale/` | `rationale.json` — the reasoning behind dashboard copy |
| `news/` | News-lane source config: `bank_aliases.json`, `google_news_topics.json`, `press_feeds.json` |
| `chart_specs/` | `schema.json` for the chart-reproduction specs ([docs/REPRODUCING_CHARTS.md](../docs/REPRODUCING_CHARTS.md)) |
| `analyst_eval/` | `cases.json` — the analyst-lane feasibility eval cases |
| `backfill_evidence/` | `evidence.json` + `report.md` from repair campaigns (bulk evidence stays local) |
| `audit_overrides.json`, `manual_statements.json`, `free_provision_overrides.json`, `audit_not_disclosed.json` | Hand-transcribed corrections read from the filings themselves. An override wins outright over any extractor |
| `audit_profiles.json` | Per-PDF format census behind [docs/AUDIT_BANK_CATALOG.md](../docs/AUDIT_BANK_CATALOG.md) |
| `workflow_state.json` | Which workflows are meant to be enabled — `scripts/check_workflow_state.py` diffs it against GitHub |
| `bddk_labels_en.json` | English labels for BDDK series (fetched once, committed) |
| `raw/` | Empty scaffold (`.gitkeep`) |

## Local staging & state (gitignored; each rides its own R2 object)

| Path | What it is |
|---|---|
| `bddk_data.db` (+`.gz`) | Bulletin/EVDS-lane staging DB — rides R2 `state/bddk_data.db.gz` |
| `bank_audit.db` (+`.gz`) | Audit-lane staging DB — rides R2 `state/bank_audit.db.gz` |
| `analyst.db` | Analyst-lane state (signals + memo hashes) — rides R2 `state/analyst.db.gz`. `analyst_*.jsonl` / `analyst_memo_*.md` beside it are its run outputs |
| `bank_audit_prose.db` | The 369k-row historical prose backfill — local-only until its D1 push is decided |
| `bank_audit_capture.db` + `audit_capture/` + `holdout_capture.db` | Full-document capture: the ledger DB, its per-partition JSONL mirror, and the 12-bank holdout. Own R2 object; only the one-row-per-filing manifest reaches D1 |

## Local PDF sets (kept deliberately; R2 is the authority)

| Path | What it is |
|---|---|
| `audit_pdfs/` | Flat fleet mirror of every filing PDF (`<TICKER>_<period>_<kind>.pdf`, ~1,095 files) so capture/extraction can re-run without re-downloading ~3.3 GB from R2 |
| `eye/` | The older hand-assembled diagnostic set (~180 filings) that local extractor tests and scripts default to (`tests/test_market_risk_extractors.py`, `scripts/backfill_document_capture.py`, `scripts/backfill_prose.py`). Kept on purpose for offline test runs |
| `_bench/` | PDF cache the `scripts/scratch/scratch_*.py` probes pull into — regenerable from R2 |
| `external_reports/` | Third-party reference PDFs (BBVA, IMF, …) — never redistributed |
| `albaraka_reports/` | `/economy` chart-reproduction sources (bop/budget/growth/inflation/trade) — the name is historical, not ALBRK-specific |

## Caches & scratch (regenerable — delete freely)

| Path | What it is |
|---|---|
| `evds_cache/` | EVDS HTTP response cache |
| `transcripts/` | Earnings-call JSON dumps — rows of record live in `bank_call_transcripts` |
| `research/` | Analyst-V2 evidence dumps (internal, like `docs/knowledge/`) |
| *(if present)* `bist_cache/` | Cache of the BIST lane **removed 2026-08-01** — dead |
| *(if present)* `knowledge.db` | June 2026 experiment, referenced by nothing |
| *(if present)* `*.stale.db`, `audit_capture.stale/` | Pre-rerun copies kept for a before/after diff that has served its purpose |

Rule of thumb: anything matching `*.stale.*`, `_bench/`, `data/_*.log`,
`_tmp_*` is scratch and safe to delete; the lane snapshots and PDF sets
above are cheap to lose but slow to rebuild.
