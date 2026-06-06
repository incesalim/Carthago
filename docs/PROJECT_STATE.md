# Project State

Concise snapshot of what's in the system right now. Updated as data
coverage or known issues change.

> **Reading order:** [README.md](../README.md) → [ARCHITECTURE.md](ARCHITECTURE.md)
> → this file → [OPERATIONS.md](OPERATIONS.md). Metric definitions in
> [METRICS.md](METRICS.md).
>
> Last verified: 2026-06-06 (EXIM extraction fix + audit data-quality check).

---

## Data coverage in D1

| Table | Source | Range | Latest |
|---|---|---|---|
| `balance_sheet`, `income_statement`, `loans`, `deposits`, `financial_ratios`, `other_data` | BDDK monthly bulletin | 2020-01 → present | 2026-04 |
| `weekly_series` | BDDK weekly bulletin | 2019-11 → present | rolling 2-week lag |
| `evds_series` | TCMB EVDS | 2018-01 → present | daily / weekly / monthly per series |
| `bank_audit_balance_sheet` (assets / liabilities / off-balance) | BRSA quarterly PDFs | 2022-Q1 → 2026-Q1 | per-bank |
| `bank_audit_profit_loss` | BRSA quarterly PDFs | same | per-bank |
| `bank_audit_credit_quality` | BRSA PDFs, IFRS 9 footnotes | same | per-bank, per-section |
| `bank_audit_profile` | BRSA PDFs, qualitative section | same | branches + personnel where disclosed |
| `bank_audit_extractions` | extraction log | one row per PDF | 974 rows (954 ok / 20 partial) |
| `bank_types`, `table_definitions`, `download_log` | metadata | — | — |

**Quarterly audit reports**: 32 banks in URL config, ~974 PDFs extracted into
D1 (~159k balance-sheet rows + ~59k P&L rows + ~7.4k IFRS 9 credit-quality
rows + ~460 bank-profile rows). PDFs themselves live in R2 at
`bddk-audit-reports/<ticker>/<TICKER>_<period>_<kind>.pdf`. Bank profile
(branches + personnel) is extracted where the bank discloses it in a
recognized phrasing — 16 of 31 banks currently parsed; the remaining 15
use phrasings not yet covered by the regex patterns.

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
| `<ticker>/<TICKER>_<period>_<kind>.pdf` | Cloudflare R2 (`bddk-audit-reports`) | audit cron when banks publish |
| `state/bddk_data.db.gz` | Cloudflare R2 (same bucket) | bulletin/EVDS cron (bulletin lane snapshot) |
| `state/bank_audit.db.gz` | Cloudflare R2 (same bucket) | audit cron (audit lane snapshot) |
| `state/history/<lane>-YYYYMMDD.db.gz` | Cloudflare R2 (same bucket) | every cron — dated backup, last 7 kept |
| Next.js page-data cache | Cloudflare KV (`NEXT_INC_CACHE_KV`) | dashboard render (12h TTL on D1 reads) |
| `data/banks/audit_report_urls.json` | git | hand-edited via PR |
| `data/banks/bddk_bank_list.json` | git | hand-edited via PR |
| `src/`, `scripts/`, `web/` | git | hand-edited via PR |

## Active workflows

Two independent ingestion lanes (separate staging DB + R2 snapshot +
concurrency group), so audit failures can't stall the bulletin pipeline:

- `.github/workflows/refresh-evds-daily.yml` — Sun–Fri 05:00 UTC. EVDS scrape → D1.
- `.github/workflows/refresh-bddk-bulletins.yml` — Sat 02:00 UTC. Monthly + weekly bulletins (no EVDS, no audit) → D1.
- `.github/workflows/refresh-data.yml` — Sat 03:00 UTC. Monthly + weekly + EVDS → D1. *(Audit removed — now its own workflow.)*
- `.github/workflows/refresh-audit.yml` — Sun 04:00 UTC. Audit-report sync + extract → `bank_audit_*` → D1. Own DB `data/bank_audit.db`, own snapshot `state/bank_audit.db.gz`, own group `bddk-audit`. Manual dispatch takes optional `bank` / `skip_scrape` inputs (the /admin per-bank trigger uses `bank` → `--only-bank … --latest-period`). After extraction it runs `scripts/check_audit_quality.py --alert` (alert-only): flags a quarter whose lines are identical to the prior one (period-shift), a balance sheet that doesn't balance, or missing rows → Telegram/Discord, never blocking the push.
- `.github/workflows/deploy-cloudflare.yml` — on push to `web/**`. Apply D1 migrations + build + deploy dashboard.
- `.github/workflows/healthcheck.yml` — daily 06:00 UTC. D1 freshness check → Telegram/Discord alert if stale.
- `.github/workflows/ci.yml` — on PRs. ruff + pytest + eslint + tsc. (Dependency bumps via `dependabot.yml`.)

Schema source of truth: hand-authored migrations in `web/migrations/`, applied
by the deploy workflow (`wrangler d1 migrations apply`); `d1_migrations` tracks
what's applied.

## Dashboard

Next.js 15 + OpenNext on Cloudflare Workers — live at
<https://turkish-banking-dashboard.incesalim10.workers.dev>. D1 reads are cached
~12h via KV (`cachedAll` → `unstable_cache`), so repeat page views don't re-query
D1. A password-gated `/admin` control center (data health, refresh triggers,
traffic) is unlocked by the `ADMIN_PASSWORD` Worker secret; optional
`GITHUB_DISPATCH_TOKEN` enables the trigger buttons and Web-Analytics creds the
traffic panel. The Pipeline panel's audit card supports a **per-bank,
latest-period** trigger, and **13 banks auto-discover** new quarters from their
IR page (no hand-added URL needed) — see [ADMIN.md](ADMIN.md) §Auto-discovery.
Setup in [OPERATIONS.md](OPERATIONS.md) / [ADMIN.md](ADMIN.md).

A **Liquidity** tab (`/liquidity`) adapts the BBVA "Banking Sector Outlook"
liquidity section: TL & FC loan/deposit ratios and TL deposit growth split
Public (state) vs Private (private + foreign), deposit dollarization, net CBRT
funding, gross reserves, residents' household FC savings, and REER. See
[METRICS.md](METRICS.md) §12.

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
  skips it rather than false-alarm). Backfill via
  `scripts/backfill_extraction.py --banks ALL [--latest-period]`.
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
