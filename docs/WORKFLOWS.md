# Workflows — families, triggers and what each owns

Every scheduled or manually dispatched job lives in `.github/workflows/`. This
file groups the 39 workflows by **purpose** and records their trigger, so a
reader can tell *refresh* from *backfill* from *repair* without opening YAML.
The runbook with inputs and recovery steps is
[`OPERATIONS.md`](OPERATIONS.md); the pipeline shape is
[`SYSTEM_MAP.md`](SYSTEM_MAP.md) §5.

**Reading the prefix:** `refresh-*` is a recurring scheduled lane; `backfill-*`,
`repair-*`, `capture-*`, `review-*`, `build-*`, `acquire-*`, `purge-*`,
`recover-*`, `reextract-*`, `measure-*`, `analyst-*`, `audit-*` are manual
dispatching operations.

---

## Refresh — recurring, scheduled

| Workflow | When (UTC) | What it writes |
|---|---|---|
| `refresh-data.yml` | Sat 03:00 | Full bulletin lane: BDDK monthly+weekly, EVDS, TBB/TKBB, KAP, TEFAS, TÜİK, Faaliyet → one D1 batch + snapshot promote |
| `refresh-bddk-bulletins.yml` | first/last 5 days 13:00; Fri 13:30 + 15:30 | BDDK bulletins only (`--skip-evds`, no audit). Probes monthly at month edges, weekly on Friday |
| `refresh-evds-daily.yml` | Sun–Fri 05:00 | EVDS **daily/workday** series only (FX, policy/funding, sterilization) |
| `refresh-news-daily.yml` | Daily 04:00 | `sync_news.py` → `news_items`, `news_item_banks` |
| `refresh-audit.yml` | filing-window crons (Jan/Apr/Jul/Oct 20–31; Feb 1–29; May/Aug/Nov 1–20; Mar 1–15) | Acquire → extract → derive/validate/build coverage → **one** D1 batch → snapshot. Quiet runs write nothing |
| `refresh-advertised-rates.yml` | Mon 06:00 | `python -m src.rates.scraper` → `bank_advertised_rates` |
| `refresh-calendar.yml` | 1st 06:00 | `python -m src.release_calendar.scraper` → `release_calendar` |
| `refresh-presentations-weekly.yml` | Sat 06:00 | `update_presentations.py` → `bank_earnings` |
| `refresh-transcripts-weekly.yml` | **manual (no cron yet)** | `update_transcripts.py` → `bank_call_transcripts` |
| `summarize-regulations.yml` | Sun 06:00 | Kimi weekly briefing → `regulation_briefings` (publication-gated) |
| `generate-reads.yml` | Sun 07:30 | free-LLM tab lead → `read_headlines` (number-validated) |
| `healthcheck.yml` | Daily 06:00 | **reads** D1 freshness + audit failures; alerts Telegram/Discord |
| `deploy-cloudflare.yml` | after green CI on `master`; dispatch for manual/rollback | migrate + build + deploy the Worker |

## Acquire / corpus capture — manual diagnostics that preserve evidence

These add raw material (PDFs, pages, native structure) without writing
analytical rows.

| Workflow | What it owns |
|---|---|
| `acquire-audit.yml` | Download a newly published audit PDF to R2 without extracting |
| `build-document-corpus.yml` | Preserve originals + typed page evidence in `document-corpus/v1/` on R2 |
| `recover-document-corpus.yml` | OCR / outline / vector recovery for selected pages, source-linked |
| `review-document-origins.yml` | Compare fresh official downloads with acquired bytes; retains transport/PDF revisions |
| `capture-related-documents.yml` | Preserve every other PDF in the source archive/member index |
| `capture-document-edition.yml` | Preserve a distinct historical PDF edition linked to an exact origin receipt |

## Backfill — manual, load or strengthen history

| Workflow | What it loads |
|---|---|
| `backfill-audit.yml` | Re-extract named banks from R2, clear D1 partitions, push, snapshot |
| `backfill-audit-source-capture.yml` | Evidence-only upgrade for 8 normalized/summary audit lanes |
| `backfill-document-capture.yml` | Document-scoped capture of every table every filing prints (own ledger + R2 object) |
| `backfill-faaliyet.yml` | Annual-report franchise history |
| `backfill-nonbank.yml` | Non-bank monthly bulletin history |
| `backfill-tefas.yml` | TEFAS fund-market history |
| `build-products.yml` | Seed the product-shelf benchmark (frozen snapshot) |
| `measure-free-provision.yml` | Read-only corpus-wide diff of a classifier change; returns an artifact, writes nothing |

## Repair — manual, targeted correction of stored rows

| Workflow | The repair |
|---|---|
| `reextract-statement.yml` | One statement lane, registry-routed; `only_failing` / `require_passing` gates |
| `repair-missing-audit-rows.yml` | Restore rows lost from D1 while the authoritative R2 snapshot still has them |
| `repair-audit-roles.yml` | Restore/repair `bank_audit_pl_roles` from stored P&L; never re-extracts a figure |
| `repair-loans-zeros.yml` | One-time re-derivation of zeros the loans loader discarded |
| `purge-partition.yml` | Remove one `(bank, period[, kind])` everywhere — the snapshot-writer order that makes it stick |

## Diagnose — manual, read-only

| Workflow | What it measures |
|---|---|
| `audit-triage.yml` | Deterministic cause per failing partition (evidence attached; no model, no figure) |
| `audit-extraction-gates.yml` | Fault-inject through the real validators/gates on an ETag-pinned snapshot |
| `test-openrouter.yml` | Scratch credential probe; writes nothing, reads no data source |

## Analyst — manual (intended cron wired but off)

| Workflow | What it produces |
|---|---|
| `analyst-daily.yml` | Deterministic detectors → signals + memos; D1 push gated on its `push` input (off by default) |
| `analyst-research.yml` | Analyst V2 agentic discovery over typed read-only tools; artifact-only |

## Infrastructure

| Workflow | Role |
|---|---|
| `ci.yml` | PR + master: ruff, pytest, eslint, tsc, vitest, standalone gates, mobile bundle |
| `deploy-cloudflare.yml` | Exact-SHA verified release + smoke check (also in Refresh above) |
| `healthcheck.yml` | Daily freshness/alert + webhook drift (also in Refresh above) |
| `telegram-webhook.yml` | Register/inspect the Q&A bot webhook (`set` / `info` / `check`) |

---

## Notes

- **Concurrency locks** keep a lane single-writer: `bddk-pipeline`, `bddk-audit`,
  `audit-document-corpus`, `carthago-production-release`. Shared ingestion groups
  use `queue: max` / `cancel-in-progress: false`.
- **CI gates are workflows too** but are documented in `scripts/README.md`;
  `check_pipeline_graph_sync.py` keeps every ingestion workflow in lockstep with
  the `/pipeline` graph, and `check_docs_sync.py` keeps `OPERATIONS.md`,
  `PROJECT_STATE.md` and `ARCHITECTURE.md` naming every workflow and secret.
- Adding a workflow means updating `docs/OPERATIONS.md` (and `PROJECT_STATE.md`)
  in the same change or CI fails.