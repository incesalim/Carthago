# BRSA audit report catalogue — how each bank files, and how extraction can fail

Catalogue of per-bank formatting in the quarterly BRSA audit PDFs (R2 bucket
`bddk-audit-reports`, ~975 PDFs, 31 banks, 2022Q1→). The extractors in
`src/audit_reports/` are deterministic (pdfplumber + heading anchors + labelled
rows — **no LLM API**), so every per-bank quirk must be encoded as an explicit
variant rule. This file is the human-readable index of those rules and the
known ways they break.

Status: seeded from the §4 (capital/liquidity) development pass (2026-06).
**Operational rule:** never run local backfills while CI backfill chunks are
queued/running — the `bddk-audit` concurrency group does NOT serialize
against local runs, and the R2 snapshot is last-writer-wins (the §4 chunk
runs clobbered the 2026-06-10 ALBRK/BURGAN repair; re-repaired as Phase-3
batch 7).
The full-fleet backfill (`backfill-audit.yml`, run in 5-bank chunks — `ALL`
exceeds the 180-min job timeout) is the census that completes this table;
`scripts/check_audit_quality.py` flags any bank whose layout we haven't
handled (capital composition + ratio reconcile, liquidity/off-balance outliers —
see *Validators* below).

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

## Per-bank quirks verified during the §2 fleet dry-run (2026-06-10)

| Bank | §2 quirk |
|---|---|
| QNBFB | Squished EN page header `I. BALANCESHEET-ASSETS CurrentPeriod PriorPeriod 31.12.2023 31.12.2022` — the dates fragment into 6 numeric tokens and the header parsed as a phantom roman-I row (fixed: `BALANCE\s*SHEET` + `Current Period Prior Period` filters) |
| SKBNK | Rows like `INVESTMENT PROPERTY (Net) (14) - - - - -` stored the dipnot as value -14 (fixed: leading-dipnot drop). Residual: occasional dash glyph lost by the text layer (`16.5.4 … 239,160 - 239,160 159,400 159,400` — 5 tokens) → row skipped, parent 16.5 fails its sum check by that child. |
| ISCTR | **2025Q1 consolidated PDF has no text layer on the statement pages** (page 11 yields headers only; pdfplumber and fitz both see no table words). Unextractable without OCR — EXCLUDE this partition from history repair (a backfill would clear the old D1 rows and push nothing). |
| TSKB | Split-digit damage in some 2025 quarters (`Expected Credit Losses (-) 1.849.927 5.` labels, triplet checks fail by 10^6×) + 2026Q1 statements not located at all. Needs its own pass. |
| EMLAK/ICBCT/PASHA | Phase-3 honest-skips: a single malformed row per filing (dipnot stored as a tiny TL value in the old data) is now skipped, so one parent/total identity check fails VISIBLY per affected quarter (EMLAK 2025Q3; ICBCT 2025Q3-Q4 equity 16.4; PASHA assets in 4 quarters) — flagged with ⚠ on /banks rather than hiding garbage |
| ISCTR | Squished AND spaced "OFF-BALANCE SHEET …" data rows were eaten by the page-header filter for years (the spaced variant even in the pre-rework extractor); fixed with OFF/OFF- lookbehinds + BİLANÇO DIŞI lookahead — off-balance section totals recovered fleet-wide |
| ING/KLNMA/PASHA/TFKB/DENIZ/SKBNK | Print contra/negative values in parens → stored negative (sign convention `paren_negative` in the census). Faithful to filing; display normalization is a Phase-4 item. |
| TAKAS | **Not sourced from the bank's own site**: takasbank.com.tr sits behind an **F5 BIG-IP WAF** that answers non-browser requests with "Request Rejected" (a full browser header set + session cookies still fail — it fingerprints TLS), so CI could never scrape it. Sourced instead from **BDDK's BdrUyg registry** (institution code **132**), which serves a **ZIP** (`unconsolidated_zip`) bundling the financial report WITH an interim activity report — `fetch_pdf_bytes` now prefers the non-`faaliyet` PDF rather than blindly taking the first. BDDK also serves only its leaf cert (omits the GlobalSign intermediate), so the fetch verifies against `src/scrapers/_http.bddk_verify()` — full verification, not a bypass. **2022Q1 omitted**: that PDF has a **broken font cmap** — the text layer returns raw glyph codes at a constant −29 shift (`)ø1$16$/ 9$5/,./$5` = `FİNANSAL VARLIKLAR`), so numbers extract but every label is mojibake and `_locate_pages` finds nothing (`loc={}`). Decodable in principle (constant offset) but would need a cmap-repair pass in the shared extractor. 16/17 periods clean. **Peer-excluded** from ranking/market-share/HHI (clearing/CCP bank, not a lender). |
| DUNYAK | **Single-column P&L** (current period only, no prior comparative) in the Q1/Q4 reports → `_detect_pl_ncols` fell back to 2 and `_parse_rows` skipped every 1-number row (~2 rows survived). Fixed 2026-07-11: single-column detector in `_detect_pl_ncols` (≥70% single-value majority on fitz text → `n_cols=1`, `pri_amount=None`); 2-col reports print "-" for empty prior so can't misfire. 2024Q1/2024Q4 additionally carry a source **roman-numbering shift** (net at XIX, tax at XVII, pre-tax at XVI) → `pl_chain` flags them though amounts tie; needs a `pl_rehier` override (AKBNK-2022 pattern). New-entrant onboarding: [knowledge/new-banks-coverage-gap-2026-07-11.md](knowledge/new-banks-coverage-gap-2026-07-11.md). |

