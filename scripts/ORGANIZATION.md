# `scripts/` — layout and lifecycle

`scripts/` holds every Python CLI entry point. **The exhaustive, CI-gated
per-script index is [`README.md`](README.md)** — this file explains the *shape*:
what the subdirectories mean, and which pipeline stage a script belongs to.
For the source domains see [`../src/README.md`](../src/README.md); for the
pipeline see [`../docs/SYSTEM_MAP.md`](../docs/SYSTEM_MAP.md).

## Directory layout

```
scripts/
├── README.md                 exhaustive index (check_scripts_index.py fails on drift)
├── ORGANIZATION.md           this file — layout + lifecycle
│
├── graduations/              WIDE-LANE BUILDERS from the document layer
│   ├── build_*_full.py       26 "bank_audit_*_full" minting scripts
│   ├── build_document_tables.py  derived per-table lane
│   ├── audit_narrow_vs_wide.py   narrow lanes audited by wide ones
│   └── report_graduated_lanes.py coverage report
│
├── diagnostics/              read-only inspection / profiling
│   ├── audit_extraction_gates.py, profile_audit_corpus.py, diag_partition.py,
│   ├── catalog_audit_templates.py, generate_audit_census.py, …
│   └── view_document_capture.py, lint_document_capture.py, extract_audit_text.py
│
├── backfills/                long-running history loads
│   └── backfill_credit_quality.py, backfill_npl_history.py
│
├── analyst/                  the analyst lane
│   ── detect.py, score_reports.py, prepare_filing_text.py, …
│
├── scratch/                  completed one-off benches/probes (read-only)
├── archive/                  retired one-shots, kept for the record
├── brand/                    brand asset binaries
│
└── *.py                      everything else — the load-bearing core
```

The flat root is intentional: `refresh.py`, `sync_audit_reports.py`,
`push_to_d1.py`, the `update_*.py` satellites and the `check_*.py` gates are the
files a reader is most often looking for, and moving them would rewrite every
workflow path. New scripts that clearly belong to one of the subdirectories
above should go there; the core lane scripts stay at root.

> **Moves are safe to make as long as the move updates all three:** the script's
> own `parents[N]` repo-root computation, any `*.py` test that loads it by path,
> and `README.md`. `check_scripts_index.py` matches **basenames**, so it survives
> a move as long as the README still names the script. Workflow `python scripts/x.py`
> references are the hard break — never move a script a workflow names.

## Lifecycle buckets

The same six stages as `docs/SYSTEM_MAP.md` §4, with representative scripts.

| Stage | What it means | Examples |
|---|---|---|
| **Acquire** | Fetch external data → local/R2. No analytical rows. | `refresh.py`, `update_monthly.py`, `update_weekly.py`, `sync_news.py`, `update_tefas.py`, `sync_audit_reports.py --no-extract`, `build_document_corpus.py` |
| **Extract** | Source bytes → structured rows. | `sync_audit_reports.py`, `reextract_statement.py`, `reextract_pl.py`, `backfill_extraction.py`, `backfill_document_capture.py`, `graduations/build_*_full.py` |
| **Publish** | Local SQLite → D1 / R2. | `push_to_d1.py` (the only D1 writer), `push_from_scratch.py`, `build_api_catalog.py`, `sync_audit_expected.py`, `seed_audit_db.py` |
| **Repair** | Targeted correction of stored rows. | `purge_partition.py`, `repair_missing_audit_rows.py`, `repair_audit_roles.py`, `repair_loans_zeros.py`, `audit_correct.py`, `apply_overrides.py`, `load_partition.py`, `revalidate_audit_db.py` |
| **Diagnose** | Read-only; writes nothing. | `check_*.py`, `healthcheck.py`, `audit_narrow_vs_wide.py`, `triage_partitions.py`, `watch_cross_period.py`, `diagnostics/*`, `scratch/*` |
| **One-off** | Finished campaign or by-hand generator. | `archive/*`, `generate_presentation.py`, `make_brand_assets.py`, `fetch_bank_logos.py`, `fetch_bddk_english_labels.py`, `compute_bank_metrics.py` |

## The gates

`check_*.py` scripts are the repo's immune system — each exists because the
thing it guards drifted silently once. They are documented in full in
[`README.md`](README.md) → *CI gates*; the ones most relevant to organization
are `check_scripts_index.py` (this index vs reality), `check_docs_sync.py`
(workflows/secrets vs ops docs), and `check_pipeline_graph_sync.py`
(workflows vs the `/pipeline` graph).