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
> Last verified: 2026-06-27. Dated change history → [CHANGELOG.md](CHANGELOG.md).

---

## Data coverage in D1

| Table | Source | Range | Latest |
|---|---|---|---|
| `balance_sheet`, `income_statement`, `loans`, `deposits`, `financial_ratios`, `other_data` | BDDK monthly bulletin | 2020-01 → present | 2026-05 |
| `weekly_series` | BDDK weekly bulletin | 2019-11 → present | rolling 2-week lag |
| `nonbank_balance_sheet` | BDDK non-bank monthly bulletin (BultenAylikBdmk) | 2008-01 → present | leasing / factoring / financing, monthly, balance sheet (Million TL); reconciles to FKB sector totals. VYŞ (sparse/variant feed) + savings-finance (not in this bulletin) deferred |
| `evds_series` | TCMB EVDS | 2018-01 → present | daily / weekly / monthly per series |
| `tbb_digital_stats` | TBB quarterly digital-banking report | 2019-Q1 → present | quarterly (Mar/Jun/Sep/Dec) |
| `tkbb_digital_stats` | TKBB Veri Peteği (Turboard JSON API) — participation-bank digital stats | 2020-Q1 → present | quarterly; active customers (total/channel-mix/province) + txn volume & count (channel/segment/category), RAW units |
| `tkbb_acquisition_stats` | TKBB Veri Peteği — remote-vs-branch acquisition | 2025-07 → present (accumulating) | monthly; source exposes only a rolling 12-month window — history builds forward, rows never deleted |
| `kap_ownership` | KAP Genel Bilgi Formu §5 + §7 subsidiaries (kap.org.tr) | current state per bank (`as_of` = filing date) | weekly full replace; 30/31 banks (ATBANK files no form); subsidiaries grid only on the full form (~15 banks) |
| `tefas_manager_daily`, `tefas_category_daily`, `tefas_allocation_daily`, `tefas_top_funds` | TEFAS fund-market JSON API (tefas.gov.tr) | rolling ~5 years (API rejects older start dates) → present | daily T+1, trading days; aggregated at ingest (no per-fund rows) |
| `bist_prices`, `bist_dividends`, `bist_shares` | Borsa İstanbul via Yahoo Finance chart API | 2014-06 → present | daily EOD (~1-day lag); 11 listed banks + XU100/XBANK indices (QNBFB delisted on Yahoo — no data) |
| `faaliyet_franchise` | Bank annual reports (Faaliyet Raporu PDFs) | annual (FY ending 31 Dec) | ATM / POS / merchant / customer / card counts (the stats audit reports don't carry; branches & employees stay in `bank_audit_profile`); deterministic regex+coordinate extraction with confidence flags. **Lane shipped; coverage pending per-bank URL curation in `data/banks/faaliyet_report_urls.json` + the `backfill-faaliyet` run** |
| `bank_audit_balance_sheet` (assets / liabilities / off-balance) | BRSA quarterly PDFs | 2022-Q1 → 2026-Q1 | per-bank |
| `bank_audit_profit_loss` | BRSA quarterly PDFs | same | per-bank |
| `bank_audit_credit_quality` | BRSA PDFs, IFRS 9 footnotes | same | per-bank, per-section |
| `bank_audit_profile` | BRSA PDFs, qualitative section | same | branches + personnel where disclosed |
| `bank_audit_capital` | BRSA PDFs, §4.1 capital adequacy | same — **fully backfilled 2026-06-10** (31/31 banks, ~1.7k rows) | CET1/Tier1/Tier2/Total/RWA + CET1/Tier1/CAR ratios, per period_type |
| `bank_audit_liquidity` | BRSA PDFs, §4.6/4.7 | same — **fully backfilled 2026-06-10** (31/31 banks, ~1.8k rows) | LCR (total/FC), NSFR, leverage ratio, per period_type |
| `bank_audit_fx_position` | BRSA PDFs, §4 currency-risk footnote | same — **backfilled 2026-06-29 (7,143 rows / 31 banks → 2026Q1)** | FX net open position per currency (EUR/USD/OTHER/TOTAL) × period_type; net_position = net_on + net_off (~99% coverage). Powers `/market-risk` |
| `bank_audit_repricing` | BRSA PDFs, §4 interest-rate-risk footnote | same — **backfilled 2026-06-29 (10,364 rows / 24 banks → 2026Q1)** | Repricing gap per bucket (lt_1m…gt_5y/non_sensitive/total) × period_type (~81% coverage; participation banks omit → validated N/A) |
| `bank_audit_oci`, `_cash_flow`, `_equity_change`, `_npl_movement`, `_stages`, `_loans_by_sector` | BRSA PDFs (statement pages + IFRS-9/credit footnotes) | 2022-Q1 → 2026-Q1 | per-bank; per-lane pass rates in the validation-status table below |
| `bank_audit_extractions` | extraction log | one row per PDF | 974 rows (954 ok / 20 partial) |
| `bank_types`, `table_definitions`, `download_log` | metadata | — | — |
| `banks` (+ alias views `v_bist_prices` / `v_news_items` / `v_bank_earnings`) | dimension (migration 0021), seeded from `bddk_bank_list.json` + `bank_names.ts` | 31-bank audited universe | canonical per-bank identity + single join key across lanes (`ticker` == `bank_ticker` == `symbol`); the views alias each lane's id column to `bank_ticker`. Powers cross-lane joins + the text-to-SQL bot |

**Quarterly audit reports**: 32 banks in URL config, ~974 PDFs extracted into
D1 (~159k balance-sheet rows + ~59k P&L rows + ~7.4k IFRS 9 credit-quality
rows + ~460 bank-profile rows). PDFs themselves live in R2 at
`bddk-audit-reports/<ticker>/<TICKER>_<period>_<kind>.pdf`. Bank profile
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

**§4 capital/liquidity (2026-06-10)**: full-fleet history backfilled via
`backfill-audit.yml` in 5-bank chunks (`ALL` exceeds the 180-min job timeout).
Per-bank §4 filing quirks and their fixes are catalogued in
[AUDIT_BANK_CATALOG.md](AUDIT_BANK_CATALOG.md); the only standing
capital-quality flags are bank-reported BRSA temporary-measure CARs
(ATBANK 2024, TEB consolidated 2022) — false positives, not parse errors.
Dashboard surfacing (e.g. cross-bank CAR/LCR view) is an open follow-up.

**Audit-lane validation status** (D1, 2026-06-14; /~975 partitions). Every extracted
statement is self-validated (internal-sum / roll-forward / cross identities); the
`/admin` coverage matrix and the non-destructive re-extract guard both key off this.

| Lane | pass | fail | skip | notes |
|---|---|---|---|---|
| `assets` / `liabilities` / `cross` | 970–974 | ≤4 | 1 | **BS frozen** (correct — don't re-extract) |
| `off_balance` | 966 | **0** | 9 | per-partition validator is **horizontal-only** (TL+FC=Total; parent=Σchildren / TOTAL=Σromans skipped because off-balance skips hierarchy levels → would false-fail). Vertical structure validated **alert-only** via `check_audit_quality._off_balance_consistency`. **2026-06-21: 17→0** via curated `audit_overrides.json` cells (no re-extraction): TEB `(III-2)` cross-ref garble ×8 (restored from 3.1+3.2 children), BURGAN/EMLAK/ISCTR single cells, and ALNTF cross-ref-annotated rows (`III-a-3,i`) fitz-read off the off_balance page (89 rows ×6 partitions, Total-cross-checked). **2026-06-27: 3 more cleared** — ATBANK 2025Q4 dropped roman section I (GARANTİ VE KEFALETLER) re-inserted (Σromans→total), EMLAK 2022Q4 mis-captured grand total corrected to 387,710,554, and the `_off_balance_consistency` Σromans helper now keeps the larger-magnitude row per roman ordinal so a stray bank-name header captured as hierarchy `5` can't hide section V (ISCTR 2025Q4) |
| `profit_loss` | 974 | **0** | 1 | **frozen** (correct). **2026-07-02 validator audit:** the net=equity cross-check (`pl_bottomline`) had silently skipped **209/975 partitions** — its label regex missed the English template ("NET PROFIT/LOSS"), the participation word-order ("NET DÖNEM KARI/ZARARI") and empty-label rows (AKBNK 2026Q1) → now falls back to hierarchy (spine roman XXV + row 25.1), coverage 209→0 skips and ~230 newly-run checks pass. `_pl_spine` switched from longest contiguous run to longest increasing **subsequence**, so one misparsed roman (HSBC "XIV."→"X", 28 partitions) no longer hides the XV–XXV tail from the chain (≤4-identity partitions 35→8). The widened checks surfaced 2 real cases: AKBNK 2022Q1–Q3 uncon tail romans shifted one ordinal (net income on XXIV., no XXV.) → fixed via new `pl_rehier` override type (renames only; amounts tie BS 16.6.2 exactly); TSKB 2022Q1 uncon printed P&L net 605,861 ≠ printed BS 16.6.2 605,673 (both faithful, source self-inconsistent) → `_PL_BOTTOMLINE_SKIP` (chain stays guarded). Skip=1 is ICBCT 2023Q2 cons `_PL_SKIP` (source rounding) |
| `oci` | 959 | **0** | 16 | **2026-06-21: 19→0.** `check_oci` drops the noisy deep `2.1.x/2.2.x` sum (net-of-tax rounding + omitted immaterial lines — cash_flow lesson), keeps roman chain III=I+II + section sums (I=Σ1.x, II=Σ2.x) + OCI.I==P&L-net cross. `apply_overrides` gained `oci`/`oci_replace`; EXIM/FIBA/QNBFB had the WRONG statement captured (equity+BS) → full fitz re-read; KLNMA prior-column mis-read fixed; ISCTR 2025Q2 wrong-table + PDF-404 → removed; ATBANK 2023Q4 `_OCI_SKIP` (source sign typo) |
| `cash_flow` | 947 | **0** | 28 | fitz-only; roman-chain-only validator (135→0 on 2026-06-21). Last 1 cleared 2026-06-21: TSKB 2022Q1 cons `_CF_SKIP` — PDF-confirmed source typo (printed V 5,027,208 ≠ I+II+III+IV 5,011,183; VII foots with the derived V) |
| `equity_change` | ~794 | ~168 | 10 | hardened. **2026-06-27: 343→~168.** Root cause for ~52% of the tail was a current/prior **period swap**: `_PRIOR_RX` matched "Önce/Öncesi Dönem" but not "Önceki Dönem" (the standard term), so a bank printing its prior-period matrix FIRST (HSBC) had that page default to `current` → enforce-distinct fallback swapped the periods positionally → stored "current" = prior-year matrix (closing ≠ BS equity, OCI row ≠ OCI statement). One-line regex fix → **HSBC 34/34, +184 of 352 cleared fleet-wide, 0 regressions**. **2026-06-27 (round 2): ~168→~98.** Two more period-assignment bugs: (a) the current page's header says "Cari Dönem" but its OPENING row reads "Önceki Dönem Sonu Bakiyesi", so the PRIOR-first marker test mislabeled the current page as prior (TSKB) → now check CURRENT first; (b) marker-LESS pages (ALNTF prints bare date-keyed rows, no Cari/Önceki word) + prior-first order → positional default swapped → now a year-based tiebreaker (the current table closes on the later period-end date = larger max-year). → **ALNTF 32→0, TSKB 33→15, ICBCT 17→6** (verified prod 168→107). **2026-06-27 (round 3): 107→~91.** (a) `_split_periods` order signal made value-based — in prior-then-current order block1 (prior) CLOSES where block2 (current) OPENS (the totals chain), fixing ANADOLU's mid-page-split swap that the year-text heuristic missed (its year is header-only); (b) `_try_fit` extended to n_cols-2: ANADOLU's consolidated row IV ("Toplam Kapsamlı Gelir") drops two fully-blank component columns → 14 tokens in a 16-col table → was dropped → its total left out of Σromans; two-zero insertion gated by Σcomponents==total AND total+minority==grand. Shipped via `--only-failing`. **2026-06-27 (round 4): equity is now FITZ-ONLY (pdfplumber removed) → 91→85.** GARAN/AKBNK "needed pdfplumber" only because their statement is on a **`/Rotate 90` page** — `fitz.get_text("words")` returns un-rotated bboxes so y-bucketing scrambled the table; fix = `page.rotation_matrix` in `_fitz_page_text` (identity for upright pages). Removed the pdfplumber reconstruction/marker/n_cols reads + the `pdf` param. A full `--force` re-extract converged real failures **91→85** but also over-extracted ISCTR's letter-spacing-corrupted image-only quarters into partial-failing rows (transient 118); a **<14-row guard** (complete statements carry ≥22 rows, broken parses ≤9 — clean gap) drops those incomplete parses so they stay empty/skip → **85** (ISCTR/sparse → 0), verified live. Remaining **85** = genuine per-bank column misalignment / sub-1% chain near-misses (TSKB) / image-only quarters. (OCI still has the same pdfplumber GARAN/AKBNK rotation fallback — open follow-up.) |
| `credit_quality` | 939 | 5 | 31 | **good** — real reconciliation (section total=S1+S2+S3 + cross-section loans≈S12+NPL); skips gross−prov=net (BRSA collective-reserve noise). 5 fails genuine (DENIZ, TFKB) |
| `stages` | 967 | **0** | 8 | NPL=100% **fixed end-to-end 2026-06-15**; residual 15 cleared 2026-06-21 (credit_quality fitz migration + per-bank `loans_by_stage` cluster fixes). (1) Validator: the NPL=100% fingerprint required stage1/stage2 non-null but the broken shape has them NULL → it skipped all 45, which showed green; now NULL counts as 0 → 45 surfaced. (2) Extractor (`credit_quality.loans_by_stage`): captured the §7.2 Stage-1/2 table on 3 column-split variants (İşbank EN/no-space coord fallback; ANADOLU wrapped header → Stage-2-only anchor; TSKB label/number y-offset → 5.5px cluster). Re-extracted 6 banks → rebuilt derived stages → **43 of 45 repaired** (npl100 45→2). Remaining 2 = FIBA + TFKB image-only quarters |
| `capital` | 842 | **0** | 133 | validator **hardened 2026-06-15** (composition Tier1=CET1+AT1, Total=Tier1+Tier2 + sub-ratios CET1/Tier1/CAR=component÷RWA). **2026-06-21: 26→0** via `audit_overrides.json` (apply_overrides now patches `bank_audit_capital`): the failures were real §4 mis-extractions recovered from the identities (passing ratios confirm the kept components) + PDF-confirmed — AT1 dropped→Tier1−CET1 (ICBCT/QNBFB/TSKB), Tier2 dropped/slipped→Total−Tier1 (QNBFB/ISCTR/SKBNK), AKTIF total misread→Tier1+Tier2, ISCTR 2025Q1/Q2 RWA column-slip→real RWA + ratios. **2026-06-27: EMLAK 2022Q1 cons/uncon AT1 (Türkiye-Varlık-Fonu instrument) dropped → derived from Tier1−CET1; EMLAK 2025Q1 cons RWA read into total_capital → restored ÖZKAYNAK 28,781,229 + RWA 125,508,698 (22.93%=reported CAR). Also the alert-only `check_audit_quality` capital reconcile was made forbearance-aware: banks reporting a BDDK transitional-adjusted CAR (ATBANK, ICBCT, ANADOLU — printed capital/RWA ≠ reported ratio) no longer false-fail; it now reconciles the bank's OWN reported ratios to each other (8% band) instead of to printed RWA** |
| `liquidity` | 945 | 0 | 30 | §4 backfilled; per-partition validator is **band-only** (ratios only, nothing to reconcile). Validated instead by a **within-bank time-series outlier scan** (`check_audit_quality._liquidity_outliers`, ≥8× = order-of-magnitude slip; covers `lcr_fc`, which the band check never read). **Verdict 2026-06-15: leverage / LCR / NSFR clean fleet-wide; only error = FIBA `lcr_fc` 2024Q1 unco + 2024Q2 unco/cons (~1.1 vs the bank's ~430)**. **2026-06-27: FIXED** — root cause was `_parse_ratio` reading the TR-thousands `1.158,00` (=1158%) as `1.158` (it assumed EN format when both `,` and `.` were present); now the rightmost separator is the decimal. Re-extracted → lcr_fc 1158/1080/1096 |
| `npl_movement` | 641 | **0** | 334 | **2026-06-21: 126→0** (FX "Kur farkı" row + closing-vs-`npl_brsa_gross` cross-check skip-if-bottom-line-right + HALKB total-block extractor fix + PASHA outflow-magnitude `abs()`). **2026-06-27: a later `npl_movement_balance_missing` check surfaced 14 (BURGAN-cons, EXIM/ODEA/QNBFB-uncon) where the opening row was unmatched → block started on Additions → opening NULL → roll-forward couldn't tie. Fixed: opening-label variants ("Ending Balance of Prior Period", "Balance at the End of the Previous Period"), `_DATE_BALANCE_RX` relaxed for ODEA's space-glued "31 Aralık 2021Bakiyesi", and the wrapped-label merge extended to closing/provision/net rows + "Performing Loans" transfer-continuations (QNBFB) → 14→0** |
| `loans_by_sector` | 171 | **0** | 804 | **annual-only** disclosure (interim has no table). **2026-06-21: 36→0.** YKBNK (22) extracted the WRONG table (capital/equity rows) — locator missed "Information ACCORDING TO sectors and counterparties" + false-matched the risk-profile/investments tables (fixed + sector wordings). The rest were per-bank multi-column structures, fixed by rewriting the parse to **x-coordinate column alignment** (`_extract_section_xy`): align each row's numbers to the Stage 2/Stage 3 header columns by word x-position; recognise "(Second/Third Stage)" + Turkish İkinci/Üçüncü; `_pick_total` chooses the total that foots when a page has two tables (ICBCT); keep whichever parse (aligned vs text) FOOTS better → no regression. Also `\d{1,4}` leading group for a missing-comma typo "1466,551" (ICBCT 2025Q4) |

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
- `.github/workflows/refresh-bddk-bulletins.yml` — Sat 02:00 UTC. Monthly + weekly bulletins (no EVDS, no audit) → D1.
- `.github/workflows/refresh-data.yml` — Sat 03:00 UTC. Monthly + weekly + EVDS + TBB digital-banking (quarterly) + TKBB participation-bank digital + KAP ownership structure + TEFAS fund market → D1. *(Audit removed — now its own workflow.)* TBB, TKBB, KAP and TEFAS are non-critical steps in `refresh.py` (an outage won't abort the BDDK refresh); they ride the bulletin lane's snapshot, so no new lane. KAP details in [OPERATIONS.md](OPERATIONS.md) §KAP ownership; TEFAS in §TEFAS fund market; TKBB in §TKBB participation-bank digital statistics.
- `.github/workflows/backfill-tefas.yml` — manual dispatch only. Resumable ~5-year TEFAS history backfill (the API rejects start dates older than 5 years; 28-day windows, rate-limited ≈2–2.5 h; re-dispatch with the same `from` to resume — completed windows are skipped via `tefas_fetch_log`).
- `.github/workflows/backfill-nonbank.yml` — manual dispatch only. One-time historical backfill of the non-bank sector lane (leasing/factoring/financing) from `from_year` (default 2020 = banking-aggregate horizon) → now (~5–10 min). The incremental refresh rides `refresh-bddk-bulletins.yml` / `refresh-data.yml` (non-critical `update_nonbank.py` step in `refresh.py`); this workflow is only for the initial history load. Apply migration 0013 (via a `web/**` deploy) before dispatching.
- `.github/workflows/refresh-presentations-weekly.yml` — Sat 06:00 UTC. `scripts/update_presentations.py` → `bank_earnings` (IR presentation decks) → D1 (`--only-tables=bank_earnings`). Bulletin lane (`bddk-pipeline` group), rides the shared snapshot. Tier-1 results filings instead ride the daily `refresh-news-daily.yml` (classified in `sync_news.py`). Apply migration 0015 (via a `web/**` deploy) before the first push.
- `.github/workflows/refresh-audit.yml` — Sun 04:00 UTC. Audit-report sync + extract → `bank_audit_*` → D1. Own DB `data/bank_audit.db`, own snapshot `state/bank_audit.db.gz`, own group `bddk-audit`. Manual dispatch takes optional `bank` / `skip_scrape` inputs (the /admin per-bank trigger uses `bank` → `--only-bank … --latest-period`). After extraction it runs `scripts/check_audit_quality.py --alert` (alert-only): flags a quarter whose lines are identical to the prior one (period-shift), a balance sheet that doesn't balance, or missing rows → Telegram/Discord, never blocking the push.
- `.github/workflows/reextract-statement.yml` — manual dispatch. Targeted single-statement re-extract via `scripts/reextract_statement.py`: pull snapshot → re-extract ONE lane (`oci`/`cash_flow`/`equity_change`/`npl_movement`) for the selected partitions → inline-validate → push that table + `bank_audit_validation` to D1 → snapshot → refresh coverage matrix. Shares the `bddk-audit` group. Inputs: `statement`, `banks`, `periods` (blank=all), `only_failing` (default true — selects `checks_failed>0 OR checks_passed=0`, so it catches the stale empties and skips the proven-passing rest), `dry_run`. This is the lane used to fix OCI/CF/NPL fleet-wide.
- `.github/workflows/backfill-audit.yml` — manual dispatch. Full re-extract (all statements) of named banks via `backfill_extraction.py` (`ALL` exceeds the timeout → 5-bank chunks).
- `.github/workflows/deploy-cloudflare.yml` — on push to `web/**`. Apply D1 migrations + build + deploy dashboard.
- `.github/workflows/healthcheck.yml` — daily 06:00 UTC. D1 freshness check → Telegram/Discord alert if stale. Also runs `scripts/verify_chart_spec.py --alert`: re-resolves every reproduced chart in `web/app/lib/chart-specs.catalog.json` against D1 and alerts if a series goes blank (0 rows) or drifts past its `verify[]` anchor. See [REPRODUCING_CHARTS.md](REPRODUCING_CHARTS.md).
- `.github/workflows/ci.yml` — on PRs. ruff + pytest + eslint + tsc + vitest. (Dependency bumps via `dependabot.yml`.)

Schema source of truth: hand-authored migrations in `web/migrations/`, applied
by the deploy workflow (`wrangler d1 migrations apply`); `d1_migrations` tracks
what's applied.

## Dashboard

Next.js 16 (React 19, TypeScript 6) + OpenNext on Cloudflare Workers — live at
<https://turkish-banking-dashboard.incesalim10.workers.dev>. D1 reads are cached
~12h via KV (`cachedAll` → `unstable_cache`), so repeat page views don't re-query
D1. A password-gated `/admin` control center (data health, refresh triggers,
traffic) is unlocked by the `ADMIN_PASSWORD` Worker secret; optional
`GITHUB_DISPATCH_TOKEN` enables the trigger buttons and Web-Analytics creds the
traffic panel. The Pipeline panel's audit card supports a **per-bank,
latest-period** trigger, and **13 banks auto-discover** new quarters from their
IR page (no hand-added URL needed) — see [ADMIN.md](ADMIN.md) §Auto-discovery.
Setup in [OPERATIONS.md](OPERATIONS.md) / [ADMIN.md](ADMIN.md).

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

**Presentation deck generator — PDF on demand (2026-07-05):**
`scripts/generate_presentation.py` turns the deterministic reads into a
board-style **PDF slide deck** (title + one slide per T1 tab + methodology),
read-only off `GET /api/reads` so it never drifts from the site. Self-contained
16:9 HTML in the editorial palette → PDF via a headless Chrome/Edge
`--print-to-pdf` (auto-detected, no new dependency); output in `reports/`
(gitignored). Flags: `--tabs` (subset/reorder), `--file` (offline), `--html-only`,
`--open`, `--title`. Run recipe in [OPERATIONS.md](OPERATIONS.md) §Generate a
presentation deck.

**Telegram Q&A bot — text-to-SQL over D1 (2026-07-05):** a public Telegram bot
that answers natural-language questions by generating **read-only SQL** against
the live D1 and summarising the rows. Runs inside the Worker as a Next route
(`web/app/api/telegram/webhook/route.ts`): Telegram POSTs each message, we verify
the `X-Telegram-Bot-Api-Secret-Token` header, ACK 200, and process in
`ctx.waitUntil`. The orchestrator (`web/app/lib/bot.ts`) rate-limits
(`bot_usage`, migration 0020; per-chat + global daily caps), asks the free model
(same Cerebras→Groq chain as "The Read", via `web/app/lib/llm.ts`) for SQL, gates
it through `web/app/lib/bot-sql.ts` (single `SELECT`/`WITH` only, writes/DDL/
multi-statement/denied-table rejected, row-capped — 29 vitest cases), executes,
then summarises the rows; the reply always includes the **raw data table + the
SQL** so the summary is checkable. The schema prompt
(`web/app/lib/bot-schema.ts`) is the accuracy driver — it drills the per-bank
(`bank_audit_*`, quarterly, thousand TL) vs sector-aggregate (`balance_sheet`
etc., monthly, million TL) split and carries few-shot Q→SQL examples. Setup (bot
token + webhook secret + LLM key as Worker secrets, then register the webhook via
`scripts/setup_telegram_webhook.py`) in [TELEGRAM_BOT.md](TELEGRAM_BOT.md). This
is separate from the outbound `scripts/notify.py` alert channel.

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

A **Compare** tab (`/cross-bank`) is a cross-bank performance heatmap built
entirely off the per-bank `bank_audit_*` tables (the monthly BDDK tables are
group aggregates only). It puts individual banks side by side across the full
performance set — total assets, NPL ratio, Stage-2 share, NPL coverage,
provision intensity, cost of risk, ROE, ROA, NIM, PPOP/assets, loan yield,
deposit cost, loan–deposit spread, Cost/Income — each cell colored by the
bank's rank vs peers (green better / red worse; a neutral `--info` ramp for
size). Two views: **Snapshot** (banks × metrics at the latest common quarter,
grouped by BDDK type or sortable by any metric column) and **Over time** (banks
× quarters for one selected metric, scored across the whole panel to surface
trends). The data layer (`web/app/lib/heatmap.ts`) builds one cached panel from
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

A **Valuation** tab (`/valuation`) does forward scenario projection + intrinsic
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

A qualitative-data layer feeds three tabs from the `news_items` table
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
`src/earnings/`) feeds **/earnings** and an "Earnings & Presentations" block on
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
  market share shipped (see Dashboard §Compare). Deferred lanes with full
  source/schema/extractor sketches in
  [knowledge/data-gaps-roadmap.md](knowledge/data-gaps-roadmap.md): **FX net open
  position** + **interest-rate repricing/maturity gap** (both in §4 market-risk
  footnotes, currently unstructured in `other_data` — need deterministic
  extractors), **credit-ratings history** (agency press + KAP, an events table),
  and the **sovereign yield curve / real rate** (EVDS subset buildable; CDS/OIS
  out of scope). Registry ids: `fx_net_open_position`, `repricing_gap`,
  `credit_rating`, `sovereign_yield_curve`.
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
  → **OPEN follow-up: fix the §4 capital extractor** (AT1/Tier2 row capture +
  total/RWA column alignment) for these banks. **Liquidity validator is at its
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
