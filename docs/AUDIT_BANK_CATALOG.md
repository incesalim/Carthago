# BRSA audit report catalogue — how each bank files, and how extraction can fail

Catalogue of per-bank formatting in the quarterly BRSA audit PDFs (R2 bucket
`bddk-audit-reports`, ~975 PDFs, 31 banks, 2022Q1→). The extractors in
`src/audit_reports/` are deterministic (pdfplumber + heading anchors + labelled
rows — **no LLM API**), so every per-bank quirk must be encoded as an explicit
variant rule. This file is the human-readable index of those rules and the
known ways they break.

Status: seeded from the §4 (capital/liquidity) development pass (2026-06).
The full-fleet backfill (`backfill-audit.yml`, run in 5-bank chunks — `ALL`
exceeds the 180-min job timeout) is the census that completes this table;
`scripts/check_audit_quality.py` flags any bank whose layout we haven't
handled (CET1 ≤ Tier1 ≤ Total, CAR ≈ Total/RWA ×100, ratio bands).

## Report structure (all banks)

| Section | Content | Extractor |
|---|---|---|
| §2 | Financial statements (BS, P&L) | `balance_sheet.py`, `profit_loss.py` |
| §4.1 | Capital adequacy (CET1/Tier1/Tier2/Total, RWA, ratios) | `capital_adequacy.py` |
| §4.6 | LCR, NSFR | `liquidity.py` |
| §4.7 | Leverage ratio | `liquidity.py` |
| §5 | Footnotes (credit quality, loans by sector, NPL movement) | `credit_quality.py`, `loans_by_sector.py`, `npl_movement.py` |

Anchors: §4.1 starts at "Common Equity Tier I Capital Before Deductions" /
"İndirimler Öncesi Çekirdek Sermaye"; liquidity at "High Quality Liquid
Assets". Pages 1–12 are skipped (cover/TOC).

## Format axes (every bank sits somewhere on each)

- **Language**: English vs Turkish labels (Çekirdek/Ana/Katkı Sermaye, Toplam
  Özkaynak, Sermaye Yeterliliği Oranı, Kaldıraç Oranı, Net İstikrarlı Fonlama
  Oranı — with Turkish i-variants `[Iİiı]`).
- **Numbers**: EN `1,234,567` / `16.79` vs TR `1.234.567` / `16,79`.
- **Percent sign**: none, leading (`%5.50`), or trailing (`11,71%`).
- **Tier naming**: "Tier I" (roman) vs "Tier 1" (digit).
- **Row numbering**: clean labels vs glued template numbers (`15.Leverage ratio`).
- **Layout**: standard 2-column (current/prior) vs multi-column (EXIM: 3-period
  BS / 4-column P&L); participation banks use a different BS hierarchy
  (equity at XIV., not XVI.).

## Per-bank quirks verified during §4 development

| Bank | Verified quirks (§4) |
|---|---|
| AKBNK | Trailing-% ratios (`11,71%`); "Tier 1" digit labels |
| DENIZ | TR decimal commas (naive parse read CAR 16,79 as 1679); NSFR row lacks "(%)"/"Rate" wording |
| HALKB | Turkish labels; leverage row number glued (`15.Kaldıraç…`) |
| ISCTR | **Open gap**: no "Total Common Equity Tier I Capital" amount line → `cet1_capital` NULL (CET1 *ratio* still captured) |
| KUVEYT | Turkish labels throughout |
| QNBFB | Duplicate Total Capital lines (intermediate + final own-funds) → extractor takes MAX; NSFR wording variant |
| TEB | Leading-% ratios (`%5.50`) |
| VAKBN | Turkish labels; glued leverage row number. Full 2022Q1→2026Q1 backfill verified in D1 (50 capital + 50 liquidity rows) |
| YKBNK | Turkish labels; "Tier 1" digit variant |
| EXIM | Multi-column statements (3-period BS, 4-column P&L) — affects §2 extractors |

Banks not listed here either extracted cleanly with the base rules during the
dev pass or have not yet been run through §4 (first pass = the 2026-06
backfill). After the backfill, fill in the coverage census below.

## Coverage census (post-backfill)

Pending — once all backfill chunks land, derive from D1:

```sql
SELECT bank_ticker,
       COUNT(DISTINCT period)                  AS periods,
       SUM(capital_adequacy_ratio IS NOT NULL) AS car_rows,
       SUM(cet1_capital IS NOT NULL)           AS cet1_amount_rows
FROM bank_audit_capital GROUP BY bank_ticker ORDER BY bank_ticker;
```

and cross-reference `check_audit_quality.py --db data/bank_audit.db` output
for non-reconciling banks. Record per-bank gaps here as they're triaged.

## Known failure modes (what to look for when a bank breaks)

1. **Silent miss** (no rows): anchor heading worded differently, or §4 deeper
   than `_SKIP_PAGES`/`_MAX_SECTION_PAGES` allow. Symptom: bank absent from
   `bank_audit_capital`. Detection: coverage census above.
2. **Wrong magnitude**: TR/EN number-format misread (the DENIZ 1679 case).
   Detection: quality-check ratio bands (CAR 5–80, leverage 0–30).
3. **Wrong line picked**: duplicate/intermediate subtotal lines (QNBFB).
   Detection: CAR ≈ Total/RWA cross-check (2% tolerance).
4. **Partial extraction**: one label variant missing while others match
   (ISCTR `cet1_capital`). Detection: NULL-share per column in census.
5. **Stale data after extractor fix**: cron skips `success=1` PDFs — a fix
   never self-heals history. Remedy: `backfill-audit.yml` for affected banks.
6. **Push gap**: new table must be in BOTH `push_to_d1.SYNC_TABLES` and the
   `--only-tables` list, and in `backfill_extraction.AUDIT_TABLES`; D1 schema
   self-heals via `_ensure_d1_schema()` (migration 0004 is the canonical DDL).

## Related docs

- `docs/MISSING_AUDIT_DATA.md` — known data gaps
- `docs/PROJECT_STATE.md` — table inventory
- `docs/OPERATIONS.md` — workflow runbook
