# Project State

Concise snapshot of what's in the system right now. Updated as data
coverage or known issues change.

> **Reading order:** [README.md](../README.md) → [ARCHITECTURE.md](ARCHITECTURE.md)
> → this file → [OPERATIONS.md](OPERATIONS.md). Metric definitions in
> [METRICS.md](METRICS.md); meta-knowledge about banking metrics (which are
> disclosed, standardized across banks, on a regular cadence, and reproducible
> from our data) in [BANKING_METRICS.md](BANKING_METRICS.md) — a 153-metric
> registry (`data/metric_knowledge/`, CLI `scripts/metric_knowledge.py`).
>
> Last verified: 2026-07-14. Dated change history → [CHANGELOG.md](CHANGELOG.md).

---

## Data coverage in D1

| Table | Source | Range | Latest |
|---|---|---|---|
| `balance_sheet`, `income_statement`, `loans`, `deposits`, `financial_ratios`, `other_data` | BDDK monthly bulletin | 2020-01 → present | 2026-05 |
| `weekly_series` | BDDK weekly bulletin | 2019-11 → present | rolling 2-week lag |
| `nonbank_balance_sheet` | BDDK non-bank monthly bulletin (BultenAylikBdmk) | 2008-01 → present | leasing / factoring / financing, monthly, balance sheet (Million TL); reconciles to FKB sector totals. VYŞ (sparse/variant feed) + savings-finance (not in this bulletin) deferred |
| `evds_series` | TCMB EVDS | 2018-01 → present | daily / weekly / monthly per series. Loan/deposit **rates here are SECTOR-level only** (`TP.KTFTUK`/`TP.KTF17`/`TP.KTF12`/`TP.TRY.MT06`) — the per-bank complement is `bank_advertised_rates` below |
| `bank_advertised_rates` | doviz.com (loans) + hangikredi (deposits) — public rate-comparison pages | 2026-07-12 → present (accumulating) | weekly (Mon); per-bank **advertised** (posted-to-new-customers) rates — the only per-bank rate source, since EVDS/BDDK publish rates at sector granularity only. Loans = POINT rate, MONTHLY % (consumer/mortgage/vehicle); deposits = min–max BAND, ANNUAL %. Each run appends a dated `snapshot_date` (the sources only expose "today", so history builds forward — rows never deleted). Distinct from the P&L-derived *realized* yield/cost in `heatmap.ts` |
| `tbb_digital_stats` | TBB quarterly digital-banking report | 2019-Q1 → present | quarterly (Mar/Jun/Sep/Dec) |
| `tkbb_digital_stats` | TKBB Veri Peteği (Turboard JSON API) — participation-bank digital stats | 2020-Q1 → present | quarterly; active customers (total/channel-mix/province) + txn volume & count (channel/segment/category), RAW units |
| `tkbb_acquisition_stats` | TKBB Veri Peteği — remote-vs-branch acquisition | 2025-07 → present (accumulating) | monthly; source exposes only a rolling 12-month window — history builds forward, rows never deleted |
| `kap_ownership` | KAP Genel Bilgi Formu §5 + §7 subsidiaries (kap.org.tr) | current state per bank (`as_of` = filing date) | weekly full replace; 30/31 banks (ATBANK files no form); subsidiaries grid only on the full form (~15 banks) |
| `tefas_manager_daily`, `tefas_category_daily`, `tefas_allocation_daily`, `tefas_top_funds` | TEFAS fund-market JSON API (tefas.gov.tr) | rolling ~5 years (API rejects older start dates) → present | daily T+1, trading days; aggregated at ingest (no per-fund rows) |
| `bist_prices`, `bist_dividends`, `bist_shares` | Borsa İstanbul via Yahoo Finance chart API | 2014-06 → present | daily EOD (~1-day lag); 11 listed banks + XU100/XBANK indices (QNBFB delisted on Yahoo — no data) |
| `faaliyet_franchise` | Bank annual reports (Faaliyet Raporu PDFs) | annual (FY ending 31 Dec) | ATM / POS / merchant / customer / card counts (the stats audit reports don't carry; branches & employees stay in `bank_audit_profile`); deterministic regex+coordinate extraction with confidence flags. **⚠️ NOT TRUSTWORTHY — the `/franchise` tab is unpublished (2026-07-12): the extractor samples stray prose numbers, ~75% of non-ATM values are wrong and the confidence flags don't correlate with correctness. Needs a rebuilt extractor + validation gate, NOT more URL curation** |
| `faaliyet_extractions` | per-PDF extraction ledger for the lane above | — | one row per annual report processed: success flag, rows written, confidence — the lane's audit trail |
| `tbb_acquisition_stats` | TBB workbooks — remote-vs-branch customer acquisition | monthly | the **TBB** twin of `tkbb_acquisition_stats` above (deposit banks vs participation banks) |
| `regulation_briefings` | BDDK/TCMB regulation text → weekly Kimi summary | weekly (Sun 06:00 UTC cron) | one briefing row per run. **Since 2026-07-13 it no longer supplies any figure on `/regulation`** — the corridor and reserve ratios are compiled from `news_items.body_text` + EVDS and reconciled, so an LLM can never set a number on the page. The briefing now supplies **editorial coverage only**: the categories the band does not model (licensing, payments, structure). Two categories stay unsourced by design — see [regulation_followups.md](regulation_followups.md) |
| `bank_audit_balance_sheet` (assets / liabilities / off-balance) | BRSA quarterly PDFs | 2022-Q1 → 2026-Q1 | per-bank |
| `bank_audit_profit_loss` | BRSA quarterly PDFs | same | per-bank |
| `bank_audit_pl_roles` | **derived** — `validator.pl_roles()`, rebuilt from stored rows beside the validation (no re-extraction) | same | **which P&L row IS the period-net / gross / the two opex lines, under THAT filer's own roman numbering.** Exists because BRSA ordinals are NOT fixed: the compressed template some participation banks file puts net-operating at XII and period-net at XXIV, not XIII/XXV. A SQL consumer that hardcodes an ordinal reads the wrong LINE — `heatmap.ts` did, and reported DUNYAK's net profit as **0** for six quarters (`COALESCE(XXV., XIX.)` fell through to XIX = discontinued-ops income, nil) while summing net operating *profit* into opex on 9. Consumers **join this table**; the resolution stays in Python, which has the Turkish fold SQL's ASCII-only `UPPER()` lacks. 9,437 rows / 9 roles |
| `bank_audit_credit_quality` | BRSA PDFs, IFRS 9 footnotes | same | per-bank, per-section |
| `bank_audit_profile` | BRSA PDFs, qualitative section | same | branches + personnel where disclosed |
| `bank_audit_free_provision` | BRSA PDFs, auditor's report + "Other provisions" note | 2022-Q1 → 2026-Q1 | **the free provision (serbest karşılık)** — discretionary reserve behind the ALBRK case. Classifier (`free_provision.py`) + **111 hand-transcribed overrides** (`data/free_provision_overrides.json`, read from full auditor qualifications; 0 = fully-cancelled/'Yoktur'/not-published). **581 rows / 503 holding / 78 zero.** Guarded by the `freeprov` validator (band + prior-chain + opinion cross-check): **anomalies 114→4** — 2 are genuine (ISCTR free provision under a clean opinion), 2 an EMLAK-2026Q1 prior-field residual. Re-extract delete-then-insert; overrides win outright. |
| `bank_audit_opinion` | BRSA PDFs, auditor's report (front matter) | 2022-Q1 → 2026-Q1 | **the auditor's verdict** — `opinion_type` clean/qualified/adverse/disclaimer + `is_modified` flag + the "Basis for Qualified…" paragraph + firm + audit-vs-review. Deterministic text classifier (`src/audit_reports/audit_opinion.py`), EN+TR / audit+review. Built + **backfilled 2026-07-15**: 976 rows / 38 banks in D1, **552 modified (57%) / 424 clean** — the free-provision practice behind the ALBRK Q1 case is sector-wide (PwC/EY/KPMG all qualify over it; state banks also over bond reclassifications). Basis paragraph captured for 545/552 modified. Backfill via `reextract-statement.yml` (statement=`audit_opinion`, force, only_failing off — no validator, like `profile`) |
| `bank_audit_capital` | BRSA PDFs, §4.1 capital adequacy | same — **fully backfilled 2026-06-10** (31/31 banks, ~1.7k rows) | CET1/Tier1/Tier2/Total/RWA + CET1/Tier1/CAR ratios, per period_type |
| `bank_audit_liquidity` | BRSA PDFs, §4.6/4.7 | same — **fully backfilled 2026-06-10** (31/31 banks, ~1.8k rows) | LCR (total/FC), NSFR, leverage ratio, per period_type |
| `bank_audit_fx_position` | BRSA PDFs, §4 currency-risk footnote | same — **backfilled 2026-06-29 (7,143 rows / 31 banks → 2026Q1)** | FX net open position per currency (EUR/USD/OTHER/TOTAL) × period_type; net_position = net_on + net_off (~99% coverage). Powers `/market-risk`. ⚠️ **D1 was stranded at that backfill** — see the note below |
| `bank_audit_repricing` | BRSA PDFs, §4 interest-rate-risk footnote | same — **backfilled 2026-06-29 (10,364 rows / 24 banks → 2026Q1)** | Repricing gap per bucket (lt_1m…gt_5y/non_sensitive/total) × period_type (~81% coverage; participation banks omit → validated N/A). ⚠️ same as above |
| `bank_audit_oci`, `_cash_flow`, `_equity_change`, `_npl_movement`, `_stages`, `_loans_by_sector` | BRSA PDFs (statement pages + IFRS-9/credit footnotes) | 2022-Q1 → 2026-Q1 | per-bank; per-lane pass rates in the validation-status table below |
| `bank_audit_extractions` | extraction log | one row per PDF | **1,050 rows, 1,050 core-success (100%)** across the 38-bank universe (D1, 2026-07-14). The per-lane pass/fail tables below are a dated **2026-06-14** snapshot taken when the fleet was 31 banks / ~975 partitions — read their counts as of that date, not as today's totals |
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

**Takasbank (`TAKAS`) — carried, but NOT a peer.** İstanbul Takas ve Saklama Bankası is
BDDK-licensed as a development-and-investment bank and files standard quarterly BRSA
reports (16 periods, 2022Q2→2026Q1), but it is Turkey's central securities-settlement /
clearing (CCP) + custody institution — market infrastructure, not a lender: **zero
deposits**, customer loans ~2.5% of assets, ~94% of the balance sheet in cash +
placements (member cash and collateral it merely custodies), plus ~178bn TL of
off-balance CCP guarantees. It is therefore **excluded from peer ranking, the
market-share league and the sector HHI** — `PEER_EXCLUDED_TICKERS` in
`web/app/lib/bank_names.ts`, enforced at the single choke point in `heatmap.ts`
(`ensure`) and `market-share.ts` (`fleetBalances`). It keeps its own `/banks/TAKAS`
page, where balance sheet / capital / liquidity ARE meaningful. Two sourcing quirks:
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

**Acquisition vs extraction (2026-06-12)**: only acquisition is automated —
`acquire-audit.yml` (weekly) discovers + downloads new PDFs to R2, refreshes the
`/admin` coverage matrix, and pings Telegram. **Extraction is admin-managed**:
`refresh-audit.yml` is dispatch-only, triggered from the matrix's per-cell
Re-extract or the Pipeline "Extract audit reports" card. The coverage matrix
(statement type × bank × period) is the control surface — a new quarter appears
as a `missing` cell to extract.

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
pins it). **Open follow-up: D1 still needs a one-off reconciliation** — re-push
`fx_position`/`repricing` from the R2 snapshot (or re-extract the two statements via
`reextract-statement.yml`) to recover the quarters D1 missed.

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

