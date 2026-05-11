# Per-bank quarterly BRSA audit reports

This module turns each bank's published quarterly BRSA Financial Report
PDF into structured rows. PDFs live in Cloudflare R2; rows live in
Cloudflare D1 (mirrored locally in `data/bddk_data.db` as a pipeline
staging area).

## Pipeline

```
data/banks/audit_report_urls.json    (URL config — one entry per bank, committed to git)
        │
        ▼   scripts/sync_audit_reports.py
        │   ├─ downloads new bank IR PDFs (parallel, idempotent)
        │   ├─ uploads to R2 at <ticker>/<TICKER>_<period>_<kind>.pdf
        │   ├─ lists R2 + diffs against bank_audit_extractions
        │   ├─ downloads pending PDFs to a TemporaryDirectory
        │   └─ extracts each with pdfplumber + fitz, upserts to local SQLite
        ▼
local data/bddk_data.db                                    R2: bddk-audit-reports
   ├── bank_audit_balance_sheet   (assets, liabilities, off-balance)        │
   ├── bank_audit_profit_loss     (P&L line items)                          │
   └── bank_audit_extractions     (one row per PDF, success flag)           │
        │                                                                    │
        ▼   scripts/push_to_d1.py --hours 168                                │
Cloudflare D1 (bddk-data)  ←  ←  ←  ←  ←  ←  ←  ←  ←  ←  ←  ←  ←   ←  ─── ───┘
```

In production this all runs inside `.github/workflows/refresh-data.yml`
every Saturday. The `sync_audit_reports.py` orchestrator is the single
entry point — `scripts/scrape_all_banks.py` and
`scripts/extract_all_audit_reports.py` still exist for local one-off use
but the cron uses the unified flow.

## What's stored

- 32 banks × up to 17 quarters (2022-Q1 → 2026-Q1) × 2 kinds
  (consolidated / unconsolidated) = 949 PDFs in R2
- ~144k balance-sheet rows + ~62k P&L rows in D1
- Each row keeps its original hierarchy (`I.`, `1.1`, `1.1.1`, …),
  Turkish or English item name, footnote refs, and TL / FC / Total amounts
- Values are stored in **thousands of TL** (the BRSA reports' native unit)

## Adding a new period

When banks file the next quarter's reports (typically late
April / July / October / February):

1. **Add new URLs** to `data/banks/audit_report_urls.json`. Each IR site
   renames files unpredictably, so URLs cannot be auto-constructed — visit
   the bank's IR page, find the new PDFs, copy the direct links.

2. **That's it.** The Saturday cron picks up the new entries
   automatically: downloads them to R2, extracts them, pushes to D1.

To pick up the change before the next Saturday cron, trigger the
workflow manually from **GitHub → Actions → Refresh BDDK data →
Run workflow**.

## Modules

| File | Purpose |
|---|---|
| `extractor.py` | PDF → structured `BankReport` (BS + P&L). Handles EN/TR layouts, participation banks, investment banks, pdfplumber column-flatten edge cases, AKBNK 2026Q1-style layouts via PyMuPDF fallback. |
| `loader.py` | `BankReport` → SQLite (idempotent upsert via DELETE-then-INSERT, plus `bank_audit_extractions` log row). |
| `schema.py` | DDL for the three `bank_audit_*` tables. |
| `r2_storage.py` | boto3 wrapper around Cloudflare R2 (S3-compatible). Used by the sync script and the one-shot `migrate_pdfs_to_r2.py`. |

## Known edge cases

| Bank | Behaviour |
|---|---|
| **VAKBN** unconsolidated | served as ZIPs containing PDF + XLSX. ZIP wrapper handled in `sync_audit_reports.fetch_pdf_bytes`. |
| **VAKBN** consolidated | only Q2 + Q4 published per BRSA practice (no Q1 / Q3). |
| **VAKIFK** | some PDFs ship with a 27-byte Java `ObjectOutputStream` wrapper. Stripped via magic-byte detection. |
| **Solo-only banks** | Odea, Pasha, Eximbank, KLNMA have no consolidated tables. URL config has them as `unconsolidated` only. |
| **TSKB** / **QNBFB** / **PASHA** / **AKTIF** / **VAKIFK** | CDNs require Referer header. Mapping in `sync_audit_reports.REFERERS`. |
| **TAKAS** | F5 bot mitigation blocks automated downloads. Manual-only; not tracked in cron. |
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
