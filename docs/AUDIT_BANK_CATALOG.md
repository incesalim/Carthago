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
| EXIM | Multi-column statements (3-period BS, 4-column P&L) — affects §2 extractors. §4: wrapped narrative line starting "capital adequacy ratio … 31 December 2021." parsed the year as CAR (fixed: ratio band 0–100); glued words "Capital AdequacyRatio (%)" (fixed: `\s*` in ratio labels); current-table total worded "Total Equity (Total Tier I and Tier II Capital)" (added variant); prior period in a separate table, so prior columns stay NULL |
| ATBANK | Turkish-only filing (Arap Türk Bankası). Inline footnote markers "(2)" after ratio labels were read as values (fixed: footnote-token skip). Reported CAR runs ~1.5pp above total/RWA in 2024 — bank applies BRSA temporary-measure adjustments, so the quality-check CAR cross-check flags it as a known false positive |
| TFKB | Split-digit text layer: the leading digit of every number detaches ("1 1,372,338" = 11,372,338; "2 0.20" = 20.20) in the §4 capital AND LCR/NSFR tables, all vintages (fixed: `_repair_split_digits` line repair in both §4 extractors). Same damage class as TSKB §2 (see AUDIT_REWORK_PLAN.md) |
| SKBNK | Row-shifted values in the current-period §4.1 table: the labelled Tier1 row carries the AT1 amount (CET1 > Tier1 flags). Fixed via identity repair — Tier1 rebuilt as CET1+AT1, candidate validated against reported Tier1 ratio × RWA. Prior-period columns are "-" in some quarters → prior row stored as zeros |
| VAKIFK | Consolidated reports prefix ratio labels with "Konsolide" ("Konsolide Sermaye Yeterliliği Oranı") — unprefixed patterns fell through to a wrapped narrative line whose trailing "30 Haziran" date parsed as CAR=30 (fixed: optional Konsolide/Consolidated prefix on all ratio labels). Unconsolidated Tier1 dipnot-ref misread healed by the SKBNK identity repair |
| TSKB | Three eras of damage. Says "Core Equity Tier 1" (not "Common") → anchor + CET1 label variants added. 2023–2024: squished text layer drops ALL inter-word spaces ("CapitalAdequacyRatio(%) 22,87") → all §4 label patterns use `\s*` between words. 2025: ratio-row values absent from the text layer → ratios NULL (amounts complete; CAR computable). Tier1 row often yields no tokens → filled as CET1+AT1 only when reported Tier1 ratio × RWA confirms within 2% (2022-era quarters where AT1 was also missed stay NULL) |
| TEB | Consolidated 2022Q2/Q4 reported CAR ~1.4pp off capital/RWA — BRSA temporary-measures basis (same false-positive class as ATBANK 2024); not a parse error |

Banks not listed here either extracted cleanly with the base rules during the
dev pass or have not yet been run through §4 (first pass = the 2026-06
backfill). After the backfill, fill in the coverage census below.

## Coverage census (generated)

Format census of the whole corpus, regenerated by
`scripts/profile_audit_corpus.py` → `scripts/generate_audit_census.py`
(rework plan Phase 0). §4 D1 coverage can additionally be derived with:

```sql
SELECT bank_ticker,
       COUNT(DISTINCT period)                  AS periods,
       SUM(capital_adequacy_ratio IS NOT NULL) AS car_rows,
       SUM(cet1_capital IS NOT NULL)           AS cet1_amount_rows
FROM bank_audit_capital GROUP BY bank_ticker ORDER BY bank_ticker;
```

<!-- census:begin (generated by scripts/generate_audit_census.py — do not edit by hand) -->

(census not yet generated — run the two scripts above)

<!-- census:end -->

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
