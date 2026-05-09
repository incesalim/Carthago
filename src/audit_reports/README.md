# Per-bank quarterly BRSA audit reports

This module turns each bank's published quarterly BRSA Financial Report PDF
into structured rows in `data/bddk_data.db`, alongside the existing BDDK
sector-aggregate tables.

## Pipeline

```
data/banks/audit_report_urls.json    (URL config — one entry per bank)
        │
        ▼   scripts/scrape_all_banks.py        (parallel download, idempotent)
data/audit_reports/{ticker}/{TICKER}_{YYYYQn}_{kind}.pdf
        │
        ▼   scripts/extract_all_audit_reports.py   (parallel extract → DB)
data/bddk_data.db
   ├── bank_audit_balance_sheet   (Assets, Liabilities, Off-Balance — 6 cols)
   ├── bank_audit_profit_loss     (P&L line items — single amount column)
   └── bank_audit_extractions     (one row per extracted PDF, success flag)
```

## What's stored

- 32 banks × up to 16 quarters (2022-Q1 → 2025-Q4) × 2 kinds (consolidated / unconsolidated)
- ~144k balance-sheet rows + ~55k P&L rows
- Each row keeps its original hierarchy (`I.`, `1.1`, `1.1.1`, …), Turkish or English item name, footnote refs, and TL / FC / Total amounts
- Values are stored in **thousands of TL** (the BRSA reports' native unit)

## Adding a new period

When banks file the next quarter's reports (typically late April / July / October / February):

1. **Add new URLs** for each bank to `data/banks/audit_report_urls.json`.
   Each IR site renames files unpredictably, so URLs cannot be auto-constructed.
   Visit the bank's IR page, find the new PDFs, copy the direct links.

2. **Download:**
   ```bash
   python scripts/scrape_all_banks.py
   ```
   Skips files already on disk; downloads only new periods. ~1 min for ~30 new PDFs.

3. **Extract to DB:**
   ```bash
   python scripts/extract_all_audit_reports.py
   ```
   Skips PDFs already loaded with `success=1`. Re-tries previous warns/failures.

## Modules

- `extractor.py` — PDF → structured `BankReport` (balance sheet + P&L). Handles
  EN/TR layouts, participation banks (Toplanan Fonlar / Kâr Payı), investment
  banks (no deposits), and pdfplumber's whitespace quirks.
- `loader.py` — `BankReport` → SQLite (idempotent upsert).
- `schema.py` — DDL for the three `bank_audit_*` tables.

## Known limitations

- **TAKAS (Takasbank)**: F5 bot mitigation blocks Python downloads. Manual
  download required for the 16 PDFs.
- **VAKBN unconsolidated**: served as ZIPs containing PDF + XLSX (handled).
- **VAKBN consolidated**: only Q2 + Q4 published per BRSA practice (no Q1/Q3).
- **Some banks publish solo only** (Odea, Pasha, Eximbank, KLNMA, Takasbank) —
  their consolidated tables are empty.
- ~3% of PDFs extract with partial coverage (one of the four statements has
  fewer than 20 rows). Tracked in `bank_audit_extractions.success`.

## Quick query examples

```sql
-- Total assets per bank (latest period)
SELECT bank_ticker, period, amount_total / 1e6 AS bn_TL
FROM bank_audit_balance_sheet
WHERE statement = 'assets'
  AND (item_name LIKE 'TOTAL ASSETS' OR item_name LIKE 'AKTİF TOPLAM%')
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
