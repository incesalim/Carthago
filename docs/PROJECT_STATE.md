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
> Last verified: 2026-07-30. Dated change history → [CHANGELOG.md](CHANGELOG.md).

---

## Data coverage in D1

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
| `bank_audit_prose` | BRSA PDFs, **all sections** | **backfilled LOCALLY 2026-08-04** — 1,060 partitions / 38 banks / 2022Q1→2026Q2, **369,007 rows, 165M chars**, in `data/bank_audit_prose.db` (gitignored, 298 MB). **NOT in D1** — the write freeze stands; merge + push recipe in OPERATIONS.md. 1,014/1,061 partitions pass `check_prose` (95.6%); the 47 failures are GARAN ×32 (§1 has no anchor of any kind), YKBNK ×8 and 7 singles, all the same family: a section resolves but yields no rows, so contiguity flags it | **the narrative** — every prose block in the filing as an item row: `section` (the printed Bölüm) + `section_role` (what it IS) + `heading`/`heading_path` + `item_order` + page span + `lang` + `text`. The first lane whose rows are sentences, not figures. Deterministic, fitz-only, **no model** (`src/audit_reports/prose.py`). Tables are excluded *geometrically* — a table row's tokens share x-positions with the rows above and below, a sentence quoting a figure does not — and running headers by line-frequency. §6/§7 **swap** between annual and interim filings and the section count is 6/7/8 depending on the bank, so `section_role` (read off each filing's own declared title) is what queries must join on, never the number. Local corpus 162 filings: median 368 rows / 157k chars per filing. Validator `check_prose` checks the **sectioning** (count, contiguity, order, the four required roles, and that the filing ends on the auditor's/activity section) — transcription itself has no arithmetic identity |
| `bank_audit_capital` | BRSA PDFs, §4.1 capital adequacy | same — **fully backfilled 2026-06-10** (31/31 banks, ~1.7k rows) | CET1/Tier1/Tier2/Total/RWA + CET1/Tier1/CAR ratios, per period_type |
| `bank_audit_liquidity` | BRSA PDFs, §4.6/4.7 | same — **fully backfilled 2026-06-10** (31/31 banks, ~1.8k rows) | LCR (total/FC), NSFR, leverage ratio, per period_type |
| `bank_audit_fx_position` | BRSA PDFs, §4 currency-risk footnote | same — **backfilled 2026-06-29 (7,143 rows / 31 banks → 2026Q1)** | FX net open position per currency (EUR/USD/OTHER/TOTAL) × period_type; net_position = net_on + net_off (~99% coverage). Powers `/market-risk`. D1 reconciled 2026-07-24 (8,208 rows / 590 partitions) — see the note below |
| `bank_audit_repricing` | BRSA PDFs, §4 interest-rate-risk footnote | same — **backfilled 2026-06-29 (10,364 rows / 24 banks → 2026Q1)** | Repricing gap per bucket (lt_1m…gt_5y/non_sensitive/total) × period_type (~81% coverage; participation banks omit → validated N/A). D1 reconciled 2026-07-24 (12,064 rows / 455 partitions) |
| `bank_audit_oci`, `_cash_flow`, `_equity_change`, `_npl_movement`, `_stages`, `_loans_by_sector` | BRSA PDFs (statement pages + IFRS-9/credit footnotes) | 2022-Q1 → 2026-Q1 | per-bank; per-lane pass rates in the validation-status table below |
| `bank_audit_source_lines` | BRSA PDFs, bounded disclosure pages for 8 completeness-targeted lanes | **schema + automatic capture complete 2026-08-07; historical population pending the manual backfill** | Local/R2 snapshot only, never D1: every PyMuPDF-reconstructed physical line + printed numeric tokens + `mapped_key`. Near-full lanes (`equity_change`, `loans_by_sector`, `npl_movement`) treat an unmapped numeric data row as validation failure; selected-summary lanes retain the deliberately omitted detail for inspection without redefining their analytical schemas. |
| `bank_audit_capture_manifest` | Derived from `bank_audit_source_lines` + normalized row counts | **migration `0042`; new extracts populate automatically; historical backfill not yet dispatched** | One compact D1 row per filing/lane: pages, line/data/mapped/unmapped counts, normalized row count, capture status and content/shape/mapping hashes. Source checks merge into the lane's existing validator once its manifest exists. Alert-ready; no shape-drift alert has been activated yet. |
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

**The 2026Q2 season opened 2026-07-24** — KLNMA filed first, on KAP. TEB was the
first PDF we *held* (`acquire-audit.yml`, 2026-07-26), which is a different fact:
acquisition reads IR pages, and a bank files on KAP days before its own site
catches up. As of **2026-08-01** seven banks have released 2026Q2 reports —
KLNMA (07-24), TEB (07-26), AKBNK (07-28), TSKB (07-29), GARAN (07-30),
YKBNK (07-31) and ENPARA. The other 30 are still at 2026Q1.

**KAP is the earliest signal, and it is already wired up.** `src/news/sources/kap.py`
returns `disclosureClass: "FR"` rows carrying `year` / `ruleType` / `period`
(2026 · "6 Aylık" · 2 for this quarter), two per bank — unconsolidated and
consolidated. It covers BIST-listed banks only, so unlisted filers (TEB, ENPARA)
still surface only from their IR pages. Note the attachment endpoint
`/tr/api/file/download/<objId>` serves the PDF wrapped in a **Java-serialised byte
array** (`AC ED 00 05` magic) under an `application/pdf` header — the raw response
is not a usable PDF, so the KAP lane is a discovery signal, not a download path.

**⚠️ TSKB 2026Q2 is a KAP cover sheet, not the report (2026-08-01).** The URLs its
IR page serves for the quarter (`tskb-consolidated-30062026.pdf`,
`tskb-bank-only-30062026.pdf`) are **14 pages / 165 KB** against 2026Q1's
**107 pages / 2.0 MB**, and page 1 reads *"Bank Financial Report … KAMUYU
AYDINLATMA PLATFORMU"*. TSKB is in `DISCOVERY_BANKS`, so an unscoped acquire run
**will** store the stub. It was deliberately excluded from the 2026-08-01
acquisition; re-acquire once the bank posts the full document.

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

**`bank_audit_coverage` per-partition push: BUILT AND TESTED, NOT ACTIVE
(2026-08-05/06).** State, precisely, because an earlier version of this entry
said both that the table had left `_FULL_REBUILD` and that it was still in it:

| | |
|---|---|
| Migration `0040_coverage_derived_at.sql` | **APPLIED in live D1** — deploy [31045271052](https://github.com/incesalim/Carthago/actions/runs/31045271052), verified: `derived_at TIMESTAMP` present, nullable, `rows_written: 0` |
| `_COVERAGE_INCREMENTAL` | **False** — a test pins it off |
| `bank_audit_coverage` in `_FULL_REBUILD` | **Yes, still.** Push behaviour is byte-for-byte what shipped before |
| Activation | flip the flag + a supervised run. Not done |

As a full-rebuild rollup its content hash makes a no-op run free, but *any*
change re-ships all ~20,000 rows: 161,272 estimated billed for eleven changed
partitions. `sync_audit_expected.write_coverage()` now writes only rows whose
values moved. A NULL stamp is out of window on purpose — rows written before
0040 are already in D1, and re-shipping them once would cost exactly what this
removes.

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

**The 250,000 cap now bounds the RUN, not each push.** It was applied per
invocation, so 203,799 then 226,069 each "passed" while the run spent 429,868.
A `D1_RUN_LEDGER` file, shared by every push in a job, is debited *before* each
write (a failed import still bills) and subtracted from the *result* of the
cycle guard — subtracting it from the input let the guard's own floor swallow
it, which would have disabled the ledger in exactly the exhausted-allowance
state where it matters most.

**⚠️ The ledger and the automatic retry contradicted each other — resolved
2026-08-05.** Booking before the write and retrying `EXIT_PUSH_FAILED` cannot
both be right:

```
attempt 1  books 203,799  ->  wrangler blips  ->  exit 4 (retryable)
attempt 2  cap is now 250,000 - 203,799 = 46,201
           estimate 203,799 > 46,201        ->  exit 3 (TERMINAL)
```

A service-side blip became a permanent budget refusal, and the operator read
*"a validation or budget refusal is deterministic … Nothing was written"* —
neither half true. Whether a half-finished import bills is not observable from
here: if it did, retrying spends twice; if it did not, the ledger has
over-booked and the retry is refused for nothing. So `audit_d1.terminal_exits()`
adds `EXIT_PUSH_FAILED` to the terminal set **while a ledger is active** — one
attempt, then a human. Without a ledger it stays retryable, which is what the
non-audit callers rely on. Reproduced end-to-end before fixing.

⚠️ **The first version of that fix reached only one of the two retry loops.**
`audit_d1` has two — `replace_partitions()` and `push_to_d1()` — as separate
copies of the same seven lines, and the ledger rule landed in the first while
the second went on retrying exit 4 into a guaranteed budget refusal. Both now go
through a single `stop_if_terminal()`, and a test asserts there is exactly one
definition and two call sites, because the duplication *was* the bug. Each loop
is tested both ways: one attempt under a ledger, the full three without.

**The ledger's wiring is now gated** (`tests/test_workflow_ledger_wiring.py`):
every workflow that pushes to D1 more than once must give each pushing step the
same run-scoped path. `check_docs_sync.py` covers workflows, `secrets.*` and
Worker bindings, not this — the gap was the reason to add a test, not to skip
one. Writing it found the **same defect in two more lanes**:
`refresh-bddk-bulletins.yml` and `refresh-data.yml` each push twice
(rows, then the `api_series` full rebuild) and had no shared ledger. Both fixed.

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
- `.github/workflows/refresh-transcripts-weekly.yml` — **manual dispatch only, no `schedule:` yet.** `scripts/update_transcripts.py` → `bank_call_transcripts` (earnings-call transcripts for the 8 listed banks that hold an English call) → optionally D1 (`--only-tables=bank_call_transcripts`). Bulletin lane (`bddk-pipeline` group), rides the shared snapshot. The missing cron is deliberate: the 2026-08-01 freeze is enforced with `gh workflow disable`, which leaves no trace in git, so a new workflow shipped with a schedule would be born **enabled** and become the only lane writing to D1 during the freeze. Its `push` input defaults to `false` for the same reason — a run ingests and re-uploads the snapshot without touching D1. Add `schedule: "0 7 * * 6"` and flip `push` when the freeze lifts. Inputs use an explicit `ALL`/`NONE` bank sentinel (a blank dispatch input arrives as the default, not empty). Apply migration 0036 (via a `web/**` deploy) before the first push.
- `.github/workflows/refresh-advertised-rates.yml` — Mon 06:00 UTC. `python -m src.rates.scraper` → `bank_advertised_rates` → D1 (`--only-tables=bank_advertised_rates`). Bulletin lane (`bddk-pipeline` group), rides the shared snapshot (re-gzips it explicitly — this lane doesn't run `refresh.py`, which is what VACUUMs+gzips for the other refresh workflows). Migration 0023 applies via the `web/**` deploy that ships it.
- `.github/workflows/refresh-calendar.yml` — 1st of month 06:00 UTC. `python -m src.release_calendar.scraper` → `release_calendar` → D1 (`--only-tables=release_calendar`). Scrapes TCMB's published "MPC Meeting and Reports Calendar" (rate decisions + minutes + Inflation Report + Financial Stability Report) so the **Ahead** strips fill themselves; retires the hand-typed `MPC_DATES` (now a render-time fallback, still guarded by `check_calendar_fresh.py`). `requests`+`lxml`, no browser — same `www.tcmb.gov.tr` host the news lane scrapes. Bulletin lane (`bddk-pipeline` group), re-gzips the snapshot explicitly. Migration 0025 applies via the `web/**` deploy that ships it.
- `.github/workflows/refresh-audit.yml` — daily during earnings windows (Jan 20–all February, Mar 1–15, Apr/Jul/Oct 20 through May/Aug/Nov 20) plus manual dispatch. It discovers and validates new PDFs, extracts pending partitions immediately, rebuilds stages/validation/coverage locally, sends one registry-derived audit batch to D1, then uploads the snapshot. A no-change run stops before all writes. Own DB/snapshot/group remain `data/bank_audit.db`, `state/bank_audit.db.gz`, `bddk-audit`; targeted `/admin` re-extraction is unchanged.
- `.github/workflows/reextract-statement.yml` — manual dispatch. Targeted single-statement re-extract via `scripts/reextract_statement.py`: pull snapshot → resolve the registry lane → re-extract its source disclosure → rebuild any dependent derived rows → inline-validate the complete relationship gate → push only factually changed tables to D1 → snapshot → refresh coverage. Shares the `bddk-audit` group. Inputs: `statement`, `banks`, `periods` (blank=all), `only_failing` (default true — selects a partition when any required non-conditional gate is not a proven pass), `require_passing` (default true — rolls source + derived + validation back together unless the whole gate passes), and `dry_run` (pulls the authoritative snapshot, then performs no D1/R2 writes). No-op tables retain their timestamps and are not pushed. This is the lane used to fix OCI/CF/NPL fleet-wide.
- `.github/workflows/audit-triage.yml` — manual dispatch, **read-only**. Diagnoses the failing partitions rather than re-extracting them: `scripts/triage_partitions.py` assigns each a deterministic CAUSE from the PDF (`dropped_cell` / `missing_row` / `column_slip` / `wrapped_cell` / `anchor_miss` / `drawn_page` / `rotated_page` / `wrong_pdf` / `unit_switch` / `source_defect` / `unclassified`), with the page and the printed token behind it; `scripts/watch_cross_period.py` compares each partition to the same bank a quarter earlier. No model is called, no figure is produced, and nothing is written anywhere — no D1, no row update, no snapshot re-upload — so it is unaffected by the write freeze. Reports come back as a build artifact. Engine + taxonomy in `src/audit_reports/triage.py`, pinned by `tests/test_triage.py`; findings in [knowledge/2026-08-02-audit-triage-engine.md](knowledge/2026-08-02-audit-triage-engine.md). First full run over all 212: `column_slip` 61, `dropped_cell` 46, `anchor_miss` 45, `unclassified` 26, `missing_row` 26, `rotated_page` 7, `drawn_page` 1 — and `source_defect` **zero**, so nothing in the corpus currently qualifies as "the filing itself doesn't foot". **Two extractor fixes recorded, neither applied** (they change the extractor, and re-extraction writes rows): `audit_opinion.extract_opinion_from_pdf`'s `max_pages=6` misses the signature on pp7–9 for **43** partitions (6→10 clears all of them), and §4 capital never reads the prior `additional_tier1_capital` column for **9** (EMLAK + QNBFB). The ~114 equity_change failures are grouped but **not** diagnosed — the obvious "missing closing row" theory is refuted at corpus scale (absent from 37% of failing and 36% of passing partitions).
- `.github/workflows/analyst-daily.yml` — **manual dispatch only, no `schedule:` yet, artifacts-only** (same freeze posture as `refresh-transcripts-weekly.yml`; contains NO D1 push step at all). The analyst layer over the audit snapshot: `scripts/analyst/detect.py` runs the deterministic detectors (reporting-unit switch, cross-period restatements — the ones the validators deliberately skip-list get *reported* here with `documented: true` — opinion type/category changes via the bilingual basis-text classifier at 95% non-other coverage, `disc_net`/cons-gap perimeter changes, and the two feasibility-verdict divergences CAR−CET1 and NPL-vs-coverage), stages signals + basis metadata into `data/analyst.db`, then `web/scripts/analyst-run.ts --memo` assembles the 11-section deterministic view (`web/app/lib/analyst/` — coverage mix-vs-erosion decomposition precomputed), writes memos with the free-model chain and drops any paragraph whose figures aren't in the data block it was shown (`unsupportedFigures`). `banks=CALIBRATE` = the ALBRK+SKBNK feasibility pair. Corpus run 2026-08-04: 455 signals in 0.2s — unit-change silent fleet-wide, cross-period 69 (fx anchor reproduces the validator skip-list 7/7 comparable), divergence 287, opinion 67, perimeter 32. Migration `0037_analyst_signals.sql` authored, **unapplied**; cron + push steps go in at freeze-lift. Build plan + as-built corrections: [knowledge/2026-08-04-analyst-build-plan.md](knowledge/2026-08-04-analyst-build-plan.md). Same-day evolution into a **full 13-section research report** (~2,400 words, tables; benchmarked figure-for-figure against an external GARAN deep-research doc): ranked STORY GATES (a deterministic editorial layer — six stories ruled LIVE/DEAD with numeric reasons; the LEAD must headline), precomputed comparisons/growth-%/totals (every hand-derivation the model attempted became a supplied figure), a relation verifier (drops a wrong direction word between two right numbers), named peer table + BDDK sector aggregates, per-stage GROSS ECL expense (sums reproduce disclosed figures), verbatim management commentary from `bank_call_transcripts` (executive turns only, claims-not-data framing), **per-bank stage definitions extracted from the prose corpus** (24/38 banks' own disclosed thresholds, generated module `web/app/lib/analyst/stage-definitions.ts` — the feasibility test's #1 missing dataset), hash-gated regeneration (`data_hash` per note; staging `data/analyst.db` persists via R2 `state/analyst.db.gz`), and `scripts/analyst/score_reports.py` (structure/lead/coverage scoring over run artifacts). Memo lane LLM: PAID `deepseek/deepseek-v4-flash` (user-authorized, Baidu-pinned, seeded) → free OSS fallbacks; nemotron excluded (reasoning-leak).
- `.github/workflows/analyst-research.yml` — **manual dispatch only, ARTIFACT-ONLY, evaluation phase** (Analyst V2, [ANALYST_V2.md](ANALYST_V2.md)). Scout → typed-tool research loop → deterministic verifier; structured findings with stable evidence ids; abstention first-class; no D1 writes, no schedule, no automatic publishing; V1 (`analyst-daily.yml`) remains the regression baseline. First cold scout run on ALBRK 2025Q1 surfaced the free-provision fingerprint (Other Provisions −6.7bn, Other Operating Income +6.1bn, the −7.7bn equity movement) with zero bank-specific logic.
- `.github/workflows/backfill-audit.yml` — manual dispatch. Full re-extract (all statements) of named banks via `backfill_extraction.py` (`ALL` exceeds the timeout → 5-bank chunks).
- `.github/workflows/purge-partition.yml` — manual dispatch. Removes one `(bank, period[, kind])` from the lane via `scripts/purge_partition.py`: pull snapshot → delete locally → delete in D1 → **re-upload the snapshot** → coverage re-sync. Clearing D1 alone does not stick (the snapshot restores the rows on the next push). Leaves the R2 PDF, so the cell returns to `missing` + `pdf_present`. For extractions that pass validation but are known wrong — built for the TEB 2026Q2 unit switch. `dry_run` defaults **true** and is genuinely read-only.
- `.github/workflows/backfill-faaliyet.yml` — manual dispatch. Fleet backfill of the Faaliyet-raporu franchise lane → `faaliyet_franchise` + `faaliyet_extractions`. The incremental refresh rides `refresh.py` (step 9, non-critical).
- `.github/workflows/summarize-regulations.yml` — Sun 06:00 UTC. Weekly regulation briefing via Kimi → `regulation_briefings` → D1. Needs the `KIMI_API_TOKEN` repo secret, which the workflow maps to env `KIMI_API_KEY` (the name `src/news/kimi.py` reads) — see [OPERATIONS.md](OPERATIONS.md) §Secrets. Grounded on the TCMB annual policy baseline, pinned once a year by dispatching this workflow with `baseline_url`/`baseline_year` (the ingest must run in CI, between the snapshot pull and upload — a local run writes a DB production never reads). Runs `--require-baseline`, so an ungrounded briefing fails instead of shipping. Posts the generated briefing to Telegram (`notify_briefing()`, split across messages under Telegram's 4k cap) whenever the LLM actually runs — silent on unchanged-input weeks; `force=true` regenerates on demand. Follow-ups in [regulation_followups.md](regulation_followups.md).
- `.github/workflows/deploy-cloudflare.yml` — **after CI goes green on `master`** (`workflow_run`, not `push` — it used to race CI). Apply D1 migrations + build + deploy dashboard.
- **Public-API catalog** — not its own workflow: `refresh-data.yml` runs `scripts/build_api_catalog.py` + `push_to_d1.py --only-tables api_series` after every BDDK refresh, so `/api/v1` sees each new period. `api_series` is full-rebuild (no per-row timestamp), so a windowed push skips it — it must be named explicitly. See [API.md](API.md).
- `.github/workflows/healthcheck.yml` — daily 06:00 UTC. D1 freshness check → Telegram/Discord alert if stale. Also runs `scripts/verify_chart_spec.py --alert`: re-resolves every reproduced chart in `web/app/lib/chart-specs.catalog.json` against D1 and alerts if a series goes blank (0 rows) or drifts past its `verify[]` anchor. See [REPRODUCING_CHARTS.md](REPRODUCING_CHARTS.md). Third check: `setup_telegram_webhook.py check --alert` asserts the bot webhook still targets the live origin.
- `.github/workflows/telegram-webhook.yml` — manual only. `set` / `info` / `check` the Q&A bot webhook; lives in CI because the bot token + webhook secret aren't available locally. Run `set` after anything that moves the site origin (e.g. the 2026-07-19 Worker rename to `carthago`, which orphaned the webhook on the dead `workers.dev` host).
- `.github/workflows/test-openrouter.yml` — manual only, **scratch**. Probes the `OPEN_ROUTER_API` secret (auth → credit budget → DeepSeek model/price list → one number-validated completion) via `scripts/scratch_test_openrouter.py`. The key was added 2026-07-05 and no lane reads it; this only answers "does it work, and what does DeepSeek cost". Delete both files once the finding lands in `docs/knowledge/` — and with them the `SCRATCH_WORKFLOWS` entry in `scripts/check_pipeline_graph_sync.py` that exempts this lane from the `/pipeline` graph gate (it moves no production data, so it draws no lineage node; a stale exemption fails CI by design).
- `.github/workflows/ci.yml` — on PRs. ruff + pytest + eslint + tsc + vitest. (Dependency bumps via `dependabot.yml`.)

Schema source of truth: hand-authored migrations in `web/migrations/`, applied
by the deploy workflow (`wrangler d1 migrations apply`); `d1_migrations` tracks
what's applied.

## Dashboard

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
  run cap in the first place.

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
