# Per-bank quarterly BRSA audit reports

> **Start here:** [`docs/audit/README.md`](../../docs/audit/README.md) is the
> audit doc hub, and [`docs/SYSTEM_MAP.md`](../../docs/SYSTEM_MAP.md) places this
> package in the wider pipeline. The active plan is
> [`docs/AUDIT_DOCUMENT_PLAN.md`](../../docs/AUDIT_DOCUMENT_PLAN.md); the repair
> playbook is [`docs/AUDIT_PIPELINE.md`](../../docs/AUDIT_PIPELINE.md); the
> extractor checklist is
> [`docs/AUDIT_EXTRACTION_GUIDE.md`](../../docs/AUDIT_EXTRACTION_GUIDE.md).
> This README covers the narrow analytical lane and its historical edge cases.

This module turns each bank's published quarterly BRSA Financial Report
PDF into structured rows. PDFs live in Cloudflare R2; rows live in
Cloudflare D1 (mirrored locally in `data/bank_audit.db` as a pipeline
staging area). Extraction is **PyMuPDF (`fitz`) only** — see the root
`AGENTS.md` and `docs/AUDIT_EXTRACTION_GUIDE.md`.

## Pipeline

```
data/banks/audit_report_urls.json    (URL config — one entry per bank, committed to git)
        │
        ▼   scripts/sync_audit_reports.py
        │   ├─ downloads new bank IR PDFs (parallel, idempotent)
        │   ├─ uploads to R2 at <ticker>/<TICKER>_<period>_<kind>.pdf
        │   ├─ lists R2 + diffs against bank_audit_extractions
        │   ├─ downloads pending PDFs to a TemporaryDirectory
        │   └─ extracts each with fitz (PyMuPDF), upserts to local SQLite
        ▼
local data/bank_audit.db                                   R2: bddk-audit-reports
   ├── bank_audit_balance_sheet   (assets, liabilities, off-balance)        │
   ├── bank_audit_profit_loss     (P&L line items)                          │
   └── bank_audit_extractions     (one row per PDF, success flag)           │
        │                                                                    │
        ▼   scripts/push_to_d1.py --hours 168                                │
Cloudflare D1 (bddk-data)  ←  ←  ←  ←  ←  ←  ←  ←  ←  ←  ←  ←  ←   ←  ─── ───┘
```

In production this runs inside `.github/workflows/refresh-audit.yml`, daily
during the quarterly filing windows, on its own lane (`data/bank_audit.db`,
R2 `state/bank_audit.db.gz`, concurrency group `bddk-audit`). The
`sync_audit_reports.py` orchestrator is the single entry point;
`scripts/archive/scrape_all_banks.py` and `extract_all_audit_reports.py` are
retired local one-offs.

## What's stored

Live counts are in [`docs/PROJECT_STATE.md`](../../docs/PROJECT_STATE.md) —
do not trust hardcoded numbers here. Shape:

- 38-bank universe × up to 18 quarters (2022-Q1 onward), consolidated +
  unconsolidated where the bank publishes both; ~98% of sector by assets.
- Each row keeps its original hierarchy (`I.`, `1.1`, `1.1.1`, …),
  Turkish or English item name, footnote refs, and TL / FC / Total amounts.
- Values are stored in **thousands of TL** (the BRSA reports' native unit).
- PDFs live in R2 bucket `bddk-audit-reports`; the lane snapshot is
  `state/bank_audit.db.gz`.

## Adding a new period

When banks file the next quarter's reports (typically late
April / July / October / February):

1. **Add new URLs** to `data/banks/audit_report_urls.json`. Each IR site
   renames files unpredictably, so URLs cannot be auto-constructed — visit
   the bank's IR page, find the new PDFs, copy the direct links.

2. **That's it.** The audit cron picks up the new entries during the filing
   window automatically: downloads them to R2, extracts them, pushes to D1.

To pick up the change immediately, trigger the workflow manually from
**GitHub → Actions → Refresh audit reports → Run workflow**.

## Modules

| File | Purpose |
|---|---|
| `extractor.py` / `profiler.py` | PDF → structured `BankReport` (frozen BS + P&L readers; fitz-only). Handles EN/TR layouts, participation and investment banks. |
| `registry.py` | The statement-type registry: each lane's extractor token, source table and validation gate. `push_to_d1.py` derives the audit table set from it. |
| `validator.py` | Per-lane relationship checks → `bank_audit_validation`. |
| `document_*.py` | The complete-document corpus subsystem (~51 modules): native table/note/section capture, OCR and reviewed grids. |
| `units.py` | Reporting-unit parsing/scaling (`bin` / `milyon`) — the cross-period anchor. |
| `source_capture.py` | Lossless source-line evidence for the normalized/summary lanes. |
| `triage.py` | Deterministic mechanical cause per failing partition. |
| `loader.py` | Rows → SQLite (idempotent upsert plus the `bank_audit_extractions` log row). |
| `schema.py` | Local DDL for the `bank_audit_*` tables (serving schema is `web/migrations/`). |
| `r2_storage.py` | boto3 wrapper around Cloudflare R2 (S3-compatible). |

## Known edge cases

| Bank | Behaviour |
|---|---|
| **VAKBN** unconsolidated | served as ZIPs containing PDF + XLSX. ZIP wrapper handled in `sync_audit_reports.fetch_pdf_bytes`. |
| **VAKBN** consolidated | only Q2 + Q4 published per BRSA practice (no Q1 / Q3). |
| **VAKIFK** | some PDFs ship with a 27-byte Java `ObjectOutputStream` wrapper. Stripped via magic-byte detection. |
| **Solo-only banks** | Odea, Pasha, Eximbank, KLNMA have no consolidated tables. URL config has them as `unconsolidated` only. |
| **TSKB** / **QNBFB** / **PASHA** / **AKTIF** / **VAKIFK** | CDNs require Referer header. Mapping in `sync_audit_reports.REFERERS`. |
| **Partial extractions** (~3% of PDFs) | one of the four statements has fewer than 20 rows. Flagged `success=0` in `bank_audit_extractions`. Mostly historical FIBA / VAKBN quarters. |

## Quick query examples

The dashboard's `web/app/lib/audit.ts` has typed wrappers; for ad-hoc
queries from a Wrangler shell:

```sql
-- Total assets per bank (latest period)
SELECT bank_ticker, period, amount_total / 1e6 AS bn_TL
FROM bank_audit_balance_sheet
WHERE statement = 'assets'
  AND item_name LIKE 'AKTİF TOPLAM%'
  AND kind = 'unconsolidated'
ORDER BY period DESC, amount_total DESC;

-- Net interest income trajectory for one bank
SELECT period, amount / 1e6 AS bn_TL
FROM bank_audit_profit_loss
WHERE bank_ticker = 'GARAN'
  AND kind = 'unconsolidated'
  AND item_name LIKE 'NET INTEREST INCOME%'
ORDER BY period;
```
