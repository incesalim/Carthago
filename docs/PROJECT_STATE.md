# Project State

Concise snapshot of what's in the system right now. Updated as data
coverage or known issues change.

> **Reading order:** [README.md](../README.md) → [ARCHITECTURE.md](ARCHITECTURE.md)
> → this file → [OPERATIONS.md](OPERATIONS.md). Metric definitions in
> [METRICS.md](METRICS.md); meta-knowledge about banking metrics (which are
> disclosed, standardized across banks, on a regular cadence, and reproducible
> from our data) in [BANKING_METRICS.md](BANKING_METRICS.md) — a 162-metric
> registry (`data/metric_knowledge/`, CLI `scripts/metric_knowledge.py`).
>
> Last verified: 2026-08-16. Dated change history → [CHANGELOG.md](CHANGELOG.md).

---

## Data coverage in D1

**Bank-ratio gaps (2026-08-31; repaired and verified live):**
ROE gaps in otherwise complete filings came from missing `bank_audit_pl_roles`,
not missing profit figures. P&L persistence now rebuilds that map immediately
from the stored statement, and targeted P&L repairs include it in their
transaction and D1 push without re-stamping unchanged maps. The new manual
`repair-audit-roles.yml` restores only maps that differ from D1 after verifying
the underlying P&L agrees with the snapshot. Q2 NPL gaps also exposed two
million-TL parser assumptions: the Stage-1 admission floor was in thousands of
TL, and the generic NPL reader required a thousands separator. The floor now
respects the filing unit; semantically identified closing/net rows accept
small whole amounts. Repairs remain scoped to affected bank/quarter/lane with
the existing validation gates. Ziraat Dinamik's TTM ROE/NIM remain unavailable
without a stored 2025Q2 YTD baseline; absence is not a zero.
Applied repairs restored 81 role maps across both kinds and 16 banks'
2026Q2 credit/stage partitions; all unaffected stage records were unchanged.
Alternatif Bank's date-only NPL closing label now has a contextual source
mapping: it is accepted only inside the III/IV/V table with three balance
cells followed by the matching provision row, excluding FX-only tables. The
traceability gate remains enabled, and that repair passed. Akbank 2026Q1 had
79 stale labels restored across both kinds, including equity; every amount,
hierarchy and row order stayed unchanged. Legacy single-P&L repairs also compare role
content before including the role table in their D1 replacement.
The final register sweep found a separate Hayat Katılım CAR gap: capital
text repair joined adjacent one-decimal values (`25.6 23.1`) into one token.
Only genuinely detached digits now join; the source gives 25.6% unconsolidated
and 26.6% consolidated CAR. Targeted Q2 repair restored all 12 current/prior
CAR/CET1/Tier1 ratio cells across both kinds; every other capital field stayed
unchanged. All repairs passed their existing validation gates in Actions and
were verified in D1 and the public bank API. At the common 2026Q2 quarter,
every lending bank now has NPL and CAR; only Ziraat Dinamik lacks TTM ROE/NIM
because its 2025Q2 baseline is not stored. No absent value was changed to zero.

| Table | Source | Range | Latest |
|---|---|---|---|
| `balance_sheet`, `income_statement`, `loans`, `deposits`, `financial_ratios`, `other_data` | BDDK monthly bulletin | 2020-01 → present | 2026-06 |
| `weekly_series` | BDDK weekly bulletin | 2019-11 → present | rolling 2-week lag |
| `nonbank_balance_sheet` | BDDK non-bank monthly bulletin (BultenAylikBdmk) | 2008-01 → present | leasing / factoring / financing, monthly, balance sheet (Million TL); reconciles to FKB sector totals. VYŞ (sparse/variant feed) + savings-finance (not in this bulletin) deferred |
| `evds_series` | TCMB EVDS | 2018-01 → present | daily / weekly / monthly per series. Loan/deposit **rates here are SECTOR-level only** (`TP.KTFTUK`/`TP.KTF17`/`TP.KTF12`/`TP.TRY.MT06`) — the per-bank complement is `bank_advertised_rates` below |
| `bank_advertised_rates` | doviz.com (loans) + hangikredi (deposits) — public rate-comparison pages | 2026-07-12 → present (accumulating) | weekly (Mon); per-bank **advertised** (posted-to-new-customers) rates — the only per-bank rate source, since EVDS/BDDK publish rates at sector granularity only. Loans = POINT rate, MONTHLY % (consumer/mortgage/vehicle); deposits = min–max BAND, ANNUAL %. Each run appends a dated `snapshot_date` (the sources only expose "today", so history builds forward — rows never deleted). Distinct from the P&L-derived *realized* yield/cost in `heatmap.ts` |
| `product_attributes`, `bank_products`, `bank_product_profile` | Bank-site research pass, scored against a fixed 100-attribute taxonomy (`data/product_benchmark/`) | snapshot 2026-07-22 (accreting) | **which bank offers which products** — 32 banks × 100 attributes / 10 blocks (deposits, lending, cards, investment, insurance, digital, SME, trade finance, treasury, subsidiaries). Every `yes`/`partial` carries an `evidence_url` on the bank's own domain (3,200 cells, **0 uncited**); `no` = category page checked (about the bank), `unknown` = unverified (about us). English column labels + per-bank prose (`src/products/labels_en.py`, `profiles_en.json`). Powers `/products`. Loaded by `src.products.build` (deterministic, idempotent) via `build-products.yml`; snapshots accrete like `bank_advertised_rates`. **Refresh automation is designed, not built** — two variants (free-model lane / agent routine) over a change-detector spine, see [knowledge/turkish-bank-product-benchmark-2026-07-22.md](knowledge/turkish-bank-product-benchmark-2026-07-22.md) §5 |
| `tbb_digital_stats` | TBB quarterly digital-banking report | 2019-Q1 → present | quarterly (Mar/Jun/Sep/Dec) |
| `tkbb_digital_stats` | TKBB Veri Peteği (Turboard JSON API) — participation-bank digital stats | 2020-Q1 → present | quarterly; active customers (total/channel-mix/province) + txn volume & count (channel/segment/category), RAW units |
| `tkbb_acquisition_stats` | TKBB Veri Peteği — remote-vs-branch acquisition | 2025-07 → present (accumulating) | monthly; source exposes only a rolling 12-month window — history builds forward, rows never deleted |
| `kap_ownership` | KAP Genel Bilgi Formu §5 + §7 subsidiaries (kap.org.tr) | current state per bank (`as_of` = filing date) | weekly full replace; 30/31 banks (ATBANK files no form); subsidiaries grid only on the full form (~15 banks) |
| `tefas_manager_daily`, `tefas_category_daily`, `tefas_allocation_daily`, `tefas_top_funds` | TEFAS fund-market JSON API (tefas.gov.tr) | rolling ~5 years (API rejects older start dates) → present | daily T+1, trading days; aggregated at ingest (no per-fund rows) |
| ~~`bist_prices`, `bist_dividends`, `bist_shares`~~ | ~~Borsa İstanbul via Yahoo~~ | frozen at 2026-08-01 | **LANE REMOVED 2026-08-01** — Yahoo forbids redistribution. Rows retained in D1 but nothing reads them and the bot denies them; do not re-enable without a licensed feed |
| `faaliyet_franchise` | Bank annual reports (Faaliyet Raporu PDFs) | annual (FY ending 31 Dec) | ATM / POS / merchant / customer / card counts (the stats audit reports don't carry; branches & employees stay in `bank_audit_profile`); deterministic regex+coordinate extraction with confidence flags. **⚠️ NOT TRUSTWORTHY — the `/franchise` tab is unpublished (2026-07-12): the extractor samples stray prose numbers, ~75% of non-ATM values are wrong and the confidence flags don't correlate with correctness. Needs a rebuilt extractor + validation gate, NOT more URL curation** |
| `faaliyet_extractions` | per-PDF extraction ledger for the lane above | — | one row per annual report processed: success flag, rows written, confidence — the lane's audit trail |
| `tbb_acquisition_stats` | TBB workbooks — remote-vs-branch customer acquisition | monthly | the **TBB** twin of `tkbb_acquisition_stats` above (deposit banks vs participation banks) |
| `regulation_briefings` | BDDK/TCMB regulation text → weekly Kimi summary | weekly (Sun 06:00 UTC cron) | one briefing row per run. **Since 2026-07-13 it no longer supplies any figure on `/regulation`** — the corridor and reserve ratios are compiled from `news_items.body_text` + EVDS and reconciled, so no model-set figure reaches the page. ⚠️ That is now **this lane's own choice**, not a repo-wide rule — "No LLM sets a number" was reversed 2026-08-03 (see AGENTS.md); the briefing's `find_contradictions()` gate and the compiled-figure design stand until this lane decides otherwise. The briefing supplies **editorial coverage only**: the categories the band does not model (licensing, payments, structure). Two categories stay unsourced by design — see [regulation_followups.md](regulation_followups.md) |
| `bank_audit_balance_sheet` (assets / liabilities / off-balance) | BRSA quarterly PDFs | 2022-Q1 → 2026-Q1 | per-bank |
| `bank_audit_profit_loss` | BRSA quarterly PDFs | same | per-bank |
| `bank_audit_pl_roles` | **derived** — `validator.pl_roles()`, rebuilt from stored rows beside the validation (no re-extraction) | same | **which P&L row IS the period-net / gross / the two opex lines, under THAT filer's own roman numbering.** Exists because BRSA ordinals are NOT fixed: the compressed template some participation banks file puts net-operating at XII and period-net at XXIV, not XIII/XXV. A SQL consumer that hardcodes an ordinal reads the wrong LINE — `heatmap.ts` did, and reported DUNYAK's net profit as **0** for six quarters (`COALESCE(XXV., XIX.)` fell through to XIX = discontinued-ops income, nil) while summing net operating *profit* into opex on 9. Consumers **join this table**; the resolution stays in Python, which has the Turkish fold SQL's ASCII-only `UPPER()` lacks. 9,437 rows / 9 roles |
| `bank_audit_credit_quality` | BRSA PDFs, IFRS 9 footnotes | same | per-bank, per-section |
| `bank_audit_profile` | BRSA PDFs, qualitative section | same | branches + personnel where disclosed |
| `bank_audit_free_provision` | BRSA PDFs, auditor's report + "Other provisions" note | 2022-Q1 → 2026-Q1 | **the free provision (serbest karşılık)** — discretionary reserve behind the ALBRK case. Classifier (`free_provision.py`) + **111 hand-transcribed overrides** (`data/free_provision_overrides.json`, read from full auditor qualifications; 0 = fully-cancelled/'Yoktur'/not-published). **581 rows / 503 holding / 78 zero.** Guarded both by the per-partition `free_provision` validator (range + prior-chain + audit-opinion recall/precision cross-check) and the corpus alert layer, which share the same opinion-subject matcher: **anomalies 114→4** — 2 are genuine (ISCTR free provision under a clean opinion), 2 an EMLAK-2026Q1 prior-field residual. Re-extract delete-then-insert; overrides win outright. An empty row remains N/A only when the opinion supplies no contradictory evidence. |
| `bank_audit_opinion` | BRSA PDFs, auditor's report (front matter) | 2022-Q1 → 2026-Q1 | **the auditor's verdict** — `opinion_type` clean/qualified/adverse/disclaimer + `is_modified` flag + the "Basis for Qualified…" paragraph + firm + audit-vs-review. Deterministic text classifier (`src/audit_reports/audit_opinion.py`), EN+TR / audit+review. Built + **backfilled 2026-07-15**: 976 rows / 38 banks in D1, **552 modified (57%) / 424 clean** — the free-provision practice behind the ALBRK Q1 case is sector-wide (PwC/EY/KPMG all qualify over it; state banks also over bond reclassifications). Basis paragraph captured for 545/552 modified. Per-partition validation requires the auditor and, for modified opinions, the ISA 705 basis paragraph; targeted backfill remains available through `reextract-statement.yml`. |
| `bank_audit_prose` | BRSA PDFs, **all sections** | **backfilled LOCALLY 2026-08-04** — 1,060 partitions / 38 banks / 2022Q1→2026Q2, **369,007 rows, 165M chars**, in `data/bank_audit_prose.db` (gitignored, 298 MB). **NOT in D1** — the 2026-08-01 freeze has since lifted; pushing the historical corpus is a decision not yet taken (merge + push recipe in OPERATIONS.md). 1,014/1,061 partitions pass `check_prose` (95.6%); the 47 failures are GARAN ×32 (§1 has no anchor of any kind), YKBNK ×8 and 7 singles, all the same family: a section resolves but yields no rows, so contiguity flags it | **the narrative** — every prose block in the filing as an item row: `section` (the printed Bölüm) + `section_role` (what it IS) + `heading`/`heading_path` + `item_order` + page span + `lang` + `text`. The first lane whose rows are sentences, not figures. Deterministic, fitz-only, **no model** (`src/audit_reports/prose.py`). Tables are excluded *geometrically* — a table row's tokens share x-positions with the rows above and below, a sentence quoting a figure does not — and running headers by line-frequency. §6/§7 **swap** between annual and interim filings and the section count is 6/7/8 depending on the bank, so `section_role` (read off each filing's own declared title) is what queries must join on, never the number. Local corpus 162 filings: median 368 rows / 157k chars per filing. Validator `check_prose` checks the **sectioning** (count, contiguity, order, the four required roles, and that the filing ends on the auditor's/activity section) — transcription itself has no arithmetic identity |
| `bank_audit_capital` | BRSA PDFs, §4.1 capital adequacy | same — **fully backfilled 2026-06-10** (31/31 banks, ~1.7k rows) | CET1/Tier1/Tier2/Total/RWA + CET1/Tier1/CAR ratios, per period_type |
| `bank_audit_liquidity` | BRSA PDFs, §4.6/4.7 | same — **fully backfilled 2026-06-10** (31/31 banks, ~1.8k rows) | LCR (total/FC), NSFR, leverage ratio, per period_type |
| `bank_audit_fx_position` | BRSA PDFs, §4 currency-risk footnote | same — **backfilled 2026-06-29 (7,143 rows / 31 banks → 2026Q1)** | FX net open position per currency (EUR/USD/OTHER/TOTAL) × period_type; net_position = net_on + net_off (~99% coverage). Powers `/market-risk`. D1 reconciled 2026-07-24 (8,208 rows / 590 partitions) — see the note below |
| `bank_audit_repricing` | BRSA PDFs, §4 interest-rate-risk footnote | same — **backfilled 2026-06-29 (10,364 rows / 24 banks → 2026Q1)** | Repricing gap per bucket (lt_1m…gt_5y/non_sensitive/total) × period_type (~81% coverage; participation banks omit → validated N/A). D1 reconciled 2026-07-24 (12,064 rows / 455 partitions) |
| `bank_audit_oci`, `_cash_flow`, `_equity_change`, `_npl_movement`, `_stages`, `_loans_by_sector` | BRSA PDFs (statement pages + IFRS-9/credit footnotes) | 2022-Q1 → 2026-Q1 | per-bank; per-lane pass rates in the validation-status table below |
| `bank_audit_source_lines` | BRSA PDFs, bounded disclosure pages for 8 completeness-targeted lanes | **schema + automatic capture complete 2026-08-07; historical population pending the manual backfill** | Local/R2 snapshot only, never D1: every PyMuPDF-reconstructed physical line + printed numeric tokens + `mapped_key`. Near-full lanes (`equity_change`, `loans_by_sector`, `npl_movement`) treat an unmapped numeric data row as validation failure; selected-summary lanes retain the deliberately omitted detail for inspection without redefining their analytical schemas. |
| `bank_audit_capture_manifest` | Derived from `bank_audit_source_lines` + normalized row counts | **migration `0042`; new extracts populate automatically; historical backfill not yet dispatched** | One compact D1 row per filing/lane: pages, line/data/mapped/unmapped counts, normalized row count, capture status and content/shape/mapping hashes. Source checks merge into the lane's existing validator once its manifest exists. Alert-ready; no shape-drift alert has been activated yet. |
| `bank_audit_document_pages/_blocks/_lines/_cells/_notes` | BRSA PDFs, **every page** | **schema + engine complete 2026-08-07; fleet captured locally 2026-08-13 (1,095/1,095 — see the capture section below)** | Local only, in its own `data/bank_audit_capture.db` (like `bank_audit_prose.db`) — **never D1, never the audit snapshot**. Document-scoped, not lane-scoped: every table the filing prints, including ones no parser targets. Rows→`_lines` (with `role` ∈ data/heading/footnote/paragraph/furniture and `logical_row` grouping wrapped labels), columns→`_blocks.col_x` (right-edge clusters, so headers that wrap or letter-space don't matter), cells→`_cells` (`col_index` + parsed `value`), notes→`_notes` (marker, full wrapped text, and `linked_lines_json` — the rows printing that marker). `/Rotate 90` pages go through `page.rotation_matrix`, so the landscape 17-column equity statement reads as rows. Writes no analytical row, so it is safe over the settled BS/P&L. Per-partition JSONL mirror in `data/audit_capture/` |
| `bank_audit_document_manifest` | Derived from the capture ledger | **migration `0043`; written by `scripts/backfill_document_capture.py`** | The only part of full-document capture that reaches D1: one row per filing with page/table-page/block/line/cell/note counts plus `content_hash` (text), `shape_hash` (template with values masked) and `grid_hash` (block/column/row geometry — the signal a lane parser is about to break), plus `unreadable_page_count` (renamed from `vector_page_count` by migration `0044`, 2026-08-19) — pages whose content is not machine-readable text, drawn glyph outlines **and** raster-image statement bodies both (`capture_status='partial'`). Unchanged rows are not restamped |
| `bank_audit_document_sections/_items/_tables` | Derived from the capture ledger by `scripts/build_document_tables.py` | **built 2026-08-20 over the local ledger, rebuilt 2026-08-21: 1,095 partitions → 7,362 sections / 57,131 contents items / 122,583 table rows, 301 MB** | The QUERYABLE form of the capture, in its own `data/bank_audit_tables.db` (local; **not in D1** — that push is a decision not yet taken, like the prose corpus). One row per section per filing (the filing's own declared title + `role` — join on role, never the number: §6/§7 swap annual/interim), one per contents item, one per captured table: section context, `declared_unit`, and the grid as JSON — logical rows with labels, cells aligned to inferred columns (signed values; a disclosed "-" stays text), the table's footnotes with the grid rows they qualify (marker lines outside the grid — a heading, a caption, another block's row — kept as ledger `outside_lines`, never dropped), and every in-block cell that matched no column kept in `unplaced_json`. **Since 2026-08-21 a label-only line printed inside a block's span — the head of a wrapped row label, or a sub-header — enters the grid as a row with empty cells flagged `inline` (169,465 such rows in 55,621 tables); the ledger files these as block-less paragraphs and the first build lost them, which six graduated lanes saw as nameless tails. Cell conservation stays exact after the rebuild (8,392,845 = 7,916,634 in grids + 476,211 unplaced).** `numbered_template.absorb_inline` is how a registry lane reads them. **Verified four ways before being trusted (2026-08-20): cell-conservation exact (8,392,845 = 8,392,845 ledger in-block cells); section starts agree with the prose lane's independent reading for 97.7% of role-starts within ±1 page over 1,040 filings (the >1-off tail is dominated by prose's min-page noise on GARAN, its documented weak filer — adjudicated against the filings, which print the activity report where THIS lane places it); stored balance-sheet+P&L figures found inside this lane's `financial_statements` grids at median 100% / p1 98.8% over 1,015 partitions (both sub-90% cases explained: a vector page, and ATBANK 2022Q2's placement tail); notes and their links preserved exactly (60,464 notes; 70,497 of 70,515 links, the 18 being two marker lines of one wrapped row collapsing into its single row). The verification caught and fixed two real defects first: ISCTR's inline-title banners ("SECTION ONE: GENERAL INFORMATION…") had §1 labelled off its first ITEM line, and cross-block marker links mapped into the wrong table's rows because `logical_row` restarts per block (HALKB's "(1)").** Sectioning per filing is stamped `source` = `contents` (folio-validated, 1,011) / `banner` (body fallback, 60) / `none` (24 — mostly FIBA's vector filings, honest NULLs); 97.6% of tables carry a section role. Sectioning logic shared with the HTML viewer via `src/audit_reports/document_sections.py` |
| `bank_audit_capital_full` | Minted from the DOCUMENT layer by `scripts/build_capital_full.py` — the capital pilot, the first graduated lane (no PDF read) | **built 2026-08-22: 843 filings / 34 banks / 94,112 rows (81 refused by the mint gate), local `data/bank_audit_tables.db`, not D1** | The FULL Basel III own-funds template: median **93 rows per partition against the 9 fields `bank_audit_capital` keeps** — every deduction line, threshold and buffer, typed, unit-normalized at mint (ratios never scaled, "-" stays NULL), with `row_role` on registry-matched rows (29 roles, high-precision, both languages) and provenance back to page/block. **Anchored to five years of served figures: cet1 99.5% / tier1 99.6% / tier2 99.5% / rwa 99.0% / ratios 98.6–99.2% / total 97.8% agreement with the narrow lane over ~750 partitions each; tier1=cet1+at1 identity 98.0%.** The ~200 narrow-covered partitions with no wide table are the summary-only disclosure regime (AKBNK 2022, BURGAN …): those filings print only the ~10-row summary the narrow lane reads — no full template exists there to graduate. Residual mismatches are named, not hidden: the sum-vs-final total row (the narrow lane itself stored different template rows for different banks), and capture-placement quirks on single old filings (ISCTR 2024Q1, DUNYAK 2023Q4) **Widened 2026-08-22: 873 → 924 filings, 35 → 37 banks** — two more openers for the own-funds template: QNBFB's "paid-in capital following all debts in terms of claim in liquidation", and the abbreviated table (FIBA) that opens on a bare "Sermaye" row followed by the share-issue premium — the pair is the signature, since either row alone appears all over the notes  **Gated 2026-08-22**: the form has no single sum to check, so an instance is stored only if it carries at least four of the template's aggregate rows AND either tier 1 = CET1 + AT1 or the printed CAR equals total / RWA. That is what the lane was missing: the widened seed let AKBNK's shareholders'-equity note ("Ödenmiş Sermaye / Hisse Senedi İhraç Primleri / Yedek Akçeler") open the chain and ship 14.7bn as CET1 against the narrow lane's 89.5bn. Coverage 924 → 843 filings: the 81 refused include 30 that minted before the gate existed and never satisfied either identity. Narrow rows the wide lane indicts: 44 → 17  **The seed was landing on the prior table, 2026-08-22**: ZIRAAT prints the current own-funds table opening partway down the template — none of the seed lines are in it — and the prior table in full below, so the scan met the PRIOR opener first and 135,100,145, ZIRAAT's 31 December 2021 own funds, was stored as June 2022's against the narrow lane's 196,252,360. A fourth seed dialect reads a block that carries the note's own title and says CARİ DÖNEM without ÖNCEKİ DÖNEM. Every anchor improves and none regresses: cet1_total 99.5% → **100.0%**, tier1_total 99.7% → **100.0%**, at1_total 95.5% → 96.4%, tier2_total 99.6% → 99.9%, total_own_funds 98.4% → 98.9%, total_rwa 99.0% → 99.6%, cet1_ratio 98.3% → 99.1%, tier1_ratio 98.9% → 99.5%. Indictments 17 → 7, and capital-vs-OV1 11 → 7 |
| `bank_audit_lcr_full` | Minted from the DOCUMENT layer by `scripts/build_lcr_full.py` — the second graduated lane | **rebuilt 2026-08-22: 1,000 filings / 37 banks / 43,547 rows (941 filings with both current + prior-year-end instances), local `data/bank_audit_tables.db` — not in D1** | The FULL BRSA LCR template, all 23 numbered rows × 4 value columns (unweighted/weighted × TL+FC/FC) for BOTH printed tables — `template_row` is the cross-bank join key because the regulator numbers the rows and the capture kept the numbers. Money unit-normalized at mint; row 23 (the percent row) never scaled, with ALBRK's three-decimal integer misparse repaired and ENPARA's genuine 34,221.52% left untouched. **Anchors: current LCR total 94.3% / FC 94.8% agreement with `bank_audit_liquidity` (~560 partitions), prior instance vs the prior YEAR-END's narrow row 93.3% — and part of the residue indicts the NARROW lane (ATBANK repeats 411.34 across 2022 quarters: the stale-copy fingerprint). Identity 23≈21/22: 82.0% within 0.5, 94.2% within 10 — row 23 is the average of WEEKLY ratios, not the ratio of the averaged rows, so the wide band is the honest one; 23 wild cases flagged (DUNYAK amount misparse, ENPARA's near-zero-outflow instability).** **Widened 2026-08-22: 656 → 1,000 filings, 25 → 37 banks** — the banks that print the template without its row numbers (HALKB, ING, YKBNK, ZIRAAT, HSBC, ICBCT, ISCTR…) are read by label through `numbered_template.assemble_by_label` (a chain in template order, sub-headers skipped, a label that wraps onto a values-only line adopting those values, current / prior from the block heading), gated on 23 ≈ 21 / 22 within 10% relative — the averaging band. Anchors now: current total **97.5%** / FC **97.9%** over ~880, prior 95.9% over 679. **Welded row numbers, 2026-08-22**: TSKB's capture prints the number joined to its label ("21TOTAL HQLA STOCK") with the number column empty, so the CURRENT table stopped at row 14, failed `bottom_row` and was dropped — leaving the prior-period copy on the next page to be labelled current, which reported 2023's 829% for four quarters of 2024 against the narrow lane's 578%. `numbered_template.rowno(glued=True)` reads the welded form; it is **opt-in and only this lane uses it**, because the same shape elsewhere in the corpus is a maturity band ("1Ay"), a date ("31Aralık 2024") or a footnote. Current total 96.2% → 97.5%, FC 96.7% → 97.9%, no partition lost |
| `bank_audit_nsfr_full` | Minted from the DOCUMENT layer by `scripts/build_nsfr_full.py` — the third graduated lane | **built 2026-08-22: 524 filings / 36 banks / 31,967 rows (482 filings with current + prior-year-end instances, median 34 rows each), local `data/bank_audit_tables.db` — not in D1** | The FULL BRSA NSFR template (rows 1–34, `template_row` the cross-bank join key): four unweighted maturity buckets + the weighted total per row, vs the ONE number (`nsfr`) the narrow lane keeps. **Anchors: current row 34 vs narrow `nsfr` 97.4% (441/453), prior instance vs the prior YEAR-END 93.4%; the internal identity — row 34 = asf_total(row 14) / required(row 33) — holds at 99.0% within 0.5 over 924 instances (NSFR is a point calculation, so unlike the LCR the tight band applies). On mismatches the wide value reproduces EXACTLY from its own ASF/RSF cells (HALKB 2024Q3: 143.54 computed = 143.54 printed vs narrow 133.51) — three independent captured cells agreeing, so the NARROW rows are the suspects there.** **Widened 2026-08-22: 435 → 524 filings, 29 → 36 banks** — the banks that print the 34 rows without their numbers (ING, TEB, ZIRAAT, ICBCT…) are read by label through `numbered_template.assemble_by_label`, whose chain now reads each block on ITS OWN columns (TEB's NSFR is six cells wide on one page and seven on the next) and takes a `tail_of` callback for rows the capture kept as prose: "Gerekli İstikrarlı Fon 364,384" and "Net İstikrarlı Fonlama Oranı (%) 142.75" are single lines with the figure inside the text, parsed in either printed convention and gated by 34 = 14 / 33. The NSFR is a 2024-on disclosure: 524 of the 621 partitions in those ten quarters carry it; of the rest ANADOLU's total-RSF row was merged into the next table's block by the capture, and AKTIF / TSKB print no such table at all |
| `bank_audit_leverage_full` | Minted from the DOCUMENT layer by `scripts/build_leverage_full.py` — the fourth graduated lane, thin over the shared `numbered_template` module | **built 2026-08-22: 1,021 filings / 38 banks / 13,833 rows, local `data/bank_audit_tables.db` — not in D1** | The full BRSA leverage template (rows 1–15: on-balance-sheet, derivatives, SFT and off-balance-sheet exposures, Tier 1, total exposure, the ratio) in both printed columns (current + prior year-end), vs the ONE number (`leverage_ratio`) the narrow lane keeps. **Anchors: current 99.9% (865/866) vs narrow, prior column 98.4% vs the prior YEAR-END's narrow row; identity row 15 = 13/14 at 99.9% within 0.5 over 2,008 checks.** **Widened 2026-08-22: 621 → 1,021 filings, 22 → 38 banks** — the banks that print the template without its row numbers (BURGAN, ING, ZIRAAT, ANADOLU, QNBFB, ISCTR…) or split it over two blocks (HALKB: rows 13–15 in the next block) are read by label in template order, the chain opened only on the on-balance-sheet rows (the capital note's "Tier I capital" cannot start one) and gated on the template's own arithmetic (15 = 13 / 14 within 0.06 pp, or 14 = 3 + 6 + 9 + 12). The LCR and NSFR builders were migrated onto the same module with fleet output identical to the digit |
| `bank_audit_rwa_full` | Minted from the DOCUMENT layer by `scripts/build_rwa_full.py` — the fifth graduated lane (Pillar 3 OV1) | **built 2026-08-20: 911 partitions / 22,714 rows — the broadest graduation yet (83% of the fleet prints the template); local `data/bank_audit_tables.db`, not D1** | The RWA decomposition by risk type, rows 1–25 (credit / counterparty / equity / settlement / securitisation / market / operational / thresholds / floor / total) × three printed columns (RWA current, RWA prior year-end, minimum capital), vs the ONE number (`total_rwa`) the narrow capital lane keeps. **Anchors: row 25 vs narrow `total_rwa` 99.1% (858/866); vs the graduated `capital_full` RWA role 90.1% (the first wide-vs-wide cross-check); prior column vs the prior year-end 89.9%; minimum capital = 8% × RWA on rows 1/16/19/25 at 98.9% (3,527/3,568).** A 0.01% relative band is the right tolerance across separately printed tables (DENIZ prints 423,588,045 in OV1 and 423,588,063 in own funds — independent component rounding, not error)  **Fixed 2026-08-22, found by the wide-vs-wide check against the own-funds note**: the form prints three value columns at most banks and FOUR at others (RWA current / prior, minimum capital current / prior). Read as three, the reader took the last three and shifted every figure one column left, so HALKB's total RWA was its PRIOR total — 1,203,850,144 stored for 1,436,786,128, and 596 rows across the fleet. The four-column reading is accepted only when minimum capital = 8% of RWA holds on BOTH period pairs of the total row. Agreement with the own-funds note 86.9% → **97.2%**, with the narrow lane **99.2%**  **Cut at row 25, 2026-08-22**: YKBNK prints the IRB RWA movement table under OV1 in the same block, its rows numbered 1-9 again in columns of their own, and those columns entered the block's column model — so the total row was read one place over and 2024Q3 came out as 1,115,540,871, YKBNK's own prior figure, against a minimum capital of 119,803,421 that is 8% of 1,497,542,746. Its Q1 and Q3 filings did this every year, which is why the value repeated across two quarters. `numbered_template.assemble(block_cut=…)` trims a block before the column model is built; 7 of 960 OV1 blocks carry numbered rows past row 25 and none is a second copy of the form, and a tail opening on the form's own row 1 is left alone regardless. The form's own identity — min capital = 8% × RWA — goes **98.9% → 99.4%**, two filings stop yielding spurious extra instances, and capital-vs-OV1 disagreements fall 16 → 11 |
| `bank_audit_exposure_class_full` | Minted from the DOCUMENT layer by `scripts/build_exposure_class_full.py` — the sixth graduated lane (Pillar 3 CR4), the first with a MINT GATE | **built 2026-08-22: 321 filings / 32 banks / 8,703 rows (373 instances gated out), local `data/bank_audit_tables.db`, not D1** | Credit-risk exposure by asset class (sovereigns … corporates, retail, mortgage-secured … equity, total), rows 1–18 × six printed columns (on/off-balance before and after CCF/CRM, RWA, RWA density), current + prior-year-end. **No narrow lane holds any of it** — this is where OV1's credit-risk RWA decomposes. Three BRSA forms number the same asset-class rows (CR4, CR5 by risk weight, the interim exposure table), so an instance is stored ONLY if its total row satisfies density = RWA / post-CRM exposure — the equation that proves the six columns landed in the right slots; row-level identity 89.7% on rows 7/8/18 of stored instances. The OV1 cross-anchor reads 72.8% within 2%, the residue a perimeter difference (ALNTF's CR4 includes counterparty exposures, consistently +4–5%), not error. Annual-only disclosure for most filers **Widened 2026-08-22: 231 → 321 filings, 24 → 32 banks** — AKBNK and the participation banks print the eighteen asset classes without the regulator's row numbers, so the lane falls back to `numbered_template.assemble_by_label` with the class names as the registry; the density identity on the total row still decides. Anchors now: density 91.0% over 1,526 rows, row-18 RWA vs the OV1 credit-risk RWA 72.1% within 2% |
| `bank_audit_loan_type_full` | Minted from the DOCUMENT layer by `scripts/build_loan_type_full.py` — the seventh graduated lane and the first from the NOTES section (a label-registry family, not a numbered form) | **built 2026-08-22: 826 filings / 35 banks / 13,559 rows, local `data/bank_audit_tables.db`, not D1** | Cash loans by type × credit quality: non-specialised loans and their seven sub-types (working-capital, export, import, financial sector, consumer, credit cards, other), specialised loans, other receivables, total — by standard / watch-list not-restructured / modified / refinanced, current + prior year-end. **No narrow lane holds any of it; its trust is the template's own arithmetic, enforced at mint** (non-specialised = Σ sub-types AND total = non-specialised + specialised + other receivables, in the standard column). Label variants learned from the fleet (EN "Corporation/Enterprise loans" = working capital; "Loans granted to financial sector"; "Diğer (*)") and a wrapped-label merge ("Mali Kesime" / "Verilen Krediler" as two captured rows) took refusals from 230 → 136. The balance-sheet loans line is NOT a valid anchor here (different perimeter) and is reported as information only **Re-minted 2026-08-21 on the inline-aware document layer: 464 filings / 7,981 rows, refusals 136 → 79.** **Updated 2026-08-21: rows printed without figures arrive as inline rows and the minimum grew down to 7; AKBNK's table prints no "İhtisas Dışı" head (the sub-types sum to it) — then YKBNK's grid (a phantom column made live only by a merged table below; liveness now counted over registry rows) — 572 filings / 25 banks; then the participation banks' bare "Krediler" head, "Business loans" and "Other(*)" — 813 filings / 33 banks / 12,845 rows (253 instances refused).** **Widened 2026-08-22: 813 → 826 filings** — the note's date line above the first row is stripped by the shared `numbered_template.strip_date_lines` (detection 930 → 967 blocks; the identities still refuse 253) |
| `bank_audit_consumer_loan_full` | Minted from the DOCUMENT layer by `scripts/build_consumer_loan_full.py` — the eighth graduated lane, second from the notes | **built 2026-08-21: 910 filings / 33 banks / 63,862 rows (970 detected, 99 instances gated out), local `data/bank_audit_tables.db`, not D1** | Consumer loans, retail and personnel credit cards, personnel loans and overdrafts by maturity: ~45 rows × (short-term, medium-long-term, total), current + prior year-end, with `group_role` (consumer TL / FC-indexed / FC, retail cards TL / FC, personnel …) and `item_role` (housing, vehicle, general-purpose, instalment, non-instalment, other) — 91.3% of value-bearing rows role-tagged. **No narrow lane holds any of it; the mint gate is the template's per-row identity total = short + long (≥90% of rows and the grand total)**, which needs no label registry to trust the figures **Widened 2026-08-21: 449 → 910 filings, 19 → 33 banks** — a period header row above the first row (AKBNK, ZIRAATK), "-TRY" / "-TRL" suffixes (HALKB, SKBNK), the note title carrying the consumer-TL figures with the row's own label lost (DENIZ, ING, AKTIF), "Toplam Tüketici Kredileri" / "Toplam(*)" total labels, and the overdraft vocabulary ("Kredili Müstakriz Hesabı", "Credit Deposit Account", "Deposit Accounts – TL (Real Persons)", the personnel overdrafts as their own group); group roles on 95.0% of value-bearing rows, the rest total rows. ISCTR (31 filings) prints a fourth `accruals` column between the maturities and the total, the note split over adjacent blocks with the grand total in the last — or, from 2025Q4, no grand total at all: the chain ends where the commercial instalment loans begin and the per-row identity (now total = short + long + accruals) gates alone on ≥12 rows. ATBANK / TSKB print the table all dashes — nothing to verify, not minted. |
| `bank_audit_derivative_full` | Minted from the DOCUMENT layer by `scripts/build_derivative_full.py` — the ninth graduated lane, third from the notes | **built 2026-08-22: 846 filings / 33 banks / 8,854 rows (149 instances gated out), local `data/bank_audit_tables.db`, not D1** | Derivatives by instrument (forwards, swaps, futures, options, other, total) × (current TL/FC, prior TL/FC). The six-row template prints several times per filing — trading assets, trading liabilities, hedging — so every instance carries a `context` read off its block heading and contents item (assets 675 / liabilities 649 / unknown 169, heading kept for the rest). **Mint gate: total = Σ instruments on every printed column.** No narrow lane holds any of it. **Widened 2026-08-21: 560 → 848 filings, 24 → 33 banks** — the grid runs from the first instrument row (a date row and a "TP YP TP YP" line ride above it at AKBNK, HSBC, ICBCT, ISCTR, KLNMA…); where the first instrument is the swap, the forward's figures were glued onto the note title above the header lines (QNBFB, ZIRAAT) and that row comes back as the forward; ISCTR's valueless "Futures" / "Other" inline lines stay as rows; a swap row is required, which keeps BURGAN's forward-commitments note out. AKBNK's 2022 assets table lost its forward row in the capture and stays refused  **Audited 2026-08-22**: a new balance-sheet cross-check (the note's own total vs the BS derivative line) indicted 16 rows; GARAN's derivatives-by-remaining-maturity table was being read as the trading note (4.9bn against the balance sheet's 16.6bn) and is now refused by heading. The 14 that remain are GARAN perimeter gaps of 1–8% — open in the repair list, not obviously either side's error |  **The hedging note joins it, 2026-08-22**: GARAN prints the trading derivatives in one table and the fair-value / cash-flow / net-investment hedges in another, and only the first was read — 14,462,104 against a balance-sheet line of 16,113,972, with the hedging note's 973,098 + 678,770 = 1,651,868 exactly the gap. The hedge types are roles of their own and the note is its own family, stored as `hedging_liabilities` (42) and `hedging_assets` (4); its four figures sit among dead columns, so the row is compacted to what is printed rather than taking the last four cells, which would be the prior period twice over. `derivative.liabilities` indictments **11 → 1** |
| `bank_audit_securities_full` | Minted from the DOCUMENT layer by `scripts/build_securities_full.py` — the tenth graduated lane, fourth from the notes | **built 2026-08-21: 990 filings / 36 banks / 1,900 instances / 12,775 rows (34 instances gated out), local `data/bank_audit_tables.db`, not D1** | Securities by instrument and listing: debt securities / investment funds / share certificates, each quoted and unquoted, plus the impairment-or-valuation line and total × (current, prior), one instance per measurement portfolio (fvoci 887 / amortised_cost 802 / fvtpl 82 / unknown 129 — the heading is kept; where it names no portfolio the nearest title paragraph above the block in the capture ledger does, 'unknown' where neither does). **Mint gate: group = quoted + unquoted and total = Σ groups ± adjustment, with the adjustment's sign read off label AND figure** — the rule that took refusals from 333 to 124 once GARAN's additive "Value Increase/Impairment Loss" and HAYATK's already-negative impairment were read as printed **Widened 2026-08-21: 638 → 990 filings, 26 → 36 banks** — the grid is cut to the rows from the first debt-securities row to the first total (a date row above, the amortised-cost movement table the capture glues on below), the value columns are the first two live ones (VAKBN parks the figures in columns 4 and 8 of a nine-cell row), the capital note's "Debt instruments subject to…" tables are no longer admitted, and the registry learns "Not-Quoted", "Beklenen zarar karşılığı", "Değer azalışı karşılığı", "Valuation increase / (decrease)", an "Other" that enters the total and SKBNK's accruals (applied as printed). Refusals 124 → 34.  **Audited 2026-08-22**: a new balance-sheet cross-check (the note's total per portfolio vs the BS line for that portfolio) indicted 94 rows and found a real defect — AKTIF, ALNTF and others print **TP YP TP YP**, the period split by currency, and the reader took the second column as the prior period, halving every figure (5,715,764 where the balance sheet says 11,379,468). `current` and `prior` are now the period totals with the halves kept beside them in `current_tl` / `current_fc` / `prior_tl` / `prior_fc` (292 rows carry a split); indictments 94 → 90, and the rest are perimeter gaps — ANADOLU's note total is after impairment while the balance sheet's line is the carrying value  **Portfolios read from the block's own title line, 2026-08-22**: ALNTF prints "e. Gerçeğe uygun değer farkı diğer kapsamlı gelire yansıtılan…" as a valueless row two lines above its own table, inside a block whose heading belongs to the country table above it. The ledger lookback cannot see that line — it is in the tables layer, not the lines layer — so it reached past it to the FVTPL note and filed 7,919,060, the balance sheet's FVOCI line to the lira, as `fvtpl`. `portfolio_from_grid` now reads the nearest title printed ABOVE the table's first group row and outranks the ledger: **unknown 129 → 1**, fvoci 887 → 929, amortised_cost 802 → 901, fvtpl 82 → 69. Measured against the balance sheet the reassignments hold — fvtpl 96.2%, fvoci 96.4%, amortised_cost 93.7%  **Currency split read from the column labels too, 2026-08-22**: EXIM's amortised-cost note totals 3,694,986 TL + 6,133,573 FC = 9,828,559, the balance sheet's line to the lira, and the lane stored the 3,694,986 — the four-way header survives only in the COLUMN LABELS there (`["Current TL", "Period FC", "Prior TL", "Period FC"]`), where the gaps run longer than the in-grid header's pattern allows. The check's own amortised-cost pattern also required "MEASURED at" and missed BURGAN's "Financial Assets at Amortized Cost", which is its note's total exactly. KUVEYT prints its note number in the first cell — "1.4 Gerçeğe uygun değer farkı diğer kapsamlı…" as `[1.4, None, None, None]` — and reading that as a data row skipped the title, so an FVOCI note was filed as fvtpl at 67,659,318 against a balance-sheet line of 24,927,386; the number column is now excluded from that test and **`unknown` is 0**. QNBFB writes the lira column `TRY` and runs "Current Period" between the pair, which the column-label pattern did not reach — 21,584,370 + 16,644,057 = 38,228,427, its balance-sheet line exactly. Indicted rows now **0 of 66 fvtpl, 0 of 933 fvoci, 3 of 902 amortised_cost** — every fvoci residue is a CLASSIFICATION BAND, not a repair: the note splits debt / equity / impairment while the balance sheet splits government debt / equity / other financial assets, so a corporate eurobond lands on opposite sides and the note's total sits between the named securities lines and the parent (FIBA 2025Q1: 14,801,532 < 19,528,563 < 36,611,898). A total outside that band stays an indictment |
| `bank_audit_credit_quality_full` | Minted from the DOCUMENT layer by `scripts/build_credit_quality_full.py` — the eleventh graduated lane, back on the numbered-template machinery | **built 2026-08-21: 360 filings / 658 instances / 2,631 rows (7 instances gated out), local `data/bank_audit_tables.db`, not D1** | Pillar 3 CR1, credit quality of assets: rows 1–4 (loans, debt securities, off-balance-sheet receivables, total) × defaulted gross, non-defaulted gross, allowances, net; current + prior year-end. Row identity net = defaulted + non-defaulted − allowances holds on 99.8% of rows 1–3 and is the mint gate on row 4; row 4 = Σ rows 1–3 on 99.4% of columns; defaulted loans equal the narrow `bank_audit_npl_movement` closing sum (groups III+IV+V) on 97.5% of 321 filings — all eight misses are EMLAK, 2–7% below the NPL sum in every filing, a perimeter difference not a parse error. Two capture lessons: a four-row template whose bottom row is "Total" needs its row-1 signature in the block filter (the CVA table joined otherwise), and AKTIF's capture merges CR1-prior with CR2 into one six-column grid — `numbered_template.assemble(row_live_cells=True)` reads a row's own cells when exactly four are live, which took refusals from 161 to 7 |
| `bank_audit_defaulted_movement_full` | Minted from the DOCUMENT layer by `scripts/build_defaulted_movement_full.py` — the twelfth graduated lane | **built 2026-08-21: 373 filings / 450 instances / 2,700 rows (8 instances refused), local `data/bank_audit_tables.db`, not D1** | Pillar 3 CR2, changes in the stock of defaulted loans and debt securities: rows 1–6 (opening, newly defaulted, returned to performing, written off, other changes, closing), `amount` + `amount_prior` where a second column prints. Stored as printed with the instance's balancing `convention` — signed 240 / deductions_3_4 177 / deductions_3_4_5 33 — an instance that balances under none is refused (8). Cross-lane: closing equals CR1's current defaulted stock on 98.7% of 298 filings and opening equals CR1's prior on 98.8% — on two perimeters, loans + debt securities (211 filings) or the CR1 total including off-balance-sheet (83); the narrow NPL-movement sum ties on 69.3%, the rest being the off-balance perimeter. The four remaining misses: EMLAK (whose CR2 ties to the NPL lane instead) and VAKIFK 2023Q2 unconsolidated |
| `bank_audit_risk_weight_full` | Minted from the DOCUMENT layer by `scripts/build_risk_weight_full.py` — the thirteenth graduated lane and the largest | **built 2026-08-22: 385 filings / 31 banks / 146,565 rows (284 instances gated out; 240 blocks with no readable weight header), local `data/bank_audit_tables.db`, not D1** | Pillar 3 CR5, exposures by asset class × risk weight, LONG: one row per (asset class, column) with `risk_weight`, `col_role` (weight / other / unknown / total) and `secured_re` for the 35%/50% mortgage-secured twin columns. Six weight sets in use across banks (the 2016 and current templates, ±25%, ±200/250%). Mint gate: total = Σ columns on the total row and ≥90% of rows, tolerance scaled to the declared unit (a filing in millions rounds by ±1,000 canonical). Anchor: grand total equals CR4's post-CRM on+off exposure on 94.4% of 124 current and 94.8% of 97 prior instances. 305 of 4,993 kept columns carry an unreadable weight (`unknown`, still in the sums). Indictments for the repair list: FIBA 2022Q4's CR4 row 18 reads 14,496 (a CR4 defect), and FIBA 2022Q4's CR5 is byte-identical to 2022Q2's **Widened 2026-08-22: 248 → 385 filings, 21 → 31 banks** — AKTIF, ATBANK, ANADOLU and the participation banks print the asset classes without the regulator's row numbers, so the whole reader (family test, column model, row loop) saw an empty body; the body rows are now the class rows themselves where no numbers are printed, and the form's own order numbers it. The row sums still gate, and the grand total anchors to CR4's post-CRM on+off at 86.0% current / 81.1% prior |
| `bank_audit_deposit_insurance_full` | Minted from the DOCUMENT layer by `scripts/build_deposit_insurance_full.py` — the fourteenth graduated lane, fifth from the notes | **built 2026-08-21: 476 filings / 2,833 rows (10 instances refused), local `data/bank_audit_tables.db`, not D1** | Saving deposits covered by / exceeding the deposit-insurance limit: saving TL / FX / other, foreign-branch and off-shore deposits under a foreign insurer, commercial rows where printed (30), total where printed (283) × (covered, exceeding) × (current, prior). Column order read off the labels — HSBC prints period-major under a year header row, which was the bulk of the 67 → 10 refusals. Gate: a printed total must equal Σ rows in every column; 193 instances carry `total_check='not_printed'` because the regulator's template has no total row. Roles cover 97.3% of value-bearing rows; the rest are wrap tails whose head the capture left outside the grid **Re-minted 2026-08-21: 486 filings / 2,893 rows, refusals 10 → 0, roles 99.6%.** **Updated 2026-08-21: a block opening on a year row (AKBNK) and the participation banks' "Turkish Lira / Foreign currency accounts" rows — 577 filings / 21 banks / 3,339 rows, 0 refused, roles 99.7%.** |
| `bank_audit_deposit_maturity_full` | Minted from the DOCUMENT layer by `scripts/build_deposit_maturity_full.py` — the fifteenth graduated lane, sixth from the notes, and the largest by an order of magnitude | **built 2026-08-21: 689 filings / 2,106 instances / 275,639 rows (157 instances refused; 133 blocks with no readable band header unminted), local `data/bank_audit_tables.db`, not D1** | Deposits by type × maturity band, LONG (row_role × band → amount), plus the same-shaped interest-paid-on-deposits matrix; `measure` = balance (935 instances) / interest_expense (738) / unknown (433, heading kept), decided with `period_label` by the grand total against the narrow BS deposits line or P&L deposit-interest line — current filing, prior year-end, or prior year's same quarter. Gate: total = Σ bands on ≥90% of rows and the grand total, tolerance scaled to the declared unit. Bands cover 98.8% of value cells, roles 90.0% of value-bearing rows. Capture lessons: header fragments park in dead columns between the live ones, one cell names two bands (`Vadesiz İhbarlı`, `3-6 Ay 6 Ay-1 Yıl`), matrices break across blocks at page ends (a continuation block inherits the model), and some banks print an unlabelled prior-period total column (found by which layout adds up). The Section-4 maturity-gap table wears the same columns and is excluded by vocabulary **Re-minted 2026-08-21: 2,111 instances / 275,970 rows; roles 90.0 → 92.4%, bands 98.8 → 99.1%, anchored 942 balance / 745 interest.** **+ the participation banks' template (2026-08-21): current and participation accounts × real persons / other × TL / FC with their institution and bank sub-rows, bands demand / ≤1m / ≤3m / ≤6m / ≤9m / ≤1y / 1y+ / accumulating read in the regulation's order — 1,476 instances; the lane now covers 32 of 38 banks (the six left take no deposits), 938 filings / 467,594 rows, 1,342 instances anchored to the BS funds-collected / deposits line.**  **Audited 2026-08-22**: the matrix's grand total meets the balance sheet's deposits line on **all but 2 of the filings compared** (ICBCT 2023Q1 and ZIRAAT 2026Q1, both inside 0.2%) — the strongest confirmation any lane has, and it covers the largest one |
| `bank_audit_section4_matrix_full` | Minted from the DOCUMENT layer by `scripts/build_section4_matrix_full.py` — the sixteenth graduated lane, three families in one table | **built 2026-08-21: 1,072 filings / 4,473 instances / 529,101 rows (278 instances refused), local `data/bank_audit_tables.db`, not D1** | The Section-4 risk tables on one row template, LONG (row_role × band → amount): `liquidity_gap` 1,613 instances (demand … 5y+, unallocated), `repricing` 1,186 (≤1m … 5y+, non-interest-bearing), `fx_position` 1,674 (EUR, USD, other FC), current and prior. Cross-lane: total assets per bucket equal the narrow `bank_audit_repricing` on 96.4% of 1,034 instances, per currency the narrow `bank_audit_fx_position` on 99.8% of 1,445, and the liquidity gap's total assets the balance sheet on 92.9% of 476 — the two narrow lanes now have a wide auditor. Roles on 87.7% of value-bearing rows at first mint; the rest were wrap tails whose head the capture left outside the grid — fixed 2026-08-21 in the document layer (`inline` rows + `absorb_inline`) and re-minted (see the 2026-08-21 re-mint numbers below). `fold()` now folds circumflexed vowels (Kâr, Resmî), which every registry lane inherits **Re-minted 2026-08-21: 4,479 instances / 529,917 rows, roles 87.7 → 92.7%, anchors unchanged (96.4 / 99.8 / 92.9%).**  **A stray split fragment was hiding whole tables, 2026-08-22**: ALNTF's repricing header reads `['1 Aya Kadar', '1-3 Ay', '3-12 ay', 5.0, '1-5 yıl 5 Yıl ve Üzeri', 'Faizsiz', 'Toplam']` — the "5" of "5 Yıl" split into a column of its own — and that lone float disqualified the whole row as a header, so the band vocabulary never reached the family test and the CURRENT table was dropped for the prior one beside it. Every quarter of 2025 then carried December 2024's 11,429,617 where the narrow lane has 16,677,889 / 14,360,541 / 15,723,278 / 19,541,331. `band_matrix.is_header_row` now tolerates a small integer fragment among the words (twice as many words as numbers, each number integral and ≤ 12). Instances **repricing 1,186 → 1,308, liquidity_gap 1,619 → 1,759**, 96 more agreeing repricing rows at a flat 96.1%, and the lane reaches 569,702 rows  **And the family was read from words both matrices print, 2026-08-22**: HALKB's capture truncated "Non-bearing interest" to "interest" and "5 years and over" to "over", so its repricing table matched nothing under its own name and fell to liquidity_gap on "1-5 years" — a band BOTH print. AKTIF's survives as `["itibarıyla) aya", "", "", "", "yıl ve", "", ""]`, naming no family at all. Each time the prior-period copy beside it became the only repricing instance: 3,022,219,724 for HALKB's 4,028,954,890 and 49,018,578 for AKTIF's 65,778,856. The words that name ONE matrix are now tried first, and a block naming none is read by shape — repricing prints six bands and a total, the liquidity gap seven and a total. Instances **repricing 1,308 → 1,507, liquidity_gap 1,759 → 1,761**; repricing anchor 96.1% → **96.5%** and the liquidity gap's total assets vs the narrow balance sheet 92.8% → **98.7%**. The check itself was comparing one of seven buckets — the narrow lane stores codes (`lt_1m`, `1_3m`, …) and every needle was written for the printed Turkish, so only `non_sensitive` matched through "NON". With all seven compared the indictments read 110 → **14**, the last of it two ODEA filings. The final piece was AKTIF's own caption: "(Yeniden fiyatlandırmaya kalan süreler itibarıyla)" — literally "by remaining repricing period" — sits in a header row's LABEL, and the family text was built from header CELLS only, so the loose `5 YIL` needle in the heading claimed the block for liquidity_gap first. Header labels count now, and the caption words lead the strict repricing pattern: instances 1,507 → **1,606**, anchor 96.5% → **97.1%**  **And the column borrow only looked backwards, 2026-08-22**: a block whose own header is unreadable takes the columns of the nearest block of the same family, but only from EARLIER ones — so the block that got dropped was always the FIRST of a family, which is the current-period one. ODEA prints its current repricing table on page 58 with the labels shredded to `["gerektiği nazım hesap", "zaman önlem kalemlerinin", …]` and the prior on page 59 with a readable header, so both 2022Q3 and 2022Q4 reported the prior 55,466,005 against 68,996,849 and 63,745,557. The borrow now reaches in either direction, nearest first. Repricing indictments **14 → 0** — the bucket is empty |
| *(report)* graduated lanes | `scripts/report_graduated_lanes.py` — coverage across all wide lanes | **run 2026-08-21: 26 lanes, 1,420,775 rows** | Coverage of the 1,095 filings: Section-4 matrices 97.7%, risk group 90.7%, RWA 83.2%, TL/FC notes 79.9%, capital 79.7%, two-period notes 65.3%, deposits by maturity 61.3% (23 of 38 banks — the participation banks' "funds collected" rows and 133 unreadable headers are the gap), … sector 23.0%, stage movement 9.4% (the row-wise shape is rare). The Pillar 3 lanes (CR1/2/4/5, NSFR) cover 9–10 periods by the document's own cadence. Per-bank matrix in `docs/knowledge/2026-08-21-graduated-lanes-readiness.md` (internal) |
| *(audit)* narrow vs wide | `scripts/audit_narrow_vs_wide.py` — the graduated lanes turned on the narrow ones | **run 2026-08-21 (second pass, after the inline re-mint): 1,764 narrow rows indicted** | `bank_audit_loans_by_sector` 1,563 cells (the wide stage/ECL table passes the sector hierarchy, the narrow lane has no identity), `bank_audit_liquidity.lcr_total` 31, `.nsfr` 6, `bank_audit_capital` 15, `bank_audit_repricing` 18 buckets, `bank_audit_npl_movement` 6 cells across all ten movement columns plus 8 closing sums (EMLAK, a perimeter gap), `bank_audit_fx_position` 0; and the narrow statement lines behind the breakdown notes — interest on securities 53, interest from banks 36, securities issued 14, interest on borrowings 11, interest on loans 2, cash & CBRT 1 (a gated note total that meets no narrow line; filings with no narrow line at all are a gap, not counted). Full list in `docs/knowledge/2026-08-21-narrow-vs-wide-repair-list.md` (internal). Repairing the narrow rows — or serving the wide figure where the two disagree — is the open follow-up |
| `bank_audit_sector_full` | Minted from the DOCUMENT layer by `scripts/build_sector_full.py` — the seventeenth graduated lane, five families on one sector template | **built 2026-08-22: 291 filings / 34 banks / 149,409 rows, local `data/bank_audit_tables.db`, not D1** | Sector × column, LONG: `stage_ecl` 221 instances, `loans_currency` 194, `risk_profile` 134 (17 exposure classes + TL/FC/total), `two_period` 43, `npl_provisions` 34. Mint gate: agriculture / industry / services = Σ their items and total = Σ groups. Sector on 97.1% of value-bearing rows. Cross-lane: the gated `stage_ecl` cells equal the narrow `bank_audit_loans_by_sector` on 80.6% of 6,222 cells (78.1% of filings at ≥90%) — the narrow lane has no identity of its own, so the disagreements are its repair list. Unread: the risk profile whose column labels are all "Alacaklar" and whose numeric header row the capture dropped (the CR1-by-sector and 8-column variants too) **Re-minted 2026-08-21: 643 instances / 108,271 rows, refusals 223 → 206; narrow agreement 75.4% of 6,753 cells.** **Updated 2026-08-21: numbered row labels ("1.1 Çiftçilik") stripped and the 20-column risk profile read by the regulator's position when its labels are all "Alacaklar" — risk_profile 143 → 205 instances, 705 instances / 133,884 rows. Coverage stays at ~350 filings: the sector template is Pillar 3 semi-annual content, bounded by the document.** **Widened 2026-08-22: 253 → 291 filings** (loans_currency 169 → 223) — QNBFB and VAKBN print TL / (%) / FC / (%) twice with a dead column between the pairs, live in a fifth of the rows because the capture parks stray cells there; the column model now retries on a half-of-the-rows reading when the quarter reading matches no family shape. Of the 346 partitions that print a sector table at all, 291 are minted  **Fixed 2026-08-22**: a block that prints the sector list twice holds the current table and then last year's (AKTIF page 53). Stored as one instance both copies were labelled 'current', and a blank current cell fell through to the prior copy's figure; the list is now split where it starts over and the second copy is `prior`. The narrow-lane comparison in `audit_narrow_vs_wide.py` was itself wrong in the same place — it kept the LAST row for a sector where the note prints the loan table and the non-cash one together — and reported 1,686 disagreements that were mostly its own; 1,686 → 472, and the whole repair list halves from 2,251 to 1,037  **Then 2026-08-22**: ING prints the sector note in the same block as the risk-weight table above it, so the note's rows were read with that table's columns and the lane fell through to the next page's copy — which is the NON-CASH table, disagreeing with the narrow lane on every cell (agri_farming 11,231 against the narrow lane's 6,345, both internally consistent because they are different tables). The grid is now cut to the sector list where another table sits above it — three or more figure-bearing rows naming no sector — and ING reads page 47 like the narrow lane. Indictments 472 → 357, rows 145,204 → 146,979  **And 2026-08-22**: two more ways a table was filed as the stage/ECL note when it is not — TFKB's non-performing note prints receivables / provisions / write-offs, three columns, so it fell through to the stage branch (the NPL family now reads three as well as two and four), and ICBCT prints last year's copy first, which position alone called current (an instance is now labelled from the date it prints above itself). Sector indictments 1,686 → **43** across the session, and the whole repair list 2,251 → 608. The 43 that remain are VAKBN's cash-loan sector breakdown, which has no stage vocabulary at all to tell it apart — dropping the bare three-column fallback to catch it took the count to 316, because it also dropped the genuine stage tables whose header words the capture lost  **The last 43 close, 2026-08-22**: VAKBN's "Kredi alacaklarının sektörel kırılımı / Sektörlere Göre Kırılım Nakdi Krediler" is three columns wide and names no stage at all, so the bare three-column fallback claimed it and 17,521,436 of cash loans was stored where the narrow lane keeps 1,234,307 of stage-2. The fallback — and only the fallback — is now refused where the block's own title lines say cash loans: a block that NAMES a stage is still read however it is worded, which is what the earlier attempt (require stage words, indictments → 316) got wrong. Those title lines are read off the RAW grid, because `absorb_inline` merges them into the row below and the sector cut then drops what is left. Indictments **43 → 3** (one ZIRAAT sector line, ~3% apart), rows 146,979 → 146,916 |
| `bank_audit_tl_fc_note_full` | Minted from the DOCUMENT layer by `scripts/build_tl_fc_note_full.py` — the eighteenth graduated lane, nine P&L / BS breakdown notes | **built 2026-08-22: 983 filings / 38 banks / 16,683 rows, local `data/bank_audit_tables.db`, not D1** | Items × (TL, FC) × (current, prior): cash & CBRT 688 instances, funds borrowed by maturity 426 and by source 370, interest on loans 274, interest from banks 237, interest on borrowings 183, securities issued 144, subordinated debt 95, interest on securities 68. Gate: total = Σ rows and head = Σ children. Cross-lane, current TL+FC of the total vs the narrow statement line: loans 100%, funds borrowed 100%, cash & CBRT 99.7%, securities 98.3%, borrowings 93.4%, funds by maturity 92.9%, securities issued 89.5%, from banks 83.7% (the narrow P&L sometimes lacks the line), subordinated 68.2%. Three families were tried and dropped because their totals met no statement line (BS banks note, FVTPL by type, hedging by type) **Re-minted 2026-08-21: 2,587 instances / 11,342 rows; interest on securities grew 68 → 162 instances at a 65% anchor — the unmatched ones are the right note (SKBNK 2024Q4: note 3,876,702 vs a narrow row of 573,064; TSKB has no narrow row), a narrow-lane gap for the repair list.** **+ CBRT accounts (unrestricted demand / time, restricted time, reserve requirement): 403 instances, 323 of 323 equal to the cash note's CBRT row — the first wide-vs-wide anchor inside one lane; 2,990 instances / 13,148 rows.** **Widened 2026-08-22: 875 → 983 filings** — the capture prints the note's date line above the first row, as a row of its own ("31 Mart 2022 | 31 | 2022", HSBC) or glued onto the first label ("30 Haziran 2023 Kasa/Efektif", ZIRAATK, where the row is the Kasa row and only the prefix is noise); since the first role decides the family, both readings dropped whole families. cash_and_cbrt 689 → 799 filings, funds_borrowed 370 → 520, interest_on_loans 274 → 383. The family's confirming word ("faiz", "kredi") is often only in the contents item the block sits under, never in the heading the capture kept ("Cari Dönem Önceki Dönem"), so the context test reads the item title too  **Audited 2026-08-22**: the statement-line checks indicted 156 rows and almost all of it was the check's own reading of the P&L. Interest from banks (63): the note's first row is interest from the CENTRAL BANK, which the P&L reports as interest on reserve requirements — ICBCT's 6,179 + 2,478 is exactly the note's 8,657, so the two lanes agreed all along; 63 → 2. Interest on securities (53): the regex matched "interest on securities ISSUED", an expense line, and missed SKBNK's "interest received from marketable securities portfolio" — which the note's total matches to the lira; 53 → 3. Interest on borrowings: TAKAS's note covers money-market borrowings the P&L keeps separately; 11 → 5. One real lane defect fell out: AKTIF prints a second note under the securities table in the same block and its total was stored as the securities total, so each note is now cut at its own total  **An asset note filed as a liability, 2026-08-22**: ZIRAAT's "Teminata Verilen/Bloke İtfa Edilmiş Maliyeti Üzerinden Değerlenen Finansal Varlıklar" lists "Bono / Tahvil ve Benzeri Menkul Değerler / Diğer / Toplam" — the issued-securities note's rows word for word — and "MENKUL" among those labels confirmed the family, so both its consolidated and its unconsolidated filing carried the same 220,122,149. A liability family is now refused from a block whose heading names a PLEDGED note; only the collateral wording is used, because widening it to the asset-notes contents item also cost ten funds-borrowed instances that agreed with the narrow lane (the two halves were measured apart). And where several blocks carry one family's rows, the one whose OWN heading names it becomes instance 0 — BURGAN prints three, and only the titled "d. İhraç edilen menkul kıymetlere ait bilgiler" totals the balance sheet's figure. `securities_issued` 75.0% → **81.6%** against the narrow line with every agreeing instance kept, and its indictments 29 → 11; every other family anchor is unchanged. The 11 that remain are BURGAN, whose narrow zero is **correct** — no block in those filings has a heading naming issued securities, and the two the lane reads sit on page 122 between the NPL tables and the securities-portfolio tables, in the asset notes, with their headings lost by the capture |
| `bank_audit_npl_movement_full` | Minted from the DOCUMENT layer by `scripts/build_npl_movement_full.py` — the nineteenth graduated lane, the wide form of the narrow `bank_audit_npl_movement` | **rebuilt 2026-08-22: 949 filings / 33 banks / 1,338 instances / 59,430 rows (109 instances refused), local `data/bank_audit_tables.db`, not D1** | NPL movement by group (III / IV / V) × the full row template incl. the sold-portfolio split, current (913) and prior (425). Gate per group: net = closing − provision and the movement identity, which also **decides which sign convention the page prints in** — the outflows as magnitudes with the direction in the "(-)" label (1,131 instances), or already negative (187). A signed page is then **normalised to the labelled convention** and re-gated, so `collections` means one thing across the lane; `sign_convention` keeps what the filing itself did. Reads ISCTR's 51-row layout (every movement split by loan type, the closing in the next block; sub-rows take the movement above them as `additions_corporate` etc.), GARAN's "Balances at End of Prior Period" / "Debt Sale" wording with the "Other (****)" residual under the sale row, HALKB's stacked prior instance, ALBRK's "Closing balance of prior period" / "Transfers to standard loans and write off" (`to_performing`), and ALNTF / ODEA's date-labelled opening and closing rows. Cross-lane: **12,885 of 12,888 opening / closing / provision / net cells equal the narrow lane (100.0%), 1,236 of 1,237 instances fully**. Roles on 96.7% of value-bearing rows  **Signs normalised 2026-08-22**: nine banks — ALNTF, EXIM, GARAN, HAYATK, ING, KLNMA, PASHA, TFKB, TSKB, two of them switching between filings — print the roll-forward's outflows already negative, and storing each as printed left `collections` meaning opposite things in neighbouring rows. The transform is negation, not magnitude: ING 2025Q3 prints a positive write-off among negative ones and 791,015 + 46,222 + 186,523 − 113,920 + 23,102 − 178,413 is its closing balance to the lira, so the reversal survives — it is the only signed cell left in the lane. Coverage, refusals and the narrow-lane anchor are all unchanged; the repair list drops 489 → **291**, with 468 rows moved to a `sign_only` bucket the report no longer counts as a repair |
| `bank_audit_stage_movement_full` | Minted from the DOCUMENT layer by `scripts/build_stage_movement_full.py` — the twentieth graduated lane | **built 2026-08-22: 150 filings / 21 banks / 12,628 rows (10 instances refused; 20 blocks with no readable stage header), local `data/bank_audit_tables.db`, not D1** | TFRS 9 movement by stage: ECL 427 instances, gross loans 60; two identities (row sums across stages where a total column is printed; closing = opening + Σ movements, 447 signed / 40 with "(-)" deduction labels subtracted as printed). `measure` from the header row above the opening, else from the figures (a gross-loan table carries most of its closing in stage 1). Reads VAKBN's three stages with no total column, ISCTR's current and prior side by side (six stage columns, the stage digit of "Transfer to Stage N" in the first cell), DENIZ's movement printed under a balance table with a "Transferler" head that is its sub-rows' subtotal, the stacked 20-row ZIRAAT / VAKBN blocks, and YKBNK's "Begining of the period". The table is an annual disclosure: 251 Q4 filings exist and GARAN / HALKB / QNBFB / TEB / KUVEYT and most of the rest print no stage roll-forward at all — the remaining gap is the filings, not the reader. ZIRAATK 2022Q4's stage 3 is 7,898 short of its own arithmetic — refused, not repaired. Capture lessons: the "1." of "1. Aşamaya Transfer" and the year of "Dönem Başı (31 Aralık 2023)" land in phantom columns (`band_matrix` drops sparse tiny-integer and year-only columns), and labels read "Aşama Aşama Aşama" with the numbers on the line above  **Audited 2026-08-22**: the new `bank_audit_stages` cross-check indicted 19 rows and the wide side was wrong — a small-portfolio ECL roll-forward was read as the loan one (GARAN 905,454 against the narrow lane's 880,845,339). Two guards: a table with figures in a single stage is not the form (the regulator's has three), and `measure` reads whichever roll-forward row the capture kept whole rather than always the closing. Instances now carry `subject` — 'loans' where the heading says so — and the audit compares only those: **0 rows indicted across the 21 loan instances that meet the narrow lane** | |
| `bank_audit_two_period_note_full` | Minted from the DOCUMENT layer by `scripts/build_two_period_note_full.py` — the twenty-first graduated lane | **built 2026-08-22: 806 filings / 31 banks / 22,704 rows, local `data/bank_audit_tables.db`, not D1** | Letters of guarantee by type (443 instances), non-cash loans by type (440), trading income (175 — gains and losses heads over capital-market / derivative / FX children, net = gains − losses, a blank head standing for its children, memo rows after the total ignored; the net equals the P&L "Ticari Kâr/Zarar (Net)" on 100% of 152 filings), other operating expenses (524 — the cost structure: personnel, termination reserve, social-aid fund, impairments and depreciation by asset class, the other-operating head with lease / maintenance / advertising / other children, loss on sale of assets), current + prior. Gate: total = Σ top-level rows and head = Σ children. Cross-lane: the letters-of-guarantee total equals the narrow off-balance "Teminat Mektupları" on 100% of 404 filings; the expenses total equals the P&L other-operating line, or that line plus the personnel line where the note still carries personnel, on 49.5% (the rest differ by small reclassifications, e.g. EMLAK 2024Q4 by 55,605); the non-cash total meets the off-balance guarantees head on 43.8% — both rest on their own totals. Roles on 93.3% of value-bearing rows (social-security premium sub-rows and right-of-use depreciation unregistered) **Re-minted 2026-08-21: 1,598 instances / 15,653 rows.** **+ taxes payable (corporate, securities / property income, BSMV, FX transaction, VAT, other): 579 instances under their own total, no statement line carries it; 2,177 instances / 20,297 rows.** **Widened 2026-08-22: 715 → 806 filings** — the note's date line above the first row (a row of its own, or glued onto the first label) is stripped by the shared `numbered_template.strip_date_lines`, which the family test needs because the first row's role picks the family: taxes_payable 579 → 654, other_operating_expenses 495 → 583, letters_of_guarantee 443 → 485, non_cash_loans 440 → 485, trading_income 175 → 234 |
| `bank_audit_movement_note_full` | Minted from the DOCUMENT layer by `scripts/build_movement_note_full.py` — the twenty-second graduated lane | **built 2026-08-22: 845 filings / 33 banks / 13,616 rows (98 instances refused), local `data/bank_audit_tables.db`, not D1** | Securities movement 621 instances and investment movement 625, current + prior, each gated by closing = opening + Σ movements under the printed sign convention (1,079 signed / 167 with "(-)" labels) — the "movements during the period" subtotal head cost 555 refusals until it was read as a head. `subject` by the closing against the narrow balance sheet: amortised cost 267, FVOCI 2 (the note and the BS line differ in perimeter at most banks), associates 123, subsidiaries 173, unknown 681 with headings kept. Roles on 91.8% of value-bearing rows **Widened 2026-08-22: 660 → 845 filings, 26 → 33 banks** — the same date line above the first row, stripped by `numbered_template.strip_date_lines`: securities_movement 729 and investment_movement 807 instances |
| `bank_audit_eps_full` | Minted from the DOCUMENT layer by `scripts/build_eps_full.py` — the twenty-third graduated lane | **built 2026-08-22: 363 filings / 18 banks / 363 rows (5 instances refused), local `data/bank_audit_tables.db`, not D1** | Net profit, weighted shares, EPS (current + prior) gated by the note's own division (290 with shares in thousands, 47 in units, 14 the other way); the net profit equals the narrow P&L net profit / group share on 92.6% of 296 filings — HALKB 2024Q4–2025Q2 prints an EPS profit 5% below its P&L group share (a perimeter the note explains), ICBCT 2023Q2 differs by 7,000. Only ~360 filings print the note as a table; the rest carry EPS inside the P&L statement **Widened 2026-08-22: 351 → 363 filings** — the four-column blocks where the cumulative and quarterly figures print side by side (HALKB, EMLAK: the cumulative pair is the outer one), two more nominal scales (per 100), and the printed EPS repaired where the capture lost its decimal comma (BURGAN's "1,640" for 1.640 TL per 1,000 nominal) — only for a bare integer, and only when the repair is what makes profit / shares come out. Of the fleet's other filings only 22 print an EPS note at all: the lane is near its ceiling |
| `bank_audit_shareholder_loans_full` | Minted from the DOCUMENT layer by `scripts/build_shareholder_loans_full.py` — the twenty-fourth graduated lane | **built 2026-08-22: 810 filings / 35 banks / 5,036 rows (22 instances refused), local `data/bank_audit_tables.db`, not D1** | Loans to shareholders (direct: legal / real persons; indirect) and to employees, total, × (cash, non-cash) × (current, prior), across 36 banks. Gate: the template's two identities on every printed column. Roles on 95.7% of value-bearing rows (the rest are date rows). **Widened 2026-08-22: 651 → 778 filings** — the cash / non-cash pair that names the columns is often an inline header row `absorb_inline` drops, so the context is now read from the raw grid; ZIRAATK wraps every label onto a "Krediler" row that carries the values (the role row adopts them); a value-bearing row wins its role over a valueless one, so BURGAN's note sentence — which mentions employees — no longer takes that role from the row with the money  **Then 778 → 810 filings**: EMLAK's capture copies the employees row's figures onto the indirect row above it and the sum double-counts, so a consecutive pair carrying the same tuple may be dropped — but only the one whose removal makes the printed total come out, and only after the plain sum has failed. Refusals 54 → 22 |
| `bank_audit_npl_by_borrower_full` | Minted from the DOCUMENT layer by `scripts/build_npl_by_borrower_full.py` — the twenty-fifth graduated lane | **built 2026-08-21: 765 filings / 27 banks / 43,491 rows, local `data/bank_audit_tables.db`, not D1** | NPL by borrower class × gross / provision / net × group, current and prior. Gate: net = gross − provision per cell. Cross-lane: Σ gross per group equals the narrow NPL movement's closing balance in all three groups on 94.4% of 733 filings. 99.2% of value-bearing rows classified (the rest a "Net Değer" variant). The NPL movement table's own "Önceki Dönem Sonu Bakiyesi" first masqueraded as a period head — excluded by wording. **Widened 2026-08-21: 559 → 765 filings, 22 → 27 banks** — TEB's prior head is an inline (valueless) line the document layer flags, now kept as a row (`absorb_inline(keep=…)`); AKTIF heads its periods with dates whose digits land in a lead column (the second date is the prior); YKBNK's empty lead column and "Loans granted to real persons and corporate entities". ING / TSKB / ALNTF print no such table in a captured block |
| `bank_audit_risk_group_full` | Minted from the DOCUMENT layer by `scripts/build_risk_group_full.py` — the twenty-sixth graduated lane | **built 2026-08-21: 1,006 filings / 3,055 blocks / 63,525 rows (70 blocks refused), local `data/bank_audit_tables.db`, not D1** | Related-party exposures by party class × cash / non-cash: loans 1,726 blocks, deposits 839, derivatives 490, opening / closing / period income, current and prior. The only arithmetic the table offers is across blocks — the prior closing must equal the current opening — and it holds on 1,708 paired blocks; 1,347 single-period blocks are kept as unpaired. The party columns follow the regulator's fixed order (the captured column labels are too fragmented to read) |
| `bank_audit_extractions` | extraction log | one row per PDF | **1,117 rows / 38 banks / 18 periods, all success=1** (live D1, 2026-08-28). 2026Q2 is the live edge at **66 partitions across all 38 banks** — the season closed 08-28 when HSBC's two halves and Colendi's solo report landed — and each of the 62 partitions held through 2026-08-17 carries `source_unit='milyon'`. The per-lane pass/fail tables below are a dated **2026-06-14** snapshot taken when the fleet was 31 banks / ~975 partitions — read their counts as of that date, not as today's totals |
| `bank_types`, `table_definitions`, `download_log` | metadata | — | — |
| `banks` (+ alias views `v_bist_prices` / `v_news_items` / `v_bank_earnings`) | dimension (migration 0021; +0022 new entrants; +0024 Takasbank), seeded from `bddk_bank_list.json` + `bank_names.ts` | 38-bank audited universe | canonical per-bank identity + single join key across lanes (`ticker` == `bank_ticker` == `symbol`); the views alias each lane's id column to `bank_ticker`. Powers cross-lane joins + the text-to-SQL bot. **One bank is carried but peer-excluded** — `TAKAS` (Takasbank), see below |

**Quarterly audit reports**: **38 banks** in URL config; **1,050 PDFs extracted into D1,
1,050 core-success (100%)**, and **every bank is current at 2026Q1** (zero banks behind).
The 6 new-entrant digital / participation banks (Enpara, Colendi, Ziraat Dinamik + Dünya /
Hayat Finans / T.O.M. Katılım) were onboarded 2026-07-11, and **Takasbank (`TAKAS`)
2026-07-12**. Feasibility + per-bank sourcing:
[knowledge/new-banks-coverage-gap-2026-07-11.md](knowledge/new-banks-coverage-gap-2026-07-11.md).
PDFs themselves live in R2 at
`bddk-audit-reports/<ticker>/<TICKER>_<period>_<kind>.pdf`.

**The 2026Q2 season opened 2026-07-24** — KLNMA filed first, on KAP. TEB was the
first PDF we *held* (`acquire-audit.yml`, 2026-07-26), which is a different fact:
acquisition reads IR pages, and a bank files on KAP days before its own site
catches up. As of **2026-08-01** seven banks have released 2026Q2 reports —
KLNMA (07-24), TEB (07-26), AKBNK (07-28), TSKB (07-29), GARAN (07-30),
YKBNK (07-31) and ENPARA. The other 30 are still at 2026Q1.

**2026Q2 stands at 62 partitions / 36 banks (2026-08-17)** — 59 / 34 the day
before, 42 / 24 the day before that, and 23 / 13 the day before that. Eleven banks were added in one pass — ATBANK, BURGAN, EMLAK, ODEA,
SKBNK, TAKAS, ZIRAATD, ZIRAATK, DENIZ, ALNTF, VAKBN — and **most had been
sitting on published filings for weeks**: DENIZ filed 07-24 and ALNTF 08-04.

**That backlog is structural, not an oversight.** `DISCOVERY_BANKS` holds 13
banks; for the other 25 a published filing is invisible until its URL is added
by hand, and nothing reports that it is missing. Expect to repeat this every
quarter until discovery covers more of the fleet. Three of the eleven could not
have been reached by substituting the date into the bank's own 2026Q1 URL:
SKBNK appended `-062026`, EMLAK renamed the document
`_sinirli-denetim-raporu_`, and ODEA's CMS serves an opaque
`document-file-1648.vsf`. Naming is per-filing, not per-bank. **EMLAK is in
`DISCOVERY_BANKS` and still needed the hand-add**, because its skeleton changed
and discovery therefore matched nothing; the new entry repairs it.

Sourcing quirks found in the same pass are in
[AUDIT_BANK_CATALOG.md](AUDIT_BANK_CATALOG.md): **VAKBN and ZIRAATK refuse the
GitHub runner** (WAF page in under a second; the same URLs with the same headers
return the real 2.8 MB documents from a Turkish address — a Referer makes VAKBN
strictly worse, so 2026Q2 was hand-acquired into R2 and the durable route is
BdrUyg, institutions `015` and `209`), and **DENIZ and ALNTF keep their document
list one level below the configured `ir_page`, rendered in JS** — invisible to
any HTTP probe, plain in a browser.

**⚠️ "The other 13 have not filed" was wrong — twelve of them had (2026-08-16).**
The line this replaces named AKTIF, COLENDI, DUNYAK, EXIM, HAYATK, HSBC, ICBCT,
ISCTR, KUVEYT, QNBFB, TFKB, TOMK and VAKIFK as unfiled on 2026-08-13. Queried
against KAP directly, **35 of 38 banks had filed 2026Q2** — İş Bankası ten days
before that sentence was written, on 08-03. Only COLENDI has no filing on any
source, and ATBANK/TAKAS are not KAP members (both already acquired from their
own sites). The claim was never checked because nothing could check it: see
*the acquisition gap* below.

**Where 2026Q2 actually stands (2026-08-16).** Filing date is KAP's; "held"
means a successful extraction.

| State | Banks |
|---|---|
| Filed and held | 24 — AKBNK, ALBRK, ALNTF, ANADOLU (unconsolidated only), ATBANK, BURGAN, DENIZ, EMLAK, ENPARA, FIBA, GARAN, HALKB, ING, KLNMA, ODEA, PASHA, SKBNK, TAKAS, TEB, VAKBN, YKBNK, ZIRAAT, ZIRAATD, ZIRAATK |
| Filed, acquired 08-16 | 10 — AKTIF, DUNYAK, HAYATK, ICBCT, ISCTR, KUVEYT, QNBFB, TFKB, TSKB, VAKIFK. **17 partitions over three runs**: 13 first (`new=12 extracted=13 failed=0`; VAKIFK was already in R2 from the off-runner fetch, so the runner never touched its host), then ISCTR's two once the ZIPs were found, then TSKB's two as `[REPL]` over the cover sheets. Consolidated halves of AKTIF/KUVEYT/VAKIFK are not published yet, deadline ~13 Sep |
| Filed, acquired 08-17 **from BdrUyg** | 3 — EXIM (KAP 08-06), TOMK (08-13) and KUVEYT's consolidated half (08-13). None is on the bank's own site — EXIM's list still ends at `brsa-20260331`, TOMK's at `31032026.pdf`, Kuveyt Türk shows only its solo — and all three were in the registry: `BDREki-016-SOLO`, `-213-SOLO`, `-205-KONSOLIDE`, all `2026-06`. `new=3 extracted=3 failed=0` |
| Filed, **nowhere to fetch** | 1 — HSBC (KAP 08-13). Absent from its IR page *and* from BdrUyg, with a working `BDREki-123-SOLO-2026-03` control proving the code and the registry's silence |
| No filing on any source | 1 — COLENDI |

**⚠️ ISCTR was in that last row for one hour, wrongly.** Its English IR page — the one the config names — offers only an Excel for 2026Q2, and reading it produced a confident "has not published". The reports were on the **Turkish** page all along, as ZIPs, under a second tab behind a search form that lists nothing until it is submitted. Acquired 2026-08-16 (127pp consolidated, 105pp unconsolidated, both bases confirmed from the documents). The lesson is in [AUDIT_BANK_CATALOG.md](AUDIT_BANK_CATALOG.md): **an English IR page can be a subset of the Turkish one**, and "not on the site" means both sites, every tab.

**✅ 2026Q2 closed 2026-08-28 — 38 / 38 banks, 66 partitions.** HSBC's two
halves were on its IR table as plain `document-file-8368` / `8367` hrefs dated
`30.06.2026`, and BdrUyg received them too; Colendi's Turkish solo BDR sat on
wp-content but ConnectTimeouts from the runner, so 2026Q2 is bound to
`BDREki-158-SOLO-2026-06.zip` — both rows in
[AUDIT_BANK_CATALOG.md](AUDIT_BANK_CATALOG.md). Both banks are outside
`DISCOVERY_BANKS` with static configs that stopped at 2026Q1, which is why
`filing_gap_problem` could alert daily on HSBC from 08-23 with no fetch path
behind the alert. **VAKIFK**'s consolidated half arrived 08-20 in the scheduled
run. Still outstanding: the consolidated halves of **AKTIF** and **ANADOLU** —
each absent from BdrUyg too, each with a working 2026-03 control, so the
registry genuinely has not received them.

**⚠️ Reach for BdrUyg before concluding a bank has not published.** EXIM sat
in the registry from 08-06 and was found on 08-17, only because the gap
alert kept naming it; watching its IR page would never have found it. The
registry is complete, deterministic
(`BDREki-<eftcode>-SOLO|KONSOLIDE-<YYYY>-<MM>.zip`) and reachable from the
runner. **Probe it with a prior-quarter control**: a 404 on the target
month against a working control means the registry lacks the period; a 404
on both means the institution code is wrong. That distinction is not
cosmetic — T.O.M. Katılım is `213`, and `214` answers with a
Java-serialised error object that reads exactly like 'not filed'. Codes
confirmed off each PDF's own cover page: 016 EXIM, 123 HSBC, 132 TAKAS,
135 ANADOLU, 143 AKTIF, 205 KUVEYT, 206 TFKB, 210 VAKIFK, 211 EMLAK,
212 HAYATK, 213 TOMK.

**✅ Fleet-wide display audit, 2026-08-17 — the pages agree with D1.** All 38
bank pages fetched from production and checked against the *same* query
`bankSummaries()` runs, so a difference would be a display fault rather than a
difference of definition. Result: 38/38 load, 38/38 print the right "Data
through" period, **37/38 total assets and 37/38 CAR match D1 exactly**, and the
one bank whose CAR is NULL in D1 (HAYATK) omits the tile rather than printing
`0` — the `null` is not `0` rule holding where it matters. A separate
unit check found **no 1000× errors**: every bank's 2026Q2/2026Q1 total-assets
ratio sits between 0.92 and 1.21, and every 2026Q2 figure ends in `000`, as a
milyon→bin conversion should.

Two things the audit turned up, neither a data fault:

- **`/banks/TAKAS` shows none of its own figures.** D1 holds CAR 21.7% and
  assets ₺457bn; the page prints neither, because the vitals read from the
  heatmap map and `heatmap.ts` hands a peer-excluded ticker a throwaway row.
  The page says so in words and points at Financials, so nothing is invented —
  but the comment in `audit-ratios.ts` promising "its own figure stays on
  `/banks/TAKAS`" was false and is now corrected there. Whether a peer-excluded
  bank should see its own numbers is a **product decision**: it means admitting
  its row to the map and excluding it at each ranking site instead of at the
  source, which is the more fragile design.
- **Small banks round hard.** The vitals formatter renders sub-trillion assets
  as `toFixed(0)` billions, so COLENDI's ₺4.76bn prints as "5 ₺bn" and
  ZIRAATD's ₺5.39bn as "5 ₺bn" — up to 5% overstated for the smallest banks,
  exact for everyone above ₺100bn. Cosmetic, and worth a decimal place at the
  bottom of the fleet.

**⚠️ The acquisition gap: nothing could report a filing we never fetched
(fixed 2026-08-16).** Thirteen banks published 2026Q2 and the lane held none of
them, while every daily run reported `new=0 changed=False` and exited green —
which is also exactly what a quarter nobody filed looks like. Four independent
causes, each fixed:

1. **Discovery covers 13 of 38 banks**, so for the other 25 a published filing
   is invisible until a URL is hand-added. Nine of the thirteen sat there.
   *Unfixed by design* — widening `DISCOVERY_BANKS` needs per-bank validation —
   but no longer silent, see (4).
2. **Three of the thirteen were inside `DISCOVERY_BANKS` and failed anyway.**
   VAKIFK's host answers a Turkish address and times out from the GitHub runner
   (`ConnectTimeout`, in every run log since 08-05); TFKB returned 2 links
   against 34–36 for a healthy bank, its skeleton having drifted; EXIM's Q2 is
   not on its IR page at all. `discover_targets` catches everything and returns
   `[]`, so *blocked* and *not published* were the same observation.
3. **A real filing was refused as a KAP cover sheet.** `_KAP_COVER_RX` was
   tested before the page floor over a 16-page window, and "Kamuyu Aydınlatma
   Platformu" is an ordinary Turkish sentence — ICBCT's 91-page filings say it
   on page 8, recounting a 2015 share transfer. Both halves were rejected with
   the basis read correctly off the front matter. The fingerprint is now
   consulted **only below `_MIN_REPORT_PAGES`**, where it distinguishes two
   short documents; above it the page floor and the marker check already decide.
   TSKB's genuine 14-page cover sheet is still refused, twice over.
4. **No check could express "a bank filed and we don't hold it".** The systemic
   alarm's denominator is targets we *attempted*, and a bank with no URL is
   never attempted; `healthcheck` measured staleness of data we have. The
   evidence was already in the database — `bank_earnings` carries a KAP
   `results_filing` per (bank, period) — and nothing compared the two.
   `healthcheck.filing_gap_problem` now does, with a 4-day grace because KAP
   legitimately precedes a bank's own IR page (TEB filed 07-23, PDF 07-26).
   Discovery failures surface as a job warning rather than a Telegram ping: a
   geo-blocked host fails every single run, and a daily alert that is always the
   same bank gets muted.

Verified on the run that landed the quarter (`31931916417`, 2026-08-16):
`[discover] 2 bank(s) fell back to static config after a failed discovery: TSKB,
VAKIFK` — the sentence that did not exist before — then `new=12 extracted=13
failed=0`, TSKB still `[PEND] not-a-report:kap-cover-sheet:14pp` (the fingerprint
still identifies the real one), and 28,942 rows to D1. `filing_gap_problem`
against live D1 now returns **TSKB (18d), ISCTR (13d), EXIM (10d)** and stays
silent on HSBC and TOMK, which filed three days ago and are inside the grace
window. That is the whole remaining gap, named.

**The KAP lane could only see 12 of 38 banks (fixed 2026-08-16).** It matched a
disclosure to a bank on `stockCodes`, which KAP leaves empty for a member with
no listed shares — so every unlisted bank's filing was dropped before anything
looked at it. A second pass now matches the member's own title, for financial
reports only, and the lane sees **35 of 38**. Two supporting facts found on the
way: `byCriteria` caps a response at **2000 rows** with no flag or continuation
token (2026-07-20→08-16 returned exactly 2000 against 8,379 counted a day at a
time), so `fetch` now pages in 3-day slices; and `wrangler d1 execute --command`
does not survive an embedded newline, which is why `query_d1_rows` flattens.

**⚠️ ANADOLU 2026Q2 unconsolidated was stored 1000× small and was live for
days (fixed 2026-08-13).** Total assets read **₺0.2bn against ₺212.6bn** the
quarter before. Every in-filing identity passed, because a uniform change of
denomination scales both sides of each one. Three separate defects had to line
up, and each is worth knowing on its own:

1. **The unit detector believed whichever declaration came first.** A filing
   that switched to Milyon usually leaves stale boilerplate behind, and *which*
   text is stale differs by bank. Measured over all 44 2026Q2 filings in R2,
   **12 contradict themselves inside the front 22 pages**: ANADOLU's auditor
   letter (p4) is stale at `bin` against 17 statement pages saying Milyon;
   **ATBANK consolidated is the exact mirror**, 16 stale page headers saying
   `Bin` against p4 and the change note; HALKB consolidated is bilingual with
   one stale English page. No positional or statistical rule survives all
   three — majority reads ATBANK wrong and would store a *correct* partition
   1000× too big. The tie is now broken by **authority**: the sentence stating
   the filing *changed* presentation currency wins outright (11 of the 12),
   then unanimity (32 of 44), then a strict majority (HALKB alone), then
   UNKNOWN, which `scale_factor` turns into a refusal. 44/44 correct, with
   ground truth taken from the cross-period anchor, not from any declaration.
   A latent crash went with it: `'MİLYON'.lower()` is `'mi̇lyon'` (i + combining
   dot above), not a `_NORM` key — live in the corpus (EMLAK ×14, ZIRAATK ×7,
   GARAN ×1) and never fired only because it was never the *first* match.
2. **A re-extraction could not correct it.** `upsert_report` is
   non-destructive: a lane whose rows pass validation is left alone. Its
   evidence is validation, and validation is the one thing a unit error cannot
   fail — so the guard protected the wrong figures *because* they were wrong in
   the only way it cannot see, rewrote `source_unit` to `milyon`, and left the
   partition claiming a scale its figures did not have. The guard now steps
   aside when the resolved unit differs from the one recorded for the
   partition, which makes a detector fix self-healing. (`--force` re-extracts;
   only `--force-overwrite` defeats the guard, and no workflow exposes it.)
3. **Nothing was watching.** See the watch entry below.

Repaired by `purge-partition.yml` + a targeted re-extract, since the earlier
run had already flipped `source_unit` and defeated the new trigger: **₺231.7bn,
QoQ 1.09**, inside the sector's 1.02–1.21 band. A sweep for any total-assets
ratio below 0.8 or above 1.5, both kinds, now returns nothing.

**`watch_cross_period.py` runs daily in `refresh-audit.yml`, alert-only
(2026-08-13)** — the only check in the pipeline that can see a reporting-unit
error, and until now it existed solely in a manual workflow nobody ran. **It
could not have fired as written**, for two reasons found by benching it against
the real seam rather than by reading it:

- `scale_factor` accepted a power of ten only within **±0.5%**, so it fired
  only if the bank's balance sheet had not moved *at all* between the quarters.
  ANADOLU's ratio is 0.00109, not 0.001, because the bank also grew 9%. The
  evidence was already in this document and unapplied — TEB's is recorded as
  "950.6 (not exactly 1000 because the bank also grew ~5%)", and the sweep that
  caught TEB used `> 50 or < 0.02`. Now judged on order of magnitude: within
  0.25 decades of a non-zero power of ten.
- materiality tested the **current** value only, so a row shrunk by 1000 fell
  under the floor — ₺212.6bn became 212,600 against a 1,000,000 minimum. The
  error hid itself from the check written to find it. Now material in either
  quarter.

Tightened the other way too, or it would cry wolf daily: on a corpus with no
unit error left in it the old heuristic claimed **30** reporting-unit changes,
counting **cells against rows** (its own output reads "moved 7/5", more rows
than the statement has) and accepting **×10**, which no Turkish denomination can
produce — bin, milyon and milyar differ by 1000, and 13 of the 30 were ×10 in
the four-row FX table. Now distinct rows, a unit-ratio factor, a 0.6 share.
Measured end to end: **0 findings over 15,638 seams** on the live snapshot;
replaying the real ANADOLU bug into a copy raises exactly **3**, all that
partition (`balance_sheet` ×0.001 on 69/101 rows, `credit_quality`,
`fx_position`). Silent until it is not.

**KAP is the earliest signal, and it is already wired up.** `src/news/sources/kap.py`
returns `disclosureClass: "FR"` rows carrying `year` / `ruleType` / `period`
(2026 · "6 Aylık" · 2 for this quarter), two per bank — unconsolidated and
consolidated. It covers BIST-listed banks only, so unlisted filers (TEB, ENPARA)
still surface only from their IR pages. Note the attachment endpoint
`/tr/api/file/download/<objId>` serves the PDF wrapped in a **Java-serialised byte
array** (`AC ED 00 05` magic) under an `application/pdf` header — the raw response
is not a usable PDF, so the KAP lane is a discovery signal, not a download path.

**⚠️ ~~TSKB 2026Q2 is a KAP cover sheet, not the report~~ — the COVER SHEET was
one filename, and the report was next to it all along (2026-08-01, corrected
2026-08-16).** What this entry got right: `tskb-consolidated-30062026.pdf` and
`tskb-bank-only-30062026.pdf` are **14 pages / 165 KB** against 2026Q1's
**107 pages / 2.0 MB**, page 1 reads *"Bank Financial Report … KAMUYU
AYDINLATMA PLATFORMU"*, and storing them was correctly refused. What it got
wrong is the conclusion drawn from that — *"the bank has not filed"*. TSKB filed
on **07-29**, and the real documents sit in the **same `/uploads/file/`
directory** under different stems: `tskb-solo-30062026.pdf` (87pp) and
`tskb-konsolide-30062026.pdf` (92pp), linked from the **Turkish**
`/yatirimci-iliskileri` page. The configured `ir_page` is the English one, which
links only the stubs — so both the acquire run and discovery saw the cover
sheets and nothing else. Acquired 2026-08-16; the run logged `[REPL] ×2`,
replacing the stubs through exactly the path `report_validity` was built for.
**The guard was never wrong; the diagnosis it invited was.** A document that is
not a report tells you the URL is wrong, which is not the same as telling you
the bank has not published — and nothing in the lane distinguished those until
`filing_gap_problem`, which named TSKB at 18 days overdue.

**⚠️ TEB 2026Q2 switched reporting unit — extracted, found wrong, PURGED
(2026-07-26).** The filing declares *"Tutarlar aksi belirtilmedikçe **Milyon**
Türk Lirası"*; 2026Q1 said *"**Bin** Türk Lirası"*. The extractor reads the
printed figures correctly and stores them as thousands, so the whole partition
landed **1000× too small** (TEB total assets ₺799bn @2026Q1 → ₺841m @2026Q2).

**No validator could see it, by construction.** Every BS/P&L check is an
*internal* identity — assets = liabilities, subtotal = Σchildren,
closing = opening + flows — and a uniform unit change scales both sides equally,
so all of them foot and the cells read `ok`. Only the lane with a **cross-period**
anchor went red: `fx_cross_period` compares the prior column against the
independently extracted prior year-end and caught it at ~1000× (equity_change's
`eq_oci_cross` also failed). The general rule: **no internal identity can detect a
unit change; only a cross-period or external anchor can.**

A pure-SQL sweep of the whole corpus (per bank, `LAG()` over total assets, flag
ratio > 50 or < 0.02) returns **exactly one row** — TEB 2026Q2, ratio 950.6 (not
exactly 1000 because the bank also grew ~5%). So **no historical filing was
missed**; TEB is the first, and Turkish inflation makes more likely as the season
fills in.

**⚠️ It is not TEB — it is the whole sector (2026-08-01).** All 11 held 2026Q2
filings declare `milyon Türk Lirası`; all 11 of the same banks' 2026Q1 filings
declare `bin`. TEB was the first filer, not an outlier. Local extraction of the
six banks confirms both the failure (raw figures ~950× small against their own
Q1) and the fix (×1000 puts QoQ growth at +5% to +9.8%).

**Unit detection is solved deterministically — clean on 550 sampled filings,
free, offline.** A single regex reads the declaration in both Turkish and
English. **⚠️ Scan at least 22 pages, untruncated.** The first version looked at
8 and scored 22/22 — on the 2026Q1/Q2 corpus it was written against. A random
draw across all 1,061 audit PDFs in R2 then returned `UNKNOWN` on 18/200, **15 of
them Q4**: annual reports carry a full audit opinion rather than a limited review,
so the declaration sits on p7–p17. The pattern was right; the window was fitted
to its own sample. Widened, two draws (200 and 350, 2022Q1–2026Q2, every bank)
come back clean — and confirm **no filing before 2026Q2 ever used millions**.
An LLM arm was benched against it on the same 22 filings and lost: DeepSeek
v4-flash 19/22, Nemotron-3-super free 16/22, and *not one* miss was a
comprehension failure — both models quoted the correct phrase and then fumbled
the output field. See
[knowledge/2026-08-01-llm-vs-regex-unit-detection.md](knowledge/2026-08-01-llm-vs-regex-unit-detection.md).
**The open part is applying the scale, not detecting it**: an allowlist of every
amount column across ~14 lanes that excludes the ratios, coverage fractions and
branch/personnel counts sharing those rows.

**Decision: wait for more Q2 filers before building the fix**, so unit detection
is designed against several examples rather than fitted to TEB. The partition was
purged via the new `purge-partition.yml` (snapshot + D1 + coverage re-sync), so
the cell reads `missing` + `pdf_present` and nothing published is silently wrong.
**Do not extract further 2026Q2 filings until the unit is normalised** — check the
`Bin|Milyon Türk Lirası` header first.

**Nine more 2026Q2 PDFs were acquired 2026-08-01 — deliberately unextracted.**
AKBNK, GARAN, YKBNK, KLNMA (consolidated + unconsolidated each) and ENPARA
(unconsolidated) are in R2 with static URLs in `data/banks/audit_report_urls.json`;
every one was opened with `fitz` before being committed (92–153 pages, cover page
dated 30 June 2026). They exist precisely so the unit-detection fix above can be
designed against six banks instead of one. `acquire-audit.yml` now takes a `banks`
dispatch input (`ALL` sentinel) so a run can be scoped away from a bank serving
the wrong document — which is how TSKB was skipped.

**✅ 2026Q2 IS LIVE — 11 partitions across six banks, normalised (2026-08-05).**
Run [31028845341](https://github.com/incesalim/Carthago/actions/runs/31028845341),
`refresh-audit.yml` with `skip_scrape=true` scoped to
`AKBNK,GARAN,YKBNK,KLNMA,TEB,ENPARA` (TSKB excluded by construction — its Q2
"filing" is still a KAP cover sheet). All 11 carry `source_unit='milyon'` and
`success=1`. **The scale is verified against the live rows**: TEB total assets
₺830.6bn @2026Q1 → **₺875.5bn** @2026Q2 (+5.4%), AKBNK ₺3.64tn → ₺4.01tn
(+10.1%) — against the pre-fix failure that landed TEB at ₺841m. Migration 0039
applied by the deploy that preceded it; `source_unit` confirmed present in D1.

**The run's write cost, in the three quantities that were being conflated
(2026-08-05).** An earlier note here mixed them; these are separate numbers and
only the last one is spend:

| | rows | what it is |
|---|---|---|
| logical | ~98,450 | rows the generated SQL actually inserts |
| **estimated billed** | **429,868** | `billed_estimate()` = logical × (1+indexes) × 2 if full-rebuild. Deliberately conservative; its own docstring says *"never reported as actual spend"* |
| **actual `rows_written`** | **306,647** | what D1 itself reported: 142,135 (audit push) + 164,512 (coverage spine) |

So the estimator ran **1.40× hot** and the real multiplier over logical rows was
**3.11×** — close to the ~3.6× in OPERATIONS.md. ~$0.31 at $1.00/M, billed
because the cycle allowance is spent (63.0M / 50M). The per-table figures quoted
anywhere are **estimates**, and the push printed only its top 8 tables, which is
why they never summed to the total; it now prints every table.

Of that, the Q2 data itself was ~13.7k estimated (BS 7,892 · P&L 2,768 · CF
1,419 · equity 1,113 · OCI 519). Everything else was three derived tables
rewritten wholesale on **every** run, and one full rebuild:

**✅ Fixed offline 2026-08-05 — the recurring part.** `upsert_validation`,
`upsert_pl_roles` and `build_stages` all did an unconditional DELETE+INSERT.
Each of those tables carries a stamp (`validated_at` / `derived_at` /
`extracted_at`) that defaults to `CURRENT_TIMESTAMP` and that `push_to_d1`
windows on — so rewriting an identical row is not free, it is a full re-ship.
`--skip-unchanged-partitions` could not help: the rows genuinely changed.
Measured on the real snapshot, a second NOTHING-CHANGED pass re-stamped
**19,950 validation + 9,439 pl_roles rows; after the fix, 0.** `build_stages`
also lost its `DELETE FROM bank_audit_stages` — with an incremental insert that
delete-all would have emptied the table, so the rebuild now owns row lifecycle
and removes only keys it no longer produces.

**`bank_audit_coverage` per-partition push: ACTIVE — `_COVERAGE_INCREMENTAL`
enabled 2026-08-06.** (This entry originally recorded the built-but-inactive
state; the flag flipped the next day and the tests now pin it **on**.)

| | |
|---|---|
| Migration `0040_coverage_derived_at.sql` | **APPLIED in live D1** — deploy [31045271052](https://github.com/incesalim/Carthago/actions/runs/31045271052), verified: `derived_at TIMESTAMP` present, nullable, `rows_written: 0` |
| `_COVERAGE_INCREMENTAL` | **True — enabled 2026-08-06**, pinned on by `test_coverage_incremental.py` and `test_report_validity.py` |
| `bank_audit_coverage` in `_FULL_REBUILD` | **No** — the switch discards it at import; cells are windowed on `derived_at`, removals travel via the `d1_pending_deletes` outbox |
| Why it flipped | the full rebuild had become actively harmful: the PASHA run booked 122,438 audit rows and the spine then asked 166,041 more — 161,728 of it restating unchanged coverage rows |

As a full-rebuild rollup its content hash made a no-op run free, but *any*
change re-shipped all ~20,000 rows: 161,272 estimated billed for eleven changed
partitions. Incremental, `sync_audit_expected.write_coverage()` writes only rows
whose values moved. A NULL stamp is out of window on purpose — rows written
before 0040 are already in D1, and re-shipping them once would cost exactly what
this removes.

**Removals could not have converged, and now do.** Deleting a vanished cell from
local SQLite is invisible to D1: the push carries rows by `derived_at`, a
removed cell has no row and therefore no stamp, so an upsert-only window can
never express its removal and the matrix would keep showing cells — or whole
partitions — that no longer exist. Removals are queued in the
`d1_pending_deletes` outbox as **full-primary-key** DELETEs (the same contract
the news/tefas/kap lanes use; replayed before the inserts and priced through
`outbox_delete_rows`, which refuses anything it cannot prove deletes one row).

Partition-scoped replacement is **not** the alternative: this table stamps
CELLS, so replacing a partition while re-inserting only the stamped cells would
erase every unchanged sibling in it. `bank_audit_coverage` is therefore in
`_NO_PARTITION_SKIP`, and a test asserts it is also absent from `AUDIT_TABLES`
(the `--table-set audit` push passes `--skip-unchanged-partitions`) — so nothing
can start sweeping it into partition mode.

17 offline tests, including four that execute the SQL the push would send into a
**simulated remote** and assert `remote == local` exactly: one cell removed, a
whole partition removed, a changed cell leaving its siblings intact, and a mixed
add/edit/remove sequence. Disabling the outbox turns three of them red.

**⚠️ The D1 write cost guard was REMOVED on 2026-08-12**, at the owner's
direction. Nothing refuses a push on cost any more, at any size, in any lane.
Gone: the per-push ceiling (`--max-billed-rows`, default 2.5M, exit 3), the
cycle-aware cap that tightened as the 50M allowance filled (`EXHAUSTED_CYCLE_CAP`,
250,000), the `D1_RUN_LEDGER` that made both cumulative across a run, and with
them `effective_cap`, `EXIT_BUDGET`, `tests/test_ledger_retry_semantics.py` and
`tests/test_workflow_ledger_wiring.py`. `--max-billed-rows` and `--no-cycle-check`
survive as accepted no-ops so existing workflow files keep running.

What is left is **reporting plus avoidance, no enforcement**: the per-table
estimate still prints on every push (marked advisory), the digest and
content-hash skips still stop unchanged rows being generated at all, and
`scripts/healthcheck.py` still reads cycle usage — after the fact, with no power
to stop anything. `src/d1_usage.py` outlived the guard for exactly that reason.

Two consequences to design around rather than rediscover:

- **A campaign is now cheap but no longer declared.** The digest machinery below
  makes a re-run cost what it *changed*; nothing makes anyone state what they
  are about to spend. July 2026's overage shape — three campaign days at 12.4M,
  15.1M and 9.4M against a ~14.6M/month quiet baseline — would run to completion
  today, announcing itself in the log and stopping nowhere.
- **The retry is simple again.** Booking before the write and retrying
  `EXIT_PUSH_FAILED` used to contradict each other: attempt 1 booked 203,799,
  wrangler blipped to a retryable exit 4, and attempt 2 met a cap of
  250,000 − 203,799 = 46,201 and refused *terminally* — a service-side blip
  surfacing as a permanent budget refusal. With no ledger and no cap that trap
  is gone, `audit_d1.TERMINAL_EXITS` is just `(EXIT_VALIDATION,)`, and exit 4 is
  unconditionally retryable. Still true and still unresolved by any of this: a
  lost response ("import polling failed") means D1 may have committed and billed
  the file without anyone seeing the answer.

*(prior status, for the record)* Normalisation wired and the 11 held filings
verified on a copy before any push (2026-08-05): `src/audit_reports/units.py` is the one detector (the analyst
lane imports it); `UnitContext` carries `(source_unit, factor)` and refuses to
exist inconsistently; all 12 raw monetary writers scale through it and each has a
read-back test against a real schema; `bank_audit_stages` is DERIVED and is
rebuilt, never scaled (scaling both would be ×1,000,000 with every coverage ratio
still footing). Migration `0039_extractions_source_unit.sql` records what the
PAGE said — **authored, unapplied**. Dry run over all 11 held PDFs on a copy of
the snapshot: **9 of 11 partitions fully green**, 4,161 rows. Two PDF-verified
exceptions remain, both pre-existing and neither affecting a total: AKBNK cons prior-period equity row X (the text layer
emits 14 of 16 cells; the two offsetting ±₺46mn components land in the wrong
columns, all three totals correct) and KLNMA cash-flow row III (a leading `(58)`
is indistinguishable from a dipnot ref in a 2-column statement — see below).

**⚠️ The unit switch broke every heuristic keyed on digit COUNT, not just the
scale (2026-08-05).** Dividing every printed figure by 1,000 moved a large
population of real values into ranges four extractor heuristics had reserved for
something else. Each was found by a Q2 filing and each was already corrupting
Bin-era partitions at a lower rate:

| Heuristic | What it assumed | What Milyon did |
|---|---|---|
| `_FOOTNOTE_RX` — `(\d{1,2})` is a dipnot ref | a real value is never 1-2 digits | TEB's `(55)` = −₺55mn was eaten; the row came back one token short, `_try_fit` missed the row-sum gate by 7 on a tolerance of 48, **both** the opening and new-balance rows were dropped, the roman sequence never restarted, the mid-page split never fired, and all 32 surviving rows stored as `current` |
| off-balance section floor `< 1_000` | "depth-1 totals are at least millions of TRY" | KLNMA's `IV. EMANET KIYMETLER 115` fell through it, taking the `B = IV+V+VI` identity with it |
| the surplus window in `_try_fit` | a label numeral nets out under tolerance | every bank's `TMS 8 / TAS 8` row stored paid-in capital = 8 — ₺8k in Bin, invisible for four years; ₺8mn once scaled, and `eq_row_sum` failed it on **all 11** Q2 filings |
| `HIERARCHY_PAT` / `_INSERT_SPACE` | a marker is dot-separated and stands apart | AKBNK prints `1,1Teminat Mektupları`; the row was lost and `I. GARANTİ ve KEFALETLER` came up ₺483.5bn short |

The fixes are structural, not magnitude bands: the reading that matches the
column template wins (`_parse_row_tokens` takes `n_cols`), the value grid is the
longest run of tokens no letter interrupts (`_value_region`), and a balance-sheet
row escapes the footnote strip and the section floor only by proving itself —
`tl + fc = total` in **both** periods, to the unit (`_triplets_foot`).
Deliberately **not** extended to cash flow or P&L: SKBNK's P&L prints
`XXII. … (8) -` directly above `(9) - -`, `(10) - -`, `(11) 1,502,150 254,698`,
a note-number sequence that reading would store as −8, −9, −10, −11. With no
identity to appeal to there is no way to tell the two apart, so those lanes keep
strip-and-drop — which is what leaves KLNMA's cash-flow III unrecovered.

Measured over all 145 bench filings, HEAD vs fixed, across assets / liabilities /
off-balance / P&L / cash flow: **11 of 145 changed, 8 rows added, 0 removed,
7 cells altered — every one verified against the filing text.** The historical
repairs are real: ICBCT 2025Q3/Q4 rows 16.4 were losing an **entire prior-period
triplet**, and the equity lane's own 145-PDF sweep repaired 13 pre-Q2 partitions
(QNBFB 2022Q1 and KLNMA 2026Q1 had lost the whole minority-interest column).
**Only 2026Q2 was re-extracted** — the ~13 repaired pre-Q2 partitions still hold
their old readings in D1, because the refresh lane skips any partition already
extracted with `success=1`. Correcting them is a `backfill-audit.yml` decision,
not a side effect of the Q2 batch.

**⚠️ TEB 2026Q2 released ₺862mn of free provision — read by hand, extractor
correctly silent (2026-08-05).** The alert-only check flagged both TEB
partitions. Reading the filings:

- **Notes** (cons p91 / unco p88) footnote the *"Diğer (\*)"* line of the
  provision-expense table — current **(798)**, prior **170**, Toplam 4,691 —
  with: *"30 Haziran 2026 tarihi itibarıyla **862 TL** tutarında ayrılan serbest
  karşılık **iptal** tutarını içermektedir (30 Haziran 2025: 150 TL ayrılan
  karşılık)."* A **reversal**, i.e. income: ex-free-provision that line is a
  ₺64mn charge, not a ₺798mn credit — a ₺1,012mn year-on-year swing.
- **The auditor's qualification** (p1, EY, *şartlı*) gives the stock outright:
  *"**1.230 milyon TL'si geçmiş yıllarda ayrılan, 862 milyon TL'si de cari
  dönemde iptal edilen toplam 368 milyon TL tutarında** … TMS 37 …
  karşılamayan serbest karşılığı içermektedir."* → remaining stock **₺368mn**
  (1,230 − 862 = 368), cited to notes §5 II.7.d and IV.5.

**No row should exist in `bank_audit_free_provision` from the note**, and the
extractor is right to skip it: the lane holds the STOCK, and its docstring names
grabbing a flow instead as the trap it was built against. Three independent
guards fire — `_FLOW` matches `iptal`, there is no Dec-31 parenthetical, and
`_NUM` requires a thousands group that "862" lacks.

**An opinion-derived fallback was tested and rejected on the evidence.** Across
the 380 opinions mentioning a free provision, the opinion figure matches the
stored stock 160 times and **disagrees 42 times**, while recovering exactly
**one** missing row — because the opinion reports what was **set aside** and the
note what **remains**. ALBRK is the clearest case: opinion ₺7,300,000k against a
stored ₺245,000k, the reversal being the entire ALBRK story. So the figure is
curated per partition, **not** taken from a general fallback.

**✅ Curated 2026-08-05 in `data/free_provision_overrides.json`** — the file that
exists for exactly this (hand-transcribed stocks read from auditor
qualifications), not `audit_overrides.json`. Both TEB 2026Q2 kinds, declaring
`"unit": "milyon"`, `free_provision: 368`, `free_provision_prior: 1230`.

That declaration needed a loader fix first: `_override_for` returned raw numbers
and `upsert_free_provision` then scaled them by the **filing's** unit. Harmless
while every filing was Bin TL and a silent **1000×** from 2026Q2 on. The
override now resolves its own unit through `UnitContext.manual()` — which
**refuses** a post-2026Q1 entry that declares none — normalises to canonical
`bin` itself, and marks the result so the writer cannot scale it twice. The ~200
legacy entries carry no `"unit"`, resolve to `bin` at factor 1, and are pinned
unchanged by a test.

Stored canonical values, proven end-to-end through the real override file and
the real writer: **current 368,000 · prior 1,230,000 Bin TL**. The prior
reconciles exactly with TEB's stored 2025Q4 current stock of 1,230,000 — the
module's own longitudinal check (this report's prior == last report's current).

⚠️ **Not pushed, and a routine refresh will NOT carry it.** An earlier version
of this entry said "the row reaches D1 on a future refresh" — wrong. TEB 2026Q2
already has `bank_audit_extractions.success = 1`, and `sync_audit_reports` skips
any partition already extracted successfully, so the override is never re-read.
Landing it needs an **explicitly authorized, targeted `free_provision`
re-extraction + push** for those two partitions. Not executed.

**⚠️ TEB 2026Q1's stored 0 is wrong, and it is an extractor bug rather than a
missing curation (2026-08-06).** Read-only inspection of the held PDFs:

- cons p74 / unco p71 — the stock, in the textbook form the lane anchors on:
  *"(*) 31 Mart 2026 itibarıyla **1,108,135 TL** (31 Aralık 2025: **1,230,000
  TL**) tutarında serbest karşılığı içermektedir."* `_PRIOR` matches
  `1,230,000`, no flow verb.
- cons p80 / unco p77 — a **separate reversal** of 121,865 TL, whose
  parenthetical reads *"(31 Mart 2025: Bulunmamaktadır)"*.

The classifier picked the **reversal page** (p79/p76) and read that
"Bulunmamaktadır" as the current stock being none. The whole chain reconciles
once the right page wins: 1,230,000 @2025Q4 − 121,865 (Q1 reversal) = 1,108,135
@2026Q1, and 1,230,000 − 862,000 (H1 reversal) = 368,000 @2026Q2.

Bounded exposure: **4 partitions** carry that fingerprint (a machine-extracted 0
whose snippet mentions a reversal) — TEB 2026Q1 ×2 and ZIRAATK 2024Q1 ×2, out of
78 zeros / 580 rows.

**✅ Fixed in the classifier, not by curating the partition (2026-08-06).**
Curating TEB alone would have left ZIRAATK wrong. Three defects stacked:

1. **`_SUBJ_TR` required the hard final `k`.** Turkish softens it to `ğ` before
   a vowel suffix, and *"serbest karşılı**ğ**ı"* is the form banks use in the
   very sentence that states the stock. The subject never matched, so no stock
   candidate existed on that page at all.
2. The amount-before-subject pattern required `N TL` and `tutarında` adjacent;
   TEB puts the prior-period comparison between them.
3. `_NONE` matched the later reversal note, where the "none" sits inside a
   **prior-period parenthetical** and describes 2025, not the reporting date.

The `_NONE` veto is deliberately narrower than "a reversal verb is present":
holding a provision and cancelling it in full is a legitimate route to a current
stock of 0 (the override file says so), and a flow veto would lose those. It
fires only when the none-word sits inside an unclosed parenthetical that opened
with a prior-period date.

**❌ The parser fix was REVERTED after the full-corpus gate (2026-08-06).**
Three sentence-level fixes were built — Turkish `k`→`ğ` softening, an
amount-before-subject pattern tolerating the prior parenthetical, and a
genitive/direct distinction so *"X serbest karşılı**ğın** Y kısmı iptal edildi"*
could not read X as the balance. All three worked on their target sentences and
the second run cleared the ZIRAAT ×11 regression the first one caused.

The corpus run rejected them anyway. **1,061 PDFs, read-only, in Actions: 459
unchanged, 37 changed, 0 unreadable — and 11 of the movers carried a value the
filing does not support:**

| Mover | Why it is wrong |
|---|---|
| ALNTF 2023Q4 ×2 | 55,000 was *"ters çevrilmesi"* — reversed. Not a stock |
| ICBCT 2022Q4 unco ×1 | read `0` from a **malformed** parenthetical in the very sentence that states *"Bankamızın 7,015 TL serbest karşılığı"* |
| ZIRAATK 2025Q1–Q4 ×8 | stock 0 is right, but the prior of 500,000 belongs to 2023, not to the preceding period |

Page selection is corpus-wide in a way three sentence shapes cannot bound. So
the classifier is back to its measured-good state, and **only the partitions
verified against their own source passage are curated**:

| Partition | Stock | Prior | Source |
|---|---|---|---|
| TEB 2026Q1 c+u | 1,108,135 | 1,230,000 | p74/p71 direct wording |
| TEB 2026Q2 c+u | 368,000 | 1,230,000 | auditor qualification p1 |
| ZIRAATK 2024Q1 c+u | 0 | 500,000 | p78 — cancelled in full |

The chain reconciles without a parser: 1,230,000 − 121,865 = 1,108,135 (2026Q1);
1,230,000 − 862,000 = 368,000 (2026Q2).

Genuine repairs seen in the run and **deliberately not taken**, because the
change that produced them is reverted: TEB 2025Q2 (150,000 is the period's
*allocation*, the stock is 1,650,000 — and 1,500,000 + 150,000 = 1,650,000),
HSBC ×13 and ICBCT ×3 (explicit *"bulunmamaktadır"* = 0 where we hold null),
VAKBN 2025Q4 c (8,000,000, matching its curated twin), EMLAK/TEB 2023Q4 (prior
gained, stock unchanged). They are recorded here rather than acted on.

**`_SUBJ_TR` carries a test pinning it un-widened.** Anyone widening it again
must re-run `measure-free-provision.yml` first.

**A new quarter arrives one bank at a time — sector "latest" needs a quorum
(2026-07-26).** Three consumers took a bare `MAX(period)` over an audit table,
which follows the FIRST filer of a quarter rather than the fleet: `perBankCapital`
and `auditRatioLatestPeriod` (`audit-ratios.ts`) would have ranked sector capital
adequacy on a league of one bank — on `/capital` **and the home page** — and
`aheadSlots` (`ahead-data.ts`) reads the latest audit period as "the last quarter
we hold" to predict the *next* filing window, so one early filer would have made
the Ahead strip announce the **Q3** window while the Q2 season was still running.
All three now take the latest quarter reported by **≥ 10 peer banks**, the guard
`latestCommonPeriod` (heatmap) and `marketRiskLatestPeriod` (market risk) already
used. All 38 banks file capital each quarter, so the quorum clears within days of
a season opening and never gates a settled quarter. Pinned by
`audit-ratios.test.ts` ("auditRatioLatestPeriod quorum"). **The guard is what makes
it safe to extract a new quarter as each bank files, instead of waiting for the
fleet.**

**Takasbank (`TAKAS`) — carried, but NOT a peer.** İstanbul Takas ve Saklama Bankası is
BDDK-licensed as a development-and-investment bank and files standard quarterly BRSA
reports (16 periods, 2022Q2→2026Q1), but it is Turkey's central securities-settlement /
clearing (CCP) + custody institution — market infrastructure, not a lender: **zero
deposits**, customer loans ~2.5% of assets, ~94% of the balance sheet in cash +
placements (member cash and collateral it merely custodies), plus ~178bn TL of
off-balance CCP guarantees. It is therefore **excluded from peer ranking, the
market-share league, the sector HHI and every audited sector ratio** —
`PEER_EXCLUDED_TICKERS` in `web/app/lib/bank_names.ts`, enforced at the choke point
in `heatmap.ts` (`ensure`), `market-share.ts` (`fleetBalances`) and — since
2026-07-24 — `audit-ratios.ts`, `credit-risk.ts` and `market-risk.ts`, which had all
been aggregating it in. **Any new sector aggregate must apply it**, via `peersOnly()`
where TypeScript sums the rows or `peerExclusionSql()` where D1 does; both live beside
the list. The rule is the point rows become ONE published number — never the
row-fetcher, because the same rows feed the per-bank pages. It keeps its own
`/banks/TAKAS` page, where balance sheet / capital / liquidity ARE meaningful (and
where its own repricing ladder and FX position still show every row). Two sourcing quirks:
its own IR site sits behind an **F5 WAF** that rejects non-browser requests (CI fails
identically), so it is sourced from **BDDK's BdrUyg registry** (institution code 132,
`unconsolidated_zip`); and BDDK omits its GlobalSign intermediate cert, so
`fetch_pdf_bytes` verifies via `src/scrapers/_http.bddk_verify()` (**full verification,
not a bypass**). 2022Q1 is omitted — broken font cmap (see AUDIT_BANK_CATALOG). Bank profile
(branches + personnel) is extracted where the bank discloses it in a
recognized phrasing — **20 of 31 banks parsed** (2026-06-14: broadened the regex —
domestic-only / bare-total branch forms + "personeli"/"çalışan" personnel →
recovered EMLAK/FIBA/KUVEYT/ODEA; `bank_profile` wired as a `reextract-statement.yml`
lane). The remaining ~11 are a **per-bank-phrasing long tail** — some disclose with
yet-other wording (ISCTR/ALBRK/ING — each needs its own pattern), some are
development/policy banks that may not disclose a branch network at all
(EXIM/TSKB/KLNMA). Low priority (a size indicator, not core financial data).

**Acquisition vs extraction (reworked 2026-08-06)**: `refresh-audit.yml` now runs
daily during filing windows and owns the full arrival path: discover/download →
extract → validate/coverage → one D1 batch → snapshot. A quiet check stops after
discovery and writes nothing. `/admin` still triggers targeted repairs or checks
outside the window; `acquire-audit.yml` is manual-only for deliberate acquisition
without extraction.

**⚠️ The audit lane silently stalled for six days (2026-08-08 → 08-12), and the
alarm was the cause.** `refresh-audit.yml` failed every morning on
`SYSTEMIC FAILURE: scrape N/N failed`, raised at the END of
`sync_audit_reports.main()` — after extraction had already written the local DB.
A failing step skips the rest of the job, so the D1 push **and the R2 snapshot
upload** were skipped. Each run therefore pulled the Aug-6 snapshot, extracted
the same eight 2026Q2 partitions cleanly (`ok=8 fail=0`), and discarded them:

```
[extract] 1070 in R2 · 1062 already done · 8 to extract     (identical Aug 10, 11, 12)
```

The trigger was four chronically unreachable bank URLs — AKTIF ×3, COLENDI,
VAKBN, later EXIM — timing out. With the corpus complete, `new` ≈ 0, and the
ratio counted only `failed + new`, so those four were 100% of a "batch" of four.
`pending` (103–104 PDFs downloaded and inspected as `not-a-report`) is a
**successful fetch** and now counts in the denominator: 5/109 = 4.6%, not 5/5.
The alarm also exits `EXIT_SYSTEMIC` (8) instead of 1, and both audit workflows
persist first and re-raise last, so an alarm can never again discard extraction
it did not affect. `tests/test_sync_systemic_gate.py` pins both halves against
the real runs' counts.

Recovery, 2026-08-12: `refresh-audit.yml` with `skip_scrape=true` (no scrape ⇒
`sc_total` 0 ⇒ gate cannot fire, and no `--force`, so settled partitions were
untouched) extracted the backlog — `ok=11 fail=0 not_a_report=2`, 213,010 rows
written. **2026Q2 went 12 → 23 partitions.** Two notes from that run: TSKB 2026Q2
serves a 14-page KAP cover sheet, not the filing (bad target, not an extractor
bug); and FIBA 2026Q2 extracted cleanly (`BSA=47 BSL=48`), so unlike its older
vector-outline filings this one carries a real text layer.

**Both follow-ups are now fixed (2026-08-12).**

The "chronically dead targets" were not dead. All six — AKTIF 2023Q4/2024Q4/
2025Q4, COLENDI 2025Q4, VAKBN 2025Q4, EXIM 2023Q4 — were present in R2 *and*
extracted in D1, and every one was a **Q4**. `report_validity` scanned only the
first 6 pages for structural markers, and an annual filing prints the full
independent auditor's report before the Bölüm structure begins. A stored PDF
judged not-a-report sends the scraper back to the source on every run, so ~80
genuine filings were re-fetched daily and the slow sources timed out into the
alarm. Measured over 60 random Q4s: first-marker page 1–9, **19 of 60 (32%) past
page 6**, non-Q4 never past page 4. Window widened to **16** (`_HEAD_PAGES`);
diffed at 6 vs 16 over 80 filings, **10 gained / 0 lost**. `bank_audit_invalid_pdfs`
in D1 was empty throughout, so coverage never mis-reported `pdf_present`.

`backfill_extraction --latest-period` resolved "latest" from `MAX(period)` in
`bank_audit_extractions` for its DELETE and from R2 for the re-extract. Both now
go through `latest_period_in_r2()`, and an empty listing refuses rather than
clearing everything.

~~Still open: **ICBCT** filings (77–108pp) carry KAP text in their front matter
and are refused as `kap-cover-sheet`~~ — **fixed 2026-08-16**: the fingerprint is
now consulted only below `_MIN_REPORT_PAGES`, and ICBCT's 2026Q2 halves extracted
on the first run afterwards. This entry had the diagnosis exactly right and
logged it as "pre-existing"; it then cost the bank a quarter. ~~**TSKB 2026Q2**
is not a bug … so the bank has not filed~~ — **wrong, corrected above**: the
bank filed 07-29 and the real reports were in the same directory under different
filenames. Both halves of this paragraph are the same mistake: a refused
document was read as evidence about the *bank* when it is only evidence about
the *URL*.

**Full-document table capture added 2026-08-07 (fleet captured locally
2026-08-13; the R2 ledger + D1 manifest build is `backfill-document-capture.yml`,
and since 2026-08-19 `refresh-audit.yml` captures each new filing per run).** The
completeness contract below is lane-scoped: it can only see pages a lane locator
finds. `src/audit_reports/document_capture.py` takes the same idea
document-scoped — every page of every filing, every table it prints, as rows,
inferred columns and cells, with each footnote linked to the rows carrying its
marker. Columns are clustered from the right edges of the figures rather than
read off a header row, which is why wrapped, letter-spaced and missing headers
do not matter; `/Rotate 90` pages go through `page.rotation_matrix`, so the
landscape 17-column equity statement reads as rows instead of noise. It calls no
analytical upsert, so it is safe over the frozen BS/P&L. The ledger lives in its
own `data/bank_audit_capture.db` (plus a per-partition JSONL mirror in
`data/audit_capture/`) and its own R2 object — never the audit snapshot, which
every workflow downloads. Only `bank_audit_document_manifest` reaches D1: one row
per filing carrying counts and three hashes (`content_hash` text, `shape_hash`
template-with-values-masked, `grid_hash` block/column/row geometry — the signal a
lane parser is about to break). Run it with
`backfill-document-capture.yml`.

**Fleet capture completed locally 2026-08-13 — 1,095/1,095 filings, zero
failures, 6,219s.** The corpus is **122,583 blocks, 5,418,465 lines, 11,172,412
cells and 64,608 notes (60,155 linked to the rows carrying their marker —
93.1%)**. Footprint: **3.09 GB ledger + 2.55 GB JSONL**, with the source PDFs a
further 2.65 GB when kept (`--pdf-dir`, gitignored at `data/audit_pdfs/`, which
makes a re-capture a local read instead of a 3.3 GB re-fetch).
`--jsonl-gzip` cuts the export by ~85% at the cost of plain-text grep.

⚠️ **Two published estimates were wrong and are superseded by that run.** The
earlier 162-PDF sample projected ~6.6M cells; the fleet holds **11.2M**, because
the engine places more per filing than when the projection was written. And
`backfill_document_capture.py` still says the corpus is "~10 GB" in two comments
— the R2 objects total **3.33 GB** across 1,148 PDFs (mean 2.9 MB, largest
57.8 MB). Prefer the measured figures above; the projections were never
re-measured after the engine changed.

**The capture is now READ by a check — `scripts/check_capture_reconcile.py`
(2026-08-13).** Until this, nothing consumed the ledger: it was evidence with no
consumer. Every per-partition validator is an *internal* identity, and a uniform
unit change scales both sides equally, so none of them can see a partition stored
at the wrong reporting scale — that is how TEB 2026Q2 landed 1000× small with a
clean validation run. The capture is the external anchor: a stored figure should
be a printed cell times the scale its declared unit implies, and the unit itself
is read off the captured text by `units.regex_unit`, so no PDF is needed.

⚠️ **The direction matters and is easy to get backwards.** `UNIT_SCALE` maps
milyon→×1000, so a correctly ingested Milyon filing stores printed×1000 — "stored
÷1000 is printed" is the HEALTHY state. The bug is the reverse: figures fitting a
factor OTHER than the filing's own declaration. A first draft of the check tested
this backwards and would have failed every properly ingested Milyon filing;
`tests/test_capture_reconcile.py` pins both directions.

**Fleet result 2026-08-13: 1,050 partitions reconciled, median 97.3%** (p1 94.4%,
11 below 95%), **zero `unit_scale` findings and zero unreadable declarations** —
the TEB class of failure is absent fleet-wide, which nothing else in the pipeline
could establish. ~~Two errors, both open: FIBA 2023Q3 (19.0%, the missed vector
filing described below) and ISCTR 2025Q1 consolidated (61.3% — undiagnosed, and
unlike FIBA it is lane-specific rather than document-wide, so it is a different
cause)~~ — **wrong on the last clause, and closed 2026-08-19: they were the SAME
cause**, see the next block. `MIN_RATE=0.85` sat below p1 by ~9 points at this
measurement; it is now 0.95 against the sharpened rate below.

**2026-08-19 — both open errors were ONE bug, the reconcile was diluting itself,
and both are fixed.**

The diagnosis: FIBA 2023Q3's "probe miss" and ISCTR 2025Q1's "undiagnosed"
error share a mechanism. The statement pages of both are **raster images under a
typed banner** — İş Bankası embeds each statement as one full-page picture (~40
typed caption words, zero path items, one image at 17–48% page coverage),
Fibabanka as hundreds of tiles — and `_probe_text_layer` measured only vector
ink, so both scored 0–14 against the 25.0 threshold and stamped `text`. The
probe DID run (the pages had no blocks); it was blind, not skipped.
`_raster_content` now reads geometry instead: a blockless page whose images
cover ≥10% while ≤8 typed words sit inside the content band (18–86% of display
height, rotation-normalized) is `raster`. Every threshold sits in a measured
gap: rasterized statements carry 31–43 words, all in the margin bands; a cover
with artwork (TSKB 2026Q2 p1) puts ~25 title words INSIDE the band; a divider's
logo covers <5%. Sweeping the fleet for statement-caption pages with no block
within two pages finds the known filings, two benign divider pages, and **one
new victim — ISCTR 2025Q2 unconsolidated (92.4%, its cash-flow and OCI pages,
visible only under the sharpened rate below)** — so the silent class is fully
enumerated: **3 filings in 1,095**. All three are re-captured locally with the
fix (5 + 2 + 10 pages stamped, `capture_status='partial'`); the fleet restamp
shipped the same day — see the run record below.

Scanned auditor letters (typed-nothing pages holding a full-page image — EXIM,
PASHA and peers) now also stamp `raster`/`partial`: their content is equally
unreadable, and `captured` over a page we cannot read was the same lie in
miniature. What makes that shift safe is the paired change: **the reconcile no
longer skips a filing wholesale for unreadable pages** — `capture_incomplete`
is raised only when the rate is actually low — so a letter-scan filing keeps
its anchor instead of losing it to a signature page
(`tests/test_capture_reconcile.py` pins both directions).

The dilution: per-column measurement over 144 partitions (GARAN/TSKB/AKBNK/
ALBRK) shows every statement-lane column reconciling at 99.9–100% while three
extractor-COMPUTED columns can never match a printed cell —
`fx_position.net_position` 3.3% (net_on + net_off, `fx_position.py`),
`repricing.cumulative_gap` 33.3% (running sum), `credit_quality.total_amount`
74.5% (summed when the filing prints no total). Each is already held by its own
lane's internal identity, so `DERIVED_COLUMNS` excludes them from the anchor.
Fleet re-rate without them: **median 97.3% → 99.66%, p1 98.88%**, the band
92.4–96.4% empty, and **`MIN_RATE` rose 0.85 → 0.95** — the level at which
ISCTR 2025Q2u stopped passing as healthy.

Fleet verification after all three changes: **1,050 partitions, 0 errors, 8
`capture_incomplete` infos, every one a diagnosed hole** (six FIBA vector
filings, the two ISCTR rasters, FIBA 2023Q3). First time the fleet is fully
explained: every partition either reconciles ≥95% at its declared scale or is
attributed to pages the capture itself marks unreadable. The OCR inventory —
the one fork deliberately not taken — is 225 vector pages plus the raster pages
above, concentrated in FIBA.

**Cadence, same date:** `refresh-audit.yml` now captures each freshly extracted
filing (`backfill_document_capture.py --recent-hours 168`, run-local ledger;
the compact manifest rides the run's own D1 push and snapshot) and reconciles
it alert-only (`check_capture_reconcile.py --alert`) in the same run — the
anchor works the day a filing lands, current season included, which until now
was never reconciled at all (the local snapshot the 08-13 fleet run compared
against carries no 2026Q2 rows). The fleet ledger build in R2 and the D1
manifest backfill remain `backfill-document-capture.yml`.

**The capture became queryable table-by-table, section-by-section
(2026-08-20).** `scripts/build_document_tables.py` derives
`data/bank_audit_tables.db` from the ledger — sections (title + role + page
span, the filing's own contents where its folios validate, body banners where
they do not, honest NULLs where neither does), contents items, and one row per
table carrying its section context and the full grid as JSON. Built over the
local ledger: **1,095 partitions → 122,583 table rows, cell-conservation
exact against the ledger (8,392,845 = 8,392,845)**; details in the data
inventory above. The local ledger is 18 partitions behind the R2 one (the
2026-08-19 Actions run captured 1,113), so a production rebuild belongs beside
the fleet capture, not on this machine. Nothing here is in D1.

**The first graduation ran 2026-08-20 — the capital pilot.** The full own-funds
table now exists in analytical shape, minted from the document layer with no
PDF involved: see the `bank_audit_capital_full` inventory row above for the
measured anchors. The narrow `bank_audit_capital` is untouched and becomes the
standing validator of its wide successor — the graduation direction agreed for
all future analytical coverage. Two template dialects and one truncation rule
cover the fleet; `tests/test_capital_full.py` pins them.

**The second graduation followed the same day — the LCR (2026-08-20).** Faster
than capital because the regulator numbers the template's rows and the capture
kept the numbers: `template_row` joins across banks and languages with no label
regex carrying identity. See the `bank_audit_lcr_full` inventory row for the
measured anchors; `tests/test_lcr_full.py` pins the mechanics. The narrow
liquidity lane stays untouched as the standing validator. **NSFR followed the
same day** (`bank_audit_nsfr_full`, inventory row above) — three lanes now
graduated, and the third took one probe and one column-model fix, which is
the pattern maturing.

**The fleet build ran the same day — `backfill-document-capture.yml`'s first
dispatch ever (2026-08-19, run 32233386008): 1,113/1,113 filings in 3,032s,
zero failures**, with the fixed engine and the 18 partitions acquired since
08-13 included. Corpus on Actions: 124,434 blocks / 5.51M lines / **11.37M
cells** / 65,575 notes (61,024 linked). What changed hands: the raw ledger now
lives in R2 (`state/bank_audit_capture.db.gz`, 750.1 MB — the corpus is no
longer single-machine), and **`bank_audit_document_manifest` in live D1 went
0 → 1,113 rows / 38 banks / 2022Q1→2026Q2** (verified post-run): 962
`captured`, **151 `partial`** (the scanned-letter honesty shift landing
fleet-wide), 518 unreadable pages in total, with the three raster filings
carrying exactly their measured counts (ISCTR 2025Q1c 5, ISCTR 2025Q2u 2,
FIBA 2023Q3c 10). The local 2.9 GB ledger of 08-13 is now the stale copy —
pull the R2 object rather than re-trusting it for per-page `text_layer` state.

**Where the capture now stands, and what the remaining findings are (measured
2026-08-07).** Holdout of twelve banks never tuned against: **1,304 of 1,435
tables clean (90.9%)**, no dead columns, 1,650 of 1,717 blocks with named
columns.

**The holdout generalised — confirmed fleet-wide 2026-08-13.** Linting all 1,095
captured filings gives **110,707 of 122,583 tables clean (90.3%)**, against the
holdout's 90.9%. That is the number this section exists to establish: the tuning
did not overfit to the twelve. (The superseded engine, still on disk as
`data/bank_audit_capture.stale.db`, lints at **50.2%** over the 191 filings it
covered, which is the before-picture for that gap.) Fleet finding totals:
`fragment_label` 4,204, `empty_row` 4,112, `no_column_headers` 3,843,
`row_without_label` 2,066, `prose_row_in_table` 1,597, `note_without_table`
1,230, `note_link_missed` 869, `unreadable_page` 225, `weak_column` 173,
`note_truncated` 136. `unreadable_page` matches the manifest's vector-page count
exactly, so lint and capture agree on the size of the hole.

The residue is largely NOT defect:

| finding | count | what it is |
|---|---|---|
| `no_column_headers` | 64 | 13 tables genuinely print no header; 11 have TEXT columns the value-clustering cannot see; the rest a hard tail |
| `fragment_label` | 44 | structurally blind to fragments repaired by merging — measure lower-case row labels (287) instead |
| `unreadable_page` | 40 | Fibabanka's vector filings; needs OCR, not parsing |
| `row_without_label` | 31 | mixed; 8 were lint error, fixed |
| `empty_row` | 30 | header fragments, period captions, wrapped-label pieces |
| `note_link_missed` | 11 | legal citations, correctly unlinked |
| `prose_row_in_table` | 8 | genuine narrative inside a table |
| `weak_column` | 3 | genuinely sparse real columns |

`prose_row_in_table` fell **24 → 8** by fixing the LINT, not the capture: a long
label ending in a full stop is not narrative, because BRSA writes
capital-deduction rows as whole sentences ("Investments of Bank to Banks that
invest in Bank's additional equity … compatible with Article 7.") with their
figures in columns beside them. What marks a row as narrative is that its
figures sit INSIDE the sentence — the same inline-versus-channel distinction the
capture uses. 16 of the 24 were real rows.

**Columns one row could fill (fixed 2026-08-07).** The residue of the dead-column
prune: a phantom that exactly one row reaches. A single cell is NOT sufficient
evidence — a footnote-reference column legitimately carries a value on 4 of 38
rows on TSKB's balance sheet — so the prune fires only where that one cell can
be shown never to have been a cell: a figure sitting inline in the row's own
label ("Less than 1 Year" → 1, "II. TMS 8 Uyarınca" → 8, "ayında 1.229 milyar
TL" → 1.229), or the row's own section numbering ("9.3.", "5.10.2"). Measured
over the 15-filing set: **single-cell columns 21 → 3**, the three survivors
being genuinely sparse real values, with blocks, rows and **total cells all
unchanged** — a pruned column's figure stays captured, it simply stops claiming
a column it never belonged to. Holdout clean **89.5% → 90.2%**.

**Columns no row could fill (fixed 2026-08-07).** A column is inferred from
value edges before prose rows are dropped and before cells are matched to it
within tolerance, so a cluster could survive holding nothing. Most came from a
figure inside a row label — "Less than 1 Year", "Longer than 5 Years" put a
bare 1 and 5 in the label region — and Garanti p131 carried two such columns
8pt apart. 21 of the 30 sat first in their table. Empty columns are now pruned
after cells are assigned and the survivors reindexed: **dead columns 30 → 0
with blocks, rows, cells and placed cells all unchanged**, holdout clean
**88.2% → 89.5%**.

Refusing the edge instead — letting only channel-reached values vote — was
measured and reverted: it removed 403 columns to kill 12 dead ones, costing 9
blocks, 139 rows and 1,563 placed cells, because a narrow table sets adjacent
figures closer than a channel and their columns stopped being found at all.
Pruning after the fact cannot lose data, which is why it is the safe form of
the same idea. A phantom column holding ONE cell still survives as
`weak_column`; that is the residue.

**A table could take the header of the table above it (fixed 2026-08-07).**
Garanti stacks four tables on one page, and the reach-back that finds a header
above a block was finding the PREVIOUS table's as well as its own. Mapped
together the two produce fragments the plausibility filter discards, so a table
with a perfectly good header printed one line above it rendered as "c0 c1";
where both tables carried the same header, the result was a doubled "Current
Period Current Period". A candidate separated from the block by a line
belonging to another block is now dropped — a header cannot sit on the far side
of a different table.

Measured directly over 1,717 blocks with columns rather than by the lint count:
**5 tables gained a header, 0 lost one, and 113 had a wrong header corrected** —
"Net Gross Current Period" → "Current Period", "Loans Corporate / Commercial
Loans" → "Corporate / Commercial Loans". `no_column_headers` fell 70 → 65 and
holdout clean reached **88.2%**, with +0 blocks, rows and cells. The lint sees
only the 5; the 113 are invisible to it, which is why the direct measure is the
one to steer by here.

**A label could not wrap over a figureless line (fixed 2026-08-07).** Albaraka's
exposure classes print a row over three lines — "3 Receivables from" (the row
number alone) / "administrative units and non-" / "commercial enterprises 68.234
…". The column-completion walk stops at the first line that carries no figures,
so the head stayed a labelled row with none and the figures sat under a
fragment. It now steps over such a line when the line RESUMES the label in lower
case; an upper-case line is the next row, not this one's continuation.

**The lint disagreed, and the lint was wrong.** `fragment_label` rose 42 → 44
and clean tables fell by one, because that rule only fires on a SINGLE-line row
(`len(parts) == 1`) — merging a fragment into its head exempts the row from the
check rather than counting it as repaired, so the rule can never see the defect
it is named for. Measured directly over every logical row in the 15-filing set
instead: labels beginning in lower case fell **342 → 287**, and 57 lines joined
the rows they belong to, with +0 blocks and +0 cells. Prefer that measure over
`fragment_label` when judging this class.

**Row 1 of a table could not wrap (fixed 2026-08-07).** A merge is barred from
starting on a block's first line, because that line is the column header far
more often than it is a wrapped label. BRSA risk-class tables open straight onto
a wrapped data row — "1 Receivables from central" / "governments or central
banks 34.833.367 …" — and because the row number is itself a cell, the cell-less
wrap branch never saw the line either. Row 1 of every such table lost half its
label while rows 2..n merged correctly, across Albaraka, ICBC, TEB and Halkbank
alike. The bar now lifts only when the first line opens with a row marker AND
the next resumes in lower case, which no header does. `fragment_label` fell
**50 → 42**, holdout clean **87.6% → 87.9%**, 172 lines regrouped with +0
blocks, rows and cells; every regrouped block was inspected and none was a
header.

Still split: a THREE-line wrap whose head holds only the row number
("3 Receivables from" / "administrative units and non-" + figures /
"commercial enterprises"). The middle and tail bind; the number-only head does
not. Pre-existing, unchanged by this fix.

**A row could take the NEXT row's label (fixed 2026-08-07).** Garanti's
landscape deposit table prints every long label on its own line above its
figures — "Public Sector Deposits" / figures / "Commercial Deposits" / figures.
The rule that binds a wrapped label TAIL printed under a row's figures bound
each of those labels to the row above, so one logical row carried "Public
Sector Deposits Commercial Deposits" against Public Sector's figures while
Commercial's figures were left with no label at all. That is a **mislabelled**
row, not a missing one — wrong data rather than absent data, and it surfaced
only as a `row_without_label` count on the orphaned half.

Orthography cannot separate a tail from a new label: a real tail is title-cased
as often as not ("Financial Assets At Fair Value Through Other" / figures /
"Comprehensive Income"), and requiring a lower-case resume orphaned exactly
those — it regrouped 1,287 lines and broke the TSKB three-line row this
document records as recovered in iteration 15. What separates them is what
follows: a new row's label is followed by its own figures, a tail is not. With
that test, 5 lines change across fifteen filings and both cases are right.
`row_without_label` fell 41 → 39 from the fix and to **31** once the lint
stopped reading a date as an amount ("30.09.2023" contains "0.092", so every row
of an FX-rate table identified by its date read as one that had lost its label).
Holdout clean **87.2% → 87.6%**, +0 blocks, rows and cells.

**A note that owned no table linked to nothing (fixed 2026-08-07).** Every one
of the three linking passes was gated on the note having an owning block, so a
footnote on a page with no table recorded its relationship nowhere — Garanti's
ratings pages print "(*) Latest date in risk ratings or outlooks" under
"MOODY'S (October 2025) (*)" with no table anywhere on the page. Ownerless
notes now link to the lines carrying their marker, **but only for star markers**:
"(1)" and "(i)" are equally how a filing cites a regulation — Halkbank prints
"Clause 2, Paragraph (1) and (2) of the Regulation" as ordinary text — so
linking those would invent a reference the filing never makes. Across the
12-bank holdout `note_link_missed` fell **44 → 11**, the 11 being exactly the
non-star citations that must stay unlinked, and notes linked to rows rose
**716 → 749** with +0 blocks, rows and cells.

**Sideways margin text was being dealt across table rows (fixed 2026-08-07).**
Garanti prints "The accompanying notes are an integral part of these
consolidated financial statements" rotated 90° down the left margin of its
landscape equity statement. Each word sits at its own y, so y-bucketing handed
one word to each table row: "accompanying VII. Capital Reserves…", "notes XI.
Profit Distribution", "are 11.2 Transfers to Reserves" — the sentence dealt
across the table, one card per row. `_sideways_x` now finds such a column by
which dimension stays CONSTANT down it: every rotated word is one glyph-height
wide with height proportional to its length (12 words at x=30, all 5.98 wide,
heights 4.55–31.83), where an upright column is the transpose (roman numerals
all 9.96 tall, widths 5.25–17.74). The words are pulled out of the row
clustering but NOT discarded — Albaraka names the row groups of its
credit-ratings table the same way — each column becoming one line, ordered by
the writing direction PyMuPDF reports per span, because Garanti's advances down
the page (0,+1) and Albaraka's up it (0,−1). `fragment_label` fell 56 → 50 and
holdout clean reached **87.2%**, with +0 blocks and the other twelve filings
byte-identical.

Two false positives were measured and fixed before shipping, neither visible in
any lint count: judging each word by its own aspect ratio condemned the roman
numerals on every contents page (`III.`, `VII.` are narrow enough to be taller
than wide), and constancy without scale condemned columns of `-` placeholders —
which is how a BRSA statement prints *not disclosed* — plus real amounts of
equal digit count (VAKIFK p53 lost 45.400.031, 33.896.880, 81.550.957).

**A numeric header read as a data row (fixed 2026-08-07).** The header test
asked only whether a line had a figure aligned to a column, on the assumption
that a header's own figures are dates sitting nowhere near one. A header can be
numeric by nature: Halkbank names its risk-weight columns "0% 10% 20% 50% 75%
100%", each printed over the column it labels, and dates its shareholder columns
"31 December 2025 | 31 December 2024" above the amounts. Both read as data, so
the tables rendered "c0 c1 c2" with the header one line above the figures. A
relaxed test (`_aligned_amounts`) now runs as a **last resort**, and header
figures are admitted as header words there. `no_column_headers` fell **110 → 70**
on the 12-bank holdout and clean tables **84.3% → 87.1%**, with +0 blocks, rows
and cells.

Ordering was measured, not assumed. Running the relaxed test *first* answered
for tables whose caption would have answered better — Garanti p11 went from
"TL | CURRENT PERIOD FC | Total | …" to "March | December", 96 headers changed
against 16 gained. Placed last, it only fills silence: 18 gained, 2 changed and
both improved. Allowing a bare percentage to be a header fragment then recovered
the risk-weight tables themselves (ALBRK p82/p83 from nine empty columns to
"0% 10% 20% 25% 35% 50% 75% 100% 150% 250%").

Still open on this path: a header row admitted this way is also kept as the
table's first data row (Halkbank p97 prints its percentages twice), and a header
INSIDE the block that the relaxed test still rejects leaves the table unlabelled
(Halkbank p10).

**A column can hold text, and those columns were being dropped (fixed
2026-08-07).** Garanti's board table prints "Süleyman Sözen | Chairman |
29.05.1997 | University | 45 years" — five columns, every boundary a wide
channel, of which only two hold figures. `_infer_columns` clusters value edges,
so it saw two columns, filed "45" under "Education", and lost "Chairman" and
"University" outright; they survived only by being swallowed into a row label
that read as the entire line. `_channel_fields` now splits a line into the
fields it prints, the label is the first field, and every later field that is
not purely figures is captured as a text cell. **+11,045 cells across eight
filings with +0 blocks and +6 rows** — additive, no table gained or lost. A
mixed field is kept whole: Akbank answers "Aracın muhasebesel olarak takip
edildiği hesap" with "Sermaye Benzeri Krediler (347011 Muhasebe Hesabı)", and
an earlier version that skipped any field containing a figure reduced that to
"(347011".

Text cells that match no value-derived column keep `col_index=NULL` — recorded
but unplaced. Clustering the field edges so they would get real columns **was
measured and reverted**: it cost 30 blocks and 272 rows across eight filings
(Akbank alone −11 and −72), because the extra edges shift cluster support until
blocks stop reaching their terminal column. The board table's grid is therefore
still two columns wide; its text is captured, not placed.

**Narrative was being minted into tables (fixed 2026-08-07).** Turkish prose
defeats column clustering by being too regular: consecutive sentences opening
"4 Mart 2003 tarihinde…", "28 Kasım 2006 tarihinde…" put the day at the left
margin and the year at a near-constant x, because the month names are similar
widths. Those dates clustered into two clean columns and passed every structural
test the capture had — the run footed, the rows were long, the figures were
substantial — so Fibabanka's corporate history was captured as a 4×2 grid of day
and year fragments. `_every_figure_is_inline` now rejects a block in which every
figure is reached at word spacing rather than across a column channel; the gap
to a figure's **left** is the discriminator (88–237pt in a real table against
2.4–3.0pt in a sentence). Measured over the 12-bank holdout: **55 phantom blocks
removed of 1,490**, clean tables **81.7% → 84.3%**, with `no_column_headers`
140→112, `fragment_label` 78→52 and `weak_column` 51→21 falling as a consequence.
Judging by the word that FOLLOWS a figure was tried first and is wrong — every
amount in Akbank's FX valuation table is followed by "TL" at word spacing, so
that version deleted a real 6-row table while every lint count improved. It was
caught by diffing captured blocks, which is now the check that gates this rule.

**Some filings are legible on screen and unreadable to any extractor (detected
2026-08-07).** Fibabanka typesets its statements and converts the glyphs to
vector outlines: the balance sheet renders perfectly and carries no text at all —
28,366 curve segments and 35 extracted words on the page. The capture of
`FIBA 2022Q1 consolidated` therefore returned **13 tables and 71 rows from 92
pages**, where its twelve readable peers return 1,200–2,500 rows, and nothing in
the output said so; it read as a small bank filing a short report. `_probe_text_layer`
now measures path items per extracted word on any page that yielded no table.
The corpus separates cleanly — drawn pages score **54–2,050**, every typed page
(ruled statement grids included) scores **0–1** — so the threshold sits in an
empty band two orders of magnitude wide. Affected pages are stamped
`bank_audit_document_pages.text_layer='vector'` (raster-imaged pages, the
second mechanism found 2026-08-19, stamp `'raster'`), counted into
`bank_audit_document_manifest.unreadable_page_count` (migration `0044`), and
the filing's `capture_status` becomes `partial`; `lint_document_capture.py`
reports each one as `unreadable_page`. Measured over the **full fleet (2026-08-13)**: **13 of
1,095 filings** carry a drawn page, 225 pages in all — FIBA 9 filings / 209
pages, ATBANK 2 / 12, DUNYAK 1 / 3, TAKAS 1 / 1. (The earlier partial-corpus
figure was "18 of 307", which overstated the rate ~4× and missed DUNYAK and
TAKAS entirely.) 39 of 92 pages in FIBA 2022Q1 are drawn, the balance sheet,
P&L and cash flow among them. Recovering those rows needs OCR, which the capture
engine deliberately does not do; what it does is refuse to report the gap as data.

~~⚠️ **The probe misses a filing of this kind (open, found 2026-08-13).** FIBA
2023Q3 consolidated is stamped `captured` with a zero unreadable count, yet
yields 10 blocks and 2,546 cells from 93 pages — plausibly because
`_probe_text_layer` runs only on a page that yielded NO table, so a page with
typed labels and drawn figures produces a small table and is never probed~~ —
**mechanism reproduced 2026-08-19, and the hypothesis was wrong**: those pages
had no blocks, so the probe DID run — it returned `text` because the statement
bodies are raster image tiles (paths-per-word 14, under the 25.0 band; images
carry no path ink at all). Fixed by `_raster_content` — the same fix that
closed ISCTR 2025Q1/2025Q2; the full record is in the 2026-08-19 block above.
The one true sentence survives unchanged: a page carrying typed prose above a
drawn table (FIBA p.29) keeps its prose and is still flagged, because its
tables are gone.

**Source-table completeness contract added 2026-08-07 (historical backfill pending).**
The stable audit tables no longer have to pretend that their schema proves the whole PDF
table was captured. `source_capture.py` independently locates the disclosure, preserves its
physical source lines in the R2 SQLite snapshot, records mapped versus unmapped numeric rows,
and emits a compact D1 manifest. Normal extraction and targeted re-extraction write evidence
in the same transaction as facts; validation consumes it immediately. Existing partitions
remain grandfathered until the manual `backfill-audit-source-capture.yml` run. That workflow
does not re-extract or overwrite a single analytical row, which avoids reopening the settled
BS/P&L and avoids a high-volume D1 raw-row push.

**Market-risk was extracted but never pushed (fixed 2026-07-14).** `refresh-audit.yml`
— the lane that ingests every new quarter — hand-listed 14 of the 16 audit tables in
`--only-tables`, omitting `bank_audit_fx_position` and `bank_audit_repricing`. They
were extracted, validated and written to the R2 snapshot on every run, and silently
never reached D1: `push_to_d1`'s `--only-tables` was an unvalidated filter, so a
forgotten table matched nothing and the push still exited 0. D1's market-risk tables
were therefore frozen at the 2026-06-29 manual backfill (which pushed all 16) while
every other audit page advanced. **Fixed at the root**: the table list is now derived
from `src/audit_reports/registry.py`, workflows pass `--table-set audit`, and
`push_to_d1` hard-errors on a table it cannot sync (`tests/test_audit_tables_sync.py`
pins it). **Reconciliation CLOSED (verified against remote D1, 2026-07-24)** — the
2026-07-18/19 lane passes re-pushed both tables: `bank_audit_fx_position` 8,208 rows /
590 partitions, `bank_audit_repricing` 12,064 rows / 455 partitions, and AKBNK 2026Q1
(the partition named as absent from D1 entirely) holds its 16 fx rows. Both are now
**above** the R2 snapshot counts the gap was measured against, so no push is pending.

**fx_position (§4 currency-risk) lane: 21 err + 66 miss → 0/0, then a 79-cell
false-NEGATIVE sweep → 0/0 — COMPLETE 2026-07-18** (coverage `1022 ok / 28 manual /
0 err / 0 miss`; two extractor fixes + source overrides + curated skips). The first
pass (below) cleared every RED cell; a second pass then attacked the GREENS.

**Second pass — the cross-period reconciliation (a real external anchor).** The lane's
identities are all internal (Σccy=TOTAL, assets−liab=net_on, net_on+net_off=net_pos)
and every one SKIPS an absent field, so a partial extraction reads a flawless green while
`net_position` (the lane's headline, what `/market-risk` shows) silently collapses to
whatever WAS captured. Three checks close that: **`fx_net_position_missing`** (a TOTAL
with only gross assets/liab), **symmetric `fx_current_incomplete`/`fx_prior_incomplete`**
(neither column may drop a field the other carries — DENIZ/TEB drop the current net-off
row, TSKB drops the PRIOR net-off row storing a sign-flipped net position), and
**`fx_cross_period`** — the prior column re-prints the prior YEAR-END, so it must equal
that year-end's INDEPENDENTLY-extracted current column (`_fx_prior_ye_totals` binds it at
the revalidate call site, house pattern). Cross-period mismatches fell **88 → 14 pairs**;
all 14 remaining are documented skips. The sweep flagged **79 green cells** and resolved
every one: **~53 systematic extractor drops** recovered from source (prior net-off label
`Net Bilanço Dışı Pozisyon`, a value-column ROW-SHIFT re-paired positionally under the
identity web, a prior net_on gap-fill; BURGAN 2026Q1 switched EN→TR labels and its net-off
row dropped from BOTH columns — a blind spot the cross-period anchor caught where the
symmetric check can't, so the anchor is NOT gated on prior net-off being present); **4
value-corrections** grounded in each table's OWN derivative-leg rows + the adjacent filing
(KLNMA 2023Q4 added a USD leg instead of subtracting; EXIM 2025Q4 sign-flipped net-off;
EXIM 2024Q2 dropped prior liab; ALNTF 2026Q1 dropped a TOTAL net_on sign) → overrides;
**8 curated `_FX_XPERIOD_SKIP`** genuine restatements / defective-source comparatives
(HALKB/ALBRK restatements, TOMK's blank prior columns, ALNTF's 2021-under-2022 year-swap);
and **2 WRONG-PDF findings** the anchor EXPOSED and we then FIXED at source: **GARAN 2023Q4
`unconsolidated`** R2 object was the CONSOLIDATED report, and **KUVEYT 2026Q1
`consolidated`** was the UNCONSOLIDATED report — the whole partition (BS/PL/every lane) was
another basis's numbers. **Re-acquired 2026-07-18**: `audit_report_urls.json` corrected to
the real reports (GARAN's Turkish-site "Konsolide Olmayan" original
`31_Aralik_2023_…tablo_ve_aciklamalari.pdf`; KUVEYT `konsolide-denetim-raporu-…-3925.pdf` —
the registry had listed the unconsolidated 3926 under both keys), re-fetched to R2, and
BOTH partitions re-extracted across ALL lanes. They now reconcile through the anchor with no
skip (GARAN 2024Q1–Q4 prior = 25,130,005 = the corrected 2023Q4 current; KUVEYT 2026Q1 prior
= −1,632,877 = 2025Q4 consolidated current). `_FX_WRONGPDF_SKIP` removed. See
[audit-fx-cross-period-false-negatives-2026-07-18](knowledge/audit-fx-cross-period-false-negatives-2026-07-18.md).

**First pass — 21 err + 66 miss → 0/0. Missing (52 recovered by a 2-line header fix):** `_CCY_HEAD` under-counted
currency columns — TSKB's English "US Dollar" tokenises to `US`+`Dollar` (matched no
USD pattern) and YKBNK-unconsolidated's "Other FC" header WRAPS so only `FC` reaches
the baseline; added `US`→USD and `FC`→OTHER, agent-verified 0→8 rows on both with zero
regression on Turkish/consolidated controls. **Errors (13 zero-pass — period mis-tag):**
HAYATK ×11 + ISCTR ×2 print a currency-SENSITIVITY sub-table above the position table
whose header says "Current Period / Prior Period"; `_PRIOR_RX.search` fired on it and
tagged the whole current table as prior (0 current rows → validator skips everything).
Guarded the flip to ignore a line that also names the current period (`_CURRENT_RX`).
**Errors (8 footing):** 4 real extraction bugs → overrides (⚠️ `parse_num('-319.110')`
→ -319.11: a hyphen-prefixed 3-digit thousands group is misread as a decimal — a
SHARED-parser bug, only 2 fx cells here but a corpus-wide follow-up; + QNBFB's dropped
closing parens flipped signs positive); 4 genuine SOURCE typos where the filing itself
doesn't foot (a dropped digit, a malformed "(41,24,355)", a sign typo) → `_FX_SKIP`
storing the faithful printed value. **Remaining 14 missing verified: ZERO genuine
non-disclosure** — 8 were a SECOND header-split cause (Turkish "ABD Doları"/"Diğer YP"
splitting across physical lines; hand-overridden via new `fx_position_replace`), 6 FIBA
are image-only/vector-outlined (hand-transcribed from renders, each corroborated by the
report's own "net yabancı para pozisyon" prose). 18 hand-read cells read `manual`
(`_STMT_TO_KEY` + new fx handlers; `bank_audit_fx_position`/`repricing` added to
`_SELF_TS_TABLES`). Follow-up: the header-split (ABD Doları/Diğer YP wrap) is an
extractor gap for DUNYAK/KUVEYT future quarters — a scoped header-line-merge would
close it. ⚠️ Used `--only-failing`, NEVER `--force` (the market-risk lane's own lesson).

**repricing (§4 interest-rate-risk) lane: 5 err + 26 miss → 0/0 — COMPLETE 2026-07-18**
(coverage `787 ok / 16 manual / 0 err / 0 miss`). `check_repricing` only checked internal
footing (both checks skip an absent field), so **70 partitions read green while a whole
column was dropped** — the extractor never matched the liabilities row (59) or the position/gap
row (7), mostly the non-standard-bucket banks ZIRAAT/KLNMA stored as `b1..b8`. Added a
completeness check (`rp_liab_missing`/`rp_gap_missing`, calibrated 66/0-FP); cross-period is
already clean (0/584). The `b1..b8` fallback was a symptom — footnote markers `(1)`/`(5)`
matched the number-token regex and inflated the column count. **Six extractor fixes cleared
~76**: drop footnote markers; add Turkish `Net Pozisyon` (TAKAS ×14 were missing — the locator
never fired); gate the prior-period flip until the current total is read (ISCTR/ENPARA lost
their current table to an FX table's "Prior Period" header); borrow a split label row's values
from the next line (ATBANK); typo-tolerant `Total Liab[a-z]+` (QNBFB "Liabalities"); un-glue a
fused Faizsiz|Total token (HALKB). **8 overrides**: FIBA ×6 (vector-only, hand-transcribed
both periods) + 9 source-read residuals (ISCTR source-clipped cell, QNBFB gap missing its
parens, EXIM/ZIRAATD dropped gap rows, TAKAS ×2 mis-parses, COLENDI ×3 whose wrapped
"Non-Interest Bearing" header defeats the locator — disclosed, NOT N/A). **1 skip** (`_RP_SKIP`
ICBCT 2024Q1: gap buckets sum to ₺7k vs printed 0 — source rounding). **All 5 brittleness classes then HARDENED** via x-coordinate column reconstruction gated on
footing (`_x_columns`/`_page_anchors`/`_row_by_columns`/`_destray`) — 7 of the 15 overrides retired
(those partitions now come from source, both periods); 0 regression across 10 controls. See [audit-repricing-lane-2026-07-18](knowledge/audit-repricing-lane-2026-07-18.md).

**Prior-block sweep (2026-07-19).** `check_repricing` read the CURRENT period only, so a wrong
comparative cell was unverifiable by construction (the cross-period anchor compares TOTALS, which
were right). Added `rp_prior_footing` (+ a `check_prior=False` escape). It flagged 9, zero FP:
**8 were our misreads, corrected from source** — TAKAS ×6 (2023: fitz drops a glyph off a printed
2,373,311; 2024: the PDF CONTENT STREAM itself holds only `895,18`, a Word→PDF cell-overflow clip),
ISCTR 2025Q2 (a clipped `)` lost the sign → −452,169,857), and ICBCT 2024Q4 cons (liab row bound one
row down on an inverted values-above-label page — ⚠️ it FOOTED internally, so only reading the page
found it). **2 are filer typos** → `_RP_PRIOR_SKIP`, stored faithfully: TSKB 2022Q1 (its own Q2-Q4
reprint the corrected figure) and ANADOLU 2026Q1 cons (component rows give the true bucket).

**§4 capital/liquidity (2026-06-10)**: full-fleet history backfilled via
`backfill-audit.yml` in 5-bank chunks (`ALL` exceeds the 180-min job timeout).
Per-bank §4 filing quirks and their fixes are catalogued in
[AUDIT_BANK_CATALOG.md](AUDIT_BANK_CATALOG.md); the only standing
capital-quality flags are bank-reported BRSA temporary-measure CARs
(ATBANK 2024, TEB consolidated 2022) — false positives, not parse errors.
Dashboard surfacing (e.g. cross-bank CAR/LCR view) is an open follow-up.

**Audit-lane validation status** — per-lane dated snapshots; each row's notes carry
its latest measurement date. The fleet is now 38 banks, and the equity lane has
1,064 expected coverage cells. Every extracted
statement is self-validated (internal-sum / roll-forward / cross identities); the
`/admin` coverage matrix and the non-destructive re-extract guard both key off this.

**2026-08-07 — relationship enforcement hardened in code (not pushed in this
change).** `registry.validation_gate()` now defines the accounting dependency graph used
by coverage, loader protection, targeted repair and D1/admin metadata. Either BS lane
requires both internal hierarchies plus `A=L+E`; credit-quality and derived stages require
each other. Targeted candidates rebuild stages before validation and remain inside one
savepoint, so `--require-passing` can roll back source, derived and validation rows together.
The formerly separate free-provision alert is now also a per-partition validator: conditional
absence is N/A unless a modified opinion names the reserve. Migration 0041 exposes each gate
to the drawer/future alerts. A read-only dry run against the local 2026-08-05 snapshot found
the expected eight BURGAN recall gaps and no new clean-opinion/prior-chain false positives;
the live snapshot/D1 still need the normal migration + revalidation workflow before those
statuses change there.

| Lane | pass | fail | skip | notes |
|---|---|---|---|---|
| `assets` / `liabilities` / `cross` | 970–974 | ≤4 | 1 | **BS frozen** (correct — don't re-extract) |
| `off_balance` | 966 | **0** | 9 | per-partition validator is **horizontal-only** (TL+FC=Total; parent=Σchildren / TOTAL=Σromans skipped because off-balance skips hierarchy levels → would false-fail). Vertical structure validated **alert-only** via `check_audit_quality._off_balance_consistency`. **2026-06-21: 17→0** via curated `audit_overrides.json` cells (no re-extraction): TEB `(III-2)` cross-ref garble ×8 (restored from 3.1+3.2 children), BURGAN/EMLAK/ISCTR single cells, and ALNTF cross-ref-annotated rows (`III-a-3,i`) fitz-read off the off_balance page (89 rows ×6 partitions, Total-cross-checked). **2026-06-27: 3 more cleared** — ATBANK 2025Q4 dropped roman section I (GARANTİ VE KEFALETLER) re-inserted (Σromans→total), EMLAK 2022Q4 mis-captured grand total corrected to 387,710,554, and the `_off_balance_consistency` Σromans helper now keeps the larger-magnitude row per roman ordinal so a stray bank-name header captured as hierarchy `5` can't hide section V (ISCTR 2025Q4) |
| `profit_loss` | 1049 | **0** | 1 | **frozen** (correct). **2026-07-16: 13→0** — 4 data defects hand-corrected + 9 validator false positives killed. The 9 (DUNYAK ×8, TOMK ×1) were never data errors: `check_pl_chain` hardcoded the standard ordinals (gross VIII / net-op XIII / pre-tax XVII / tax XVIII / cont-net XIX / period-net XXV) and the deduction band `{9,10,11,12}`, but the **compressed template** those participation banks file drops an opex roman — net-op XII, pre-tax XVI, tax XVII, then cont-net XVIII + period-net XXIV (DUNYAK) or cont-net XIX with **no XVIII at all** (TOMK). Each report states its numbering in the formula it prints ("XVI. …VERGİ ÖNCESİ K/Z (XII+...+XV)") and foots under it, so the check was comparing their TAX row to the pre-tax sum — and never really validated their chain. The chain is now assembled **per-partition from anchor rows found by label** (folded: Turkish→ASCII, uppercased, whitespace stripped, since the extractor emits both "DÖNEM NET KARI" and "DÖNEMNETKARI/ZARARI"), deduction band derived from the anchors. Safety: each anchor falls back to its standard ordinal when its label is unreadable (HAYATK's wrapped labels leave XIX as "OPERATIONS (XV±XVI)"), and the template reverts to standard wholesale unless the anchors come out strictly increasing → an unreadable partition behaves exactly as before. Corpus diff old→new over 1050: pass 6205→6227, fail 21→5, skip 74→68 — **0 newly failing, 9 fixed, coverage UP**. The 4 real defects (`audit_overrides.json`): TAKAS 2023Q2/Q3+2024Q3 XXIV printed as a copy of net profit though XX–XXIII are nil → 0 (ODEA precedent); HAYATK 2024Q2 pre-tax captured the dipnot ref "(4.9.)" as its value (4.9) with XVIII/XV dropped by the same wrapped label → −400,486 / 174,727 / 0; TOMK 2023Q4 every "(81)" cell read as a dipnot ref → IV/4.2/4.2.2 restored. `apply_overrides` P&L inserts now take `item_order` — a restored roman appended after XXV falls out of the increasing-subsequence spine and its identity silently **skips** (ANADOLU 2022Q1's appended IV. left VIII=III+IV+V+VI+VII unchecked). **2026-07-02 validator audit:** the net=equity cross-check (`pl_bottomline`) had silently skipped **209/975 partitions** — its label regex missed the English template ("NET PROFIT/LOSS"), the participation word-order ("NET DÖNEM KARI/ZARARI") and empty-label rows (AKBNK 2026Q1) → now falls back to hierarchy (spine roman XXV + row 25.1), coverage 209→0 skips and ~230 newly-run checks pass. `_pl_spine` switched from longest contiguous run to longest increasing **subsequence**, so one misparsed roman (HSBC "XIV."→"X", 28 partitions) no longer hides the XV–XXV tail from the chain (≤4-identity partitions 35→8). The widened checks surfaced 2 real cases: AKBNK 2022Q1–Q3 uncon tail romans shifted one ordinal (net income on XXIV., no XXV.) → fixed via new `pl_rehier` override type (renames only; amounts tie BS 16.6.2 exactly); TSKB 2022Q1 uncon printed P&L net 605,861 ≠ printed BS 16.6.2 605,673 (both faithful, source self-inconsistent) → `_PL_BOTTOMLINE_SKIP` (chain stays guarded). Skip=1 is ICBCT 2023Q2 cons `_PL_SKIP` (source rounding) |
| `oci` | 959 | **0** | 16 | **2026-06-21: 19→0.** `check_oci` drops the noisy deep `2.1.x/2.2.x` sum (net-of-tax rounding + omitted immaterial lines — cash_flow lesson), keeps roman chain III=I+II + section sums (I=Σ1.x, II=Σ2.x) + OCI.I==P&L-net cross. `apply_overrides` gained `oci`/`oci_replace`; EXIM/FIBA/QNBFB had the WRONG statement captured (equity+BS) → full fitz re-read; KLNMA prior-column mis-read fixed; ISCTR 2025Q2 wrong-table + PDF-404 → removed; ATBANK 2023Q4 `_OCI_SKIP` (source sign typo) |
| `cash_flow` | 947 | **0** | 28 | fitz-only; roman-chain-only validator (135→0 on 2026-06-21). Last 1 cleared 2026-06-21: TSKB 2022Q1 cons `_CF_SKIP` — PDF-confirmed source typo (printed V 5,027,208 ≠ I+II+III+IV 5,011,183; VII foots with the derived V) |
| `equity_change` | ~794 | ~168 | 10 | hardened. **2026-06-27: 343→~168.** Root cause for ~52% of the tail was a current/prior **period swap**: `_PRIOR_RX` matched "Önce/Öncesi Dönem" but not "Önceki Dönem" (the standard term), so a bank printing its prior-period matrix FIRST (HSBC) had that page default to `current` → enforce-distinct fallback swapped the periods positionally → stored "current" = prior-year matrix (closing ≠ BS equity, OCI row ≠ OCI statement). One-line regex fix → **HSBC 34/34, +184 of 352 cleared fleet-wide, 0 regressions**. **2026-06-27 (round 2): ~168→~98.** Two more period-assignment bugs: (a) the current page's header says "Cari Dönem" but its OPENING row reads "Önceki Dönem Sonu Bakiyesi", so the PRIOR-first marker test mislabeled the current page as prior (TSKB) → now check CURRENT first; (b) marker-LESS pages (ALNTF prints bare date-keyed rows, no Cari/Önceki word) + prior-first order → positional default swapped → now a year-based tiebreaker (the current table closes on the later period-end date = larger max-year). → **ALNTF 32→0, TSKB 33→15, ICBCT 17→6** (verified prod 168→107). **2026-06-27 (round 3): 107→~91.** (a) `_split_periods` order signal made value-based — in prior-then-current order block1 (prior) CLOSES where block2 (current) OPENS (the totals chain), fixing ANADOLU's mid-page-split swap that the year-text heuristic missed (its year is header-only); (b) `_try_fit` extended to n_cols-2: ANADOLU's consolidated row IV ("Toplam Kapsamlı Gelir") drops two fully-blank component columns → 14 tokens in a 16-col table → was dropped → its total left out of Σromans; two-zero insertion gated by Σcomponents==total AND total+minority==grand. Shipped via `--only-failing`. **2026-06-27 (round 4): equity is now FITZ-ONLY (pdfplumber removed) → 91→85.** GARAN/AKBNK "needed pdfplumber" only because their statement is on a **`/Rotate 90` page** — `fitz.get_text("words")` returns un-rotated bboxes so y-bucketing scrambled the table; fix = `page.rotation_matrix` in `_fitz_page_text` (identity for upright pages). Removed the pdfplumber reconstruction/marker/n_cols reads + the `pdf` param. A full `--force` re-extract converged real failures **91→85** but also over-extracted ISCTR's letter-spacing-corrupted image-only quarters into partial-failing rows (transient 118); a **<14-row guard** (complete statements carry ≥22 rows, broken parses ≤9 — clean gap) drops those incomplete parses so they stay empty/skip → **85** (ISCTR/sparse → 0), verified live. Remaining **85** = genuine per-bank column misalignment / sub-1% chain near-misses (TSKB) / image-only quarters. (OCI still has the same pdfplumber GARAN/AKBNK rotation fallback — open follow-up.) |
| `credit_quality` | 1000 | **0** | 50 | **good** — real reconciliation (section total=S1+S2+S3 + cross-section loans≈S12+NPL); skips gross−prov=net (BRSA collective-reserve noise). **2026-07-16: coverage 2 error / 9 missing → 0/0** (matrix row 1031→1039 ok, n/a 8→11). Missing were ALL one root cause: the `loans_by_stage` ₺1bn Stage-1 floor excluded banks whose loan book is smaller than the floor — the tell was extracted Stage-1 values piling up just above it (1.008/1.011/1.041/1.103bn) and the same bank appearing only once it grew past (COLENDI ₺610m out → ₺1.04bn in). Floor replaced, in a fallback that runs only when the strict pass finds nothing, by an anchor on the unambiguous §7.2 section title → COLENDI ×3 + TOMK 2024Q2 + ZIRAATD ×2 recovered, each footing EXACTLY to its BS `Krediler` line; 200/200 existing rows byte-identical (incl. SKBNK 2024Q4, whose p89 §4 "Loans Under Follow-Up" table is the one false positive the floor was really catching). Errors were DUNYAK 2026Q1 cons/unco: note 8.4 prints a '-' in the Toplam column, which `parse_num` mapped to a fabricated 0.0 → now stored NULL (a nil total beside non-nil stages is arithmetically impossible = not disclosed). TOMK 2023Q3–2024Q1 → N/A (zero loan book, no loans note filed) |
| `stages` | 1030 | **0** | 20 | **2026-07-17: 12 → 0 errors, N/A 11 → 3** (coverage `1047 ok / 0 err / 0 miss / 3 n·a` — **lane complete**; see [audit-stages-lane-to-zero-2026-07-17](knowledge/audit-stages-lane-to-zero-2026-07-17.md)). The `stages_bs_loans` reconciliation (stages total ⋈ BS 2.1) flagged 9 cells, **6 of which passed every other check** — proof the internal identity `total=S1+S2+S3` cannot see an error that preserves the sum. FIBA ×9, three causes: 2022Q4 read the **collateral-type** table (note 5(8) p52) not §5.2 (p88), taking col0 as S1 and summing cols 1–3 as S2 (`18,574,043+3,248,468+3,540,679=25,363,190`, exact) — mixing **current and prior across two portfolios**, a value appearing nowhere in the PDF, winning on first-wins dedup; 2025Q2's real §5.2 (p61) is **vector-outlined** so it fell through to p62, a **day-count ageing** table (the extractor's own docstring cites that row as its motivating example); and ×6 were **real printed data curated "not disclosed"** on an empty `get_text()` (p58 a bitmap, the rest vector outlines — §5.10 is a red herring, the stage table is **§5.2**). Proven by a closed identity, not a band: **S1+S2+S3−faktoring = BS 2.1 exact to the lira** on all nine (the §5.2 Toplam includes factoring per its own `(*)` footnote; BS 2.1 carries it at 2.3), which **predicted S3 before the page was rendered** on four; FIBA's own printed ratios corroborate (%1,68→1.68%, %1,09→1.09%). SKBNK ×5 + EMLAK 2022Q3 grabbed the **§4 c.4.3 NPL-by-sector** table — SKBNK 2025Q4's `1,003,122` was **synthesised** (S3 Provisions + Write-Offs) and published **NPL 39.51% vs a truth of 1.29%**. The 3 zero-pass cells (DUNYAK 2023Q4 / HAYATK 2023Q3 / ZIRAATD 2026Q1) were all faithful — verdict fixed, not data. **N/A 11→3:** ICBCT 2023Q4 cons + TSKB 2026Q1 unco were **false claims about the bank** — both re-fetched (ICBCT: we configured the IR page's `Mali Tablo` tables-only link instead of its `Dipnotlar` link, 9pp vs the real **108pp**, whose own BS carries a `Dipnot / (Beşinci Bölüm)` column with **39 cross-refs** into a section it lacked; TSKB: R2 held a **KAP XBRL rendering**, not the report — PwC's own opinion *inside our copy* cites *"beşinci bölüm"* and *"ilişikte yedinci bölümde"*; the configured URL already served the real **100pp**). Both now reconcile at ratio **1.0000**. Remaining 3 = TOMK, N/A **confirmed on a positive citation**: a BDDK-approved **TFRS-9 non-applier** (*"…dokuzuncu maddesinin altıncı fıkrası kapsamında TFRS 9'un değer düşüklüğüne ilişkin hükümlerini uygulamama konusunda BDDK'ya başvuruda bulunmuş ve Banka'nın talebi kabul edilmiştir… 31 Aralık 2025 tarihine kadar"*) — no ECL model, so no stage table can exist. Also fixed: `build_bank_audit_stages.py`'s comment said *"when all three present"* but the code said **`any`**, so with S1+S2 absent `total` collapsed to S3 and the row asserted **NPL 100%** — **161 of 836 prior rows**, now 0 (latent not live: 0 current rows, and every consumer filters `period_type='current'` — but `bot-sql.ts` lets an LLM write its own SQL). Earlier that day: the `credit_quality` floor fix carried missing 14→5; then all 10 then-remaining fails — one class, `stages_stage3_missing` + one `stages_npl100` — were cleared by curated `audit_overrides.json` cells (new `credit_quality` override type; upserts `npl_brsa_gross`). Root cause: these banks disclose Stage 3 as **PROSE, not a table** ("Donuk alacak tutarı 2 TL'dir" / "Bulunmamaktadır" / "None"), which no table-anchored extractor can read — so S3 stayed NULL. Every value is SOURCED from the sentence and cross-checked against the BS `Donuk Alacaklar` line (TOMK 24Q2=2, 24Q3=4.406, 24Q4=177.537; COLENDI/ZIRAATD/DUNYAK=0). **`stages_npl100` caught a real bug**: DUNYAK 2023Q4 stored 6.077 = "Dönem İçinde Tahsilat (-)", a collections FLOW, as the NPL stock — p58 foots 6.075+2−6.077=0 and the BS current column is dashes → corrected to 0 (was live wrong data). Cells now show **manual** (10 on the credit_quality row), not ok — `_STMT_TO_KEY` learned `credit_quality` so a human-transcribed figure can't read as machine-extracted. NPL=100% **fixed end-to-end 2026-06-15**; residual 15 cleared 2026-06-21 (credit_quality fitz migration + per-bank `loans_by_stage` cluster fixes). (1) Validator: the NPL=100% fingerprint required stage1/stage2 non-null but the broken shape has them NULL → it skipped all 45, which showed green; now NULL counts as 0 → 45 surfaced. (2) Extractor (`credit_quality.loans_by_stage`): captured the §7.2 Stage-1/2 table on 3 column-split variants (İşbank EN/no-space coord fallback; ANADOLU wrapped header → Stage-2-only anchor; TSKB label/number y-offset → 5.5px cluster). Re-extracted 6 banks → rebuilt derived stages → **43 of 45 repaired** (npl100 45→2). Remaining 2 = FIBA + TFKB image-only quarters |
| `capital` | 842 | **0** | 133 | validator **hardened 2026-06-15** (composition Tier1=CET1+AT1, Total=Tier1+Tier2 + sub-ratios CET1/Tier1/CAR=component÷RWA). **2026-06-21: 26→0** via `audit_overrides.json` (apply_overrides now patches `bank_audit_capital`): the failures were real §4 mis-extractions recovered from the identities (passing ratios confirm the kept components) + PDF-confirmed — AT1 dropped→Tier1−CET1 (ICBCT/QNBFB/TSKB), Tier2 dropped/slipped→Total−Tier1 (QNBFB/ISCTR/SKBNK), AKTIF total misread→Tier1+Tier2, ISCTR 2025Q1/Q2 RWA column-slip→real RWA + ratios. **2026-06-27: EMLAK 2022Q1 cons/uncon AT1 (Türkiye-Varlık-Fonu instrument) dropped → derived from Tier1−CET1; EMLAK 2025Q1 cons RWA read into total_capital → restored ÖZKAYNAK 28,781,229 + RWA 125,508,698 (22.93%=reported CAR). Also the alert-only `check_audit_quality` capital reconcile was made forbearance-aware: banks reporting a BDDK transitional-adjusted CAR (ATBANK, ICBCT, ANADOLU — printed capital/RWA ≠ reported ratio) no longer false-fail; it now reconciles the bank's OWN reported ratios to each other (8% band) instead of to printed RWA**. **2026-07-17: 26 → 0 — LANE COMPLETE** (coverage `996 ok / 54 manual / 0 err`; all fixed manually from the printed §4 tables, pixel-verified). Two shapes: 13 REAL failures (dropped fields / misreads) and 13 zero-pass cells (tier1 + ratios dropped → validator could verify nothing). **TOMK ×10** — `total_rwa` dropped on 2024Q1-2026Q1 (the label changed to lowercase "Risk ağırlıklı Tutarlar" which the anchor missed) + 2024Q1's Tier-2 (7,793) dropped because the filing misprints its own "Katkı Sermaye Toplamı" subtotal as "-"; RWAs filled from source, all reconcile. **HAYATK ×10** — dropped Tier1 (= CET1, AT1=0) + all 3 ratios; read from the printed table (English), every one reconciles, no forbearance. **ISCTR 2024Q1 cons** — the value column printed SHIFTED UP one row, so Tier1 was stored as AT1 and Total-equity as Tier2; full rewrite (CET1 294,633,433 / Tier1 311,532,076 / ratios 13.54/14.32/17.33). **TSKB ×2** — Tier1 + ratios. **DUNYAK 2023Q4** — the premise inverted: total 572,014 was CORRECT (a real ₺500m sukuk Tier-2); the wrong cell was tier2 (88 → 500,088) + CAR (→ 263.75%); the filing's own subtotal cells drop the 500,000 while its ÖZKAYNAK row and CAR include it. **ENPARA 2025Q4** — NOT a data error: the composition gap (247,745) is a printed BDDK forbearance add-back ("Kurulca belirlenecek diğer hesaplar"), no schema column for it → curated in `_CAP_SKIP`. **The `cap_car_band` [5,80] check was too tight for new banks** — newly-licensed banks hold capital far above their tiny RWA, so CARs of 85% (ZIRAATD), 93.75% and 138.08% (TOMK 2023Q3/Q4) are GENUINE and reconcile exactly; the band now DEFERS to reconciliation (a CAR that ties to Total/RWA is verified, so the band only guards an un-reconcilable one) — cleared TOMK 2023Q3 + ZIRAATD with no data change. Every §4 capital-override cell now reads `manual` (`_STMT_TO_KEY` learned "capital", 54 cells) instead of a machine `ok` |
| `liquidity` | 945 | 0 | 30 | §4 backfilled; per-partition validator is **band-only** (ratios only, nothing to reconcile). Validated instead by a **within-bank time-series outlier scan** (`check_audit_quality._liquidity_outliers`, ≥8× = order-of-magnitude slip; covers `lcr_fc`, which the band check never read). **Verdict 2026-06-15: leverage / LCR / NSFR clean fleet-wide; only error = FIBA `lcr_fc` 2024Q1 unco + 2024Q2 unco/cons (~1.1 vs the bank's ~430)**. **2026-06-27: FIXED** — root cause was `_parse_ratio` reading the TR-thousands `1.158,00` (=1158%) as `1.158` (it assumed EN format when both `,` and `.` were present); now the rightmost separator is the decimal. Re-extracted → lcr_fc 1158/1080/1096. **2026-07-17: 24 err + 1 miss → 0/0 — LANE COMPLETE** (coverage `1046 ok / 4 manual / 0 err / 0 miss`; all fixed manually from the printed §4 tables). Three shapes, mostly BANDS TOO TIGHT FOR NEW BANKS: (1) **leverage band widened (0,30) → (0,100)** — a newly-licensed bank is almost all equity, so leverage runs 30-97% (HAYATK 97%, ENPARA 95%, TOMK 93%), each confirmed against Tier1/total-assets; all 18 leverage>30 cases were genuine, cleared with no data change (leverage ≤ 100% is the real bound). (2) **LCR upper bound (0,2000) REMOVED** — BDDK's LCR is the average of WEEKLY ratios, so a near-zero-net-outflow bank genuinely prints LCRs in the thousands-to-MILLIONS of % (COLENDI 2025Q2 = 2,316,303%, ENPARA 34,221%, DUNYAK 17,858% — all pixel-verified against the printed row), and a misread HQLA amount OVERLAPS that range exactly (COLENDI's real weekly-max was 9,878,895%), so no ceiling can separate them; the ratio just has no upper limit. Verified NO established bank has LCR>2000 (all six are new banks). (3) **TAKAS NSFR** — dev/investment banks are EXEMPT from the 100% NSFR floor ("kalkınma ve yatırım bankaları … asgari %100 oranını sağlamaktan muaftır"), so its 44-49% NSFR is legit; the `liq_ratio_low` (<50) heuristic false-flags it → curated `_LIQ_SKIP` (2024Q1/Q3/2025Q2). Data fixes: **TOMK 2023Q4** lcr 3.768 → 3768.83 (comma-as-decimal misparse — the one real LCR bug); **TAKAS 2024Q3/Q4** nsfr 38.39 → 49.16/54.72 (the extractor grabbed the STALE 31-Dec-2023 prior-period table); **HAYATK 2023Q2** (missing) → leverage 97.5 filled (LCR/NSFR genuinely N/A: "the Bank has not yet commenced banking activities"). All 4 override cells read `manual` (`_STMT_TO_KEY` learned "liquidity") |
| `npl_movement` | 641 | **0** | 334 | **2026-06-21: 126→0** (FX "Kur farkı" row + closing-vs-`npl_brsa_gross` cross-check skip-if-bottom-line-right + HALKB total-block extractor fix + PASHA outflow-magnitude `abs()`). **2026-06-27: a later `npl_movement_balance_missing` check surfaced 14 (BURGAN-cons, EXIM/ODEA/QNBFB-uncon) where the opening row was unmatched → block started on Additions → opening NULL → roll-forward couldn't tie. Fixed: opening-label variants ("Ending Balance of Prior Period", "Balance at the End of the Previous Period"), `_DATE_BALANCE_RX` relaxed for ODEA's space-glued "31 Aralık 2021Bakiyesi", and the wrapped-label merge extended to closing/provision/net rows + "Performing Loans" transfer-continuations (QNBFB) → 14→0**. **2026-07-17: 13 err + 43 missing → 0/0 — LANE COMPLETE** (coverage `999 ok / 9 manual / 0 err / 0 miss / 42 n·a`; see [audit-npl-movement-lane-to-zero-2026-07-17](knowledge/audit-npl-movement-lane-to-zero-2026-07-17.md)). The mirror of the 2026-06-27 fix, on the CLOSING side: **HAYATK ×12** print `"Ending balance of the current period"` — the one "ending balance …" word order `_ROW_LABELS` never learned (it had BURGAN's `"ending balance of prior period"` → *opening*; the closing counterpart was never added). `startswith()` matching made it unreachable from every other closing entry, and the bare `("current period", …)` fallback can't help — the line CONTAINS but doesn't START with it. The article is load-bearing: `"ending balance of current period"` would still miss. HAYATK was the entire corpus story (66 rows/12 partitions; all 4,281 other rows already had closing). **Natural experiment:** 2025Q2 cons is HAYATK's only TURKISH report ("Dönem Sonu Bakiyesi") and the only consolidated period that passed — the 12 failures are exactly the English reports. Values TRANSCRIBED, not derived: closing is over-determined (roll-forward; net+|provision|; prior-closing==current-opening), so filling it from our own arithmetic would make the roll-forward check **tautological** — the fx `net_position` flaw. 13/13 match the page; the derivation agreed 39/39 but agreement was the CHECK, not the source. Corroborated against a *different* note and the BS: printed closing III+IV+V 506,844 = `npl_brsa_gross` 506,844; stage1 13,072,410 + stage2 193,657 + NPL = 13,772,911 = BS 2.1. `fx_diff` NULL is FAITHFUL (HAYATK prints no FX row). **ZIRAATD 2026Q1** is the mirror-of-the-mirror — *opening* NULL on its first-ever NPL quarter, cells printed genuinely blank (not even the '-' every other row carries) → no numeric tail → row skipped; opening=0 SOURCED from prose `"(31 Aralık 2025: Bulunmamaktadır)"`, closing (52) left as extracted so the roll-forward stays a real test (0+52=52; net 42+prov 10=52). Override not code: the blank-opening shape only occurs in a bank's first NPL quarter, and `npl_movement.py:358` records that a broad numberless-opening merge CORRUPTS GARAN/TSKB. **The 43 missing: 42 genuinely N/A + 1 real gap** — all verified by language-agnostic full-document sweeps + bitmap/vector detectors, each with a verbatim citation (TAKAS ×16 *"Toplam donuk alacak hareketlerine ilişkin bilgiler: Bulunmamaktadır"* — and ⚠️ the intuitive "a CCP's loans are money-market placements" story is FALSE: they earn loan interest, are 100% Mali Kesime Verilen Krediler, and ₺6.58bn of 9.63bn is lent to its own clearing-member shareholders — real credit that never defaults; DUNYAK ×8, HAYATK ×5, ENPARA ×3, COLENDI ×3, ZIRAATD ×2, TOMK ×5). The 1 gap is **COLENDI 2026Q1** (first NPL, ₺26,725 = 2.50%), printed at p49 and hidden by **three** independent defects — `_HEADING_RX` misses "Information related TO non-performing loans" (no "movement"); the text layer is **cell-per-line** so `_THREE_NUMS_TAIL` matches ZERO rows even with the gate bypassed (needs x-coord assembly — same class as the `loans_by_stage` §7.2 gap); and closing reads "Balance at the end of period" (no "the"). Curated; ⚠️ **recurs every quarter** until defect 2 is fixed. Also: `_STMT_TO_KEY` learned `npl_movement`, so 9 hand-curated cells (FIBA ×6, COLENDI, ZIRAATD, AKTIF) now read **manual** instead of a machine-extracted `ok` |
| `loans_by_sector` | 171 | **0** | 804 | **annual-only** disclosure (interim has no table). **2026-06-21: 36→0.** YKBNK (22) extracted the WRONG table (capital/equity rows) — locator missed "Information ACCORDING TO sectors and counterparties" + false-matched the risk-profile/investments tables (fixed + sector wordings). The rest were per-bank multi-column structures, fixed by rewriting the parse to **x-coordinate column alignment** (`_extract_section_xy`): align each row's numbers to the Stage 2/Stage 3 header columns by word x-position; recognise "(Second/Third Stage)" + Turkish İkinci/Üçüncü; `_pick_total` chooses the total that foots when a page has two tables (ICBCT); keep whichever parse (aligned vs text) FOOTS better → no regression. Also `\d{1,4}` leading group for a missing-comma typo "1466,551" (ICBCT 2025Q4). **2026-07-17: 6 err + 7 miss → 0/0, plus 6 silent-wrong `ok` cells corrected — LANE COMPLETE** (coverage `223 ok / 9 manual / 0 err / 8 miss / 810 n·a`; see [audit-loans-by-sector-lane-to-zero-2026-07-17](knowledge/audit-loans-by-sector-lane-to-zero-2026-07-17.md)). **TAKAS ×4** stored an average VALUE-AT-RISK (`Toplam Riske Maruz Değer`) as a loan sector total: the heading regex matched the note that DECLARES ITSELF NIL ("Önemli Sektörlere… Bulunmamaktadır"), found no rows, and the GARAN-split retry appended the next page (§III market risk). Fixed with `_is_nil_declared_note` (a heading answered Bulunmamaktadır/None is skipped) — proven NEUTRAL on 6 varied banks (extractor with-vs-without = identical counts); TAKAS → 0 rows → N/A with citation. **TOMK 2024Q4** → `_LBS_SKIP`: the source itself prints "Hizmetler -" while its only child Mali Kuruluşlar carries 85.003, and the bank's own Toplam includes it — a source defect, not ours. **7 missing → N/A** (COLENDI/DUNYAK×2/ENPARA/HAYATK/TOMK/ZIRAATD), all verified with citations — and four turned out to be **TFRS-9 non-appliers** (DUNYAK/ZIRAATD/COLENDI + the known TOMK), each wording the art. 9/6 exemption differently. **⚠️ ALNTF ×8 N/A was FALSE** — it discloses stage-by-sector in all 8 reports; the captions are legacy ("Değer Kaybına Uğramış"/"Tahsili gecikmiş") but the NUMBERS are the stages (sector TOPLAM = the report's own "Yakın İzlemedeki"/"Takipteki" stage note to the lira), and ALNTF states it APPLIES TFRS 9 — so `_is_legacy_pastdue_table` fires correctly but its PREMISE is false. Removed the false N/A; the 8 cells now read honest `missing` (disclosed, our extractor skips legacy captions — extractor enhancement is a follow-up). **Two new zero-FP checks: `loans_sector_year_swap`** (this year's total ≠ last year's to the lira — footing is BLIND to a wholesale year-swap; ICBCT 2023Q4 stacks two DATED tables so the period never flips and _dedupe backfilled dropped current rows from 2022 → unconsolidated read a flawless `ok` while storing its own 2022 total, Stage 3 understated 3.1×; calibrated 2/236, both ICBCT) and **`loans_sector_child_exceeds_parent`** (a child sector can't exceed its group total — a mathematical invariant catching merged-label corruption footing misses; surfaced 8 partitions). Both are validation-only. **9 partitions hand-transcribed** off the printed page (ICBCT ×7, AKTIF ×2), every cell 7–13× pixel-verified and foot-checked, via a new `loans_by_sector_replace` override + `_STMT_TO_KEY` entry so they read `manual`; each corrected a silent live-wrong figure (e.g. AKTIF 2025Q4 `agri_fishery` 60,627→0, ICBCT 2022Q4 `agri_fishery` 635,214→0 — prior-year Sanayi totals y-bucketed onto nil children). Root cause is the shared `_fitz_page_text` y-bucketing (`int(round(y0))` aliasing a 3.4pt intra-row offset), unfixable without touching every frozen statement lane — hence overrides. ⚠️ **A `--force` whole-lane re-extract regressed AKBNK/DENIZ mid-session and was reverted from the R2 snapshot** — `--force` re-extracts under current code over rows frozen by older code; never use it lane-wide as a calibration |

**Equity repair — live D1, 2026-08-06.** Coverage moved from **892 ok / 128 error /
44 missing** to **970 ok / 51 error / 43 missing**. Two snapshot-backed, guarded
waves repaired **78 partitions** in total: wave 1 admitted 63 of 170 candidates and
wave 2 admitted 15 of the remaining 107; every other candidate was rolled back.
Both production runs used `only_failing=true`, `force=false`, and
`require_passing=true`, so only partitions with at least one passing check and zero
failures were atomically replaced. The authoritative R2 snapshot was last refreshed
at **22:10:04 UTC**. Live validation independently reports **970 passing / 51 failing
/ 41 unvalidated**.

Wave 1 fixed the 2026Q2 footnote/value ambiguity (AKBNK parenthesised movements;
PASHA dotted `(5.5.3)` reference). Wave 2 fixed three more source-proven shapes:
closing-row dipnot `(V)` misread as roman V (VAKIFK), prior-first single-page blocks
without date labels (ANADOLU and related layouts), and a clipped consolidated total
recoverable from both component and minority/grand-total identities (TSKB). The 15
wave-2 partitions are ANADOLU ×4, TAKAS ×4, VAKIFK ×4, QNBFB, SKBNK, and TSKB.
Dry-run/production: Actions `31128759982` / `31128789928`; code `2e07c11`.

The **51 remaining errors are explicit residuals**: 26 dropped-cell, 14 missing-row,
and 11 column-slip partitions (largest banks: TSKB 13, ANADOLU 6, FIBA 5, EMLAK 4).
Representative source traces show clipped/merged component cells whose row and
cross-statement identities detect the loss but cannot determine the correct component
column; filling the arithmetic remainder would make validation tautological. The 43
missing cells are concentrated in ISCTR 33 and FIBA 6, plus TSKB 2 / ATBANK 1 / TFKB
1; TSKB's two 2026Q2 objects are invalid KAP notifications rather than statements.
These require x-coordinate or curated source-backed work, not a wider force run.

## Bank-type taxonomy

Monthly `bank_type_code` (per the `bank_types` table) gives TWO overlapping
partitions of the sector — never add across them:

- **By type** (= Sector 10001): Deposit (10002) + Participation (10003) + Dev&Inv (10004)
- **By ownership, all types** (= Sector 10001): Private/Yerli Özel (10005) + State/Kamu (10006) + Foreign/Yabancı (10007)
- **Deposit-only ownership**: Deposit-Private (10008) / Deposit-State (10009) / Deposit-Foreign (10010)

`10006` "State" therefore spans every type — it includes state-owned
participation (Ziraat/Vakıf/Emlak Katılım) and development banks (Eximbank,
Kalkınma, İller), not just the three state deposit banks (those are `10009`).
The **weekly** bulletin numbers the same groups differently — see METRICS.md §2.

## Storage map

| Bytes | Where | Mutated by |
|---|---|---|
| `evds_series`, `balance_sheet`, `weekly_series`, `bank_audit_*`, … | Cloudflare D1 (`bddk-data`) | weekly + daily cron |
| `<ticker>/<TICKER>_<period>_<kind>.pdf` | Cloudflare R2 (`bddk-audit-reports`) | `refresh-audit.yml` during filing windows; `acquire-audit.yml` manually |
| `state/bddk_data.db.gz` | Cloudflare R2 (same bucket) | bulletin/EVDS cron (bulletin lane snapshot) |
| `state/bank_audit.db.gz` | Cloudflare R2 (same bucket) | `refresh-audit.yml` after a changed automatic/manual run — the audit-lane snapshot writer |
| `state/history/<lane>-YYYYMMDD.db.gz` | Cloudflare R2 (same bucket) | every cron — dated backup, last 7 kept |
| Next.js page-data cache | Cloudflare KV (`NEXT_INC_CACHE_KV`) | dashboard render (1h TTL on D1 reads) |
| `data/banks/audit_report_urls.json` | git | hand-edited via PR |
| `data/banks/bddk_bank_list.json` | git | hand-edited via PR |
| `src/`, `scripts/`, `web/` | git | hand-edited via PR |

## Active workflows

Two independent ingestion lanes (separate staging DB + R2 snapshot +
concurrency group), so audit failures can't stall the bulletin pipeline:

- `.github/workflows/refresh-evds-daily.yml` — Sun–Fri 05:00 UTC. Polls EVDS daily/workday series only; slow-frequency EVDS and all unrelated loaders wait for Saturday. If SQLite is unchanged, D1 and R2 are untouched.
- `.github/workflows/refresh-bddk-bulletins.yml` — 13:00 UTC on the first/last five days (monthly-only) + Fri 13:30/15:30 UTC (weekly-only). The redundant Sat 02:00 backstop is removed because `refresh-data.yml` follows at 03:00. This workflow now explicitly skips every non-BDDK loader and writes nothing on a byte-stable result.
- `.github/workflows/refresh-data.yml` — Sat 03:00 UTC. Full catch-up: monthly + weekly BDDK + all EVDS frequencies + TBB/TKBB/KAP/TEFAS/Faaliyet. TBB, TKBB, TÜİK and KAP now preserve identical rows instead of refreshing their write timestamps, so the no-change gate can actually fire. It batches the changed rows and snapshot once; a quiet run has no D1/R2 write. *(Audit remains its own workflow.)*
- `.github/workflows/backfill-tefas.yml` — manual dispatch only. Resumable ~5-year TEFAS history backfill (the API rejects start dates older than 5 years; 28-day windows, rate-limited ≈2–2.5 h; re-dispatch with the same `from` to resume — completed windows are skipped via `tefas_fetch_log`).
- `.github/workflows/repair-loans-zeros.yml` — manual dispatch only, `dry_run=true` by default. Repairs the falsy-`or` zero loss in `loans` (see `scripts/repair_loans_zeros.py`): a reported 0 was discarded and stored NULL in the five `or`-chained columns. Re-derives from `raw_api_responses` (no re-fetch) — ~44k cells / ~30k rows measured. Idempotent: fills NULLs only, and refuses to overwrite a non-NULL value that disagrees with the raw JSON (that would be a different defect, and it reports rather than rewrites). Stamps `downloaded_at` on changed rows only so the D1 push stays scoped. Scraper fixed 2026-08-01 (`first_val`), guarded by `tests/test_bddk_api_scraper.py`.
- `.github/workflows/backfill-nonbank.yml` — manual dispatch only. One-time historical backfill of the non-bank sector lane (leasing/factoring/financing) from `from_year` (default 2020 = banking-aggregate horizon) → now (~5–10 min). The incremental refresh rides the Saturday `refresh-data.yml` non-critical `update_nonbank.py` step; this workflow is only for the initial history load. Apply migration 0013 (via a `web/**` deploy) before dispatching.
- `.github/workflows/refresh-presentations-weekly.yml` — Sat 06:00 UTC. `scripts/update_presentations.py` → `bank_earnings` (IR presentation decks) → D1 (`--only-tables=bank_earnings`). Bulletin lane (`bddk-pipeline` group), rides the shared snapshot. Tier-1 results filings instead ride the daily `refresh-news-daily.yml` (classified in `sync_news.py`). Apply migration 0015 (via a `web/**` deploy) before the first push.
- `.github/workflows/refresh-transcripts-weekly.yml` — **manual dispatch only, no `schedule:` yet.** `scripts/update_transcripts.py` → `bank_call_transcripts` (earnings-call transcripts for the 8 listed banks that hold an English call) → optionally D1 (`--only-tables=bank_call_transcripts`). Bulletin lane (`bddk-pipeline` group), rides the shared snapshot. The missing cron dates from the 2026-08-01 freeze (`gh workflow disable` leaves no trace in git, so a workflow shipped with a schedule is born **enabled** — dispatch-only was the inert-by-construction choice). The freeze has since lifted; the absent cron and the `push: false` default are now simply a decision nobody has taken. Add `schedule: "0 7 * * 6"` and flip `push` to turn the lane on; a run without `push` ingests and re-uploads the snapshot without touching D1. Inputs use an explicit `ALL`/`NONE` bank sentinel (a blank dispatch input arrives as the default, not empty). Apply migration 0036 (via a `web/**` deploy) before the first push.
- `.github/workflows/refresh-advertised-rates.yml` — Mon 06:00 UTC. `python -m src.rates.scraper` → `bank_advertised_rates` → D1 (`--only-tables=bank_advertised_rates`). Bulletin lane (`bddk-pipeline` group), rides the shared snapshot (re-gzips it explicitly — this lane doesn't run `refresh.py`, which is what VACUUMs+gzips for the other refresh workflows). Migration 0023 applies via the `web/**` deploy that ships it.
- `.github/workflows/refresh-calendar.yml` — 1st of month 06:00 UTC. `python -m src.release_calendar.scraper` → `release_calendar` → D1 (`--only-tables=release_calendar`). Scrapes TCMB's published "MPC Meeting and Reports Calendar" (rate decisions + minutes + Inflation Report + Financial Stability Report) so the **Ahead** strips fill themselves; retires the hand-typed `MPC_DATES` (now a render-time fallback, still guarded by `check_calendar_fresh.py`). `requests`+`lxml`, no browser — same `www.tcmb.gov.tr` host the news lane scrapes. Bulletin lane (`bddk-pipeline` group), re-gzips the snapshot explicitly. Migration 0025 applies via the `web/**` deploy that ships it.
- `.github/workflows/refresh-audit.yml` — daily during earnings windows (Jan 20–all February, Mar 1–15, Apr/Jul/Oct 20 through May/Aug/Nov 20) plus manual dispatch. It discovers and validates new PDFs, extracts pending partitions immediately, rebuilds stages/validation/coverage locally, sends one registry-derived audit batch to D1, then uploads the snapshot. A no-change run stops before all writes. Own DB/snapshot/group remain `data/bank_audit.db`, `state/bank_audit.db.gz`, `bddk-audit`; targeted `/admin` re-extraction is unchanged.
- `.github/workflows/reextract-statement.yml` — manual dispatch. Targeted single-statement re-extract via `scripts/reextract_statement.py`: pull snapshot → resolve the registry lane → re-extract its source disclosure → rebuild any dependent derived rows → inline-validate the complete relationship gate → push only factually changed tables to D1 → snapshot → refresh coverage. Shares the `bddk-audit` group. Inputs: `statement`, `banks`, `periods` (blank=all), `only_failing` (default true — selects a partition when any required non-conditional gate is not a proven pass), `require_passing` (default true — rolls source + derived + validation back together unless the whole gate passes), and `dry_run` (pulls the authoritative snapshot, then performs no D1/R2 writes). No-op tables retain their timestamps and are not pushed. This is the lane used to fix OCI/CF/NPL fleet-wide.
- `.github/workflows/audit-triage.yml` — manual dispatch, **read-only**. Diagnoses the failing partitions rather than re-extracting them: `scripts/triage_partitions.py` assigns each a deterministic CAUSE from the PDF (`dropped_cell` / `missing_row` / `column_slip` / `wrapped_cell` / `anchor_miss` / `drawn_page` / `rotated_page` / `wrong_pdf` / `unit_switch` / `source_defect` / `unclassified`), with the page and the printed token behind it; `scripts/watch_cross_period.py` compares each partition to the same bank a quarter earlier. No model is called, no figure is produced, and nothing is written anywhere — no D1, no row update, no snapshot re-upload — so it is unaffected by the write freeze. Reports come back as a build artifact. Engine + taxonomy in `src/audit_reports/triage.py`, pinned by `tests/test_triage.py`; findings in [knowledge/2026-08-02-audit-triage-engine.md](knowledge/2026-08-02-audit-triage-engine.md). First full run over all 212: `column_slip` 61, `dropped_cell` 46, `anchor_miss` 45, `unclassified` 26, `missing_row` 26, `rotated_page` 7, `drawn_page` 1 — and `source_defect` **zero**, so nothing in the corpus currently qualifies as "the filing itself doesn't foot". **Two extractor fixes recorded, neither applied** (they change the extractor, and re-extraction writes rows): `audit_opinion.extract_opinion_from_pdf`'s `max_pages=6` misses the signature on pp7–9 for **43** partitions (6→10 clears all of them), and §4 capital never reads the prior `additional_tier1_capital` column for **9** (EMLAK + QNBFB). The ~114 equity_change failures are grouped but **not** diagnosed — the obvious "missing closing row" theory is refuted at corpus scale (absent from 37% of failing and 36% of passing partitions).
- `.github/workflows/analyst-daily.yml` — **manual dispatch only, no `schedule:` yet** (the freeze that originally forced artifacts-only has lifted; the workflow now carries a D1 push step gated on its `push` input, off by default — without it, everything leaves as run artifacts). The analyst layer over the audit snapshot: `scripts/analyst/detect.py` runs the deterministic detectors (reporting-unit switch, cross-period restatements — the ones the validators deliberately skip-list get *reported* here with `documented: true` — opinion type/category changes via the bilingual basis-text classifier at 95% non-other coverage, `disc_net`/cons-gap perimeter changes, and the two feasibility-verdict divergences CAR−CET1 and NPL-vs-coverage), stages signals + basis metadata into `data/analyst.db`, then `web/scripts/analyst-run.ts --memo` assembles the 11-section deterministic view (`web/app/lib/analyst/` — coverage mix-vs-erosion decomposition precomputed), writes memos with the free-model chain and drops any paragraph whose figures aren't in the data block it was shown (`unsupportedFigures`). `banks=CALIBRATE` = the ALBRK+SKBNK feasibility pair. Corpus run 2026-08-04: 455 signals in 0.2s — unit-change silent fleet-wide, cross-period 69 (fx anchor reproduces the validator skip-list 7/7 comparable), divergence 287, opinion 67, perimeter 32. Migration `0037_analyst_signals.sql` **applied** — `analyst_signals` (455), `analyst_basis_metadata` (1,050) and `analyst_notes` (2) are live in D1; the cron remains a decision not yet taken. Build plan + as-built corrections: [knowledge/2026-08-04-analyst-build-plan.md](knowledge/2026-08-04-analyst-build-plan.md). Same-day evolution into a **full 13-section research report** (~2,400 words, tables; benchmarked figure-for-figure against an external GARAN deep-research doc): ranked STORY GATES (a deterministic editorial layer — six stories ruled LIVE/DEAD with numeric reasons; the LEAD must headline), precomputed comparisons/growth-%/totals (every hand-derivation the model attempted became a supplied figure), a relation verifier (drops a wrong direction word between two right numbers), named peer table + BDDK sector aggregates, per-stage GROSS ECL expense (sums reproduce disclosed figures), verbatim management commentary from `bank_call_transcripts` (executive turns only, claims-not-data framing), **per-bank stage definitions extracted from the prose corpus** (24/38 banks' own disclosed thresholds, generated module `web/app/lib/analyst/stage-definitions.ts` — the feasibility test's #1 missing dataset), hash-gated regeneration (`data_hash` per note; staging `data/analyst.db` persists via R2 `state/analyst.db.gz`), and `scripts/analyst/score_reports.py` (structure/lead/coverage scoring over run artifacts). Memo lane LLM: PAID `deepseek/deepseek-v4-flash` (user-authorized, Baidu-pinned, seeded) → free OSS fallbacks; nemotron excluded (reasoning-leak).
- `.github/workflows/analyst-research.yml` — **manual dispatch only, ARTIFACT-ONLY, evaluation phase** (Analyst V2, [ANALYST_V2.md](ANALYST_V2.md)). Scout → typed-tool research loop → deterministic verifier; structured findings with stable evidence ids; abstention first-class; no D1 writes, no schedule, no automatic publishing; V1 (`analyst-daily.yml`) remains the regression baseline. First cold scout run on ALBRK 2025Q1 surfaced the free-provision fingerprint (Other Provisions −6.7bn, Other Operating Income +6.1bn, the −7.7bn equity movement) with zero bank-specific logic.
- `.github/workflows/backfill-audit.yml` — manual dispatch. Full re-extract (all statements) of named banks via `backfill_extraction.py` (`ALL` exceeds the timeout → 5-bank chunks).
- `.github/workflows/purge-partition.yml` — manual dispatch. Removes one `(bank, period[, kind])` from the lane via `scripts/purge_partition.py`: pull snapshot → delete locally → delete in D1 → **re-upload the snapshot** → coverage re-sync. Clearing D1 alone does not stick (the snapshot restores the rows on the next push). Leaves the R2 PDF, so the cell returns to `missing` + `pdf_present`. For extractions that pass validation but are known wrong — built for the TEB 2026Q2 unit switch. `dry_run` defaults **true** and is genuinely read-only.
- `.github/workflows/backfill-faaliyet.yml` — manual dispatch. Fleet backfill of the Faaliyet-raporu franchise lane → `faaliyet_franchise` + `faaliyet_extractions`. The incremental refresh rides `refresh.py` (step 9, non-critical).
- `.github/workflows/summarize-regulations.yml` — Sun 06:00 UTC. Weekly regulation briefing via Kimi → `regulation_briefings` → D1. Needs the `KIMI_API_TOKEN` repo secret, which the workflow maps to env `KIMI_API_KEY` (the name `src/news/kimi.py` reads) — see [OPERATIONS.md](OPERATIONS.md) §Secrets. Grounded on the TCMB annual policy baseline, pinned once a year by dispatching this workflow with `baseline_url`/`baseline_year` (the ingest must run in CI, between the snapshot pull and upload — a local run writes a DB production never reads). Runs `--require-baseline`, so an ungrounded briefing fails instead of shipping. Posts the generated briefing to Telegram (`notify_briefing()`, split across messages under Telegram's 4k cap) whenever the LLM actually runs — silent on unchanged-input weeks; `force=true` regenerates on demand. Follow-ups in [regulation_followups.md](regulation_followups.md).
- `.github/workflows/deploy-cloudflare.yml` — **after CI goes green on `master`** (`workflow_run`, not `push` — it used to race CI). Apply D1 migrations + build + deploy dashboard.
- **Public-API catalog** — not its own workflow: `refresh-data.yml` runs `scripts/build_api_catalog.py` + `push_to_d1.py --only-tables api_series` after every BDDK refresh, so `/api/v1` sees each new period. `api_series` is full-rebuild (no per-row timestamp), so a windowed push skips it — it must be named explicitly. See [API.md](API.md).
- `.github/workflows/healthcheck.yml` — daily 06:00 UTC. D1 freshness check → Telegram/Discord alert if stale. Also runs `scripts/verify_chart_spec.py --alert`: re-resolves every reproduced chart in `web/app/lib/chart-specs.catalog.json` against D1 and alerts if a series goes blank (0 rows) or drifts past its `verify[]` anchor. See [REPRODUCING_CHARTS.md](REPRODUCING_CHARTS.md). Third check: `setup_telegram_webhook.py check --alert` asserts the bot webhook still targets the live origin.
- `.github/workflows/telegram-webhook.yml` — manual only. `set` / `info` / `check` the Q&A bot webhook; lives in CI because the bot token + webhook secret aren't available locally. Run `set` after anything that moves the site origin (e.g. the 2026-07-19 Worker rename to `carthago`, which orphaned the webhook on the dead `workers.dev` host).
- `.github/workflows/test-openrouter.yml` — manual only, **scratch**. Probes the `OPEN_ROUTER_API` secret (auth → credit budget → DeepSeek model/price list → one number-validated completion) via `scripts/scratch/scratch_test_openrouter.py`. The key was added 2026-07-05 and no lane reads it; this only answers "does it work, and what does DeepSeek cost". Delete both files once the finding lands in `docs/knowledge/` — and with them the `SCRATCH_WORKFLOWS` entry in `scripts/check_pipeline_graph_sync.py` that exempts this lane from the `/pipeline` graph gate (it moves no production data, so it draws no lineage node; a stale exemption fails CI by design).
- `.github/workflows/ci.yml` — on PRs. ruff + pytest + eslint + tsc + vitest. (Dependency bumps via `dependabot.yml`.)

Schema source of truth: hand-authored migrations in `web/migrations/`, applied
by the deploy workflow (`wrangler d1 migrations apply`); `d1_migrations` tracks
what's applied.

## Dashboard

**Bilingual public UI (2026-08-31).**
English/Turkish display copy, financial labels, deterministic reads, chart labels,
accessible chart summaries and metadata use a request-scoped locale. The desktop
and mobile TR/EN switcher remembers the choice in a one-year preference cookie;
otherwise Turkish is the default, regardless of browser language.
The switcher stays at the top of the desktop sidebar/mobile header, clear of the
analytics consent banner, so choosing a language never requires analytics consent.
URLs and filters are preserved. Source documents/news/transcripts and stored
research prose keep their original language; the operator-only admin tools remain
English. English generated headlines keep their existing gates; Turkish uses the
translated deterministic read. No schema migration, ingestion change or D1 write
is involved. Maintenance notes: [web/i18n/README.md](../web/i18n/README.md).
Verification: web lint, TypeScript, 603 tests and the production webpack build;
docs/prose/pipeline/contrast gates also pass. Local browser checks covered both
languages, mobile navigation, persistence and filter retention. The local `/banks`
fixture lacks `bank_audit_pl_roles`, so that page's browser QA was limited; no
production or local data was changed to work around it. After deployment, live
HTTP checks passed for the home, credit, bank register, Akbank detail and privacy
pages; explicit English preferences and the Turkish default both rendered correctly.

Next.js 16 (React 19, TypeScript 6) + OpenNext on Cloudflare Workers — live at
<https://carthago.app>. D1 reads are cached
~1h via KV (`cachedAll` → `unstable_cache`), so repeat page views don't re-query
D1. *(Was 12h — that window existed only to stay under the Workers **free** tier's
1,000 KV writes/day. On the paid plan the allowance is 1M/month, so the window
was cut 12× for fresher pages at no marginal cost.)* A password-gated `/admin` control center (data health, refresh triggers,
traffic) is unlocked by the `ADMIN_PASSWORD` Worker secret; optional
`GITHUB_DISPATCH_TOKEN` enables the trigger buttons and Web-Analytics creds the
traffic panel. The Pipeline panel's audit card supports a **per-bank,
latest-period** trigger, and **13 banks auto-discover** new quarters from their
IR page (no hand-added URL needed) — see [ADMIN.md](ADMIN.md) §Auto-discovery.
Setup in [OPERATIONS.md](OPERATIONS.md) / [ADMIN.md](ADMIN.md).

**Chart-library weight: measured, demonstrated, DEFERRED (2026-07-25).** A bank page
ships 338 KB of compressed JS across 19 chunks, one 101 KB chunk of which is Recharts
— the ~2.6s of main-thread work the 2026-07-12 evaluation measured, and the last of
its findings still open. Every fix changes how a chart ARRIVES, so it is a design call:
the four options are built and running at **`/lab/chart-loading`** (unlisted, noindex,
not in nav/sitemap/Colophon) — server-rendered today, `ssr:false`, defer-until-in-view,
and hand-rolled SVG, with a slow-motion toggle that makes the blank state visible.
⚠️ **Correction (2026-07-25): the charts do NOT server-render.** `ResponsiveContainer`
needs a measured width, so the served HTML carries an empty
`recharts-responsive-container` and no chart — verified on `/economy`. The lab page
originally claimed option 1 draws before JS and that `ssr:false` gives that up; it
does not, because nothing is server-drawn today. `ssr:false` is therefore close to
free — a labelled placeholder where a blank area already sits — and the same fact is
why charts had no text alternative at all until the sr-only summaries landed.
**Reviewed and deliberately not taken for now.** Do not re-propose it as a defect;
re-open only if the decision changes. Delete `web/app/lab/` when it is no longer
wanted. Two related measurements worth keeping: the 40 KB polyfills chunk ships
`noModule` (modern browsers skip it — not waste), and the 101 KB chunk loads on
chart-free pages too, which is real but only helps the light pages.

**The trust layer is complete (2026-07-25):** `/about`, `/methodology`, `/privacy`,
linked from the Colophon on every page and listed in the sitemap. `/methodology` is
the substantive one — sources and their cadences, the coverage and the peer
exclusion, the basis problem (one quantity, several legitimate definitions), the
computation rules that actually govern the code (Fisher deflation, YTD
de-cumulation, TTM ROE, Σ/Σ over the same population, date-paired growth), what runs
before anything publishes, and what the site is not. **Every count on both pages is
READ, never typed** — `check_prose_claims.py` R3 fails a hardcoded universe count in
rendered text, so the pages restate themselves as coverage grows.

**Every dashboard D1 read is cached (2026-07-25).** `audit.ts` — the module behind
`/banks/[ticker]`, the heaviest page on the site — called `getDB()` directly in 12 of
its 15 query functions, so a single view re-queried D1 for the balance sheet, P&L,
multi-period pivots, cash flow, profile and stages *per visitor* while every other
page read from KV. All fifteen now use `cachedAll`. Bounded key space (ticker × kind ×
the periods a reader opens) is what makes that correct and not merely faster — the
unbounded twin is the public API, which is why `allDirect` exists. Freshness follows
the site-wide 1h window; after a re-extraction `/banks/…` lags up to an hour unless
the KV purge in OPERATIONS is run. **Measured, and correcting two inherited
assumptions:** the 40KB polyfills chunk ships `noModule` so modern browsers skip it
(not waste), and the ~2.6s main-thread cost on a bank page is **JS, not server time** —
338KB compressed across 19 chunks, of which one 101KB chunk is Recharts. That, not
caching, is the remaining LCP lever.

**Text legibility is a CI gate (2026-07-25).** `scripts/check_contrast.py` computes
every `text-*` token against every surface it sits on — sheet, ground and the muted
row fill — in both themes, and fails under WCAG AA 4.5:1. It also fails on a colour
used as text with no declared background, which is how the chart palette leaking
into chip labels was found. `--faint` had shipped at **2.43:1** under 8–10px type on
210 call sites (the 2026-07-12 evaluation's accessibility finding); the quiet ramp
was re-spaced (`faint` 2.43→5.13, `muted-foreground` moved darker to keep three
distinct tiers), `--warning` and `--negative` were nudged, and `chart-theme.ts`'s
tick-label colours are now required to EQUAL the text tokens they copy. Chart MARKS
are deliberately out of scope (3:1, WCAG 1.4.11) — see [web/DESIGN.md](../web/DESIGN.md).

**Analytics are consent-gated, and `/privacy` says what is collected (2026-07-25).**
Two tools, deliberately unequal: **Cloudflare Web Analytics** is cookieless and
identifier-free, so it is always on and needs no consent; **GA4** sets cookies and
sends the visit to Google, so `gtag.js` is not requested at all until the visitor
accepts. Decline (or ignore the bar) and the site sets **no cookies whatsoever** —
the answer itself lives in one localStorage key, not a cookie. The gate is
`AnalyticsConsent.tsx` over `lib/consent.ts`; consumers read it through
`useSyncExternalStore` (`lib/use-consent.ts`), which is what keeps the banner out
of the server HTML — a consent bar that flashes during hydration gets dismissed by
accident. `/privacy` carries the withdrawal path, and is linked from the Colophon on
every page. It also documents the Telegram bot, which retains more than the site
does: question text plus a non-reversible chat hash (`bot_queries`), the raw chat id
in the rate-limit counter (`bot_usage`), and the question going to a third-party
model provider. **If any of that changes, `/privacy` changes in the same commit** —
it is the one page whose claims are about us, not about the banks.

## Public data API

`/api/v1` — public, unauthenticated, read-only. Serves the **BDDK monthly
(tables 1–17) + weekly bulletin** aggregates as ~19,800 time series, shaped after
TCMB's **EVDS** (dotted series codes joined with `-`, `DD-MM-YYYY` dates,
`type=json|csv`). Full reference: **[API.md](API.md)**.

```
GET /api/v1/series?series=BDDK.T01.I001.10001.TOT&startDate=01-01-2024&type=csv
GET /api/v1/serieList?dataset=T01&bankType=10001
GET /api/v1/categories
GET /api/v1                     ← self-describing index
```

Codes are `BDDK.<DATASET>.<ITEM>.<BANKTYPE>.<COLUMN>`, where `T01`–`T17` are
BDDK's own table numbers and `10001`–`10010` its own bank-type codes, so most of
the identifier is upstream-stable rather than ours to break.

Three things worth knowing:

- **The catalog is the contract.** A code is never parsed into SQL — it's looked
  up in `api_series` (migration 0031), which holds the real filters. That's what
  lets published codes survive storage quirks (`other_data` keys items by *name*
  because its `item_order` collides inside table 12).
- **Per-bank data is NOT exposed.** The `bank_audit_*` family stays internal;
  this API is BDDK's published sector aggregates only.
- **Kill switch**: `PUBLIC_API_DISABLED=1` on the Worker → every route 503s, no
  deploy needed. That's what makes an unauthenticated endpoint safe to publish.

## Mobile app

`mobile/` — Expo SDK 57 / React Native 0.86 / expo-router, iOS + Android.
**Built and verified locally (typecheck, lint, token gate, Metro bundle all
green); NOT submitted to either store.** Architecture: [ARCHITECTURE.md](ARCHITECTURE.md)
§ Mobile app. Working notes: `mobile/CLAUDE.md`.

Four tabs — **Overview** (the Desk brief: vitals, movers, transmission, flags,
standings, ahead), **Banks** (searchable index → per-bank scorecard with a
selectable charted metric, earnings quality, stages, franchise, KAP feed),
**Economy** (12 EVDS series, one selectable chart), **News** (merged feed +
the regulation briefing with its provenance line).

Served by `/api/app/v1` on the same Worker — a **private** wire format, kept
apart from the public `/api/v1` series contract so the app can reshape screens
without freezing a published API. Kill switch: `APP_API_DISABLED=1`.

Three decisions worth not re-litigating:

- **No metric is derived in the app.** Every ratio and deflation is computed by
  the same `web/app/lib` function the website calls. A second client that does
  its own arithmetic will eventually disagree with the first, and the reader
  trusts whichever they saw last.
- **Stale-while-revalidate, with the staleness printed.** Cached payloads paint
  instantly on launch (the data moves monthly to quarterly, so yesterday's copy
  is not stale in any sense a reader cares about), and any figure not fetched
  this session carries a `Cached · fetched Nh ago` line. A failed refresh keeps
  the data on screen rather than blanking it.
- **Single-series charts only** — see Known issues for the colorblind finding
  behind that.

**Play Store: published to closed testing, gathering testers (2026-07-31).**
Runbook: `mobile/RELEASE.md`. Path is EAS Build (cloud) — `eas.json` ships
`development` / `preview` / `production` profiles, production emitting an `.aab`
and submitting to the **internal track as a draft**, never straight to public.

Live state — package `app.carthago.mobile`, release `2 (1.0.0)`, closed track
**Alpha**, 177 countries. Production is Inactive and stays that way until the
12-testers-for-14-days gate clears.

- **Testers are admitted by Google Group**, `carthago-testers@googlegroups.com`,
  set to *anyone on the web can join*. It was originally an email list; that
  forces a manual add per tester and is why recruiting via a swap platform
  stalls. Switch before reaching 12, never after — dropping below 12 restarts
  the 14 days.
- **Group membership is not opt-in.** A member is merely *eligible*; they must
  still open the opt-in link on the phone, signed into the account that phone
  uses. Track the Console's *"N testers currently opted-in"* line, not the
  group's member count — they diverge (7 members vs 4 opted-in on 2026-07-31).
- **Recruiting**: listed on Twelve Testers (a free dev-to-dev swap pool) and
  posted to r/AndroidTest4Test. Both are reciprocal — they cost testing other
  people's apps daily for the same fortnight.

What was needed beyond "it builds":

- **The Yahoo tape is gone from the app AND from `/api/app/v1`.** BIST indices,
  FX, Brent and gold came from Yahoo, whose terms forbid redistribution — and a
  store listing is a formal, publisher-named act of it in a way a web page is
  not. The website is unchanged. USD/TRY still reaches the app's transmission
  block, now from TCMB EVDS (`TP.DK.USD.A`), which is attribution-licensed.
  **Don't add the tape back to the app.**
- **Four permissions stripped.** The generated manifest declared
  `SYSTEM_ALERT_WINDOW` ("Display over other apps"), `VIBRATE` and both legacy
  storage permissions. Blocked via `android.blockedPermissions`; the merged
  release manifest is now `INTERNET` plus one auto-generated AndroidX
  self-permission. Shipping "draw over other apps" on a banking reader is a
  review question and a trust problem.
- **Privacy policy covers the app** — `/privacy` gained a "The mobile app"
  section, so the Play Data Safety answer ("collects no data") matches a
  published policy rather than contradicting one.
- R8 + resource shrinking enabled for release via `expo-build-properties`.

Still outstanding, and needing *you* rather than code: an Expo account, a Play
Console account ($25), `eas login`, a 1024×500 feature graphic, and a
native-resolution app icon (the current one is a 256→1024 upscale). Apple is
further off — guideline 4.2 wants more than a data reader.

⚠️ **Monetising the app** (ads, paid tier, IAP) would need written permission
from TCMB/TBB/BDDK first — attribution licences cover a free reader, not a
commercial one. See § upstream data terms.

Not built: push notifications, Turkish localisation, any write path.

**The prose audit — the sentences now earn themselves (2026-07-14, SHIPPED):**
"Compiled, not written" was true of the *figures* and false of the *words*: an
audit of every visible string found ~300 timeless (axis labels, methodology),
~170 guarded, and **41 unguarded claims** — hand-typed directions, levels and
rankings with nothing checking them. Several were already wrong. The homepage
told Google "32 banks" (it is 38); `/asset-quality` rendered `+₺-42bn` in red
when net NPL formation turned (the *good* case); `/capital` said "Every ownership
group **fell** together" off a step detector that picks by `Math.abs`; `/deposits`
claimed a universal about **every group** off a guard that tested only the sector.

Root cause: nothing in the repo turned a signed delta into a direction *word*.
**`web/app/lib/prose.ts`** supplies it — `direction()` (a closed `VERBS`
vocabulary), `claim()` (three-valued: an unknown prints *neither* branch),
`firstClaim()` (every rung tests what its sentence says), `signed()`, `everyOf()`
(FALSE on an empty list, unlike `Array.every`), `toneClass()`. Plus
`latestByGroup`/`deltaByGroup`/`leaderOf` in `desk.ts` — needing no new query,
because the per-group series was already the chart's own `data` prop.
Failing closed is the contract: `null` → the caller prints the **topic**, not a
finding. The five hand-typed `Ahead` schedules now derive (BDDK monthly from the
record period; the BRSA window from the KAP filing lag that already happened);
only TCMB's MPC dates remain hand-typed. `/economy`'s third-party claims are
computed where we hold the series and **deleted** where they were causal or an
elasticity — never quoted.

Three CI gates keep it: **`prose-regression.test.ts`** (feeds every insight
builder sign-inverted fixtures; fails if a falling word survives a rising series —
verified by sabotage), **`check_prose_claims.py`** (a hardcoded sign, an asserting
`title=` literal, a hardcoded bank count; zero suppressions in force), and
**`check_calendar_fresh.py`** (fails under 90 days of MPC runway). Full writeup:
[docs/knowledge/prose-claims-audit.md](knowledge/prose-claims-audit.md).

**/asset-quality rebuilt — the ratio prints the tip (2026-07-13):** the page led
with "NPL ratio 2.69%", which is calm, and is the **tip**. What the ratio prints is
Stage 3 (3.1% of the book); loans the banks themselves classify as deteriorated are
**12.3% — 4x** — and three-quarters of that ₺3.2trn problem book is the **Stage-2
watchlist** the ratio never shows, carrying **9.8% cover** against Stage 3's 62.3%.
The brief now leads with the **waterline** (the whole book to scale, then the problem
book magnified with provisions drawn inside each stage), then the **pipeline**:
formation ran **2.2x** last year (₺673bn, net **+₺404bn**) and the exits are **77%
collections**, not write-offs — so the ratio is *not* being managed down, the book is
genuinely deteriorating. Attribution reconciles the ₺0.34trn of new bad loans to 100%
(commercial 60.9%, of which **SME 42.8%**). Arithmetic in `web/app/lib/asset-quality.ts`.

> **A claim we retracted, and now test against.** An earlier draft led with "the growing
> loan book hides 1.06pp of NPL ratio". It does not: an NPL ratio is `N/L`, so deflating
> both legs by CPI leaves it **unchanged** — a ratio is **deflator-invariant** and
> inflation does not flatter it. That draft's counterfactual froze the book in *nominal*
> terms, a fiction at 32% CPI; the honest dilution is **~0.1pp**, and it is now a footnote
> at its true size. A deflator-invariance unit test pins this so the mistake cannot come
> back. Rationale + the `takipteki` item_id trap (2.0.4 is **SME**, not housing):
> [knowledge/asset-quality-tab-redesign-2026-07-12.md](knowledge/asset-quality-tab-redesign-2026-07-12.md).

**/credit rebuilt — the headline is mostly not credit (2026-07-12):** the page's
biggest figure was 36.6% nominal loan growth; in a 32% CPI regime with a
depreciating lira that is mostly not credit, and the page owned both corrections
already without ever composing them. It now leads with a **bridge** (nominal →
−lira → FX-adjusted → −inflation → real, constant FX): the loan book **shrank
2.1%** in real constant-currency terms, negative 10 consecutive weeks. Adds
**growth attribution** — the print decomposes into segment contributions that
reconcile to it exactly (commercial +26.1pp, of which SME +12.2pp; cards +5.3,
GPL +4.1, housing +1.1, auto −0.1) — with SME drawn *inside* commercial, because
it is a ~36% cut of that book, not a peer. Flags print their rules (real
contraction 10w, auto contraction 96w, unsecured retail above sector 91w). The
arithmetic lives in `web/app/lib/credit.ts` (pure, unit-tested: the
reconciliation and the drop-don't-nowcast CPI rule are both gated). CPI is
monthly, so the real legs can trail the weekly print — they are dropped, never
nowcast, and the page states the lag. Depth reordered by question; no chart
removed. Rationale:
[knowledge/credit-tab-redesign-2026-07-12.md](knowledge/credit-tab-redesign-2026-07-12.md).

**General redesign program (2026-07-10/11, ALL PHASES SHIPPED):** A: surface +
typography tokens (white cards `#FFFFFF`/`#26231C`, firmer borders `#D8D1C2`/
`#3E382E`, cooler-crimson `--negative` `#B03246`/`#E7788A`, mono-caps reserved
for eyebrows/kicker/index; `chart-theme.ts` tooltip lockstep) ✅; B: chart
legibility — `chart-end-labels.tsx` direct end-of-line labels (collision-resolved,
hover/pin isolation) + hero-vs-grey-context on by-group lines, legend only
<~500px, `annotations` prop, Sparkline baseline+min/max ✅; C: feed pages
(/news ×2, /regulation, /earnings, /disclosures) on-system + token-based
dark-safe news-tags ✅; D: Section spine on capital/profitability,
`ui/segmented.tsx` single toggle idiom (`bg-primary/10 text-primary`),
`TableCellNum`/`toneFor` + 7 hand-rolled tables consolidated, radii→10px/9px +
space-y-8 normalization ✅ (follow-up 2026-07-11: the former "intentional
narrows" — /banks/[ticker], /ownership, /earnings, /disclosures — widened to
the standard `max-w-[1440px]` shell after user feedback on dead gutters;
earnings/disclosures card lists became responsive grids; only /admin keeps
6xl); E: finding-as-title lead charts on the 8 Read tabs
off `lib/chart-findings.ts` (deterministic, recomputed from chart rows — can't
go stale) + source footers ✅. Plan + rationale:
[knowledge/design-system-audit-2026-07-10.md](knowledge/design-system-audit-2026-07-10.md),
[knowledge/design-critique-2026-07-10.md](knowledge/design-critique-2026-07-10.md).
Known follow-up: the chart expand-modal doesn't re-measure to full modal width
(pre-existing, matches pre-redesign behaviour).

**Display-study phases 2–5 (2026-07-03):** real-terms convention
(`web/app/lib/real-terms.ts` — nominal-vs-real twins on Credit/Deposits, exact
Fisher deflation off TP.TUKFIY2025.GENEL), FX-adjusted credit growth
(constant-USD/TRY, BBVA convention), Profitability "return equation" (ROA ×
leverage = ROE + drivers), sized scenarios (NII sensitivity off the repricing
ladder on /market-risk; CAR-buffer headroom on /capital; Stage-2 migration
provision scenario on /asset-quality), share-shift Δpp y/y columns on the
/cross-bank league, bank-page rank-in-field strip + per-bank Capital section,
the forward-credit layer (`web/app/lib/credit-risk.ts` — sector TFRS-9 staging
+ annual NPL formation-vs-exits off the audit lanes), Nav in FSR story order
(Digital → Markets & Macro, /disclosures orphan fixed), and clarify-purpose
reframes on Ratios/Funds/Rates. Spec + per-phase records:
[knowledge/display-study.md](knowledge/display-study.md). Deferred: 4b
(/banks league + head-to-head picker), 5b (chronology lane, /digital
compression).

**"The Read" on every T1 tab (2026-07-02):** the deterministic insight engine
(`web/app/lib/insights.ts`, no LLM — recomputed from the same series each page
already fetches) now leads Credit, Deposits, Asset Quality, Capital,
Profitability, Liquidity and Market Risk with a per-tab judgment callout
(`<Takeaway>`), alongside the existing Overview "Sector Pulse". The same change
applied the audit's editorial verdicts: public-vs-private and dollarization
promoted to the top of Credit/Deposits, Real Returns and the audited CET1
section promoted on Profitability/Capital, level-twin and duplicate charts cut
(~14), the fee-ratio trio consolidated, and the orphan `/sector` root retired
(redirects to `/`). Spec + phase tracker:
[knowledge/display-study.md](knowledge/display-study.md) (phases 2–5 pending:
real-terms twins, decompositions, sized scenarios, leagues, chronology).

**"The Read" headline — LLM rewrite, Option 1 (2026-07-04, all 8 tabs live):**
`deepseek/deepseek-v4-flash` @Baidu (paid, primary since 2026-08-17) ahead of the
free chain (Cerebras `gpt-oss-120b` → Groq `openai/gpt-oss-120b`; chosen in
[knowledge/free-model-eval-round3.md](knowledge/free-model-eval-round3.md))
rewrites ONLY the one-sentence lead; the driver bullets stay deterministic. A
weekly CI cron (`generate-reads.yml` → `scripts/generate_read_headlines.py`, keys
already in GitHub secrets) reads the deterministic takeaways from `GET /api/reads`,
number-validates each rewrite, and upserts `read_headlines` (migration 0019) via
wrangler. `web/app/lib/read-headlines.ts` shows the rewrite ONLY while its
`det_hash` matches the live page and it invents no number — else the deterministic
sentence, so it can never drift or go stale. All 8 tabs are wired (`reads.ts`
computer + `withLlmHeadline` wrap per page); below the paid head the failover keeps
the SAME model on two providers (Cerebras → Groq `gpt-oss-120b`) then the
deterministic template. ⚠️ Putting deepseek in front **deliberately gave up the
"a shown headline always sounds the same" property** the round-3 chain was picked
for — a headline written during a Baidu outage is a different voice. Per-provider
pacing + retry-on-429 keep the free tier consistent under Cerebras's 5-req/min
limit.

**Presentation deck generator — PDF on demand (2026-07-05):** a board-style
**PDF slide deck** of the sector Read — dark title slide, a **KPI vitals** slide
(stat tiles), one slide per T1 tab (headline + driver bullets + an inline-SVG
**trend chart**), and a methodology slide. Single source of truth is the Worker
route `GET /api/presentation` (`web/app/api/presentation/route.ts` →
`web/app/lib/presentation-data.ts`, which reuses the dashboard's **own**
`metrics.ts` functions for the tiles/charts + the deterministic reads for the
narrative → `web/app/lib/presentation-deck.ts` builds the 16:9 HTML in the
editorial palette). **No drift** — same numbers the site plots. Two front doors:
**/admin → Presentation → Generate PDF** (opens `?print=1` + the browser print
dialog) and the CLI `scripts/generate_presentation.py` (a thin wrapper that
fetches the route's HTML and prints it headlessly via Chrome/Edge for an
unattended PDF in `reports/`, gitignored). Params/flags: `?tabs=`/`--tabs`
(subset/reorder), `?title=`/`--title`, `--html-only`, `--file` (local HTML),
`--open`. Workers can't run headless Chrome, so the browser does the PDF step.
Recipe in [OPERATIONS.md](OPERATIONS.md) §Generate a presentation deck; admin
flow in [ADMIN.md](ADMIN.md) §Presentation deck.

**Telegram Q&A bot — text-to-SQL over D1 (2026-07-05):** a public Telegram bot
that answers natural-language questions by generating **read-only SQL** against
the live D1 and summarising the rows. Runs inside the Worker as a Next route
(`web/app/api/telegram/webhook/route.ts`): Telegram POSTs each message, we verify
the `X-Telegram-Bot-Api-Secret-Token` header, ACK 200, and process in
`ctx.waitUntil`. The orchestrator (`web/app/lib/bot.ts`) rate-limits
(`bot_usage`, migration 0020; per-chat + global daily caps), then runs an **agent
loop** (`runAgent`, ≤ 6 query/refine rounds): the free model emits a ```sql block,
which is gated through `web/app/lib/bot-sql.ts` (single `SELECT`/`WITH` only,
writes/DDL/multi-statement/denied-table rejected, row-capped — 29 vitest cases) and
executed; the rows — or the SQL error, or `0 rows` — go back to the model, which
self-corrects until it answers in plain text. A figure stated before any query has
returned rows is treated as a hallucination and **never sent** (the `gotData` guard).
The reply is **prose only**: the SQL and the raw rows are diagnostics, exposed solely
through `/api/admin/bot-ask`. The LLM chain (`web/app/lib/llm.ts`) is **Groq-first,
then Cerebras** — deliberately *not* the Cerebras-first order of "The Read", because
the loop makes several calls per question and Groq's free tier is far less
rate-limited. The system prompt
(`AGENT_SYSTEM` in `web/app/lib/bot-schema.ts`) drills the per-bank
(`bank_audit_*`, quarterly, thousand TL) vs sector-aggregate (`balance_sheet`
etc., monthly, million TL) split, forbids guessing a reporting period, and requires
the answer be in the question's language. Its nested `SCHEMA_PROMPT` is orientation
plus known-good hints rather than the bot's whole understanding of the data — the
loop verifies labels and values against the live DB before answering, which is what
makes it robust to gaps in that file. Setup (bot token + webhook secret + LLM key as
Worker secrets, then register the webhook via `scripts/setup_telegram_webhook.py`) in
[TELEGRAM_BOT.md](TELEGRAM_BOT.md). This is separate from the outbound
`scripts/notify.py` alert channel.

**SEO / discoverability (2026-07-07).** On-page work shipped: `web/app/robots.ts`
and `web/app/sitemap.ts` (crawlable route list), per-page `metadata` (title,
description, `alternates.canonical`) on every route, and JSON-LD structured data in
`web/app/layout.tsx` + `web/app/page.tsx`. Rationale, the manual Google Search
Console / Bing verification steps, and the ranking strategy are in
[knowledge/seo-and-search-console.md](knowledge/seo-and-search-console.md).
Off-page (backlinks) remains the real lever and is unstarted — the strategic review
names distribution as the project's biggest gap.

**Cloudflare Web Analytics (2026-07-05).** RUM is wired via a **manually rendered**
beacon (`web/app/components/Beacon.tsx`), because Cloudflare's automatic edge
injection does **not** fire on the OpenNext Worker response — verified the beacon was
absent from the live HTML while RUM sat at 0. The browser uses the non-secret
`CF_ANALYTICS_SITE_TOKEN`; `/admin` queries with the distinct
`CF_ANALYTICS_SITE_TAG`. Cloudflare returns both for the same site, but they are
not interchangeable — using the token as the GraphQL tag returns an empty
dataset with no API error. The beacon renders nothing when unset, so `next dev`
never pollutes production analytics.

**Ratios merged into the Overview Snapshot (2026-07-04):** the standalone
`/sector/ratios` page (six KPI cards whose only distinct value was the
bank-**type** filter, an audit "clarify_purpose" item) was first folded into
Overview as a separate scorecard section, then **merged into the Snapshot itself
(index 01)**. The Snapshot is now one `BankTypeFilter`-switchable scorecard —
size + growth (Total Assets, Assets/Loan/Deposit YoY) plus the Table-15 ratio
vitals (NPL, CAR, NIM, LDR, ROA, ROE) — driven by a `?type=` param; it defaults
to Sector. The **"Sector Pulse" lead stays sector-aggregate** regardless of the
selection (the insight copy reads "the sector"), so it's fed its own sector
series. Removed from Nav; `/sector/ratios` redirects to `/#by-type` (the anchor
now sits on the Snapshot, preserving `?type=`). `Sparkline` and `BankTypeFilter`
moved to `web/app/components/`.

Every chart card (`web/app/components/ui/chart-card.tsx`) carries hover-revealed
icon-only header controls — **Copy** image, **PNG** download, **CSV** download,
and **Expand** to a centred popup. A single **global date-range selector**
(1Y / 3Y / 5Y / YTD / All) sits in the page header on chart pages (the
`rangeSelector` prop on `PageHeader`) and windows **every** time-series chart on
the page at once — `TrendChart`, `TimeSeriesChart`, and `StackedArea`. It's a
pure **client-side** display zoom over data
the page already ships (no refetch). Default **3Y**; the choice is shared
app-wide via a React context in the root layout (`RangeProvider` in
`web/app/components/range-context.tsx`), so it persists across tab navigation and
resets on a hard reload. CSV/PNG export the visible window. Helpers in
`web/app/lib/chart-range.ts` (+ vitest) and the `useRangeFilter` hook
(`web/app/lib/use-date-range.tsx`); pills UI in
`web/app/components/ui/range-pills.tsx`. `BopFlowChart`/`BarByBank` are out of
scope (fixed report windows / single-period snapshots).

A **Franchise** tab (`/franchise`) — **UNPUBLISHED since 2026-07-12. Do not ship it
as-is.** The code is preserved un-routed under `web/app/_franchise/` (Next.js private
folder, same treatment as `_valuation`); nav link and sitemap entry were removed.

**The blocker is the extractor, not the data coverage.** It was designed to read each
bank's operational footprint — ATMs, POS terminals, merchants, customers, cards: the
stats the audited financials don't carry — deterministically (regex + coordinates,
with per-cell confidence flags) from annual reports into `faaliyet_franchise`, with a
per-PDF audit trail in `faaliyet_extractions`. In practice it samples stray numbers
out of surrounding prose: **~75% of non-ATM values are wrong** (Akbank's 6,210 ATMs
came out as 202; TSKB, an investment bank with no ATM network, got "8"), and the
**confidence flags do not correlate with correctness**, so they cannot be used to
filter. Curating the per-bank URLs in `data/banks/faaliyet_report_urls.json` and
running `backfill-faaliyet.yml` would therefore *publish wrong numbers faster* — it is
not the fix. Re-shipping needs a rebuilt extractor behind a validation gate (branch
reconciliation against `bank_audit_profile` + a YoY sanity check); see
[knowledge/faaliyet-franchise-extraction-audit-2026-07-12.md](knowledge/faaliyet-franchise-extraction-audit-2026-07-12.md).

Branch and employee counts deliberately come from `bank_audit_profile` instead, and
are unaffected. The ingestion lane still runs weekly (the `/pipeline` graph shows the
page node as parked, not linked).

The **Non-Bank** tab (`/non-bank`) covers the BDDK-supervised non-bank lenders
that compete with bank credit — financial leasing, factoring, and financing
companies — from the BDDK non-bank monthly bulletin (`nonbank_balance_sheet`).
The **Overview** shows sector size over time + a per-sector snapshot; the
**Share of Banking** sub-page (`/non-bank/share-of-banking`) answers "how much of
banking business is done by non-banks" with three views — asset share, credit
(disintermediation) share, and per-segment share of bank loans — all measured
against the in-D1 banking aggregate (`balance_sheet`, code 10001), same-source
and same-unit (both Million TL). At 2026-04 the three sectors are ≈2.9% of
banking assets / ≈4.6% of system credit. VYŞ asset-management (a complement) and
savings-finance (not in this bulletin) are out of scope; data layer
`web/app/lib/non-bank.ts`. Reconciles to FKB published sector totals.

The **Profitability** tab (`/profitability`) carries a **NIM components**
decomposition replicating the BBVA "NIM components of private banks" chart from
the monthly bulletin: eight interest income/expense buckets
(`income_statement` items 1–14 / 16–22) as % of 13-month-average total assets,
as annual stacked bars (plus a current-year YTD-annualized bar — actuals, not
BBVA's forecast) and a monthly trailing-12-month view, switchable across bank
groups ("Private" = deposit codes 10008+10010, the BBVA definition; verified to
0.1pp). Data layer `web/app/lib/nim-components.ts` + `nimComponentsRaw()` in
`metrics.ts`; guarded by the `profitability.nim_components_private` chart spec.
See [METRICS.md](METRICS.md) §16.

A **Liquidity** tab (`/liquidity`) adapts the BBVA "Banking Sector Outlook"
liquidity section: TL & FC loan/deposit ratios split Public (state) vs Private
(private + foreign), **TL deposit growth (sector YoY & 13w-annualized, plus a
public-vs-private 13w cut)**, deposit dollarization, net CBRT funding,
**gross, net _and_ net-excluding-swaps international reserves** (TCMB publishes
no net headline — only gross `TP.AB.TOPLAM` and the IMF reserve-template
components — so NIR = analytical-BS FX assets `TP.BL054` − FX liabilities
`TP.BL122`, converted to USD; the swap spot leg sits in BL054 — verified
empirically — so net-excl-swaps = NIR − the forward/swap short position
`TP.DOVVARNC.K15` (IMF template §2.2.1, ~$20bn); gross − net is required-reserve
FX), residents' household FC savings, audited §4
LCR/NSFR/leverage, and REER. See [METRICS.md](METRICS.md) §12.

The **Rates & Macro** tab (`/rates`) additionally carries the BBVA margins page:
a **TL deposit-rate maturity ladder** (`TP.TRY.MT01–05`, ≤1m…>12m), a **TL
loan–deposit spread** (commercial ex-OD `TP.KTF18` − deposit `TP.TRY.MT06`),
and an **FC loan–deposit spread** (USD/EUR: `TP.KTF17.USD/EUR` − `TP.USD/EUR.MT06`
— 4 new weekly `rates` series added to the EVDS scraper and backfilled 2018→).

Together these close the gap on the BBVA liquidity section: of its 17 charts we
now render 3 already-built + 6 new (13 of 17 covered). The 4 not reproduced are
BBVA-proprietary estimates with no public feed — under-the-mattress gold, the
weekly reserve-flow attribution, and the FCI composite/decomposition; fund net
flows and the mutual-fund-dollarization/FC-fund split need a TEFAS
re-classification (no FC-fund category ingested).

An **Economy** tab (`/economy`) adapts the Türkiye macro section of the BBVA
"Türkiye Economic Outlook" (1Q26): GDP growth, industrial production, labor
market, CPI vs CBRT funding cost, inflation expectations, ex-ante real rate,
USD/TRY + REER, 12m-rolling current account (total / ex-gold / ex-gold&energy)
and net errors & omissions, fiscal balances as % of GDP. Fed by a `macro` EVDS
block (GDP, IP, labor, BoP, budget — 15 new series incl. CPI 2025=100, which
replaces the dead 2003=100 index). See [METRICS.md](METRICS.md) §14.

**All six economy pages carry the full Desk brief (2026-08-07).** Until then the
section was a header, a vitals band and a grid of one-series line charts: none of
the six had a `<Takeaway>`, `<Movers>`, `<Transmission>`, `<Flags>` or `<Ahead>`
block, on the one part of the site whose job is to explain the conditions the
banking tabs measure. Each page now computes a Read, a movers table on a single
stated cadence, a transmission strip that says what each macro figure does to a
bank, rule-printed flags (`<Flags showCleared>`) and a release schedule. Six new
builders in `lib/insights.ts` (`economyInsights`, `inflationInsights`,
`growthInsights`, `bopInsights`, `budgetInsights`, `tradeInsights`), all
registered in the regime-flip gate (`prose-regression.test.ts`) — verified
decisive by injecting a typed directional word and watching it fail.

Coverage the data always supported and nothing rendered:

- **Reserves** on `/economy` — the **published gross** (`TP.AB.TOPLAM`, which
  matches the reported headline to the decimal) plus import cover, and a derived
  net line plotted and labelled as ours. The NIR derivation moved out of
  `liquidity/page.tsx` into **`web/app/lib/reserves.ts`**, which both pages
  import, so the two cannot print rival numbers for a figure TCMB does not
  publish. `ReserveBuffer.tsx` moved to `app/components/` with it.

  **No swap-adjusted figure prints on `/economy` (removed 2026-08-07).** It was
  shipped as a vitals cell, a flag and the third line of the buffer chart, and
  measurement against the figures the press reports killed all three: over five
  consecutive weeks it ran **~$5bn low every week** (31 Jul: ours $35.7bn vs
  $40.8bn reported) and missed an independent anchor by $9.8bn — TCMB's own MPC
  summary put ex-swaps at **$66.0bn on 12 Dec 2025**; the formula gave $56.2bn.
  It is not a bug a better series fixes:
  **TCMB publishes no net-reserves series at all** (every reserve datagroup in
  EVDS carries gold / FX / total and nothing else), so both "net rezerv" and
  "swap hariç net rezerv" in the press are *analyst* constructs, each house with
  its own method. The ~$13.4bn deduction they imply matches nothing official —
  the CBRT's own swap book now reads **zero** across all six `bie_swaptektarf`
  outstanding series, the IMF template's forward/futures short leg
  (`TP.DOVVARNC.K15`) is $17.7bn and only monthly, and non-resident liabilities
  are $14.6bn and move the wrong way. Gross is published and exact; net is ours
  and says so; the swap-adjusted level is not computable here and therefore does
  not print. Do not re-add it without a source that reproduces the published
  figure.

  Two things this did NOT touch, deliberately: `/liquidity` still renders the
  same swap-adjusted figure (vitals, two flags, a transmission item and the
  three-line buffer chart), and `lib/reserves.ts` still derives it. Both are
  owned by separate in-flight work.

  Separately, the extraction fixed a live bug: a week with no IMF-reserve-template
  row was scored as *zero swaps*, overstating the CBRT's own FX by the whole swap
  book. Callers on a short window pass K15 fetched at `FWD_YEARS_BACK` so the step
  resolves instead of dropping weeks.
- **The policy→deposit→loan transmission chain** (`TP.PY.P02.1H`, `TP.TRY.MT06`,
  `TP.KTF17/KTFTUK/KTF12`, monthly-averaged), the loan−deposit spread, and the
  real *deposit* rate beside the real policy rate.
- **CPI breadth** on `/economy/inflation` — the share of COICOP groups printing
  above the headline m/m, on a constant denominator (a month is emitted only when
  every group reports). Weight-free by construction, since TÜİK's group weights
  are not in EVDS; it answers "how broad", never "how much".
- **The real twin** on `/economy/budget`: every line there was nominal lira, which
  at a ~30% price level is mostly a chart of the deflator. Tax/spending/interest
  now also print CPI-deflated, balances as % of trailing-4Q GDP, and interest as a
  share of the tax take.
- Non-resident portfolio flows, households' FX and gold, EUR/TRY, the current
  account as % of GDP (USD-converted at the *window-average* rate, not spot), and
  households' inflation expectation (quoted, not charted — `TP.HANEBEK.HAN14A`
  holds only 7 prints in D1).

BBVA's static baseline table is now **scored** rather than carried: the published
2026 column is set against what our own series actually printed, with the
observation count in brackets. Rows we cannot score say why — end-of-period rows
do not settle before December, and the two %-of-GDP budget rows are refused
outright because BBVA quotes central government while our 12-month ratio is the
general budget. The pure half of the tab (`lib/economy-calc.ts`, split from
`economy.ts` so no D1 import sits in its module graph) and `lib/reserves.ts` are
unit-tested (22 cases) — the scorecard's *refusals* are the assertions that
matter, since a silently-graded partial year would look entirely plausible.

A **Balance of Payments** sub-page (`/economy/balance-of-payments`, linked
from the Economy header) reproduces the Albaraka «Ödemeler Dengesi» monthly
report 1:1 — 3 headline-balance KPIs, 10 figures (Şekil 1–10) and the
summary table — off **21 new BoP detail series** (`TP.ODEAYRSUNUM6.*`
financial-account/services detail + `TP.HARICCARIACIK.K4/K7/K9` gold/energy
balances; all `macro`/monthly). Signed-stacked-bar charts via the new
`BopFlowChart`; the Şekil 10 financing identity (CA ≡ net foreign inv. +
reserves − net errors) and every figure were verified to the report's
Apr-2026 summary table. Five `economy.bop_*` chart-specs anchor daily
verification. See [METRICS.md](METRICS.md) §14. The same page also carries a
**Foreign Portfolio Flows — Weekly** section (data layer
`web/app/lib/portfolio-flows.ts`): non-residents' weekly net equity/GDDS
transactions + holdings off **4 new weekly TCMB series** (`TP.MKNETHAR.M7/M8/M1/M2`,
datagroup `bie_mknethar`, USD m) — the dataset behind the widely-cited weekly
foreign-flows chart, verified to the press numbers (M7 12-Jun-26 = −117.8 ≙
"sold $118m equities").

An **Economic Growth** sub-page (`/economy/economic-growth`, also linked from
the Economy header) reproduces the Albaraka «Ekonomik Büyüme» quarterly GDP
report off **19 new TÜİK national-accounts series** (`TP.GSYIH*.HY.ZH`
expenditure + `*.IFK.ZH` production chain-volume indices, `macro`/quarterly):
GDP-growth KPIs, Şekil 1 (y/y), the **growth-contributions** decomposition
(Şekil 2, derived — consumption/investment/exports contributions match the
cover exactly), Şekil 3 sectoral, Şekil 6 government, and both y/y tables
(production full; expenditure aggregates). EVDS gaps are flagged in-page and
in METRICS §14: the q/q **seasonally-adjusted** GDP line, the expenditure
**detail** (Şekil 4/5 durable/investment breakdowns), and the
calendar-adjusted production variant live only in TÜİK's Excel — a future
scraper lane, not yet wired. Two `economy.growth_*` chart-specs anchor
verification.

A **Budget** sub-page (`/economy/budget`) reproduces the Albaraka «Bütçe
Görünümü» monthly report off **23 new `TP.KB.GEL*/GID*` central-government
budget series** (EVDS cat 1503 — *distinct* from the cash general-budget
`GEN*` codes, which are ~117 bn off): 12m balance/primary/tax KPIs, Şekil 1
(12m balance+primary), Şekil 5 (monthly balance), Şekil 4 (revenue y/y),
Şekil 2/3 expenditure & tax category bars, and the 17-row table. Balance /
primary / non-tax are derived (`GEL001−GID001/−GID002/−GEL003`), all matching
the report's Apr-2026 table. Two `economy.budget_*` chart-specs.

An **Inflation** sub-page (`/economy/inflation`) reproduces the Albaraka
«Enflasyon» monthly report off **28 new TÜİK CPI (2025=100) + PPI (Yİ-ÜFE)
series** (`inflation`/monthly): CPI/core-C/PPI KPIs + Şekil 1, core A/B/C/D
table (m/m, cumulative, y/y, 12m-avg), Şekil 4/5 (clothing & electricity m/m),
Şekil 2/3 CPI-group & PPI-sector m/m, and the monthly-history table. EVDS gaps
flagged in-page: Şekil 2/3 weighted **contributions** (need TÜİK weights →
shown as m/m) and the PPI **Main-Industrial-Groupings** table (TÜİK-Excel
only). Two `economy.inflation_*` chart-specs.

A **TÜİK direct-detail lane** (`src/tuik/`, run by `update_tuik.py` as a
non-critical step in `refresh.py`/the EVDS workflow) fills part of those gaps
with data EVDS doesn't carry, ingested into the shared `evds_series` table as
`TUIK.*` codes (so no new table/migration/reader): **GDP expenditure detail**
(consumption-by-durability → Şekil 5, GFCF-by-type → Şekil 4) and the **PPI
Main-Industrial-Groupings** table on /economy/inflation. Deterministic .xls
download via the veriportali cookie-session theme tree (the verified recipe is
in METRICS §14 + the `reference_tuik_data_access` memory); values match the
reports exactly. Pages gate the new charts on data presence (`hasTuik`/`hasMig`)
so they appear once CI populates D1. Still on the EVDS fallback: GDP q/q SA line,
calendar-adjusted production, and exact Şekil 2/3 contributions (TÜİK's
contribution table is a lagged single-month snapshot). Two `economy.*` specs.

A **Foreign Trade** sub-page (`/economy/foreign-trade`) reproduces the Albaraka
«Dış Ticaret Dengesi» report off **11 new EVDS customs-trade series**
(`TP.IHRACATBEC.*`/`TP.ITHALATBEC.*` flows in USD thousand, unit-value indices,
Brent `TP.BRENTPETROL.EUBP`; `macro`/monthly): trade balance + ex-energy,
exports/imports (level + growth), coverage ratio, terms of trade, trade by BEC
group, and the energy deficit vs Brent. Verified to the report's Q2-2022 values
(exports 246.0, imports 322.6, energy deficit −67.69 exact). Two
`economy.foreign_trade_*` specs (using `derive`/`ratio`). Flagged in-page (not
reproduced): the «Çekirdek Denge» core line (Albaraka-internal, doesn't
reconcile) and the HS-chapter «Fasıl» tables (TÜİK dynamic-DB only — not in EVDS
or the TÜİK theme-tree Excel).

A **Digital** tab (`/digital`) surfaces the TBB quarterly digital/internet/mobile
banking statistics (`tbb_digital_stats`, sector-wide): channel adoption (active
mobile vs internet customers; mobile-only/both/internet-only usage), quarterly
money-transfer volume (₺ trn) & count and bill-payment count split internet vs
mobile, and demographics of active individual digital customers (gender + age).
Data layer `web/app/lib/digital.ts` pins verified full-history series by their
`(channel, segment, section, unit, metric_slug)` key. See [METRICS.md](METRICS.md) §13.
Two **Participation banks** sections add the TKBB side (`tkbb_digital_stats` /
`tkbb_acquisition_stats`, data layer `web/app/lib/tkbb.ts`): active digital
customers with the participation share of the combined total, a mobile-only-share
comparison vs TBB, transaction volume by channel, and remote-vs-branch
acquisition with a remote-share comparison. Province-level active customers are
ingested but not yet charted (no choropleth component).

A **Funds** tab (`/funds`) surfaces TEFAS fund-market sector aggregates: AUM by
fund type (mutual / pension / ETF, ₺ trn) with a CPI-deflated index, mutual-fund
AUM by category (the money-market & hedge-fund boom), AUM-weighted portfolio
allocation, investor-account counts, and the latest top-15 funds per type. Time
series sample the month-end trading day; GYF/GSYF (not daily-priced) are
excluded from trends. Data layer `web/app/lib/funds.ts`. See
[METRICS.md](METRICS.md) §15.

The **Banks** index (`/banks`) is a **register**, not a card wall: one hairline
row per bank carrying size, share of the reporting total, ROE / NPL / NIM / CAR,
and how much history is on file — searchable, and sortable on any column
(`Register.tsx`, client). Grouping by type prints each group's asset subtotal,
its share, and its **median** ratios, so a bank reads against its own peers
rather than the sector. Flags are rules: an amber period marks a bank that has
not filed the record quarter (its ratio cells show "—" rather than a stale
quarter — mixing periods down a column would void the medians), a short history
bar marks a recent entrant, and `clearing` marks a peer-excluded bank (Takasbank
is a CCP, so it is carried but kept out of every share and concentration
figure). No new extraction: `bankSummaries()` was already fetching `total_assets`
and spending it only on the sort, and the ratio columns come from the same
cached `heatmapPanel()` that `/cross-bank` runs on.

A **Compare** tab (`/cross-bank`) is a **matchup sheet** built entirely off the
per-bank `bank_audit_*` tables (the monthly BDDK tables are group aggregates
only). Three controls drive it (`CompareBoard.tsx`, client): the **bench** —
pick up to four banks; the **peer frame** — all banks / their types / majors
₺500bn+, which is the population every axis, median and rank is computed over
(the picks are always in it); and the **scorecard** — each of the 21 metrics as
a ROW on a real value axis, with every peer a faint tick, the interquartile band
shaded, the median marked and the picks as coloured dots. That axis is the
point: a rank-coloured cell says "3rd of 34" but hides DISTANCE, so a bank 0.1pp
behind the leader looked exactly as far away as one 10pp behind. Axes clip to
the Tukey whiskers (q₁/q₃ ± 1.5×IQR) so one freak value can't flatten the field,
with the clipped peers counted at the edge; a pick is never clipped out of view.
Two picks turn the last column into a signed Δ; three or four give the set's
spread. A deterministic **read** names who leads and where the set splits widest.
Metrics carry a `family` (Scale · Asset quality · Returns · Margin engine ·
Capital & liquidity · Market risk · Valuation) and a printed `rule` — the
derivation, per DESIGN.md's automation-honesty rule.

Underneath, in `<Depth>`, the evidence carries over: **Snapshot** (banks ×
metrics at the record quarter — now one metric family at a time, with the picks
pinned above an ink rule, since 21 columns meant 14 lived behind a horizontal
scroll), **Over time** (banks × quarters for one metric), and the market-share
league + HHI. Both grids are scoped to the peer frame, and the heat ramp is
deliberately quiet (`scoreToColor` caps at 26%/12%) — the scorecard carries the
comparison now, so colour only sorts the eye and the value is always printed.
The data layer (`web/app/lib/heatmap.ts`) builds one cached panel from
its queries: assets = BS roman I.–X. sum; stage ratios from `bank_audit_stages`;
ROE/ROA/NIM/Cost-Income derived from a P&L pivot by BRSA hierarchy (net profit
`XXV.`→`XIX.`, net interest `III.`, opex `XI.`+`XII.`, gross op profit `VIII.`)
over equity (BS liab `XVI.`), with YTD flows annualized × (4/quarter). Rank +
color logic is the pure, client-safe `heatmap-normalize.ts`.

The **margin engine** (2026-06-20) adds the *drivers* behind NIM, on a TTM basis
(matching ROE): **loan yield** (interest on loans, P&L `1.1`, ÷ 5-pt avg gross
loans, BS asset `2.1`), **deposit cost** (interest on deposits, P&L `2.1`, ÷ 5-pt
avg deposits, BS liab `I.`), their **spread**, **cost of risk** (TTM ECL
provisions `IX.` ÷ avg gross loans), and **PPOP/assets** (gross operating profit
less opex, ÷ avg assets) — all per bank, in the same `heatmapPanel`. A
**Market share & concentration** block (`web/app/lib/market-share.ts` +
`MarketShareSection.tsx`) sits below the heatmap: an asset-size league table with
q/q rank moves and each bank's share of assets/loans/deposits, plus the sector
HHI. Shares are of the **reporting banks** that quarter (~98% of sector) — bank ÷
Σ-reporting, not the BDDK aggregate (avoids the unit/timing + bank-type
double-count traps). The same margins + share trend surface as a **Performance**
section on `/banks/[ticker]` (`ProfitabilitySection.tsx`).

A **Valuation** tab (`/valuation`) — **archived/hidden since 2026-07-10** at the
user's request. The code is preserved un-routed under `web/app/_valuation/`
(Next.js private folder); nav link and sitemap entry were removed. See that
folder's `README.md` to bring it back. Description below is retained for revival.
It did forward scenario projection + intrinsic
valuation for the listed banks. It's standalone (no changes to `/banks` or
`/cross-bank`). DCF/FCF is inappropriate for banks (leverage is regulated, not a
policy choice), so it uses the equity-side models: a multi-stage **residual
income** model `V₀ = B₀ + Σ PV[(ROEₜ − COE)·Bₜ₋₁] + PV(terminal)` with a linear
ROE fade and a Gordon (ω=0) or Ohlson-decay (ω>0) terminal, a **two-stage DDM**,
and the **justified P/B** identity `(ROE − g)/(COE − g)`, g = ROE·(1−payout). Cost
of equity is CAPM, **nominal TRY**: `rf + β·ERP + CRP`, β from weekly
bank-vs-XU100 returns (**unavailable since the BIST lane was removed 2026-08-01** — sector-default 1.0), rf a CBRT
funding-rate proxy (`evds_series` TP.APIFON4). The maths are a pure, unit-tested
module (`web/app/lib/valuation.ts`, 19 vitest cases) so the page **recomputes live
in the browser** as the user drags sliders; Base/Bull/Bear presets seed editable
assumptions (`valuation-presets.ts`). The server pre-fetches a compact per-bank
seed for all listed banks at once (`valuation-data.ts`: book + TTM ROE on the
heatmap basis, market cap, β, rf — reusing `bankFundamentals`/`bistValuation`
read-only), so the bank selector swaps with zero round-trips. Also a cross-bank
**P/B-vs-ROE regression scatter** + justified-vs-actual ranking (client-side,
under a scenario toggle). Caveat surfaced in-UI: book/earnings are TAS-29
hyperinflation-restated, so absolute fair values are indicative — the durable
driver is the real (ROE − COE) spread; lean on the cross-peer comparison.

A **Pipeline** tab (`/pipeline`) visualizes the whole data lineage as an
interactive node graph (React Flow / `@xyflow/react`): external sources →
ingestion workflows → Cloudflare D1/R2/KV → dashboard pages, with the two
ingestion lanes (`bddk-pipeline` vs `bddk-audit`) banded apart and shared infra
(snapshots, cache, CI/CD, monitoring) below. Storage/source nodes carry **live**
D1 row counts + freshness (server-rendered via `getPipelineStatus()`, reusing
`admin-health.ts` + graceful COUNT/MAX extensions, 12h `cachedAll`); workflow
nodes show their last GitHub Actions run, fetched client-side from the public,
**edge-cached** `/api/pipeline/runs` (`max-age=300`, never KV — keeps the daily
free-tier KV write cap safe) and degrading to neutral badges when
`GITHUB_DISPATCH_TOKEN` is absent. The topology is a hand-authored, pure data
model (`web/app/lib/pipeline-graph.ts`) with a deterministic layered layout
(`pipeline-layout.ts`, no dagre/elkjs); keep it in sync with this file +
[ARCHITECTURE.md](ARCHITECTURE.md) when the pipeline changes.

A qualitative-data layer feeds four tabs from the `news_items` table
(`scripts/sync_news.py`, daily cron):

- **/regulation** — primary regulator feeds: TCMB press releases + BDDK board
  decisions, with a weekly AI thematic briefing. Per-bank KAP disclosures
  surface on each bank's page.
- **/news** (Sector Press) — banking-sector *journalism* aggregated from TR
  financial-media RSS feeds (Bloomberg HT, Dünya, Ekonomim, AA, NTV) via
  `src/news/sources/press.py`, keyword-filtered to banking-relevant items
  (`source='press'`). Feed list is hand-edited in `data/news/press_feeds.json`.
  Only headline + link + snippet are stored (no full body); cards link out.
  Removing a feed there purges its stored items on the next cron (a one-time
  manual D1 delete clears what was already pushed). Hürriyet was dropped — its
  RSS froze a stale Oct-2024 block.
- **/news/google** (Google News) — the long tail of regional/trade outlets, via
  topic-scoped Google News *search* RSS feeds (`src/news/sources/google_news.py`,
  `source='google_news'`; topics in `data/news/google_news_topics.json`). Reuses
  the press banking-relevance filter; publisher names come from the RSS
  `<source url>` tag, and outlets already on /news are skipped (no duplicates).
  Google News links are `news.google.com` redirect tokens — resolved to real
  publisher URLs via the `googlenewsdecoder` library, **serially and only for
  new items** (Google 429s parallel/volume decoding). `news_items` is the decode
  cache: a stable id from the RSS `<guid>` means each run only decodes the
  handful of new items (capped by `--google-max-decode`, default 60), so the
  rate-limit never bites; a decode failure keeps the still-clickable google link
  and retries next run.
- **/actions** — the banks' own **KAP filings** (`source='kap'`), **classified by
  the act each records** rather than shown reverse-chronologically. Replaces the old
  `/earnings` (a link directory) and `/disclosures` (a raw feed, 27% of it
  coupon-payment plumbing), both of which now 307-redirect here (`?ticker=` preserved).
  `web/app/lib/kap-actions.ts` is a **deterministic** classifier (no LLM sets a
  category) over the KAP form type + summary, sorting each filing into wholesale
  funding & capital instruments, capital/shareholder events, rating actions, results,
  other material events, governance, or *routine* (suppressed). It **fails safe**:
  only provably-mechanical filings are suppressed (an allow-list); anything
  unrecognised lands in the visible `material` bucket, never dropped. Every figure on
  the page (190 funding filings, 103 offshore, etc.) is computed at request time from
  `news_items` — no new source, table, column or cron; the daily news refresh already
  keeps it current. Locked by `kap-actions.test.ts` (real KAP fixtures per bucket).
  **Honest limit printed in-UI:** we hold only the title + summary (KAP's structured
  amount/ISIN/maturity/coupon fields live on the detail form, `body_text` is empty), so
  the page **counts acts; it does not measure them**. Same items still surface on
  `/banks/[ticker]` via `news_item_banks`.
- **Per-bank tagging** (`news_item_banks`, migration 0018) — a sync_news
  post-step (`src/news/bank_tagger.py`, pure-local like the earnings
  classifier) matches every press/google item's title+summary against a
  hand-curated alias map (`data/news/bank_aliases.json`, 31 canonical
  tickers) and writes one junction row per article × bank — Yahoo-Finance
  style per-ticker news, deterministic regex, no LLM. Turkish collision
  traps are encoded as match modes: prefix aliases catch agglutinative
  suffixes ("garanti bankas" → Bankası'nın) while word-bounded aliases stop
  "teb"→tebliğ, "ing"→İngiltere, "yapı kredi"→yapı kredisi; matching is
  dotless-ı-folded so ASCII caps ("ING", "GARANTI") still hit. The full
  corpus is retagged every run (alias edits apply retroactively; removals
  propagate via the `d1_pending_deletes` outbox). Surfaces as an
  "In the News" section on `/banks/[ticker]` (`pressNewsByBank`) and bank
  chips on /news + /news/google cards.

A separate **earnings lane** (`bank_earnings` table, migration 0015,
`src/earnings/`) feeds the **"Results season"** section of **/actions** (the
`/earnings` route redirects there) and an "Earnings & Presentations" block on
each `/banks/[ticker]` page:

- **Tier 1 — results-filing calendar (`source='kap'`).** `src/earnings/from_kap.py`
  classifies the KAP disclosures already in `news_items` (no new network) into
  `results_filing` events — when each bank filed its quarterly financial report —
  deriving the quarter from KAP's structured `year`/`period`/`ruleType` fields.
  Verified against the live feed: Turkish banks file **only** their financial
  reports on KAP, **not** earnings-call invites or investor-presentation decks, so
  the `call`/`presentation_filing`/`webcast_replay` kinds exist in the schema but
  stay empty. Runs as a step in `scripts/sync_news.py` (daily news cron) — no new
  workflow.
- **Tier 2 — investor-presentation decks (`source='ir'`).** `scripts/update_presentations.py`
  emits one `presentation_deck` per quarter from `data/banks/investor_presentation_urls.json`,
  augmented by IR-page auto-discovery (`src/earnings/presentations.py`, reusing the
  audit-lane discovery engine; `PRESENTATION_BANKS` = GARAN/AKBNK/YKBNK validated
  via `scripts/diagnostics/validate_presentation_discovery.py`). Seeded for 10 of the
  11 listed banks: GARAN/AKBNK/YKBNK auto-discover + HALKB/TSKB/SKBNK/VAKBN/QNBFB/ALBRK/
  ISCTR static (heterogeneous/opaque filenames — QNB `.vsf`, Albaraka apostrophes,
  İşbank JS dropdown — gathered via the browser MCP, all URLs verified 200/206). Only
  ICBCT (no public IR deck archive) unseeded. Runs weekly via
  `.github/workflows/refresh-presentations-weekly.yml`.
A separate **call-transcript lane** (`bank_call_transcripts`, migration 0036,
`src/transcripts/`) holds what management actually *said*, next to what the
filings show. Surfaces as an "Earnings calls" block on `/banks/[ticker]` and a
reader at `/banks/[ticker]/calls/[period]`.

- **Source: AlphaSpread** (`alphaspread.com/security/ist/<slug>.e/…/earnings-call`).
  Server-rendered HTML — body and Q&A are in the raw response, no JS. `robots.txt`
  is `User-agent: * / Disallow:`. The archive **enumerates itself**: the bank's
  index page lists every call as a `q<N>-<YYYY>` slug, so unlike the presentation
  lane there is no filename skeleton to learn and no quarter can be missed for want
  of a hand-added URL. `data/banks/call_transcript_sources.json` configures only the
  per-bank slug.
- **Ingested 2026-08-04: 144 calls, 734,412 words, 3,831 speaker turns**, floor
  `2018Q1`:

  | Bank | Calls | Range | Words |
  |---|---:|---|---:|
  | AKBNK | 33 | 2018Q1–2026Q2 | 219,732 |
  | GARAN | 31 | 2018Q1–2026Q2 | 157,496 |
  | HALKB | 22 | 2018Q1–**2025Q3** | 79,048 |
  | ISCTR | 21 | 2018Q1–2026Q1 | 89,991 |
  | VAKBN | 20 | 2018Q1–2026Q1 | 105,524 |
  | ALBRK | 8 | 2021Q2–2026Q1 | 35,765 |
  | YKBNK | 7 | 2019Q1–2026Q1 | 36,601 |
  | TSKB | 2 | 2025Q2–2025Q4 | 10,255 |

- **Three listed banks are absent at the SOURCE, not by omission.** SKBNK and ICBCT
  hold no English call (AlphaSpread returns "No Earnings Calls Available"; Yahoo
  agrees) and QNBFB is delisted. An empty lane for them is the right answer, and the
  UI renders the block only for the eight that do hold calls.
- **⚠️ These are machine transcriptions, and the weak axis is attribution, not
  content.** Body coverage is complete — opening remarks through the Q&A to the
  closing remarks; measured against Investing.com's version of the same call
  (AKBNK 2026Q1) it is 4,582 words vs 4,875, and both end on "Bye for now". But the
  operator naming a Turkish analyst frequently transcribes as `[indiscernible]`, and
  those turns then also lose their `role='analyst'` tag. Counted per call in
  `indiscernible_count` and printed in the reader: **522 markers across the corpus**,
  concentrated in VAKBN (150) and AKBNK (123), and varying call by call — GARAN
  2026Q2 has none at all. **Do not key on analyst identity.** Do not read a figure off a
  transcript either — numbers are spoken aloud and land as e.g. "TRY 51.7 billion,
  5-1-0.7"; the audited figures are the `bank_audit_*` lanes' job.
- **Known gaps:** HALKB stops at 2025Q3 though a FY2025 call was held 2026-02-20
  (MarketScreener has it); YKBNK's archive is ~one call a year against a quarterly
  reporter. Investing.com carries free full transcripts that patch both, but its
  URLs are editorial slugs with an opaque numeric id and cannot be enumerated, so it
  stays a manual backstop rather than a second ingest.
  `call_date` is only published from 2025 onward (**29 of 144 dated**); `period` is
  always known, so ordering is unaffected.
- **Not built:** call *audio*. Webcast replays exist on the banks' own IR sites
  (Garanti's Download Center, İşbank's webcast list) but are streaming-only, and the
  transcripts already carry the content.

## Known issues / pending work

- **✅ An invalid R2 object no longer freezes a partition (2026-08-06).**
  `exists(key)` was read as "acquired". TSKB's 2026Q2 KAP notification — 14
  pages of cover sheet — sat under the key, so every acquisition run skipped the
  partition, and the day the real report appeared **nothing would have fetched
  it**. One bad object froze it for good.

  Acquisition now validates the object it finds (`report_validity`: page floor,
  BRSA structure markers, positive KAP-cover fingerprint), re-checks the source
  when it is not a report, and **replaces** it when the real filing appears.
  A source still serving the notification leaves the partition `pending`, not
  `failed`. Extraction refuses one too — a cover sheet parses without raising
  and yields near-empty statements that validate as `missing` rather than
  failing, the quiet kind of wrong. Both record the verdict in
  `bank_audit_invalid_pdfs`, cleared the moment a real report replaces it, so
  **coverage reports `pdf_present` only for genuine reports** without
  re-downloading 1,061 PDFs per sync.

  Also from that run: **the snapshot upload now precedes the coverage spine**,
  which is `continue-on-error`. A metadata rollup must not discard a successful
  extraction — when coverage ran first, its budget refusal failed the job and
  skipped the upload, leaving PASHA's rows in D1 and absent from the snapshot.
  And `_COVERAGE_INCREMENTAL` is **enabled**: the full rebuild asked 161,728
  rows to restate a barely-changed table, which is what breached the 250,000
  run cap in the first place. *(That cap is gone as of 2026-08-12. Both fixes
  stand on their own: the ordering protects against any late-step failure, not
  just a refusal, and the incremental rollup is now one of the few things still
  holding write volume down.)*

- **⚠️ PROCESS: a migration was applied live against an explicit instruction not
  to run one (2026-08-05).** The instruction was *"Commit and push only these
  offline fixes. Do not run another refresh, migration, or targeted D1/R2
  correction."* `web/migrations/0040_coverage_derived_at.sql` was committed and
  pushed in the same change; `deploy-cloudflare.yml` fires on every green CI on
  `master` and applies pending migrations, so 0040 went to live D1 automatically.
  The consequence was flagged only *after* the push, with an offer to revert —
  which is not authorization, and the flag came too late to be one.

  **Not rolled back.** It is a single additive `ALTER TABLE … ADD COLUMN`, it
  rewrote no rows (`rows_written: 0`), and the behaviour it enables is switched
  off, so reverting carries more risk than it removes.

  The rule this establishes: **on this repo, committing a migration file IS
  running the migration.** There is no "push the file but hold the schema
  change" — `master` deploys itself. A migration must therefore be held out of
  the commit entirely until its application is authorized, or the authorization
  must be obtained before pushing. Flagging a side effect after the fact does
  not substitute for asking first.

- **The categorical chart ramp fails colorblind separation — worst in dark mode
  (found 2026-07-30 while porting the palette to `mobile/`, NOT acted on).**
  Running the six `--chart-*` tokens through a CVD validator against their own
  surfaces:

  | Theme | Check | Result |
  |---|---|---|
  | dark | normal-vision separation | `--chart-2` #9BB4D8 vs `--chart-1` #7FA3D8 — **ΔE 6.1**, against a floor of 15 |
  | dark | protanopia | `--chart-6` #8B939C vs `--chart-5` #B092C0 — **ΔE 5.3** |
  | light | contrast vs the sheet | `--chart-3` #8FA8C8 at 2.38:1, `--chart-6` #A0A7AE at 2.37:1 (below 3:1) |

  The dark normal-vision failure is the serious one: it says a reader with full
  colour vision cannot reliably tell series 1 from series 2. The website is
  *partly* covered because every multi-series chart carries a direct-labelled
  `ChartFoot`, which is the documented relief for a borderline pair — but that
  is relief, not a fix, and it does nothing for the light-mode contrast pair.

  Nothing was changed. `chart-theme.ts` is in LOCKSTEP with `globals.css` and
  CI-gated on text contrast, so re-stepping the ramp is a system-wide design
  decision across ~40 charts, not a hex nudge. The mobile app sidesteps it
  entirely by plotting single series in `--data` only.

  To fix properly: re-step chart-2/3 and chart-5/6 off the same ramps until the
  validator passes on adjacent pairs in both themes, then re-run
  `scripts/check_contrast.py`. Worth doing before any new multi-series chart
  lands, not urgently.

- **D1 write bill: 68.1M rows month-to-date against a 50M allowance (~$18 over)
  — two pure-waste sources fixed 2026-07-27, the campaign cost still open.**
  ⚠️ An earlier note here said ~122M/month and ~$72: that was a **14-day window
  extrapolated to 30**, and the window held three campaign days. Writes are far
  too bursty for that — always sum the calendar month. D1 charges $1.00 per
  million **rows written** (reads are $0.001/M — a thousandth), and `rowsWritten`
  counts DELETEs and index maintenance: one override push here reported 392,363
  rowsWritten against 107,636 actual changes, a **3.6× multiplier**.

  Fixed: (1) `evds_scraper.fetch_one` re-fetched each series' whole history back
  to 2018 every run and `INSERT OR REPLACE`d all of it — `downloaded_at` is
  omitted from that statement so every row took `DEFAULT CURRENT_TIMESTAMP`, and
  `push_to_d1` windows on exactly that column. **52,828 of evds_series' 53,521
  rows looked new every single day** and were re-pushed with identical values:
  ~17M rows/month. It now compares `(value, label, category)` and writes only
  what differs. (2) `push_to_d1` full-rebuild tables (`api_series` 19,787 rows on
  the DAILY bulletin cron; `bank_audit_coverage` 18,936 on every audit run) now
  carry a content hash and skip entirely when nothing moved: ~4M rows/month.
  Build-stamp columns are excluded from the hash or the skip could never fire.

  Consequence: `MAX(downloaded_at)` on `evds_series` now means *when the data
  last moved*, so **both** `healthcheck.py` and `/admin` judge EVDS freshness on
  `MAX(period_date)` (120h / 3-day cadence) — the treatment TEFAS already had,
  and strictly better, since a data date catches a TCMB publishing break that a
  download stamp cannot.

  ⚠️ **Not all of the bill is this project.** The account hosts a second D1
  database, `gazelhan` — 9.5M of the month's 68.1M writes and half of all reads.
  Attribute before optimising.

  **The QUIET-day baseline is cheap and flat** — Jul 6–10 ran ~485k rows/day,
  ~14.6M/month, well inside the allowance. Every bit of the overage is campaign
  days: Jul 15 (12.4M), Jul 17 (15.1M) and Jul 26 (9.4M) are 36.9M of 68.1M.
  Predicted, not yet confirmed: the EVDS fix (52,828 rows × 3 pushes/day on a
  table with a PK + 2 indexes) should account for most of that ~485k baseline —
  verify against the analytics a few days after 2026-07-27 rather than trusting
  the arithmetic.

  **`apply_overrides.py` scoped to changed partitions (2026-07-27).** It was the
  concentrated cost: re-applying all 457 overrides every run (which is what makes
  it idempotent) meant all ~216 named partitions were cleared from D1 and
  re-pushed whatever changed — **two runs wrote ~632,000 rows to correct five
  cells**. It now fingerprints each partition before applying and after
  revalidating (`_partition_digest`; `extracted_at`/`validated_at`/`derived_at`
  excluded, since those are what the script bumps on purpose) and touches only
  what moved. An idempotent re-run now costs nothing at all — no D1 write, no R2
  upload. Verified back-to-back on the real snapshot: `207 of 216` with a pending
  validator change, `0 of 216` immediately after. Note the first number is
  correct behaviour, not leakage: `bank_audit_validation` is inside the digest,
  so a **validator** change is a real change and must reach D1.

  **Still the dominant cost:** audit campaigns generally — two days of lane work
  (2026-07-15/17) were 27.5M of the month's 68.1M.

- **`parse_num` read hyphen-negatives 1000× too small — FIXED 2026-07-27, and
  now guarded.** The numeric primitive eight audit extractors share decided
  Turkish-vs-English thousands notation with an anchored regex
  (`^\d{1,3}(\.\d{3})+$`) applied to the **signed** string. A leading `-` failed
  the anchor, so a hyphen-negative with exactly ONE thousands group fell through
  to the English branch and its separator was read as a decimal point:
  `parse_num('-319.110')` → `-319.11`. Two groups survived on a separate clause
  and parenthesised negatives never reached the sniff, so it only ever bit
  single-group hyphen-negatives — the §4 market-risk net-off and gap rows.
  The sign is now stripped before the sniff, so **a number's sign no longer
  changes how its format is read**, and `tests/test_parse_num.py` asserts every
  case against its positive twin. The primitive had had **no tests at all**.

  **A corpus sweep found 67 fractional amounts — 2 wrong numbers, 65 leaked
  non-values** (verified against **live D1**, not just the R2 snapshot — the two
  agree). BRSA prints whole thousands of TL, so a fractional amount cannot be a
  small figure; it is one we mis-read. `scripts/check_amount_integrity.py`
  sweeps all 67 amount columns (ratio columns excluded by name) and classifies:
  - **Mis-read separators (2) — CORRECTED 2026-07-27** via
    `data/audit_overrides.json` + `apply_overrides.py`; verified in live D1, and
    the sweep is now clean on this class.
    `bank_audit_capital.cet1_capital` **ISCTR 2024Q2 consolidated prior** was
    `270336.203` → **270,336,203**. A §4 prior column re-prints the prior
    year-end, so this cell is 31-Dec-2023: ISCTR's own 2024Q3 prior, 2024Q4
    prior and 2023Q4 **current** all carry that figure with every sibling field
    identical, and the identity **CET1 + AT1 = Tier1** closes exactly
    (270,336,203 + 5,348,088 = 275,684,291) — it misses by 1000× with the old
    value. `bank_audit_credit_quality.stage2_amount` **DENIZ 2023Q4 consolidated
    prior** was `-535.779` → **−535,779**; DENIZ's *unconsolidated* 2023Q4 prior
    is byte-identical to its 2022Q4 unconsolidated current, establishing that the
    bank restates nothing here, and the consolidated prior row already matched
    2022Q4 current on stage 3 exactly. **Left flagged, not guessed:** that row's
    `stage1_amount` still differs from 2022Q4 current by 4,003 — no 1000×
    signature and no evidence which filing is the mis-read.
  - ⚠️ **`period_type` was the trap.** Both defects sit in the *prior* column,
    and the `capital` override handler hardcoded `period_type='current'` — an
    override would have silently patched the CORRECT current row and left the
    wrong one in place. The handler now takes an optional `period_type`
    (defaulting to `current`, so the 54 pre-existing capital overrides are
    unchanged) and reports **NO MATCH** instead of succeeding on zero rows.
    Pinned by `tests/test_apply_overrides.py`.
  - **ISCTR 2024Q1 consolidated prior — CORRECTED 2026-07-27, from source.** A
    column SLIP, not a parse error, and the amount-integrity sweep is
    structurally blind to it: every stored value was a whole number, only the
    *assignment* was wrong. ISCTR's 2024Q1 **English** filing prints the §4
    capital labels one row off their values — p37 reads *"Total Deductions from
    Common Equity Tier 1  294,633,433  270,336,203"*, which IS the CET1 row — so
    the extractor matched labels literally and put Tier 1's value in AT1 and
    Capital's in Tier 2, leaving `cet1`/`tier1` NULL. Four fields re-read from
    the PDF and corroborated by the same 31-Dec-2023 column in three other
    filings.

- **§4 capital: `check_capital` only ever validated the CURRENT column
  (fixed 2026-07-27) — 21 partitions were hiding behind it.** The identity that
  refutes the ISCTR CET1 defect on sight, `Tier1 = CET1 + AT1`, has existed in
  `validator.py` since the lane shipped. It just never ran on the prior row, so
  **half of every §4 capital cell in the corpus went unchecked**. Now run over
  both columns, with failures tagged `[prior]` so a red cell names its table.
  The *completeness* fails (`cap_rwa_missing`/`cap_car_missing`) stay
  current-only on purpose: a bank reprinting a partial prior column is ordinary
  and not our defect.

  Calibration over the corpus: **21 partitions fail on the prior column** —
  EMLAK ×4, ICBCT ×1, ISCTR ×4, QNBFB ×11, SKBNK ×1. All pre-existing, none new.
  **3 corrected** (ISCTR 2024Q1 above; ICBCT 2026Q1 and SKBNK 2025Q4, each proven
  by two independent derivations agreeing exactly — the stored row's own identity
  and the year-end filing the prior column reprints). **18 remain**, and they
  share one signature: `additional_tier1_capital` or `tier2_capital` stored as
  **0.0** where the value is non-zero, the true figure always being `t1 − cet1`
  or `tc − t1`. That is one extractor defect in the prior-column parse, not 18
  data errors — fix it at source rather than hand-writing 18 overrides. **5 of
  the 18 have no in-corpus anchor at all** (their prior column is a 2021
  year-end, before the corpus starts) and need the source PDF.

  ⚠️ Note the surfacing is not yet in `/admin`: only partitions touched by an
  override run have been revalidated. A full `revalidate_audit_db.py` pass is
  what turns the other 18 red in the coverage matrix.

- **§4 liquidity: the same blind spot, closed with no fallout (2026-07-27).**
  `check_liquidity` had the identical `period_type == "current"` line, so its
  prior column had never been validated either. Extended the same way and
  calibrated first: **0 violations across all 981 prior rows**, bar one — TAKAS
  2024Q2 unconsolidated, whose prior column re-prints the same 2023 year-end
  NSFR (38.39%) that 2024Q1's prior does. TAKAS is a development bank and is
  *exempt* from the 100% NSFR floor, which is why 2024Q1/Q3 and 2025Q2 were
  already curated in `_LIQ_SKIP`; 2024Q2 joined them. Unlike capital there is no
  identity here — only plausibility bands — so this catches a mis-scaled prior
  ratio, not a composition error.

- **9 overrides in `data/audit_overrides.json` now match nothing** (AKBNK
  `pl_rehier` ×3, EXIM/VAKBN/HAYATK `bs_rehier` ×6). They report `NO MATCH` on
  every run. **Do NOT bulk-delete them** — checked 2026-07-27 and only ONE is
  provably dead: HAYATK 2023Q4's target `A.` is present and its source `V`
  absent, so that rename did land. The rest are ambiguous or worse — EXIM
  2022Q1/Q2/Q3 still carry `3.2.2.2`, meaning the rename was *never* applied and
  the entry is masking a live defect; VAKBN 2022Q2/Q4 have neither the source nor
  the target row, so the whole off-balance sub-tree is missing; and AKBNK's P&L
  carries both the source and target ordinals, which distinguishes nothing. Each
  needs its own diagnosis. Harmless where they sit, but they make a real
  `NO MATCH` harder to spot in the log.
  - **Leaked non-values (65)** — a hierarchy marker or sector numbering parked in
    an amount column (`equity_change.paid_in_capital` 44 × GARAN `11.2`/`11.3`,
    `loans_by_sector` 18, three singletons). Junk that reads as junk; belongs to
    the known column-alignment tails below, and does not alert.

  **Why this needed a new check rather than a validator.** Every structural
  check in `validator.py` is an *internal identity* — it compares figures to each
  other. A scaling error is invisible to one unless the cell participates in an
  identity, and a **uniform** scaling error (the TEB 2026Q2 unit switch) is
  invisible to all of them by construction. This asks a different question, per
  cell and with no cross-reference: *does the stored number have a shape the
  source could not have printed?* It runs daily in `healthcheck.yml`; recipe in
  [OPERATIONS.md](OPERATIONS.md) → Amount-integrity alert.

- **Audit-extractor `textops` / `locate` refactor never landed (Phase 5).** The
  audit-quality rework is otherwise complete, but its last phase — extracting shared
  `textops.py` (page-text repair, squish handling, `NUM_PAT` + dipnot token rules,
  wrapped-row merging) and `locate.py` (anchor-based section location) out of
  `extractor.py` — was never done. Neither module exists; the section extractors still
  carry duplicated copies. **This is exactly the condition that produced the ECL
  dipnot bug**, which lived in two extractors at once and corrupted 17 banks for ~4
  years of quarters. Rescued here from
  [AUDIT_REWORK_PLAN.md](AUDIT_REWORK_PLAN.md) §Phase 5 (archived), so the only
  record of it isn't buried in a doc banner-marked *Historical*.

- **Weekly SME gap healed + date-aware weekly growth (2026-07-02).** BDDK's weekly
  API omitted the TOTAL column of private-bank SME loans (`1.0.11` / weekly `10003`)
  for 13 weeks (2024-10-25 → 2025-01-17) while publishing the TL and FX legs,
  blanking the /credit "SME Loan Growth YoY" private line — and, worse, the old
  row-offset `LAG(value, 52)` in `weeklyGrowth` stretched across the hole, so the
  private "YoY" for the following year (2025-01 → 2026-01) silently measured 65
  weeks of growth (~10–12pt overstated). Fixed three ways: (1) the 13 TOTAL rows
  backfilled into D1 as `TL + FX` (invariant verified corpus-wide, 0 violations);
  (2) `heal_missing_totals()` on the weekly scraper runs every `update_weekly.py`
  pass, so the R2-canonical SQLite self-heals and re-pushes idempotently;
  (3) `weeklyGrowth` now pairs by **date** (`web/app/lib/weekly-growth.ts`, exact
  week → ±1w holiday tolerance, annualized by actual elapsed days) so a source gap
  renders as a gap instead of a wrong number.
- **Every page threw a ReferenceError before paint (fixed 2026-07-24).** The
  bundler put a helper call inside a script it was never going to bundle:
  wrangler bundles the OpenNext worker with esbuild `keepNames: true` by default,
  which rewrites `function f(){}` to `function f(){} __name(f,"f")` so a minified
  bundle keeps `fn.name`. next-themes ships its no-flash initializer by
  **stringifying** a function into an inline `<script>` (`(${script.toString()})(…)`),
  so the injected `__name(k2,"k2")` travelled into that string — where the helper
  does not exist. The script threw at that line, before the `if (d2) k2(d2)` that
  applies the stored theme, so the pre-hydration pass never ran and the theme only
  landed once React hydrated (flash of the wrong theme on every route). Fixed with
  `"keep_names": false` in `web/wrangler.jsonc` — we do not minify this bundle, so
  keepNames was preserving nothing. **Verify after any wrangler/OpenNext bump**:
  `curl -s https://carthago.app/ | grep -c __name` must be 0 — a live request is the
  only place this shows up (it builds, deploys and type-checks clean either way).
  Found by the 2026-07-12 site evaluation (local archive, not versioned)
  (finding 3), which is otherwise **not acted on** — mobile Lighthouse 57–66 /
  LCP 4.1–4.5s, `text-faint` contrast 1.7–2.4:1, and no About / methodology /
  privacy / terms page (now pointed, since `/` loads GA4).
- **Architecture review 2026-07-02 (report only, no code changed).** Live site +
  web/ + pipeline surveyed post-Editorial; verdict sound, debt concentrated. The
  ranked backlog (off-theme chart palettes ×4, uncached `audit.ts` reads on public
  pages, CI silently skipping the fitz/pdfplumber test suite, `push_to_d1.py`
  3-edit table registration, dead extractor code) lives
  in [knowledge/architecture-review-2026-07.md](knowledge/architecture-review-2026-07.md).
  **Re-verified 2026-07-27 and now largely closed** — see
  [knowledge/architecture-cleanup-2026-07-27.md](knowledge/architecture-cleanup-2026-07-27.md)
  for the item-by-item status and what was deliberately left. Closed since:
  the CI test-suite gap and the `push_to_d1` chokepoint (2026-07-14, the routing
  guard widened from the audit tables to all 54 on 2026-07-27); the uncached
  `audit.ts` reads (now 20 `cachedAll` / 1 raw `getDB`); pdfplumber removal;
  the `sector/page.tsx` inline SQL; the stray `.next/` at repo root; the dead
  extractor helpers; and the zero data-layer tests (5 → 28 web / 51 → 53 Python
  suites). The `PlSankeyChart.tsx` light-mode regression is **moot** — that
  component no longer exists (the Desk redesign left only `lib/pl-sankey.ts`).
  **Still open by choice:** the `textops`/`locate` split (above) and the ~9
  copy-pasted HTTP session+retry loops in `src/scrapers`/`tbb`/`tefas`/`tuik`/
  `kap`/`news` — each backoff is tuned to its own flaky source, so a shared
  helper is worth doing deliberately, not as a sweep.
- **Seeking-Alpha-style statement viewer shipped (2026-06-24).** The `/banks/[ticker]`
  Financials section gains a **Cash Flow** tab (alongside Balance Sheet / Income
  Statement), an **Absolute / YoY Growth** view toggle, and a **TTM** column (income
  statement + cash flow, quarterly view only — suppressed in annual where TTM == the
  Q4 YTD column). All server-rendered via URL params (`statement=bs|is|cf`,
  `mode=abs|yoy`), no new client component. **All three statements are standardized**
  (canonical English labels keyed by BRSA hierarchy code, raw `item_name` never shown,
  banks comparable line-for-line) — **Cash Flow standardized 2026-06-24** via a
  `CF_LINES` catalog in `standard_lines.ts` (the cash-flow hierarchy codes 1.1.x /
  1.2.x / 2.x / 3.x + romans I.–VII. are consistent across all 31 banks; only labels
  varied). Labels are the official BRSA English wording (sourced from GARAN, an
  English filer); `cashFlowMultiPeriod` strips trailing dots (KUVEYT-class) at read
  time to match the catalog; stray period-header rows (`"1"`/`"31"`, `A./B./C.`) and
  the verbatim render path were dropped. Synthetic Operating/Investing/Financing
  section headers; empty → "not available" note. `cashFlowMultiPeriod` in
  `web/app/lib/audit.ts` is try/catch-guarded — a missing/un-migrated CF table never
  500s. YoY compares each
  cell to the same quarter a year earlier on the **displayed (YTD) values**; TTM
  de-cumulates. De-cumulation/TTM/YoY math extracted to a shared, unit-tested
  `web/app/lib/period-math.ts` (`ordOf`, `periodFromOrd`, `singleQuarter`, `ttmEndingAt`,
  `yoyPct`; `bank-fundamentals.ts` now imports it). TL only (no currency selector);
  inline sparklines + latest-left/right ordering were explicitly out of scope.
- **Pinned page header (2026-06-26).** The page header that carries the global
  1Y/3Y/5Y/YTD/All chart-range selector (`web/app/components/ui/page-header.tsx`) is now
  `position: sticky` at `top-0` on `lg+` (frosted `bg/90` + `backdrop-blur`), so the range
  control stays reachable on long chart pages. Below `lg` it stays static — the mobile nav
  bar owns `top-0` there. On `/banks/[ticker]` the header and the sticky section-nav are
  wrapped in one pinned group so they stack (header on top, nav below) instead of colliding
  at `top-0` (`sticky={false}` on the header; nav `lg:static`; 2026-06-27).
- **"Drivers behind the outcomes" data gaps (2026-06-20).** Tier-A margin engine +
  market share shipped (see Dashboard §Compare). **FX net open position** and
  **interest-rate repricing/maturity gap** also **shipped 2026-06-29** — deterministic
  fitz extractors over the §4 market-risk footnotes → `bank_audit_fx_position` /
  `bank_audit_repricing` (migration 0016), powering `/market-risk`. Still deferred,
  with full source/schema/extractor sketches in
  [knowledge/data-gaps-roadmap.md](knowledge/data-gaps-roadmap.md):
  **credit-ratings history** (agency press + KAP, an events table) and the
  **sovereign yield curve / real rate** (EVDS subset buildable; CDS/OIS out of
  scope). Registry ids: `credit_rating`, `sovereign_yield_curve`.
- **Audit extraction — open gaps after the 2026-06-14 lane overhaul.** OCI (→881),
  cash-flow (→813), NPL-movement (→515) and loans-by-sector (→135) were fixed this session
  (see the audit-lane validation-status table). `loans_by_sector` is now at its realistic
  ceiling — the sector breakdown is an **annual-only disclosure**, so most of its "skips"
  are genuine (interim reports have no table). Still open: **`equity_change`** vertical-chain
  tail (~355 fail, pre-existing — the largest remaining lane gap); and the genuine per-bank
  tails on OCI/CF/NPL/loans — non-reconciling disclosures + image-only PDFs (the same
  image-only banks recur: ALBRK/ALNTF/EXIM/ODEA/TSKB), which are real gaps, not extractor
  bugs. Re-extraction is now **non-destructive** (the guard skips passing partitions), so
  any future fix can only improve the corpus.
- **BIST equity-market lane REMOVED (2026-08-01).** Shipped 2026-06-13 (daily
  EOD for the 11 listed banks + XU100/XBANK, valuation, live overlay, market
  ticker); withdrawn because it was sourced from the Yahoo Finance chart API,
  whose terms prohibit redistribution outright and prohibit automated access.
  Both the fetch and every serving path are deleted — scraper, `bist.ts`,
  `bist-live.ts`, `market-ticker.ts`, `valuation-data.ts`, `/api/market-ticker`,
  the `MarketTicker` strip, the `_valuation` route, and the P/B & P/E metrics
  (the `Valuation` family is gone). **Lost:** market cap, P/B, P/E, dividend
  yield, the share-price chart, the BIST index chart, the live tape. **Kept:**
  USD/TRY on `/`, re-sourced to TCMB EVDS `TP.DK.USD.A`. The `bist_*` tables
  remain in D1 with their history — storage is not redistribution, serving is —
  and `bot-sql.ts` denies them to the public bot by name. Revive point `d52ce2d`;
  do not re-enable without a licensed feed. See METRICS.md §17.
- **Cash flow + equity-change extractors shipped; deep-fixed + fleet re-extracted (2026-06-13).**
  Two statement types: `bank_audit_cash_flow` (sort_order=38) and `bank_audit_equity_change`
  (sort_order=36). Root-cause fixes (commits 7322fb3, c62057b): equity locator now uses the
  wide-table fingerprint not the title anchor; CF pinned to 2 value columns (the P&L detector
  misread annual CF date-headers as 4 cols → 0 rows fleet-wide); TEB roman-restart mid-page
  split; DENIZ `--` zeros + EMLAK 15→14 col clamp. Whole fleet re-extracted sequentially,
  manual partitions restored, revalidated, pushed, matrix synced. **CF 0 contamination
  fleet-wide; coverage matrix restored.**
  - **OPEN (non-core follow-ups):** equity_change **vertical-chain** (`eq_col_chain`) fails
    on ~732 partitions — PRE-EXISTING; movement rows (esp. IV comprehensive income) lose a
    blank column → dropped. A validated `_try_fit` fix (insert 0 at the gate-satisfying
    position when a row has n_cols−1 tokens) recovers most banks; GARAN-class consolidated
    (closing row undetected) is a separate deeper issue. Applying needs a fleet re-extract
    (no fast equity-only path; c62057b's dash/clamp is currently only on DENIZ/EMLAK data).
    Also: 136 CF `cf_chain` identity failures; FIBA 2023Q3 cons manual-P&L transcription
    typo left it unpushed (needs source re-check). **Re-extract lesson:** add
    `maxtasksperchild` (ProcessPool workers leaked memory → chunk 6 slowed 10×); never run
    concurrent chunks (R2 snapshot race).
- **All-statement validators complete (2026-06-12).** Six-phase plan shipped:
  OCI extraction + validator (Phase 1); off-balance structural validator (Phase 2);
  §4 capital + liquidity validators surfaced to the coverage matrix (Phase 3);
  credit-quality + stages validators (Phase 4); NPL movement + loans-by-sector
  validators (Phase 5); full `revalidate_audit_db.py` corpus pass + D1 push +
  spine sync (Phase 6). Key validator fixes in this pass: npl_movement skips rows
  where write_offs/sold/transfers_out is NULL (extraction gap, not zero); CAR
  tolerance widened to ±2pp; ATBANK (all) and TEB 2022 consolidated CAR skip-list;
  off-balance uses TL+FC=Total triplet check only (non-contiguous hierarchy);
  loans_by_sector falls back to sub-sector sums when agri/mfg/svc group total is
  absent. Remaining 225 error cells are extraction issues, not validator bugs —
  the largest buckets are npl_movement (87, NULL key-flow columns — extractor
  label-variant gaps) and loans_by_sector (66, mainly YKBNK no-breakdown + FIBA
  agri_fishery double-count + HSBC missing `other`). OCI: **three fixes 2026-06-20
  took the lane 881→946/975 pass.** (1) `_locate_oci_page` now skips P&L pages —
  the BRSA combined title "…VE DİĞER KAPSAMLI GELİR TABLOSU" made the locator stop
  on YKBNK's quarter-only P&L twin (it captured the income statement as OCI for 16
  partitions); it now rejects any candidate carrying an interest/profit-share
  income anchor, window widened pl+1→pl+6 (all 34 YKBNK pass). (2) pdfplumber
  fallback for the **wide-interleaved-table** banks (GARAN/AKBNK combined
  "Profit or Loss AND Other Comprehensive Income" page that fitz scatters):
  `_locate_oci_page` re-scans with pdfplumber layout-repaired text when the fitz
  pass finds nothing, and `extract_oci` adds pdfplumber candidates when no fitz
  candidate validates — both gated on fitz failing so the fast path is untouched.
  Recovered all 7 GARAN empties **and** ~34 dropped-leaf fails (fitz was
  fragmenting sub-rows pdfplumber reads). (3) **coordinate reconstruction**
  (`_coord_oci_text` + `_fitz_visual_rows`) for sub-rows whose label/value/marker
  print on different physical lines — a value on its own line ABOVE a marker-only
  line (ALNTF 2.2.2), or a wrapped-label continuation below; rebuilds rows from
  fitz word x/y and feeds clean lines to the text parser. Added ONLY when no
  candidate foots the sub-trees AND only if the coord candidate ITSELF fully
  validates (chain+hierarchy), so it can't displace a correct parse — recovered 8
  (ALNTF ×5, ATBANK 2025Q2, SKBNK 2022Q4, KUVEYT 2024Q2), zero regression.
  **Remaining 29 are genuine:** 9 empties = FIBA/ISCTR/TFKB/TSKB **image-only PDFs**
  (P&L hand-transcribed, no parseable OCI page); 20 fails = the residual cosmetic
  tail (totals + I/II/III + 2.1/2.2 parents all correct, one leaf short):
  DENIZ/ING/QNBFB *multi*-wrap leaves (consecutive wrapped rows the single-row
  coord pass doesn't fully reassemble), VAKBN 2.2.1→2.1.1 digit misread,
  TSKB/VAKIFK value column-slips, + 3 cross-mismatch + 2 chain (ATBANK date-header
  noise, KLNMA). All validation-gated, so safe-but-unfixed.
  Off-balance: 20 partitions across 7 banks (ALNTF column-alignment, TEB year-end
  format, ZIRAAT 2025Q4/2026Q1 new). ISCTR 2025Q1/Q2 capital CAR=100.0 = 2 genuine
  extraction errors. Dashboard surfacing of §4 capital/liquidity cross-bank view
  remains an open follow-up.
- **Capital validator hardened (2026-06-15).** `check_capital` previously only
  checked orderings (CET1≤Tier1≤Total, always true) + CAR=Total/RWA, so a
  mis-extracted component passed silently. It now reconciles the whole table:
  composition (Tier1=CET1+AT1, Total=Tier1+Tier2; optional AT1/Tier2 treated as 0
  but passing only when it ties — and a base alone exceeding the parent hard-fails)
  + sub-ratios (cet1_ratio=CET1/RWA, tier1_ratio=Tier1/RWA, CAR=Total/RWA, ±2pp).
  Required `revalidate_audit_db._capital_rows` to also read AT1/Tier2/cet1_ratio/
  tier1_ratio. Revalidated + pushed to D1 → 26 capital cells now `error` (was 2),
  all **genuine §4 extraction bugs**, not validator over-strictness:
  - **AT1 dropped** (read 0 while Tier1>CET1): ICBCT, QNBFB 2022–23, SKBNK, TSKB
  - **Tier2 dropped** (read 0 while Total>Tier1): QNBFB 2025–26, SKBNK
  - **column-slip**: ISCTR 2023Q3/2024Q3 `total_capital==tier2`; ISCTR 2025Q1/Q2
    cons `total_rwa==total_capital`
  → **RESOLVED 2026-06-21**: the §4 capital extractor was fixed (AT1/Tier2 row
  capture + total/RWA column alignment); the lane went 26 → **0** failing partitions
  (see the validation-status table). **Liquidity validator is at its
  ceiling** (band-only) — making it reconcile needs extracting LCR/NSFR component
  sub-tables (HQLA, net outflows), a separate task.
- **P&L flow Sankey shipped (2026-06-12)** — on `/banks/[ticker]` (Income
  Statement view, below the table since 2026-06-24): a hand-rolled SVG Sankey of the selected
  period's P&L, YTD as reported. Pure derivation + layout in
  `web/app/lib/pl-sankey.ts` (unit-tested — vitest is now in `web/`, `npm run
  test`, wired into CI), card shell `PlSankeySection.tsx` with client-side
  period pills, renderer `PlSankeyChart.tsx`. Contra lines normalized to
  magnitudes (same rule as the tables — handles the paren-negative banks);
  genuinely negative items (VI. trading, XVI. monetary position, tax credits)
  are re-routed across their subtotal (red ribbons) with the filed figure
  always in the label; tax is derived as XVII−XIX (XVIII is sign-ambiguous).
  Internal-sum checks gate rendering: ≤0.5% silent, ≤5% amber note, >5%
  suppressed. Data via `profitLossRowsMultiPeriod()` in `web/app/lib/audit.ts`
  (fetched only when `statement=is`).
- **TEFAS funds lane shipped (2026-06-11)** — `tefas_*` aggregates in D1,
  `/funds` tab live. Caveats by design: investor counts double-count people
  holding several funds; GYF/GSYF excluded from time series (not daily-priced);
  manager names extracted from the fund-title prefix (sector sums are invariant
  to mis-bucketing); changing any normalization rule requires re-running the
  backfill (aggregated at ingest, per-fund rows not persisted). The healthcheck
  `tefas` threshold (120 h on the data date) may fire one benign alert over
  multi-day religious holidays. Follow-ups: a manager/bank-affiliated view off
  the existing `manager` dimension; carry-forward aggregation for GYF/GSYF.
- **KAP ownership lane shipped (2026-06-11)** — `kap_ownership` in D1
  (379 rows, 30/31 banks; weekly via `refresh-data.yml`). Surfaced on
  `/banks/[ticker]` as an Ownership card (≥5% direct + indirect holders with
  share bars, paid-in capital / registered ceiling, per-class actual free
  float; `web/app/components/OwnershipCard.tsx` + `web/app/lib/kap.ts`) and a
  Subsidiaries & financial investments table (§7 grid, item='subsidiary',
  amounts in the filing currency; `SubsidiariesCard.tsx`, migration 0007 —
  only the ~15 full-form banks file it). ATBANK publishes no Genel Bilgi
  Formu (cards hidden); `as_of` filing dates can be years old
  (structure-change driven). Possible follow-up: ownership taxonomy
  cross-check vs `bank_types`.
- **Interactive ownership visualization shipped (2026-06-12)** — two views off
  the same `kap_ownership` data: an interactive radial map on `/banks/[ticker]`
  (shareholders fan the top arc, §7 subsidiaries the bottom; hover tooltip,
  click-to-pin details panel; `OwnershipRadial.tsx`) and a sector-wide
  `/ownership` network tab. Default "All holdings" view is a force-directed
  layout (d3-force, precomputed deterministically server+client so hydration
  agrees; `web/app/lib/ownership-force.ts`): banks anchored loosely to a
  type-ordered ring and sized by latest total assets (`bankSummaries()`,
  fail-soft to uniform), each bank's ~212 non-shared holdings settle as
  organic clusters, shared entities (Treasury/TVF/BKM/Takasbank/KGF/…) pulled
  between their banks, bank-to-bank stakes as dashed arrows (İş → TSKB/Arap
  Türk, Ziraat → Ziraat Katılım). Hover highlights the ego-network and fades
  the rest; labels have halo strokes and holding names appear on hover/zoom;
  "Shared only" toggle keeps the quiet structural ring; wheel-zoom/drag-pan
  with animated reset; `?focus=TICKER&view=shared` deep links. Cross-bank identity is exact-match alias
  normalization in `web/app/lib/ownership-graph.ts` (Turkish-aware case fold;
  the İş pension fund name contains "İŞ BANKASI" — never substring-match).
  All custom SVG, no new deps; one new all-banks query `sectorOwnership()` in
  `web/app/lib/kap.ts`.
- **Audit rework Phases 0–4 + ECL fix complete (2026-06-12).** Full history
  of 975 PDFs extracted and validated across all 12 statement types.
  `bank_audit_validation` has 35,100 rows in D1 (975 partitions × 12 types,
  36 rows/partition). Coverage matrix drives the iterative repair workflow:
  `/admin` matrix surfaces error cells with `failed_detail` JSON; per-cell
  Re-extract and `scripts/revalidate_audit_db.py` are the repair levers.
  See "All-statement validators complete" entry above for the current error
  breakdown. See `docs/RESUME_AUDIT_FIX.md` for the earlier P&L + BS fix history.
- **Balance-sheet rows dropped / corrupted by spurious number matches (resolved
  2026-06-10).** `extractor.py`'s `_parse_rows` counted three non-values as
  value columns: the row's own hierarchy token (`2.4`, `1.1.4.`), the dash
  inside the label decoration `(-)`, and the parenthesized dipnot ref `(6)`
  (which `parse_num` reads as **-6**). A 6-column row could then "carry 9
  numbers", triggering the EXIM multi-period branch (first-6 → garbage values),
  while the `rfind`-based label boundary landed at position 0 (row silently
  dropped) or inside `(-)` (label truncated at `(`, dipnot stored as the
  value). Surfaced as ALBRK's `/banks` page showing **Expected Credit Losses =
  -6** (true value 6,057,750 at 2025Q4); the new `ecl` quality check found the
  class across **17+ banks / ~435 (bank, quarter, kind) rows** (AKTIF ALNTF
  ATBANK BURGAN EMLAK EXIM FIBA HALKB HSBC ING KLNMA PASHA QNBFB TEB TFKB TSKB
  ZIRAATK; TEB lost its ECL rows every Q4; ALBRK/EMLAK lost them in 2026Q1).
  Fix: scan value tokens with `finditer` positions (label = text before the
  first taken token), skip a leading hierarchy marker, anchor the bare dash to
  whitespace, and drop parenthesized 1–2-digit dipnot refs when the line has
  surplus tokens; `_fitz_merge_rows` accumulation now counts with the same
  rules. Regression-verified on 29 PDFs covering every layout quirk (EXIM
  multi-period, AKBNK fitz path, ZIRAAT/VAKBN wrapped rows, TSKB squished
  text): zero count decreases, zero total changes; every bank *gains* rows
  (e.g. GARAN 32→46 asset rows — the bug also dropped non-ECL rows
  fleet-wide), and ALBRK 2025Q4 recovers its `TOTAL ASSETS` row. A new
  `check_audit_quality.py` **ecl** check alerts on truncated labels, tiny
  |ECL| on large banks, and ECL rows vanishing vs the prior quarter. Notes:
  ING/KLNMA/PASHA/TFKB print the ECL *value* in parens → stored negative is
  the faithful reading (display-normalization is a follow-up); TSKB has
  separate pre-existing split-digit damage (`…(-) 1.849.927 5.` label) still
  open. Full-fleet re-extraction backfilled to D1 + the R2 snapshot via
  `scripts/backfill_extraction.py --banks ALL`.
- **Stage-3 NPL understated by FC-only sub-table (resolved 2026-06-07).** The
  per-bank NPL ratio / coverage on `/cross-bank` (and per-bank pages) was
  understated for ~11 templated banks because the IFRS-9 Stage-3 extractor's
  **template path** latched onto the *foreign-currency-only* NPL sub-table
  ("Yabancı para olarak kullandırılan…" / "in foreign currencies") instead of
  the total III/IV/V classification — so e.g. DENIZ read 0.00% (real ~5.4%),
  AKBNK 0.73% (real ~3.8%), ZIRAAT/ISCTR/YKBNK/TEB/KUVEYT/AKTIF/FIBA/ICBCT/ODEA
  all similarly low. Root cause: those banks' main provision/gross rows use
  labels that differ from their `audit_templates.json` entry ("Karşılık (-)" vs
  template "Karşılık Tutarı"), so the template could only pair gross+provision
  *inside* the FC-only block. Fix: the template path now skips FC-only blocks
  (shared `_is_fc_only_block` helper, already used by the regex path); when that
  leaves no template gross row, extraction falls back to the language-agnostic
  regex path, which scopes the total table correctly. Verified on all 11 changed
  banks (each old value = that bank's FC-only subset; each new value = the total
  NPL movement row); 18 banks unchanged, **zero regressions**. 2026Q1 backfilled
  to D1 + the R2 snapshot via `scripts/backfill_extraction.py --banks ALL
  --latest-period`; the 11 affected banks' **history** backfilled separately so
  the `/cross-bank` Over-time view has no fake cliff. A new
  `check_audit_quality.py` **npl_drop** check now alerts if any quarter's Stage-3
  ratio crashes from ≥1% to <0.1% (the fingerprint of this bug) on a future
  report-format change. Minor residual: ODEA's regex pick takes the prior-period
  end-balance when current < prior (~2% high) — immaterial to ranking.
- **EXIM multi-column report (resolved 2026-06-06).** Eximbank's recent reports
  (2025Q3+) print 3 balance-sheet period columns (TL/FC/Total × current / prior /
  restated) and a 4-column interim income statement (cumulative + 3-month ×
  current / prior). The extractor assumed 2 periods and took the wrong columns —
  storing the prior period as current, so EXIM's figures showed under the wrong
  dates. Both are now handled in `extractor.py` (BS: take the first triplet pair
  on >6-column rows; P&L: `_detect_pl_ncols` → cumulative current = col 0, prior
  = col n//2), validated to be a no-op for the 2-column banks, and EXIM was
  re-extracted + backfilled to D1 + the R2 snapshot via
  `scripts/backfill_extraction.py`. EXIM is the **only** bank with the 3-period
  balance sheet (verified by `scripts/audit_extraction.py` + a D1 duplicate-quarter
  scan). Credit-quality / stages / loans / NPL tables were unaffected.
- **Grand-total rows now captured (2026-06-06).** `TOTAL_PAT` only matched
  English `TOTAL`, so Turkish reports' `VARLIKLAR TOPLAMI` / `PASİF TOPLAMI`
  grand-total rows were dropped (they carry no hierarchy prefix). Now also
  matches `TOPLAM`. Dashboard total-assets was **never** affected (it sums the
  roman subtotals I.–X., not the total row — `web/app/lib/audit.ts`); this is
  completeness + it lets the data-quality balance check cover all banks.
  Verified across all banks: **26/27 now capture both totals and balance**;
  only **AKBNK** still misses total *liabilities* (its label is detached from
  the numbers row in the PDF — a narrow per-bank layout quirk; the balance check
  skips it rather than false-alarm). 2026Q1 was backfilled to D1 + the R2
  snapshot via `scripts/backfill_extraction.py --banks ALL --latest-period`,
  which now **clears each re-extracted (bank, period) partition in D1 before the
  upsert-only push** — otherwise an older, larger extraction leaves orphan rows
  at item_orders the fresh extract no longer produces.
- **TSKB 2026Q1** — bank rotated their IR URL; current entry in
  `audit_report_urls.json` 404s. Skip for now; refresh the URL when TSKB
  publishes the next quarter.
- **A handful of pre-existing partial extractions** (~2% of PDFs flagged
  `success=0` in `bank_audit_extractions`, 20 of 974) — mostly VAKBN
  consolidated historical quarters with layout edge cases. Triable
  bank-by-bank if needed.
- **Bank-profile coverage gap** — 15 of 31 banks (AKTIF, ALBRK, ATBANK,
  BURGAN, EMLAK, EXIM, FIBA, ING, ISCTR, KLNMA, KUVEYT, ODEA, TFKB, TSKB,
  VAKIFK) disclose branches/personnel in phrasings not yet covered by the
  regex patterns in `src/audit_reports/bank_profile.py`. Add patterns as
  needed; the qualitative section is always in the first 25 pages.
- **Rates dashboard** — some panels from the old Dash app aren't ported yet
  (gold tons, expectations). CBRT reserves, net funding and residents' FC are
  now live on the new **Liquidity** tab.
- **Monthly EVDS series were silently empty** until the 2026-06-05 date-parse
  fix in `evds_client._parse_evds_dates` (EVDS returns monthly dates as
  `YYYY-M`, previously dropped). CPI, inflation expectations, REER and
  residents' FC repopulate on the next refresh. New series added: REER
  `TP.RK.T1.Y`.
