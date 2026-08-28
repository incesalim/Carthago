# BRSA audit report catalogue — how each bank files, and how extraction can fail

Catalogue of per-bank formatting in the quarterly BRSA audit PDFs (R2 bucket
`bddk-audit-reports`, ~975 PDFs, 31 banks, 2022Q1→). The extractors in
`src/audit_reports/` are deterministic (PyMuPDF/fitz + heading anchors + labelled
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
| ALNTF | **2026Q1 sourced from BdrUyg (code 124), not the bank's site.** Alternatifbank *filed* 2026Q1 with BDDK (BdrUyg lists SOLO + KONSOLIDE 2026-03) but had not published it on its own IR page, whose newest report was still 31.12.2025 — leaving it the only bank in the fleet behind. Its IR URLs are opaque `/uploads/<timestamp>.pdf` (unguessable, and it's not in `DISCOVERY_BANKS`), so there was nothing to fall back to. Fixed by pointing 2026Q1 (both kinds) at BdrUyg's zip; no code change needed — the zip-unwrap + `bddk_verify()` path added for TAKAS is bank-agnostic. **General rule: when a bank's IR page lags, is WAF-blocked, or has unguessable URLs, pull from BdrUyg.** |
| TAKAS | **Not sourced from the bank's own site**: takasbank.com.tr sits behind an **F5 BIG-IP WAF** that answers non-browser requests with "Request Rejected" (a full browser header set + session cookies still fail — it fingerprints TLS), so CI could never scrape it. Sourced instead from **BDDK's BdrUyg registry** (institution code **132**), which serves a **ZIP** (`unconsolidated_zip`) bundling the financial report WITH an interim activity report — `fetch_pdf_bytes` now prefers the non-`faaliyet` PDF rather than blindly taking the first. BDDK also serves only its leaf cert (omits the GlobalSign intermediate), so the fetch verifies against `src/scrapers/_http.bddk_verify()` — full verification, not a bypass. **2022Q1 omitted**: that PDF has a **broken font cmap** — the text layer returns raw glyph codes at a constant −29 shift (`)ø1$16$/ 9$5/,./$5` = `FİNANSAL VARLIKLAR`), so numbers extract but every label is mojibake and `_locate_pages` finds nothing (`loc={}`). Decodable in principle (constant offset) but would need a cmap-repair pass in the shared extractor. 16/17 periods clean. **Peer-excluded** from ranking/market-share/HHI (clearing/CCP bank, not a lender). |
| VAKBN / ZIRAATK | **Their origins refuse the GitHub runner, and only the runner (2026-08-13).** On the 2026Q2 files both answer `not-pdf:b'<!DOCTYP'` within a second — a WAF page, not a slow download — while the same URLs, fetched with the exact headers `sync_audit_reports` already sends, return the real ~2.8 MB documents from a Turkish address. So the block is on *who is asking*, not on the URL, and the config is correct. **A Referer does not help and was tried and reverted**: ZIRAATK swapped one reject page for another, and VAKBN stopped answering at all and burned the full 120s timeout — strictly worse, because a hanging target is what fed the systemic alarm that stalled this lane for six days. 2026Q2 was acquired by fetching the bytes off-runner and putting them in R2 under `r2_storage.make_key`, gated through `report_validity` exactly as `scrape_to_r2` does (VAKBN 127/121pp, ZIRAATK 123/118pp), then extracted in Actions with `skip_scrape=true`. **The durable route is BdrUyg — VAKBN is institution `015`, ZIRAATK `209`** — which is runner-reachable and already carries TAKAS and ALNTF's 2026Q1. Neither had a `2026-06` zip there on 2026-08-13; the registry lags the banks' own sites by weeks, so re-check it before the next quarter rather than planning on the hand-fetch. |
| DENIZ / ALNTF | **Their IR list is client-side, and it is not on the page the config names (2026-08-13).** Both had filed 2026Q2 weeks earlier — DENIZ on 24 July, ALNTF on 4 August — and no HTTP probe of their `ir_page` could see it: the documents live one level down, at `.../bagimsiz-denetim-raporlari/bddk-konsolide[-olmayan]-finansal-raporlar` (DENIZ) and `.../finansal-raporlar/bddk-konsolide[-olmayan]-finansal-rapor` (ALNTF), and both render the list in JS. Read in a browser they list the quarter plainly. The configured `ir_page` is left as-is for both — it is the right landing page, it simply is not the document list — and neither bank is in `DISCOVERY_BANKS`, so nothing depends on parsing it. **When a bank looks like it has not filed, check the sub-page in a browser before concluding it.** ALNTF's own site is also the reason its 2026Q1 came from BdrUyg (below); by 2026Q2 the site was ahead of the registry, so the two sources swap places quarter to quarter. |
| EXIM / TOMK / KUVEYT | **2026Q2 came from BdrUyg, because their own sites never posted it (2026-08-17).** All three filed on KAP (EXIM 08-06, TOMK and KUVEYT 08-13) and none appeared on the bank's IR page — EXIM's BRSA list still ends at `brsa-20260331`, TOMK's at `31032026.pdf`, and Kuveyt Türk shows only its solo report. The registry had all three: `BDREki-016-SOLO-2026-06.zip` (92pp), `BDREki-213-SOLO-2026-06.zip` (98pp) and `BDREki-205-KONSOLIDE-2026-06.zip` (92pp), each downloaded and put through `report_validity` + `report_basis_from_pdf`. **Institution codes were proved, not recalled**: every probe carried a **2026-03 control**, so a 404 on June against a working March says "the registry has not received it" rather than "the code is wrong", and identity was read off each PDF's own cover page. That method also corrected a guess — T.O.M. Katılım is **213**, not 214 (214 answers with a Java-serialised error object). Mapped in the same sweep: 206 Türkiye Finans, 211 Emlak Katılım, 212 Hayat Finans. **This is the ALNTF pattern repeating**, and it is worth reaching for earlier: BdrUyg is a complete, deterministic, runner-reachable source, and it had EXIM eleven days before anyone would have found it by watching an IR page. |
| COLENDI | **The wp file hangs the runner; the report comes from BdrUyg, code `158` (2026-08-28).** Colendi published its 2026Q2 Turkish solo BDR as a plain href on the same wp-content page the config uses since 2025Q3 (`2026-08/30.06.2026-–-Konsolide-Olmayan-Bagimsiz-Denetim-Raporu.pdf`) — that URL serves 200 / 2.1 MB from a Turkish address and ConnectTimeouts from the GitHub runner: the VAKBN / ZIRAATK shape again. The registry carries the same filing: `BDREki-158-SOLO-2026-06.zip` (73pp, cover reads `COLENDİ BANK … 30 HAZİRAN 2026 … KONSOLİDE OLMAYAN`), with `BDREki-158-SOLO-2026-03.zip` as the control (200 — code proved, not recalled). 2026Q2 is bound as `unconsolidated_zip`. **This also retro-fixes the 2026-08-16 verdict: Colendi had filed; "no filing on any source" merely predated the upload.** |
| HSBC | **2026Q2 was on the IR table after all (2026-08-28).** The 2026-08-16 record read "absent from its IR page *and* from BdrUyg" (KAP filed 08-13; both were true then). By 08-28 the `denetim-raporlari` table listed both halves as plain `<a href="/medium/document-file-NNNN.vsf">` rows carrying `30.06.2026` — `8368` consolidated, `8367` unconsolidated — and BdrUyg had caught up too (`BDREki-123-SOLO/KONSOLIDE-2026-06` both 200). Config binds the two `.vsf` URLs, the pattern that has served every quarter since 2022Q1; the registry is the fallback. The daily `filing_gap_problem` alert from 08-23 was honest — what was missing was a fetch path: HSBC is outside `DISCOVERY_BANKS` and its static config stopped at 2026Q1. |
| VAKIFK | **Its IR host refuses the GitHub runner too (2026-08-16)** — the same shape as VAKBN/ZIRAATK above, but it hit *discovery* rather than the fetch, so it was quieter: `[discover] VAKIFK: FAILED (ConnectTimeout ...)` in every run log while the same page enumerates 34 reports from a Turkish address. Discovery is fail-safe, so the run fell back to a static config with no 2026Q2 entry and reported nothing wrong. 2026Q2 unconsolidated was acquired off-runner into R2 (97pp, gated through `report_validity`), and the URL is now in the config so the runner never touches the host. **The filename carries no basis marker** — `vakif-katilim-bankasi_30_06_2026.pdf`, where Q1 had `_tr_solo` / `_tr_konsolide` — and discovery's skeleton match therefore guessed *consolidated*; the document's own front matter says unconsolidated. The basis guard would have caught it, but a skeleton match on a name that lost its marker is a coin flip, not a read. Consolidated is not published yet. **And once the config held the right answer, discovery kept offering the wrong one**: 2026-08-17 logged `[FAIL] VAKIFK 2026Q2 consolidated basis-mismatch:has-unconsolidated`, a refusal that was correct and permanent — it could only clear when Vakıf Katılım publishes a consolidated report. `scrape_to_r2` now drops a discovered target whose URL the config already binds to a different kind for the same quarter (one document cannot be two bases), because a standing `[FAIL]` sits in the systemic alarm's numerator and three unrelated transient failures would have turned the job red over it. |
| ICBCT | **Its filings say "Kamuyu Aydınlatma Platformu" in the notes (2026-08-16)** — page 8, recounting a 2015 share transfer announced there — and the acquisition guard read the phrase as a KAP cover sheet, refusing both 91-page halves of 2026Q2. Fixed in `report_validity` (the fingerprint is now only consulted below the page floor). Also note the naming: 2026Q2 moved to a `2026_30_06_` **prefix** where every earlier quarter used a `31.03.2026`-style date, and the consolidated file ends `Final 1.pdf` — per-filing naming, not per-bank, so its URLs stay hand-maintained. |
| TSKB | **The English page serves the KAP cover sheet; the Turkish page serves the report (2026-08-16).** For sixteen days `tskb-bank-only-30062026.pdf` and `tskb-consolidated-30062026.pdf` — both linked from the configured English `ir_page`, both found by discovery — returned the same 14-page KAP notification, and that was read as "TSKB has not published 2026Q2". The bank had, on 07-29. The real filings sit on `/yatirimci-iliskileri` under plainly different names: `tskb-solo-30062026.pdf` (87pp) and `tskb-konsolide-30062026.pdf` (92pp), same `/uploads/file/` directory. So the two documents differ only by filename stem, and the English stem is the wrong one. Both now in the config, which wins over discovery (targets are built from config first and discovery skips a `(ticker, period, kind)` already claimed), so the cover sheets in R2 are replaced on the next run by the path `report_validity` was built for. `ir_page` is left English — changing it would re-derive this bank's discovery skeletons, and TSKB's naming has already drifted four times. |
| ISCTR | **The reports are on the TURKISH page, as ZIPs, behind a search form (2026-08-16).** The English page (`/en/about-us/financial-statements`, the configured `ir_page`) offers only `ISBTRUnconsolidatedFinancials30062026.xlsx` for 2026Q2 — Excel, no PDF — and reading only that page produced a confident, wrong conclusion that İş Bankası had not published. It had, on 08-03. The filings live at `/bankamizi-taniyin/finansal-bilgiler`, under the **second tab** ("Mali Tablolar ve Bağımsız Denetim Raporları", not the activity-report tab that renders first), behind a Yıl+Çeyrek form that lists nothing until its `searchButton` is clicked — so no HTTP probe and no first-glance browser look will find it either. Both halves are **ZIPs** bundling one PDF and one xlsx: `.../Mali Tablolar ve Bağımsız Denetim Raporları/Konsolide/Isbank<DDMMYYYY>Konsolide.zip` and `.../KonsolideOlmayan/Isbank<DDMMYYYY>Solo.zip`. `fetch_pdf_bytes` unwraps them unchanged — the path added for BdrUyg is source-agnostic and its non-`faaliyet` preference picks the right member. The **date-substituted URL is predictable**, unlike this bank's PDF names, so next quarter is a one-line edit. Earlier quarters keep their English-page PDF URLs (`TAS Consolidated/pdf/isbnk<date>cons.pdf`); those 404 for 2026Q2. **General rule this cost us: an English IR page can be a subset of the Turkish one — check both before concluding a bank has not filed.** |
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
| fn_market_risk † | — | ~100% |
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

† `fn_market_risk` = the §4 market-risk standardised-approach RWA / capital-charge
table. Fingerprint added 2026-07-15 (`PIYASARISKI` / `MARKETRISK`; 30/30 local banks —
exact corpus count populates on the next census run). **NOT extracted.** Notable: its
rate-risk capital-charge line is disclosed by **both** bank types — conventional
*"faiz oranı riski (genel ve spesifik)"* and participation *"kâr payı oranı riski"* — so
it is the **one rate-risk field spanning all 38 banks**, unlike the repricing ladder
(`fn_interest_rate_risk`, 81%, conventional-only). Candidate extraction for a
participation-inclusive rate-risk metric (would extend the §4 market-risk lane).

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
