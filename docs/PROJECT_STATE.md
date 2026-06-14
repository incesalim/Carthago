# Project State

Concise snapshot of what's in the system right now. Updated as data
coverage or known issues change.

> **Reading order:** [README.md](../README.md) → [ARCHITECTURE.md](ARCHITECTURE.md)
> → this file → [OPERATIONS.md](OPERATIONS.md). Metric definitions in
> [METRICS.md](METRICS.md).
>
> Last verified: 2026-06-14 — **Engine strategy is now per-statement: fitz-only for OCI +
> cash flow, multi-engine kept for equity.** Measured that the multi-engine model
> (read a page with pdfplumber AND fitz) costs a full PDF re-open (~225 ms/page, ~60× the
> fitz-only cost) + the poison-PDF hang risk. It only earns that on EQUITY — pdfplumber's
> x-clustering uniquely separates the wide interleaved-footnote banks (GARAN/AKBNK → 0 rows
> fitz-only). On OCI + cash flow (narrow tables) pdfplumber adds **zero** accuracy: verified
> via `--force` re-extract on 2026 — OCI fitz-only **17/19 == multi-engine** (only ALBRK
> fails, under both engines), CF fitz-only **15/23** with the 8 fails pre-existing
> dropped-sub-row banks (FIBA/KUVEYT/SKBNK/TEB) AND **AKBNK recovered from empty**. So OCI
> (`oci.py`) drops its pdfplumber candidates (keeps the validation-guided n-template select;
> pdfplumber only as a no-fitz fallback) and the CF block (`extractor.py`) parses with fitz,
> falling back to the both-engines parser only if fitz yields 0 rows. `reextract_statement.py`
> gains a `cash_flow` lane (commit `c83eaaa`). **Re-extracted ALL periods fleet-wide
> (2022Q1→2026Q1): OCI 62 → 881 / 975 pass; cash flow 802 → 813 / 975.** OCI's jump is because
> ~94% were broken across all years (same n_cols bug); CF moved little — already healthy, the +11
> is recovered stale empties, its 135 fails are the dropped-sub-row tail. Also fixed `--only-failing`
> (commit `3d028b0`): now means NOT-passing (`checks_failed>0 OR checks_passed=0`) so it catches the
> stale empties (was failed-only, which skipped them) → a fleet re-extract downloads only the bad
> partitions (CF: 173 not 975); workflow defaults it true. Remaining tail — OCI 78 / CF 135 fails +
> ~16/27 empties — is the dropped-sub-row issue (ALBRK OCI 2.2.2 / the CF banks' 2.2 — shared
> `_parse_rows`, engine-independent) plus image-only/no-PDF partitions.
>
> Prior: 2026-06-14 — **OCI ("Diğer Kapsamlı Gelir") extraction fixed with the
> validation-guided approach.** OCI was barely extracted (53 of 55 2026 partitions had
> ZERO rows): the P&L-tuned column detector reads a 2-column interim OCI page as 4
> columns, so the shared `_parse_page` returned 0 / garbage rows. New
> `src/audit_reports/oci.py` mirrors the equity "new approach" — read the located OCI
> page with pdfplumber + fitz at n∈{detected,2,4} and keep the reconstruction whose
> **roman chain validates** (III = I + II) rather than the most-rows one. n=2 wins for
> interim; multi-engine recovers banks one engine fragments (TEB needs fitz). Sample of
> 14 (empties + partials): **12/14 now pass `check_oci`, up from ~0** (the locator was
> already fine post-fitz-changes — the DB's "empties" were stale). Strictly ADDITIVE:
> never touches the frozen `_parse_page`/`_detect_pl_ncols`; the `extract()` call-site
> swap is isolated to the OCI block (BS/P&L/equity/CF byte-unchanged). `reextract_statement.py`
> gains an `oci` lane; new `.github/workflows/reextract-statement.yml` (workflow_dispatch)
> ships it (statement=oci, periods=2026Q1, only_failing OFF — empties are
> `checks_failed=0`/skipped, so `--only-failing` would miss them; the non-destructive
> guard still skips passing). Commits `cf5c4e7`, `8f320ce`. **Shipped to D1+R2 (run
> 27500669011): 55 OCI partitions → 52 pass, was ~1.** Tail of 3: ALBRK cons+uncons
> (chain validates but drops the wrapped sub-row 2.2.2 → hierarchy sub-tree short) and
> TSKB uncons (P&L page is image-only → `pl=None` → no OCI page → empty; genuine
> OCR/manual gap). OPEN: those 3, and extend OCI to pre-2026 periods.
>
> Prior: 2026-06-14 — **re-extraction is now NON-DESTRUCTIVE: it can never
> overwrite correct data.** `loader.upsert_report` skips writing any statement whose
> stored data already PASSES validation (`bank_audit_validation`: `checks_failed=0 &
> checks_passed>0`) — assets+liabilities protected as a pair (they cross-check),
> every other statement per-statement; failing/missing statements are still re-extracted.
> So a plain re-run, a `--force` re-extract, OR a full backfill can only *improve* the
> DB, never regress a validated partition. Escape hatch: `force=True`
> (`sync_audit_reports.py --force-overwrite`, `reextract_statement.py --force`). Bonus —
> `upsert_report` now records validation by **revalidating from the STORED rows**
> (`revalidate_partition`, all 14 statement types) instead of the in-memory report
> (which covered only 8), so the recorded verdict always matches what's in the DB.
> Regression test `tests/test_upsert_guard.py`; touched `loader.py`, `validator.py`
> (`statement_passes`), `reextract_statement.py`, `sync_audit_reports.py`. Separately,
> re-pushed the `/admin` coverage matrix: the D1 spine tables
> (`bank_audit_expected`/`_statement_types`/`_coverage`) had silently gone to 0 again
> (a `sync_audit_expected.py --push` D1 write that didn't land — the full-rebuild
> clears-then-inserts and prints "done" regardless), now 975/14/13650 + R2 refreshed.
>
> Prior: 2026-06-14 — **equity_change 2025/26 hardened (fails 205 → 79) +
> self-validating fast iterate loop; committed to fitz.** (1) A few BRSA PDFs (e.g.
> VAKBN 2025Q4: 159 pages, 273 `/ObjStm`) made pdfplumber's page-tree resolution hang
> ~2 min — the equity re-extract wedged on it. Locators now take page COUNT + text from
> **fitz** (30 ms vs 2 min); `extract()` shuts the stream instead of `pdf.close()` (which
> re-enumerates pages). VAKBN equity-only: **124 s hang → 0.7 s.** (2) Equity parse keeps
> the reconstruction whose **column chain VALIDATES** among pdfplumber + 2 fitz engines
> (validation-guided, not max-rows), with a both-template (14/16) retry gated to failing
> pages. (3) `n_cols` detected from pdfplumber text (fitz over-counts → AKBNK/BURGAN uncons
> 1→17 rows). (4) mid-page split closing must follow the table body (fixed VAKBN current↔prior
> flip). Commits `753d885`, `e0d301e`, `ec7f073`. **Self-validating loop:**
> `reextract_statement.py` validates each partition INLINE (factored `revalidate_partition`),
> prints live `[vFAIL]`, pushes `bank_audit_validation`; new `--only-failing` re-extracts ONLY
> the failing set → edit→measure dropped ~10 min → ~2 min. **2025/26 equity: 206/285 clean
> (shipped D1+R2), 79 flagged** as a per-bank follow-up. OCR/table-tool exploration done (OCR
> *does* recover the corrupted text — letter-spacing/numbers clean — but feeding our column
> parser needs a grid-reconstruction layer; `pdfplumber.extract_tables` ~4 min/page) →
> **committed to fitz** (already primary: fitz locators + 2 of 3 equity candidates; pdfplumber
> stays a thin fallback for interleaved-footnote banks GARAN/AKBNK + BS/P&L). The 79 split
> into corrupted-text (OCR), clean-but-mis-gridded (grid), and genuine gaps (HSBC, BS-side, no
> tool fixes); `scripts/_eq_failreport.py` lists them.
>
> **Prior: 2026-06-13 — equity/CF deep-fixed + full fleet re-extracted +
> coverage matrix restored.** Post-backfill diagnosis found the earlier "two bug"
> fix was a band-aid; the real root causes were: (1) the equity-page **locator
> gated on a fragile title anchor** → missed ODEA (image-only title) / Ziraat
> ("ÖZKAYNAKLAR DEĞİŞİM") — now detects by the wide-table fingerprint (≥3 lines
> ≥10 tokens); (2) **cash flow used the P&L column detector** → misread annual CF
> date-headers as 4 cols → 0 CF rows fleet-wide — now pinned to 2 cols; (3) mid-page
> split missed TEB (no closing row) — added roman-restart split; (4) DENIZ `--`
> double-dash zeros + EMLAK 15→16 col mis-clamp (commits b8b1c51, 8a91444). Whole
> fleet (31 banks, 975 PDFs) re-extracted **sequentially** (never concurrent — that
> races the R2 snapshot), 11 manual image-only partitions restored + 25 overrides
> re-applied, revalidated, pushed, snapshot uploaded. Result: **CF 0 contamination
> fleet-wide** (was 14 banks), CF 839/975 pass; DENIZ 0→1152 / EMLAK 0→1085 equity
> rows; **coverage matrix RESTORED** (D1 spine tables had been 0 rows — sync had never
> run post-schema-work). OPEN follow-ups (non-core): equity_change **vertical-chain**
> ~732 fails (PRE-EXISTING; validated `_try_fit` n−1-token insertion fix recovers most
> banks but GARAN-class closing-row issue remains; needs a re-extract to apply);
> 136 CF cf_chain fails; FIBA 2023Q3 cons manual-P&L transcription typo (unpushed).
> **Prior: 2026-06-12 — cash flow + equity-change extractors added**:
> 14 statement types in the registry (2 new: `cash_flow` sort_order=38,
> `equity_change` sort_order=36). Both `is_core=False` with structural validators
> (CF roman chain V=I+II+III+IV / VII=V+VI; equity row-sum + col-chain + OCI cross
> + BS equity cross).
> **Prior state (2026-06-12):** audit validator fleet complete across 12 types;
> 975 partitions revalidated; coverage matrix 11 700 cells: 8 696 ok / 42 manual /
> 225 error / 2 737 missing.

---

## Data coverage in D1

| Table | Source | Range | Latest |
|---|---|---|---|
| `balance_sheet`, `income_statement`, `loans`, `deposits`, `financial_ratios`, `other_data` | BDDK monthly bulletin | 2020-01 → present | 2026-04 |
| `weekly_series` | BDDK weekly bulletin | 2019-11 → present | rolling 2-week lag |
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
| `bank_audit_extractions` | extraction log | one row per PDF | 974 rows (954 ok / 20 partial) |
| `bank_types`, `table_definitions`, `download_log` | metadata | — | — |

**Quarterly audit reports**: 32 banks in URL config, ~974 PDFs extracted into
D1 (~159k balance-sheet rows + ~59k P&L rows + ~7.4k IFRS 9 credit-quality
rows + ~460 bank-profile rows). PDFs themselves live in R2 at
`bddk-audit-reports/<ticker>/<TICKER>_<period>_<kind>.pdf`. Bank profile
(branches + personnel) is extracted where the bank discloses it in a
recognized phrasing — 16 of 31 banks currently parsed; the remaining 15
use phrasings not yet covered by the regex patterns.

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
- `.github/workflows/refresh-audit.yml` — Sun 04:00 UTC. Audit-report sync + extract → `bank_audit_*` → D1. Own DB `data/bank_audit.db`, own snapshot `state/bank_audit.db.gz`, own group `bddk-audit`. Manual dispatch takes optional `bank` / `skip_scrape` inputs (the /admin per-bank trigger uses `bank` → `--only-bank … --latest-period`). After extraction it runs `scripts/check_audit_quality.py --alert` (alert-only): flags a quarter whose lines are identical to the prior one (period-shift), a balance sheet that doesn't balance, or missing rows → Telegram/Discord, never blocking the push.
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
verification. See [METRICS.md](METRICS.md) §14.

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
provision intensity, ROE, ROA, NIM, Cost/Income — each cell colored by the
bank's rank vs peers (green better / red worse; a neutral `--info` ramp for
size). Two views: **Snapshot** (banks × metrics at the latest common quarter,
grouped by BDDK type or sortable by any metric column) and **Over time** (banks
× quarters for one selected metric, scored across the whole panel to surface
trends). The data layer (`web/app/lib/heatmap.ts`) builds one cached panel from
four queries: assets = BS roman I.–X. sum; stage ratios from `bank_audit_stages`;
ROE/ROA/NIM/Cost-Income derived from a P&L pivot by BRSA hierarchy (net profit
`XXV.`→`XIX.`, net interest `III.`, opex `XI.`+`XII.`, gross op profit `VIII.`)
over equity (BS liab `XVI.`), with YTD flows annualized × (4/quarter). Rank +
color logic is the pure, client-safe `heatmap-normalize.ts`.