## Coverage census (generated)

Format census of the whole corpus, regenerated by
`scripts/diagnostics/profile_audit_corpus.py` → `scripts/diagnostics/generate_audit_census.py`
(rework plan Phase 0). §4 D1 coverage can additionally be derived with:

```sql
SELECT bank_ticker,
       COUNT(DISTINCT period)                  AS periods,
       SUM(capital_adequacy_ratio IS NOT NULL) AS car_rows,
       SUM(cet1_capital IS NOT NULL)           AS cet1_amount_rows
FROM bank_audit_capital GROUP BY bank_ticker ORDER BY bank_ticker;
```

<!-- census:begin (generated by scripts/generate_audit_census.py — do not edit by hand) -->

Census of 975 report profiles across 31 banks (regenerated from data/audit_profiles.json).

| Bank | Type | Reports | Periods | Lang | Text | Dipnot styles | Sign | BS cols | Equity at |
|---|---|---|---|---|---|---|---|---|---|
| AKBNK | deposit | 34 | 2022Q1→2026Q1 | en/tr | spaced | — | plain | 6 | XVI |
| AKTIF | deposit | 34 | 2022Q1→2026Q1 | tr | spaced | paren_int | plain | 6 | XVI |
| ALBRK | participation | 34 | 2022Q1→2026Q1 | en | spaced/squished | paren_int | plain | 6 | XIV |
| ALNTF | deposit | 32 | 2022Q1→2025Q4 | tr | spaced | — | plain | 6 | XVI |
| ANADOLU | deposit | 34 | 2022Q1→2026Q1 | tr | spaced/squished | — | plain | 6 | XVI |
| ATBANK | deposit | 34 | 2022Q1→2026Q1 | tr | spaced/squished | paren_int | plain | 6 | XVI |
| BURGAN | deposit | 34 | 2022Q1→2026Q1 | en/tr | spaced | — | plain | 6 | XVI |
| DENIZ | deposit | 34 | 2022Q1→2026Q1 | tr | spaced | — | paren_negative/plain | 6 | XVI |
| EMLAK | participation | 34 | 2022Q1→2026Q1 | tr | spaced/squished | paren_int | plain | 6 | XIV |
| EXIM | deposit | 17 | 2022Q1→2026Q1 | en | spaced/squished | paren_int | plain | 6/9 | XVI |
| FIBA | deposit | 34 | 2022Q1→2026Q1 | tr | spaced | — | plain | 6 | XVI |
| GARAN | deposit | 34 | 2022Q1→2026Q1 | en | spaced | — | plain | 6 | XVI |
| HALKB | deposit | 34 | 2022Q1→2026Q1 | en | spaced | paren_int | plain | 6 | XVI |
| HSBC | deposit | 34 | 2022Q1→2026Q1 | tr | spaced/squished | — | plain | 6 | XVI |
| ICBCT | deposit | 34 | 2022Q1→2026Q1 | tr | spaced | — | plain | 6 | XVI |
| ING | deposit | 34 | 2022Q1→2026Q1 | tr | spaced | roman_paren | paren_negative | 6 | XVI |
| ISCTR | deposit | 33 | 2022Q1→2026Q1 | en | spaced/squished | — | plain | 18/6 | XVI |
| KLNMA | deposit | 18 | 2022Q1→2026Q1 | tr | spaced | paren_int/section_ref | paren_negative | 6 | XVI |
| KUVEYT | participation | 34 | 2022Q1→2026Q1 | tr | spaced | section_ref | plain | 6 | XIV |
| ODEA | deposit | 17 | 2022Q1→2026Q1 | tr | spaced | — | plain | 6 | XVI |
| PASHA | deposit | 17 | 2022Q1→2026Q1 | tr | spaced | paren_int/section_ref | paren_negative | 6 | XVI |
| QNBFB | deposit | 34 | 2022Q1→2026Q1 | en | spaced/squished | paren_int | plain | 6 | XVI |
| SKBNK | deposit | 34 | 2022Q1→2026Q1 | en | spaced/squished | paren_int | paren_negative | 6 | XVI |
| TEB | deposit | 34 | 2022Q1→2026Q1 | tr | spaced | roman_paren | plain | 6 | XVI |
| TFKB | participation | 34 | 2022Q1→2026Q1 | tr | spaced | paren_int/section_ref | paren_negative/plain | 6 | XIV |
| TSKB | deposit | 34 | 2022Q1→2026Q1 | en | spaced/squished | paren_int | plain | 6 | XVI |
| VAKBN | deposit | 25 | 2022Q1→2026Q1 | tr | spaced/squished | — | plain | 6 | XVI |
| VAKIFK | participation | 34 | 2022Q1→2026Q1 | tr | spaced/squished | paren_int | plain | 6 | XIV |
| YKBNK | deposit | 34 | 2022Q1→2026Q1 | en | spaced | — | plain | 6 | XVI |
| ZIRAAT | deposit | 34 | 2022Q1→2026Q1 | tr | spaced | paren_int | plain | 6 | XVI |
| ZIRAATK | participation | 34 | 2022Q1→2026Q1 | tr | spaced/squished | paren_int | plain | 6 | XIV |

