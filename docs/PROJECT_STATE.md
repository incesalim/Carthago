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
> Last verified: 2026-06-19. Dated change history → [CHANGELOG.md](CHANGELOG.md).

---

## Data coverage in D1

| Table | Source | Range | Latest |
|---|---|---|---|
| `balance_sheet`, `income_statement`, `loans`, `deposits`, `financial_ratios`, `other_data` | BDDK monthly bulletin | 2020-01 → present | 2026-04 |
| `weekly_series` | BDDK weekly bulletin | 2019-11 → present | rolling 2-week lag |
| `nonbank_balance_sheet` | BDDK non-bank monthly bulletin (BultenAylikBdmk) | 2008-01 → present | leasing / factoring / financing, monthly, balance sheet (Million TL); reconciles to FKB sector totals. VYŞ (sparse/variant feed) + savings-finance (not in this bulletin) deferred |
| `evds_series` | TCMB EVDS | 2018-01 → present | daily / weekly / monthly per series |
| `tbb_digital_stats` | TBB quarterly digital-banking report | 2019-Q1 → present | quarterly (Mar/Jun/Sep/Dec) |
| `kap_ownership` | KAP Genel Bilgi Formu §5 + §7 subsidiaries (kap.org.tr) | current state per bank (`as_of` = filing date) | weekly full replace; 30/31 banks (ATBANK files no form); subsidiaries grid only on the full form (~15 banks) |
| `tefas_manager_daily`, `tefas_category_daily`, `tefas_allocation_daily`, `tefas_top_funds` | TEFAS fund-market JSON API (tefas.gov.tr) | rolling ~5 years (API rejects older start dates) → present | daily T+1, trading days; aggregated at ingest (no per-fund rows) |
| `bist_prices`, `bist_dividends`, `bist_shares` | Borsa İstanbul via Yahoo Finance chart API | 2014-06 → present | daily EOD (~1-day lag); 11 listed banks + XU100/XBANK indices (QNBFB delisted on Yahoo — no data) |
| `bank_audit_balance_sheet` (assets / liabilities / off-balance) | BRSA quarterly PDFs | 2022-Q1 → 2026-Q1 | per-bank |
| `bank_audit_profit_loss` | BRSA quarterly PDFs | same | per-bank |
| `bank_audit_credit_quality` | BRSA PDFs, IFRS 9 footnotes | same | per-bank, per-section |
| `bank_audit_profile` | BRSA PDFs, qualitative section | same | branches + personnel where disclosed |
| `bank_audit_capital` | BRSA PDFs, §4.1 capital adequacy | same — **fully backfilled 2026-06-10** (31/31 banks, ~1.7k rows) | CET1/Tier1/Tier2/Total/RWA + CET1/Tier1/CAR ratios, per period_type |
| `bank_audit_liquidity` | BRSA PDFs, §4.6/4.7 | same — **fully backfilled 2026-06-10** (31/31 banks, ~1.8k rows) | LCR (total/FC), NSFR, leverage ratio, per period_type |
| `bank_audit_oci`, `_cash_flow`, `_equity_change`, `_npl_movement`, `_stages`, `_loans_by_sector` | BRSA PDFs (statement pages + IFRS-9/credit footnotes) | 2022-Q1 → 2026-Q1 | per-bank; per-lane pass rates in the validation-status table below |
| `bank_audit_extractions` | extraction log | one row per PDF | 974 rows (954 ok / 20 partial) |
| `bank_types`, `table_definitions`, `download_log` | metadata | — | — |

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
| `off_balance` | 948 | 18 | 9 | per-partition validator is **horizontal-only** (TL+FC=Total; parent=Σchildren / TOTAL=Σromans skipped because off-balance skips hierarchy levels → would false-fail). Vertical structure validated **alert-only** via `check_audit_quality._off_balance_consistency` (within-bank total/Σromans ratio outlier — a stable per-bank gap is structural, a jump = dropped section). 2026-06-15: 3 real errors flagged (ATBANK 2025Q4 8×, EMLAK 2022Q4 total≈0, ISCTR 2025Q4 2×); DENIZ's stable ~5% gap correctly ignored |
| `profit_loss` | 964 | 10 | 1 | **frozen** (correct) |
| `oci` | **881** | 78 | 16 | fixed 2026-06-14 (was ~62); validation-guided, fitz-only |
| `cash_flow` | **813** | 135 | 27 | fitz-only; 135 = dropped-sub-row tail |
| `equity_change` | 610 | 355 | 10 | hardened; vertical-chain tail still open |
| `credit_quality` | 939 | 5 | 31 | **good** — real reconciliation (section total=S1+S2+S3 + cross-section loans≈S12+NPL); skips gross−prov=net (BRSA collective-reserve noise). 5 fails genuine (DENIZ, TFKB) |
| `stages` | 952 | **15** | 8 | NPL=100% **fixed end-to-end 2026-06-15**. (1) Validator: the NPL=100% fingerprint required stage1/stage2 non-null but the broken shape has them NULL → it skipped all 45, which showed green; now NULL counts as 0 → 45 surfaced. (2) Extractor (`credit_quality.loans_by_stage`): captured the §7.2 Stage-1/2 table on 3 column-split variants (İşbank EN/no-space coord fallback; ANADOLU wrapped header → Stage-2-only anchor; TSKB label/number y-offset → 5.5px cluster). Re-extracted 6 banks → rebuilt derived stages → **43 of 45 repaired** (npl100 45→2). Remaining 2 = FIBA + TFKB image-only quarters |
| `capital` | 816 | **26** | 133 | validator **hardened 2026-06-15** (was 2 fail): now reconciles composition (Tier1=CET1+AT1, Total=Tier1+Tier2) + sub-ratios (CET1/Tier1/CAR = component÷RWA), not just orderings. The 26 fails are **real §4 mis-extractions** (AT1/Tier2 dropped → read 0; total↔Tier2 / RWA↔total column-slips): ICBCT, QNBFB, TSKB, ISCTR, SKBNK, AKTIF |
| `liquidity` | 945 | 0 | 30 | §4 backfilled; per-partition validator is **band-only** (ratios only, nothing to reconcile). Validated instead by a **within-bank time-series outlier scan** (`check_audit_quality._liquidity_outliers`, ≥8× = order-of-magnitude slip; covers `lcr_fc`, which the band check never read). **Verdict 2026-06-15: leverage / LCR / NSFR clean fleet-wide; only error = FIBA `lcr_fc` 2024Q1 unco + 2024Q2 unco/cons (~1.1 vs the bank's ~430)** |
| `npl_movement` | **515** | 126 | 334 | fixed 2026-06-14 (was 195); 3 generic bugs + fitz-only |
| `loans_by_sector` | **135** | 36 | 804 | fixed 2026-06-14 (was 99); **annual-only** disclosure → most skips are genuine (interim has no table); ceiling ≈ Q4 partitions |

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

- `.github/workflows/refresh-evds-daily.yml` — Sun–Fri 05:00 UTC. EVDS scrape → D1. Also carries the non-critical BIST / TBB / KAP / TEFAS steps of `refresh.py` (BIST re-fetches a trailing 35-day window daily — self-heals the EOD ~1-day lag, holidays and late closes; TEFAS re-fetches a trailing 7-day window daily).
- `.github/workflows/refresh-bddk-bulletins.yml` — Sat 02:00 UTC. Monthly + weekly bulletins (no EVDS, no audit) → D1.
- `.github/workflows/refresh-data.yml` — Sat 03:00 UTC. Monthly + weekly + EVDS + TBB digital-banking (quarterly) + KAP ownership structure + TEFAS fund market → D1. *(Audit removed — now its own workflow.)* TBB, KAP and TEFAS are non-critical steps in `refresh.py` (an outage won't abort the BDDK refresh); they ride the bulletin lane's snapshot, so no new lane. KAP details in [OPERATIONS.md](OPERATIONS.md) §KAP ownership; TEFAS in §TEFAS fund market.
- `.github/workflows/backfill-tefas.yml` — manual dispatch only. Resumable ~5-year TEFAS history backfill (the API rejects start dates older than 5 years; 28-day windows, rate-limited ≈2–2.5 h; re-dispatch with the same `from` to resume — completed windows are skipped via `tefas_fetch_log`).
- `.github/workflows/backfill-nonbank.yml` — manual dispatch only. One-time historical backfill of the non-bank sector lane (leasing/factoring/financing) from `from_year` (default 2020 = banking-aggregate horizon) → now (~5–10 min). The incremental refresh rides `refresh-bddk-bulletins.yml` / `refresh-data.yml` (non-critical `update_nonbank.py` step in `refresh.py`); this workflow is only for the initial history load. Apply migration 0013 (via a `web/**` deploy) before dispatching.
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

Every chart card (`web/app/components/ui/chart-card.tsx`) carries hover-revealed
icon-only header controls — **Copy** image, **PNG** download, **CSV** download,
and **Expand** to a centred popup. A single **global date-range selector**
(1Y / 3Y / 5Y / YTD / All) sits in the page header on chart pages (the
`rangeSelector` prop on `PageHeader`) and windows **every** time-series chart on
the page at once — `TrendChart`, `TimeSeriesChart`, `StackedArea`, and the
`/sector` total-assets area. It's a pure **client-side** display zoom over data
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
liquidity section: TL & FC loan/deposit ratios and TL deposit growth split
Public (state) vs Private (private + foreign), deposit dollarization, net CBRT
funding, gross reserves, residents' household FC savings, and REER. See
[METRICS.md](METRICS.md) §12.

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

## Known issues / pending work

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
  agri_fishery double-count + HSBC missing `other`). OCI: the 16 YKBNK Q2/Q3
  partitions that captured P&L rows are **FIXED (2026-06-20)** — `_locate_oci_page`
  now skips P&L pages (the BRSA combined-title "…VE DİĞER KAPSAMLI GELİR TABLOSU"
  made the locator stop on YKBNK's quarter-only P&L twin; it now skips any candidate
  carrying an interest/profit-share income anchor, window widened pl+1→pl+6) and the
  affected partitions + ~15 recoverable empties (GARAN/FIBA/ISCTR/TFKB/TSKB, where
  P&L parsed but the OCI page was past the old window) were re-extracted via
  `reextract-statement.yml`.
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
  Statement view, above the table): a hand-rolled SVG Sankey of the selected
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
