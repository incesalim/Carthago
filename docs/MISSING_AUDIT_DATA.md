# Missing audit data — to resolve manually

_Generated from the local DB + R2. Coverage: this lists every (bank, period, kind) cell that is missing financial-tables and/or IFRS-9 Stage 1/2/3 data, for report kinds the bank actually files._

> ## STATUS 2026-06-12 — financials (BS + income statement) COMPLETE
> - **Balance-sheet validation: 0 failures fleet-wide. Failed extractions: 0 (967/967 succeed).**
> - **Section 0b (the 68→17 BS survivors): ALL RESOLVED** — identity-gated extractor
>   fixes + curated cell overrides (`data/audit_overrides.json`, `scripts/apply_overrides.py`).
> - **Section 0 + the FIBA/TFKB/ISCTR/TSKB "financials" rows in Section 2: RESOLVED** —
>   these reports publish their statement PAGES as scanned images; the
>   balance sheet + income statement were hand-transcribed from screenshots via
>   `scripts/load_partition.py` (`data/manual_statements.json`), each BS validated
>   to 0 and each P&L cross-checked to BS equity. (FIBA 2022Q1 cons+uncons,
>   2023Q3 cons, 2024Q1 cons, 2025Q1/Q2 uncons, 2025Q3 cons+uncons; TFKB 2022Q3
>   cons; TSKB 2026Q1 uncons; ISCTR 2025Q1 cons.)
> - **STILL OPEN:** the **IFRS-9 NPL / Stage 1-2-3 footnote** for those image
>   partitions (a separate table — often also image-only), plus the
>   "NPL/Stage only" rows in Section 2, and the "Need a document" cells in
>   Section 1 (no usable PDF in R2). The sections below are kept for that
>   remaining NPL/Stage + missing-document work.

The original tallies (now partly resolved — see status block):
- **Need a document** (no usable PDF in R2 — unpublished, or our URL serves a summary): 11 cells
- **Extractor fix needed** (full PDF is in R2, parser fails): 19 cells

---

## 0b. Failing identity checks after the 2026-06-11 fix campaign (68→17)

Seven general, identity-gated extractor fixes cleared 51 of 68 failing
balance-sheet partitions (bare dotless romans, bracketed/roman footnote-ref
masking that no longer eats TR-format negatives, wrapped bare-marker rows,
duplicated-digit repair, paren-negative value protection, identity-gated
first-triplet fallback). The 17 survivors below stay ⚠-flagged on /banks:

**Genuine source-digit errors — the PDF's own numbers don't reconcile; not
guessed (fixing would fabricate data):**
- EXIM 2024Q4 unconsolidated — 1.3.2 Equity Securities (TP+YP=4,621,868 but
  Toplam=4,671,868, off 50,000); V. Tangible (336,253 vs 336,235); 16.4
  (off 99). Internal inconsistencies in the filing's own digits.
- TSKB 2025Q3 unconsolidated — text layer shatters numbers into 4+ fragments
  ("1.878.676 6. 019.66"); beyond identity-gated repair (≤3 fragments).
- ODEA 2023Q4 (asset 2.2, off 10); TEB 2024Q4 (asset 4.3, off 10) — single
  rows off by ~10 thousand TL on multi-billion statements.
- BURGAN 2023Q2 consolidated — V. Tangible off 2,815,370.

**Idiosyncratic layout/wrap (one-off per filing; left for targeted follow-up):**
- FIBA 2025Q4 / 2026Q1 — a roman section's values wrap to the line ABOVE its
  label (deferred-tax XII), so the section is dropped from Σromans.
- KUVEYT 2022Q2 / 2025Q4 cons; EMLAK 2022Q3 / 2023Q2; TEB 2024Q4; BURGAN
  2025Q3 — statement_total short: a roman section missing from Σromans via a
  wrap variant.
- ATBANK 2022Q2 cons — equity label split mid-word ("ÖZKAYNAK LAR 9").
- QNBFB 2022Q4 cons — squished "XV. OTHERLIABILITIES".
- YKBNK 2022Q3 / Q4 cons — consolidated equity components individually
  consistent but don't sum to the parent (label/value interleave wrap).
- EXIM 2023Q2 / 2025Q3 / Q4 / 2026Q1 — equity YP column format / small
  growing diffs.

All 17 are visible as ⚠ on the dashboard and in /admin; none are silently
wrong. They are correct candidates for OCR (the shattered/source-error ones)
or a future per-filing layout pass (the wrap ones).

## 0. Permanent gaps — statement pages have NO TEXT LAYER (2026-06-11 audit)

The files below are the banks' official uploads, re-checked against the live
IR URLs — the statement pages are scans/images with no extractable text on
either copy. Unfixable without OCR (pipeline stays deterministic). They show
as missing on the dashboard, never as wrong numbers.

| Bank | Period(s) | Kind | Note |
|---|---|---|---|
| ISCTR | 2025Q1 | consolidated | statements at pp.11-12 image-only; live URL serves the same file |
| FIBA | 2022Q1, 2023Q3, 2024Q1, 2025Q3 (+2025Q1/Q2 liabilities page) | varies | statement pages ~50-300 chars of text; live URL identical |
| TSKB | 2026Q1 | unconsolidated | real report now live at the IR URL but its text layer shatters numbers into 4+ fragments — identity-gated repair can fix only ≤3; kept as gap rather than storing wrong values. (CONSOLIDATED 2026Q1: FILLED 2026-06-11 — clean PDF from live URL uploaded to R2 + extracted, 180 rows, 0 identity failures) |