### Format drift (quarter-over-quarter changes)

- **AKBNK** 2022Q3→2022Q4 (unconsolidated): language en→tr
- **ALBRK** 2022Q1→2022Q2 (consolidated): text squished→spaced
- **ALBRK** 2022Q4→2023Q1 (consolidated): text spaced→squished
- **ALBRK** 2024Q4→2025Q1 (consolidated): text squished→spaced
- **ALBRK** 2025Q3→2025Q4 (consolidated): text spaced→squished
- **ALBRK** 2025Q4→2026Q1 (consolidated): text squished→spaced
- **ALBRK** 2022Q1→2022Q2 (unconsolidated): text squished→spaced
- **ALBRK** 2022Q4→2023Q1 (unconsolidated): text spaced→squished
- **ALBRK** 2023Q3→2023Q4 (unconsolidated): text squished→spaced
- **ALBRK** 2025Q3→2025Q4 (unconsolidated): text spaced→squished
- **ALBRK** 2025Q4→2026Q1 (unconsolidated): text squished→spaced
- **ANADOLU** 2022Q1→2022Q2 (consolidated): text squished→spaced
- **ANADOLU** 2022Q3→2022Q4 (consolidated): text spaced→squished
- **ANADOLU** 2023Q2→2023Q3 (consolidated): text squished→spaced
- **ANADOLU** 2023Q3→2023Q4 (consolidated): text spaced→squished
- **ANADOLU** 2023Q4→2024Q1 (consolidated): text squished→spaced
- **ANADOLU** 2024Q2→2024Q3 (consolidated): text spaced→squished
- **ANADOLU** 2024Q3→2024Q4 (consolidated): text squished→spaced
- **ANADOLU** 2022Q1→2022Q2 (unconsolidated): text spaced→squished
- **ANADOLU** 2022Q2→2022Q3 (unconsolidated): text squished→spaced
- **ANADOLU** 2022Q3→2022Q4 (unconsolidated): text spaced→squished
- **ANADOLU** 2023Q2→2023Q3 (unconsolidated): text squished→spaced
- **ANADOLU** 2023Q3→2023Q4 (unconsolidated): text spaced→squished
- **ANADOLU** 2023Q4→2024Q1 (unconsolidated): text squished→spaced
- **ANADOLU** 2024Q2→2024Q3 (unconsolidated): text spaced→squished
- **ANADOLU** 2024Q3→2024Q4 (unconsolidated): text squished→spaced
- **ATBANK** 2023Q1→2023Q2 (consolidated): text spaced→squished
- **ATBANK** 2024Q1→2024Q2 (consolidated): text squished→spaced
- **ATBANK** 2024Q2→2024Q3 (consolidated): text spaced→squished
- **ATBANK** 2024Q3→2024Q4 (consolidated): text squished→spaced
- **ATBANK** 2023Q1→2023Q2 (unconsolidated): text spaced→squished
- **ATBANK** 2024Q1→2024Q2 (unconsolidated): text squished→spaced
- **ATBANK** 2024Q2→2024Q3 (unconsolidated): text spaced→squished
- **ATBANK** 2024Q3→2024Q4 (unconsolidated): text squished→spaced
- **BURGAN** 2025Q4→2026Q1 (consolidated): language en→tr
- **BURGAN** 2025Q4→2026Q1 (unconsolidated): language en→tr
- **DENIZ** 2022Q3→2022Q4 (consolidated): sign plain→paren_negative
- **DENIZ** 2022Q4→2023Q1 (consolidated): sign paren_negative→plain
- **EMLAK** 2022Q4→2023Q1 (consolidated): text spaced→squished
- **EMLAK** 2023Q1→2023Q2 (consolidated): text squished→spaced
- **EMLAK** 2023Q2→2023Q3 (consolidated): text spaced→squished
- **EMLAK** 2023Q4→2024Q1 (consolidated): text squished→spaced
- **EMLAK** 2023Q2→2023Q3 (unconsolidated): text spaced→squished
- **EMLAK** 2023Q3→2023Q4 (unconsolidated): text squished→spaced
- **EMLAK** 2025Q4→2026Q1 (unconsolidated): text spaced→squished
- **EXIM** 2023Q3→2023Q4 (unconsolidated): text spaced→squished
- **EXIM** 2023Q4→2024Q1 (unconsolidated): text squished→spaced
- **EXIM** 2025Q2→2025Q3 (unconsolidated): bs_ncols 6→9
- **HSBC** 2022Q2→2022Q3 (consolidated): text spaced→squished
- **HSBC** 2022Q3→2022Q4 (consolidated): text squished→spaced
- **HSBC** 2023Q2→2023Q3 (consolidated): text spaced→squished
- **HSBC** 2023Q3→2023Q4 (consolidated): text squished→spaced
- **HSBC** 2023Q4→2024Q1 (consolidated): text spaced→squished
- **HSBC** 2024Q1→2024Q2 (consolidated): text squished→spaced
- **HSBC** 2022Q1→2022Q2 (unconsolidated): text spaced→squished
- **HSBC** 2022Q3→2022Q4 (unconsolidated): text squished→spaced
- **HSBC** 2024Q1→2024Q2 (unconsolidated): text spaced→squished
- **HSBC** 2024Q2→2024Q3 (unconsolidated): text squished→spaced
- **ISCTR** 2023Q4→2024Q1 (consolidated): text spaced→squished
- **ISCTR** 2024Q3→2024Q4 (consolidated): text squished→spaced
- **ISCTR** 2023Q4→2024Q1 (unconsolidated): text spaced→squished
- **ISCTR** 2024Q3→2024Q4 (unconsolidated): bs_ncols 6→18, text squished→spaced
- **ISCTR** 2024Q4→2025Q1 (unconsolidated): bs_ncols 18→6
- **ISCTR** 2025Q2→2025Q3 (unconsolidated): bs_ncols 6→18
- **ISCTR** 2025Q3→2025Q4 (unconsolidated): bs_ncols 18→6
- **QNBFB** 2022Q2→2022Q3 (consolidated): text spaced→squished
- **QNBFB** 2023Q2→2023Q3 (consolidated): text squished→spaced
- **QNBFB** 2023Q3→2023Q4 (consolidated): text spaced→squished
- **QNBFB** 2024Q2→2024Q3 (consolidated): text squished→spaced
- **QNBFB** 2022Q2→2022Q3 (unconsolidated): text spaced→squished
- **QNBFB** 2023Q2→2023Q3 (unconsolidated): text squished→spaced
- **QNBFB** 2023Q3→2023Q4 (unconsolidated): text spaced→squished
- **QNBFB** 2024Q2→2024Q3 (unconsolidated): text squished→spaced
- **SKBNK** 2022Q4→2023Q1 (unconsolidated): text spaced→squished
- **SKBNK** 2023Q2→2023Q3 (unconsolidated): text squished→spaced
- **TFKB** 2023Q4→2024Q1 (consolidated): sign paren_negative→plain
- **TFKB** 2024Q1→2024Q2 (consolidated): sign plain→paren_negative
- **TFKB** 2022Q2→2022Q3 (unconsolidated): sign plain→paren_negative
- **TFKB** 2022Q3→2022Q4 (unconsolidated): sign paren_negative→plain
- **TSKB** 2022Q4→2023Q1 (consolidated): text spaced→squished
- **TSKB** 2023Q1→2023Q2 (consolidated): text squished→spaced
- **TSKB** 2023Q2→2023Q3 (consolidated): text spaced→squished
- **TSKB** 2023Q3→2023Q4 (consolidated): text squished→spaced
- **TSKB** 2023Q4→2024Q1 (consolidated): text spaced→squished
- **TSKB** 2024Q4→2025Q1 (consolidated): text squished→spaced
- **TSKB** 2023Q4→2024Q1 (unconsolidated): text spaced→squished
- **TSKB** 2024Q2→2024Q3 (unconsolidated): text squished→spaced
- **TSKB** 2024Q3→2024Q4 (unconsolidated): text spaced→squished
- **TSKB** 2024Q4→2025Q1 (unconsolidated): text squished→spaced
- **VAKBN** 2024Q1→2024Q2 (unconsolidated): text spaced→squished
- **VAKBN** 2024Q2→2024Q3 (unconsolidated): text squished→spaced
- **VAKIFK** 2022Q1→2022Q2 (consolidated): text spaced→squished
- **VAKIFK** 2022Q2→2022Q3 (consolidated): text squished→spaced
- **VAKIFK** 2022Q1→2022Q2 (unconsolidated): text spaced→squished
- **VAKIFK** 2022Q2→2022Q3 (unconsolidated): text squished→spaced
- **ZIRAATK** 2022Q1→2022Q2 (consolidated): text squished→spaced
- **ZIRAATK** 2022Q2→2022Q3 (consolidated): text spaced→squished
- **ZIRAATK** 2023Q4→2024Q1 (consolidated): text squished→spaced
- **ZIRAATK** 2022Q1→2022Q2 (unconsolidated): text squished→spaced
- **ZIRAATK** 2022Q2→2022Q3 (unconsolidated): text spaced→squished
- **ZIRAATK** 2023Q4→2024Q1 (unconsolidated): text squished→spaced
- **ZIRAATK** 2024Q2→2024Q3 (unconsolidated): text spaced→squished
- **ZIRAATK** 2024Q3→2024Q4 (unconsolidated): text squished→spaced