A qualitative-data layer feeds two tabs from the `news_items` table
(`scripts/sync_news.py`, daily cron):

- **/regulation** — primary regulator feeds: TCMB press releases + BDDK board
  decisions, with a weekly AI thematic briefing. Per-bank KAP disclosures
  surface on each bank's page.
- **/news** — banking-sector *journalism* aggregated from TR financial-media
  RSS feeds (Bloomberg HT, Dünya, Ekonomim, AA, NTV) via
  `src/news/sources/press.py`, keyword-filtered to banking-relevant items
  (`source='press'`). Feed list is hand-edited in `data/news/press_feeds.json`.
  Only headline + link + snippet are stored (no full body); cards link out.
  Removing a feed there purges its stored items on the next cron (a one-time
  manual D1 delete clears what was already pushed). Hürriyet was dropped — its
  RSS froze a stale Oct-2024 block.

## Known issues / pending work

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
  agri_fishery double-count + HSBC missing `other`). OCI: 16 partitions from YKBNK
  where the OCI extractor accidentally captures P&L rows (extractor fix deferred).
  Off-balance: 20 partitions across 7 banks (ALNTF column-alignment, TEB year-end
  format, ZIRAAT 2025Q4/2026Q1 new). ISCTR 2025Q1/Q2 capital CAR=100.0 = 2 genuine
  extraction errors. Dashboard surfacing of §4 capital/liquidity cross-bank view
  remains an open follow-up.
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
