# Project State

Concise snapshot of what's in the system right now. Updated as data
coverage or known issues change.

> **Reading order:** [README.md](../README.md) → [ARCHITECTURE.md](ARCHITECTURE.md)
> → this file → [OPERATIONS.md](OPERATIONS.md). Metric definitions in
> [METRICS.md](METRICS.md).
>
> Last verified: 2026-06-05.

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

Sector (10001) = Private Deposit (10005) + State Deposit (10006) + Foreign
Deposit (10007) + Participation (10003) + Dev&Inv (10004). The weekly
bulletin uses different code mappings — see METRICS.md §2.

## Storage map

| Bytes | Where | Mutated by |
|---|---|---|
| `evds_series`, `balance_sheet`, `weekly_series`, `bank_audit_*`, … | Cloudflare D1 (`bddk-data`) | weekly + daily cron |
| `<ticker>/<TICKER>_<period>_<kind>.pdf` | Cloudflare R2 (`bddk-audit-reports`) | audit cron when banks publish |
| `state/bddk_data.db.gz` | Cloudflare R2 (same bucket) | bulletin/EVDS cron (bulletin lane snapshot) |
| `state/bank_audit.db.gz` | Cloudflare R2 (same bucket) | audit cron (audit lane snapshot) |
| Next.js page-data cache | Cloudflare KV (`NEXT_INC_CACHE_KV`) | dashboard render (1h TTL on D1 reads) |
| `data/banks/audit_report_urls.json` | git | hand-edited via PR |
| `data/banks/bddk_bank_list.json` | git | hand-edited via PR |
| `src/`, `scripts/`, `web/` | git | hand-edited via PR |

## Active workflows

Two independent ingestion lanes (separate staging DB + R2 snapshot +
concurrency group), so audit failures can't stall the bulletin pipeline:

- `.github/workflows/refresh-evds-daily.yml` — Sun–Fri 05:00 UTC. EVDS scrape → D1.
- `.github/workflows/refresh-bddk-bulletins.yml` — Sat 02:00 UTC. Monthly + weekly bulletins (no EVDS, no audit) → D1.
- `.github/workflows/refresh-data.yml` — Sat 03:00 UTC. Monthly + weekly + EVDS → D1. *(Audit removed — now its own workflow.)*
- `.github/workflows/refresh-audit.yml` — Sun 04:00 UTC. Audit-report sync + extract → `bank_audit_*` → D1. Own DB `data/bank_audit.db`, own snapshot `state/bank_audit.db.gz`, own group `bddk-audit`.
- `.github/workflows/deploy-cloudflare.yml` — on push to `web/**`. Build + deploy dashboard.

## Dashboard

Next.js 15 + OpenNext on Cloudflare Workers — live at
<https://turkish-banking-dashboard.incesalim10.workers.dev>. D1 reads are cached
~1h via KV (`cachedAll` → `unstable_cache`), so repeat page views don't re-query
D1. A password-gated `/admin` control center (data health, refresh triggers,
traffic) is unlocked by the `ADMIN_PASSWORD` Worker secret; optional
`GITHUB_DISPATCH_TOKEN` enables the trigger buttons and Web-Analytics creds the
traffic panel. Setup in [OPERATIONS.md](OPERATIONS.md) / [ADMIN.md](ADMIN.md).

## Known issues / pending work

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
- **Rates dashboard** — 6 panels from the old Dash app aren't ported yet
  (CBRT reserves, gold tons, net funding, residents' FC, expectations).
  EVDS scraper extended to fetch the underlying series; charts can be
  wired once D1 has a few weeks of data.
