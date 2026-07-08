# Docs index

Canonical documentation for the BDDK banking-data pipeline + dashboard.

**Reading order:** [README.md](../README.md) → [ARCHITECTURE.md](ARCHITECTURE.md)
→ [PROJECT_STATE.md](PROJECT_STATE.md) → [OPERATIONS.md](OPERATIONS.md).
Metric definitions live in [METRICS.md](METRICS.md).

## Core

| Doc | What it covers |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | End-to-end cloud stack: data flow, the two-lane workflow model, R2 snapshots, KV caching, the spine-table guard. |
| [PROJECT_STATE.md](PROJECT_STATE.md) | Snapshot of what's in the system **right now** — data coverage in D1, bank taxonomy, storage map, known issues. |
| [CHANGELOG.md](CHANGELOG.md) | Dated history of pipeline / dashboard changes (split out of PROJECT_STATE). |
| [OPERATIONS.md](OPERATIONS.md) | How to run & maintain: the workflow schedule, manual recipes per lane, troubleshooting, disaster recovery. |
| [METRICS.md](METRICS.md) | Authoritative metric reference — sources (BDDK/EVDS/TBB/TEFAS/BIST/KAP), bank-type taxonomy, currency conventions, dashboard placements. |
| [BANKING_METRICS.md](BANKING_METRICS.md) | The 153-metric registry: what each metric means, how it's computed, and where it surfaces. |
| [ADMIN.md](ADMIN.md) | Setup & use of the `/admin` control center (coverage matrix, pipeline/traffic panels, auth, manual triggers). |
| [TELEGRAM_BOT.md](TELEGRAM_BOT.md) | The public Q&A bot: the agent loop, the read-only SQL gate, the grounding guard, setup, and the `bot-ask` test harness. |
| [SCHEMA_CONVENTIONS.md](SCHEMA_CONVENTIONS.md) | Naming rules for new D1 migrations (≥ 0022), enforced in CI by `scripts/check_schema_naming.py`. |

## Audit lane (per-bank BRSA report extraction)

| Doc | What it covers |
|---|---|
| [AUDIT_PIPELINE.md](AUDIT_PIPELINE.md) | How audit PDFs become D1 rows: the two-lane model, the statement-type registry, the repair playbook. |
| [AUDIT_EXTRACTION_GUIDE.md](AUDIT_EXTRACTION_GUIDE.md) | Checklist for writing / fixing a statement extractor (understand → identities → extract → validate → evidence → repair). |
| [AUDIT_BANK_CATALOG.md](AUDIT_BANK_CATALOG.md) | Auto-generated census of every bank × PDF: format profiles + per-bank filing quirks. |
| [MISSING_AUDIT_DATA.md](MISSING_AUDIT_DATA.md) | Partitions that can't be fixed from the inputs (image-only PDFs, absent filings, annual-only tables). |

## Reference & history

| Doc | What it covers |
|---|---|
| [REPRODUCING_CHARTS.md](REPRODUCING_CHARTS.md) | The chart-spec creation + verification loop (catalog, schema, `verify_chart_spec.py`). |
| [regulation_followups.md](regulation_followups.md) | Tracking file for regulatory changes that need code updates. |
| [AUDIT_REWORK_PLAN.md](AUDIT_REWORK_PLAN.md) | **Historical** — the completed 6-phase audit-quality rework. |
| [RESUME_AUDIT_FIX.md](RESUME_AUDIT_FIX.md) | **Historical** — closure record of the 2026-06-12 balance-sheet ECL corruption fix. |
| [knowledge/](knowledge/) | Dated, status-marked working notes: strategic + architecture reviews, the dashboard audit and display study, free-model evals, the SEO/Search-Console record, and external-report distillations (BBVA outlook, CBRT FSR chart inventory, FT visual-journalism precedents). Not a data source for any page. |