**Audit-lane validation status** — a **dated snapshot: D1 as of 2026-06-14**, when the
fleet was 31 banks / ~975 partitions (it is now 38 / 1,050; the counts below have not
been re-run). Every extracted
statement is self-validated (internal-sum / roll-forward / cross identities); the
`/admin` coverage matrix and the non-destructive re-extract guard both key off this.

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

OCI/CF/NPL were fixed this way: a recent-vs-older-quarter diagnostic → small generic
fixes → ship via `reextract-statement.yml`. Residual fails are genuine per-bank
non-reconciling disclosures + image-only PDFs, not extractor bugs.

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
| `<ticker>/<TICKER>_<period>_<kind>.pdf` | Cloudflare R2 (`bddk-audit-reports`) | `acquire-audit.yml` (weekly) when banks publish |
| `state/bddk_data.db.gz` | Cloudflare R2 (same bucket) | bulletin/EVDS cron (bulletin lane snapshot) |
| `state/bank_audit.db.gz` | Cloudflare R2 (same bucket) | `refresh-audit.yml` (admin-triggered extraction) — the audit-lane snapshot writer |
| `state/history/<lane>-YYYYMMDD.db.gz` | Cloudflare R2 (same bucket) | every cron — dated backup, last 7 kept |
| Next.js page-data cache | Cloudflare KV (`NEXT_INC_CACHE_KV`) | dashboard render (12h TTL on D1 reads) |
| `data/banks/audit_report_urls.json` | git | hand-edited via PR |
| `data/banks/bddk_bank_list.json` | git | hand-edited via PR |
| `src/`, `scripts/`, `web/` | git | hand-edited via PR |