### §4/§5 table inventory (reports containing each anchor)

| Table | Reports | Share |
|---|---|---|
| fn_fees_commissions | 975 | 100% |
| fn_credit_stages | 974 | 99% |
| fn_fx_position | 972 | 99% |
| fn_liquidity_maturity | 972 | 99% |
| s4_capital | 972 | 99% |
| s4_leverage | 972 | 99% |
| s4_liquidity | 954 | 97% |
| fn_segment | 870 | 89% |
| fn_interest_rate_risk | 794 | 81% |
| fn_npl_movement | 747 | 76% |
| fn_related_party | 549 | 56% |
| fn_loans_by_sector | 230 | 23% |

### Reports with NO located balance sheet (10)

- FIBA 2022Q1 consolidated
- FIBA 2022Q1 unconsolidated
- FIBA 2023Q3 consolidated
- FIBA 2024Q1 consolidated
- FIBA 2025Q3 consolidated
- FIBA 2025Q3 unconsolidated
- ISCTR 2025Q1 consolidated
- TFKB 2022Q3 consolidated
- TSKB 2026Q1 consolidated
- TSKB 2026Q1 unconsolidated

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

## Validators (2026-06-15 hardening)

A green validator ≠ correct data: a check can structurally evade the very defect it
targets (see `feedback_verify_validators_against_data`). Each audit validator was
audited against the corpus and tightened:

- **Capital** (`validator.check_capital`) — was orderings-only (CET1≤Tier1≤Total,
  always true) so a mis-extracted component passed silently. Now **reconciles the
  table**: composition `Tier1 = CET1 + AT1` and `Total = Tier1 + Tier2` (optional
  AT1/Tier2 treated as 0 but passing only when it ties; the base alone exceeding the
  parent is a hard fail), plus sub-ratios `cet1_ratio = CET1/RWA`, `tier1_ratio =
  Tier1/RWA`, `CAR = Total/RWA` (±2pp). Surfaced 26 real mis-extractions (AT1/Tier2
  dropped to 0; total↔Tier2 / RWA↔total column slips) that the old check passed.
  GOTCHA: the deployment reader `revalidate_audit_db._capital_rows` must SELECT every
  column the check uses or it silently skips.
- **Stages** (`validator.check_stages`) — the NPL=100% fingerprint (stage3≈total,
  S1+S2≈0) required `stage1`/`stage2` non-null, but the broken shape has them NULL
  (`loans_by_stage` missing), so it **skipped all 45 broken partitions** which then
  scored green on the ECL/coverage sub-checks. Now NULL counts as 0 (a real bank
  never has ~100% of loans in stage 3). The fix is end-to-end: the `credit_quality`
  extractor now captures `loans_by_stage` on column-split/no-space layouts →
  **43/45 repaired** (npl100 45→2; FIBA + TFKB image-only remain).
- **Liquidity** & **Off-balance** — reconciliation-free per partition (liquidity
  stores only ratios; off-balance skips hierarchy levels). The per-partition
  validators are band-only / horizontal-only (a ceiling). Real validation is a
  **within-bank time-series outlier scan** in `check_audit_quality.py`:
  `_liquidity_outliers` (value ≥8× off the bank's own median = a decimal/wrong-cell
  slip; covers `lcr_fc`, which the band check never reads) and
  `_off_balance_consistency` (TOTAL/Σromans jumping off the bank's median = a dropped
  roman section). A stable per-bank offset is structural and stays clean; only a jump
  flags. Alert-only (cron), not a matrix-status change.

## Related docs

- `docs/MISSING_AUDIT_DATA.md` — known data gaps
- `docs/PROJECT_STATE.md` — table inventory
- `docs/OPERATIONS.md` — workflow runbook