## 1. Need a document — provide the full BRSA report PDF (or wait for publication)

| Bank | Period | Kind | Missing | In R2? | Source / IR page |
|---|---|---|---|---|---|
| ALNTF | 2026Q1 | consolidated | financials + NPL/Stage | absent | https://www.alternatifbank.com.tr/hakkimizda/yatirimci-iliskileri/raporlar/finansal-raporlar |
| ALNTF | 2026Q1 | unconsolidated | financials + NPL/Stage | absent | https://www.alternatifbank.com.tr/hakkimizda/yatirimci-iliskileri/raporlar/finansal-raporlar |
| EXIM | 2026Q1 | unconsolidated | financials + NPL/Stage | absent | https://www.eximbank.gov.tr/en/financial-informations/financial-audit-reports/brsa |
| ICBCT | 2023Q4 | consolidated | NPL/Stage | 0.7MB (summary) | https://www.icbc.com.tr/tr/images/pdf/31122023_ICBC Turkey Konsolide Mali Tablolar.pdf |
| ISCTR | 2026Q1 | consolidated | financials + NPL/Stage | absent | https://www.isbank.com.tr/en/about-us/financial-statements |
| KLNMA | 2022Q1 | consolidated | financials + NPL/Stage | absent | https://kalkinma.com.tr/yatirimci-iliskileri/finansal-raporlar/denetim-raporlari |
| KLNMA | 2023Q1 | consolidated | financials + NPL/Stage | absent | https://kalkinma.com.tr/yatirimci-iliskileri/finansal-raporlar/denetim-raporlari |
| KLNMA | 2024Q1 | consolidated | financials + NPL/Stage | absent | https://kalkinma.com.tr/yatirimci-iliskileri/finansal-raporlar/denetim-raporlari |
| KLNMA | 2025Q1 | consolidated | financials + NPL/Stage | absent | https://kalkinma.com.tr/yatirimci-iliskileri/finansal-raporlar/denetim-raporlari |
| TSKB | 2026Q1 | consolidated | financials + NPL/Stage | 0.4MB (summary) | https://www.tskb.com.tr/uploads/file/tskb-consolidated-31032026.pdf |
| TSKB | 2026Q1 | unconsolidated | financials + NPL/Stage | 0.4MB (summary) | https://www.tskb.com.tr/uploads/file/tskb-bank-only-31032026.pdf |

## 2. Extractor fix needed — PDF already in R2, only parsing fails

| Bank | Period | Kind | Missing | PDF size | Note |
|---|---|---|---|---|---|
| BURGAN | 2022Q2 | consolidated | NPL/Stage | 3.2MB | NPL footnote layout |
| FIBA | 2022Q1 | consolidated | financials + NPL/Stage | 11.6MB | financial-tables locator fails on this PDF |
| FIBA | 2023Q3 | consolidated | financials + NPL/Stage | 5.8MB | financial-tables locator fails on this PDF |
| FIBA | 2024Q1 | consolidated | financials + NPL/Stage | 13.9MB | financial-tables locator fails on this PDF |
| FIBA | 2025Q3 | consolidated | financials + NPL/Stage | 9.5MB | financial-tables locator fails on this PDF |
| FIBA | 2022Q1 | unconsolidated | financials + NPL/Stage | 11.5MB | financial-tables locator fails on this PDF |
| FIBA | 2025Q3 | unconsolidated | financials + NPL/Stage | 9.8MB | financial-tables locator fails on this PDF |
| ISCTR | 2023Q2 | consolidated | NPL/Stage | 1.4MB | NPL footnote layout |
| ODEA | 2025Q4 | unconsolidated | NPL/Stage | 2.0MB | NPL header spelled-out (no III.Grup line) |
| TFKB | 2022Q3 | consolidated | financials + NPL/Stage | 1.3MB | cross-page NPL table (gross/provision on different pages) |
| TFKB | 2023Q4 | consolidated | NPL/Stage | 3.0MB | cross-page NPL table (gross/provision on different pages) |
| TFKB | 2024Q1 | consolidated | NPL/Stage | 3.1MB | cross-page NPL table (gross/provision on different pages) |
| TFKB | 2025Q1 | consolidated | NPL/Stage | 2.7MB | cross-page NPL table (gross/provision on different pages) |
| TFKB | 2026Q1 | consolidated | NPL/Stage | 1.6MB | cross-page NPL table (gross/provision on different pages) |
| TFKB | 2023Q4 | unconsolidated | NPL/Stage | 2.8MB | cross-page NPL table (gross/provision on different pages) |
| TFKB | 2024Q2 | unconsolidated | NPL/Stage | 2.0MB | cross-page NPL table (gross/provision on different pages) |
| TFKB | 2024Q3 | unconsolidated | NPL/Stage | 4.4MB | cross-page NPL table (gross/provision on different pages) |
| TFKB | 2024Q4 | unconsolidated | NPL/Stage | 6.0MB | cross-page NPL table (gross/provision on different pages) |
| TSKB | 2022Q4 | unconsolidated | NPL/Stage | 1.5MB | no-space rendering |

---

## What "data" means per cell
- **financials + NPL/Stage**: need the whole report (balance sheet, income statement, and the IFRS-9 NPL footnote).
- **NPL/Stage only**: balance sheet + income statement are already loaded; only the Stage 1/2/3 figures are missing — i.e. the "III./IV./V. Grup" NPL classification table (gross / Karşılık provision / net) plus the "Standart Nitelikli / Yakın İzlemedeki" loans-by-stage table.