## Active workflows

Two independent ingestion lanes (separate staging DB + R2 snapshot +
concurrency group), so audit failures can't stall the bulletin pipeline:

- `.github/workflows/refresh-evds-daily.yml` — Sun–Fri 05:00 UTC. EVDS scrape → D1. Also carries the non-critical BIST / TBB / TKBB / KAP / TEFAS steps of `refresh.py` (BIST re-fetches a trailing 35-day window daily — self-heals the EOD ~1-day lag, holidays and late closes; TEFAS re-fetches a trailing 7-day window daily).
- `.github/workflows/refresh-bddk-bulletins.yml` — Daily 13:00 UTC (monthly-only) + Fri 13:30/15:30 UTC (weekly-only) + Sat 02:00 UTC (weekly backstop). BDDK bulletins (no EVDS, no audit) → D1. The **daily** run probes for a new monthly (`update_monthly.py` scrapes only when BDDK has published one — mid-month, no fixed day); the **Friday** runs grab the weekly the same afternoon BDDK publishes it (~16:00–18:00 Turkey). Per-schedule lane split via `github.event.schedule`; manual dispatch does both. A positive Telegram ping (`notify_new_bddk.py`) fires when a new weekly/monthly period lands.
- `.github/workflows/refresh-data.yml` — Sat 03:00 UTC. Monthly + weekly + EVDS + TBB digital-banking (quarterly) + TKBB participation-bank digital + KAP ownership structure + TEFAS fund market → D1. *(Audit removed — now its own workflow.)* TBB, TKBB, KAP and TEFAS are non-critical steps in `refresh.py` (an outage won't abort the BDDK refresh); they ride the bulletin lane's snapshot, so no new lane. KAP details in [OPERATIONS.md](OPERATIONS.md) §KAP ownership; TEFAS in §TEFAS fund market; TKBB in §TKBB participation-bank digital statistics.
- `.github/workflows/backfill-tefas.yml` — manual dispatch only. Resumable ~5-year TEFAS history backfill (the API rejects start dates older than 5 years; 28-day windows, rate-limited ≈2–2.5 h; re-dispatch with the same `from` to resume — completed windows are skipped via `tefas_fetch_log`).
- `.github/workflows/backfill-nonbank.yml` — manual dispatch only. One-time historical backfill of the non-bank sector lane (leasing/factoring/financing) from `from_year` (default 2020 = banking-aggregate horizon) → now (~5–10 min). The incremental refresh rides `refresh-bddk-bulletins.yml` / `refresh-data.yml` (non-critical `update_nonbank.py` step in `refresh.py`); this workflow is only for the initial history load. Apply migration 0013 (via a `web/**` deploy) before dispatching.
- `.github/workflows/refresh-presentations-weekly.yml` — Sat 06:00 UTC. `scripts/update_presentations.py` → `bank_earnings` (IR presentation decks) → D1 (`--only-tables=bank_earnings`). Bulletin lane (`bddk-pipeline` group), rides the shared snapshot. Tier-1 results filings instead ride the daily `refresh-news-daily.yml` (classified in `sync_news.py`). Apply migration 0015 (via a `web/**` deploy) before the first push.
- `.github/workflows/refresh-advertised-rates.yml` — Mon 06:00 UTC. `python -m src.rates.scraper` → `bank_advertised_rates` → D1 (`--only-tables=bank_advertised_rates`). Bulletin lane (`bddk-pipeline` group), rides the shared snapshot (re-gzips it explicitly — this lane doesn't run `refresh.py`, which is what VACUUMs+gzips for the other refresh workflows). Migration 0023 applies via the `web/**` deploy that ships it.
- `.github/workflows/refresh-calendar.yml` — 1st of month 06:00 UTC. `python -m src.release_calendar.scraper` → `release_calendar` → D1 (`--only-tables=release_calendar`). Scrapes TCMB's published "MPC Meeting and Reports Calendar" (rate decisions + minutes + Inflation Report + Financial Stability Report) so the **Ahead** strips fill themselves; retires the hand-typed `MPC_DATES` (now a render-time fallback, still guarded by `check_calendar_fresh.py`). `requests`+`lxml`, no browser — same `www.tcmb.gov.tr` host the news lane scrapes. Bulletin lane (`bddk-pipeline` group), re-gzips the snapshot explicitly. Migration 0025 applies via the `web/**` deploy that ships it.
- `.github/workflows/refresh-audit.yml` — **manual dispatch only** (no schedule; extraction is admin-reviewed — the Sunday 04:00 UTC cron belongs to `acquire-audit.yml`, which only *acquires* PDFs). Audit-report extract → `bank_audit_*` → D1. Own DB `data/bank_audit.db`, own snapshot `state/bank_audit.db.gz`, own group `bddk-audit`. Dispatch takes optional `bank` / `skip_scrape` inputs (the /admin per-bank trigger uses `bank` → `--only-bank … --latest-period`). After extraction it runs `scripts/check_audit_quality.py --alert` (alert-only): flags a quarter whose lines are identical to the prior one (period-shift), a balance sheet that doesn't balance, or missing rows → Telegram/Discord, never blocking the push.
- `.github/workflows/reextract-statement.yml` — manual dispatch. Targeted single-statement re-extract via `scripts/reextract_statement.py`: pull snapshot → re-extract ONE lane (`oci`/`cash_flow`/`equity_change`/`npl_movement`) for the selected partitions → inline-validate → push that table + `bank_audit_validation` to D1 → snapshot → refresh coverage matrix. Shares the `bddk-audit` group. Inputs: `statement`, `banks`, `periods` (blank=all), `only_failing` (default true — selects `checks_failed>0 OR checks_passed=0`, so it catches the stale empties and skips the proven-passing rest), `dry_run`. This is the lane used to fix OCI/CF/NPL fleet-wide.
- `.github/workflows/backfill-audit.yml` — manual dispatch. Full re-extract (all statements) of named banks via `backfill_extraction.py` (`ALL` exceeds the timeout → 5-bank chunks).
- `.github/workflows/backfill-faaliyet.yml` — manual dispatch. Fleet backfill of the Faaliyet-raporu franchise lane → `faaliyet_franchise` + `faaliyet_extractions`. The incremental refresh rides `refresh.py` (step 9, non-critical).
- `.github/workflows/summarize-regulations.yml` — Sun 06:00 UTC. Weekly regulation briefing via Kimi → `regulation_briefings` → D1. Needs the `KIMI_API_TOKEN` repo secret, which the workflow maps to env `KIMI_API_KEY` (the name `src/news/kimi.py` reads) — see [OPERATIONS.md](OPERATIONS.md) §Secrets. Open follow-up in [regulation_followups.md](regulation_followups.md).
- `.github/workflows/deploy-cloudflare.yml` — on push to `web/**`. Apply D1 migrations + build + deploy dashboard.
- `.github/workflows/healthcheck.yml` — daily 06:00 UTC. D1 freshness check → Telegram/Discord alert if stale. Also runs `scripts/verify_chart_spec.py --alert`: re-resolves every reproduced chart in `web/app/lib/chart-specs.catalog.json` against D1 and alerts if a series goes blank (0 rows) or drifts past its `verify[]` anchor. See [REPRODUCING_CHARTS.md](REPRODUCING_CHARTS.md).
- `.github/workflows/ci.yml` — on PRs. ruff + pytest + eslint + tsc + vitest. (Dependency bumps via `dependabot.yml`.)

Schema source of truth: hand-authored migrations in `web/migrations/`, applied
by the deploy workflow (`wrangler d1 migrations apply`); `d1_migrations` tracks
what's applied.

## Dashboard

Next.js 16 (React 19, TypeScript 6) + OpenNext on Cloudflare Workers — live at
<https://carthago.app>. D1 reads are cached
~12h via KV (`cachedAll` → `unstable_cache`), so repeat page views don't re-query
D1. A password-gated `/admin` control center (data health, refresh triggers,
traffic) is unlocked by the `ADMIN_PASSWORD` Worker secret; optional
`GITHUB_DISPATCH_TOKEN` enables the trigger buttons and Web-Analytics creds the
traffic panel. The Pipeline panel's audit card supports a **per-bank,
latest-period** trigger, and **13 banks auto-discover** new quarters from their
IR page (no hand-added URL needed) — see [ADMIN.md](ADMIN.md) §Auto-discovery.
Setup in [OPERATIONS.md](OPERATIONS.md) / [ADMIN.md](ADMIN.md).

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

**"The Read" headline — LLM rewrite, Option 1 (2026-07-04, all 8 tabs live):** a
free model (Cerebras `gpt-oss-120b` → Groq `openai/gpt-oss-120b` → `gemma-4-31b`;
chosen in [knowledge/free-model-eval-round3.md](knowledge/free-model-eval-round3.md))
rewrites ONLY the one-sentence lead; the driver bullets stay deterministic. A
weekly CI cron (`generate-reads.yml` → `scripts/generate_read_headlines.py`, keys
already in GitHub secrets) reads the deterministic takeaways from `GET /api/reads`,
number-validates each rewrite, and upserts `read_headlines` (migration 0019) via
wrangler. `web/app/lib/read-headlines.ts` shows the rewrite ONLY while its
`det_hash` matches the live page and it invents no number — else the deterministic
sentence, so it can never drift or go stale. Kimi still owns the regulations
snapshot. All 8 tabs are wired (`reads.ts` computer + `withLlmHeadline` wrap per
page); the failover keeps the SAME model on two providers (Cerebras → Groq
`gpt-oss-120b`) then the deterministic template, so a shown headline always sounds
the same. Per-provider pacing + retry-on-429 keep the primary consistent under
Cerebras's 5-req/min limit.

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
absent from the live HTML while RUM sat at 0. The beacon token is the non-secret
`CF_ANALYTICS_SITE_TAG` var, which is therefore **dual-purpose**: the client beacon's
token *and* the key the `/admin` Traffic panel queries against. It renders nothing
when unset, so `next dev` never pollutes production analytics.

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
and net errors & omissions, fiscal balances as % of GDP, plus BBVA's static
baseline-scenario table. Fed by a `macro` EVDS block (GDP, IP, labor, BoP,
budget — 15 new series incl. CPI 2025=100, which replaces the dead 2003=100
index). See [METRICS.md](METRICS.md) §14.

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
bank-vs-XU100 returns (`bist_prices`, ≥30 obs else a sector-default 1.0), rf a CBRT
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
- **Not built:** earnings-call transcripts/audio — no free, deterministic feed
  exists for Turkish banks (third-party transcripts are paywalled/ToS-gray; webcasts
  are streaming-only). Out of scope given the no-paid-vendor / no-LLM-API constraints.

## Known issues / pending work

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
- **P&L Sankey paints dark palette in light mode (live, 2026-07-02).** Regression
  from the Editorial theme: `web/app/banks/[ticker]/PlSankeyChart.tsx:209` sniffs
  dark mode via `t.tooltipBg !== "#ffffff"`, but Editorial's light `tooltipBg` is
  `#FBFAF7` → always "dark" → dark node/ribbon fills on every `/banks/[ticker]`
  light-theme view. One-line fix when taken: `t.mode === "dark"` (the idiom
  `NimComponentsChart`/`BopFlowChart` already use).
- **Architecture review 2026-07-02 (report only, no code changed).** Live site +
  web/ + pipeline surveyed post-Editorial; verdict sound, debt concentrated. The
  ranked backlog (off-theme chart palettes ×4, uncached `audit.ts` reads on public
  pages, CI silently skipping the fitz/pdfplumber test suite, `push_to_d1.py`
  3-edit table registration, dead extractor code, Dependabot #90 lockfile) lives
  in [knowledge/architecture-review-2026-07.md](knowledge/architecture-review-2026-07.md).
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
- **BIST equity-market lane shipped (2026-06-13).** Daily EOD prices for the 11
  BIST-listed banks + the XU100 / XBANK indices via the Yahoo Finance chart API
  (keyless, headless) → `bist_prices` / `bist_dividends` / `bist_shares` in D1
  (12y backfill, 2014→present). Source: `src/scrapers/bist_client.py` +
  `bist_scraper.py`; rides the daily EVDS workflow (non-critical step in
  `refresh.py`). Universe derived from `data/banks/bddk_bank_list.json`
  (`listed && bist_ticker`) — never hardcoded. Surfaced: an "Equity Markets"
  rebased XU100-vs-XBANK chart on `/economy`, and a "Market & Valuation" section
  on `/banks/[ticker]` (price chart + market cap, P/B, P/E, dividend yield).
  Valuation combines Yahoo close × shares with the *audited* book equity (label-
  matched, so participation banks at roman XIV. resolve) and TTM net income
  (de-cumulated, telescoping — same methodology as `/cross-bank` ROE; see
  `web/app/lib/bank-fundamentals.ts`). Caveats: QNBFB has ~0.12% float and is
  delisted on Yahoo → no price/valuation (omitted from `bist_shares.json`);
  `bist_shares` is best-effort refreshed from Yahoo `quoteSummary` each run with
  the committed JSON as fallback — refresh the seed on capital actions.
  `/cross-bank` now also carries **P/B and P/E columns** (neutral coloring;
  snapshot uses the quarter-end close, over-time uses current shares so deep
  history is approximate across capital actions) — `heatmapPanel` computes them
  from `bist_prices`/`bist_shares` + the shared `ttmNet` helper; listed banks
  only (others blank). The per-bank P/B/P/E reuse single-ticker helpers in
  `bank-fundamentals.ts` rather than refactoring `heatmapPanel`, kept identical
  to avoid regressing the shipped ROE.
  **Live overlay (2026-06-13):** all three surfaces overlay the latest (delayed
  ~15-min) Yahoo price at render time (`web/app/lib/bist-live.ts`) — per-bank
  price/market-cap/P/B/P/E/yield with an "as of HH:MM" label, cross-bank snapshot
  P/B/P/E, and a live final point on the `/economy` index chart. Price-linear
  rescale (`applyLivePrice`); graceful fallback to the stored close. Cached on
  Cloudflare's **edge cache + per-isolate memory, never KV** (the 12h KV window
  guards the write cap), 2.5 s timeout, kill switch `BIST_LIVE_DISABLED=1`.
  Not real-time (paid feed); this is a request-time read overlay — no D1 writes.
  **Market ticker (2026-06-13):** a scrolling live strip on `/economy` + `/news`
  (`MarketTicker.tsx`) — BIST indices, USD/TRY, EUR/TRY, Brent, gold $/oz +
  derived gram-gold ₺, each with day-change %. One batched Yahoo `spark` request
  (`getMarketTicker()` → `rawQuotes`); client polls `/api/market-ticker` every
  60 s; hidden on failure / kill switch.
- **Cash flow + equity-change extractors shipped; deep-fixed + fleet re-extracted (2026-06-13).**
  Two statement types: `bank_audit_cash_flow` (sort_order=38) and `bank_audit_equity_change`
  (sort_order=36). Root-cause fixes (commits b8b1c51, 8a91444): equity locator now uses the
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
    (no fast equity-only path; 8a91444's dash/clamp is currently only on DENIZ/EMLAK data).
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
