# Project State

Concise snapshot of what's in the system right now. Updated as data
coverage or known issues change.

> **Reading order:** [README.md](../README.md) → [ARCHITECTURE.md](ARCHITECTURE.md)
> → this file → [OPERATIONS.md](OPERATIONS.md). Metric definitions in
> [METRICS.md](METRICS.md).
>
> Last verified: 2026-05-11.

---

## Data coverage in D1

| Table | Source | Range | Latest |
|---|---|---|---|
| `balance_sheet`, `income_statement`, `loans`, `deposits`, `financial_ratios`, `other_data` | BDDK monthly bulletin | 2020-01 → present | 2026-03 |
| `weekly_series` | BDDK weekly bulletin | 2019-11 → present | rolling 2-week lag |
| `evds_series` | TCMB EVDS | 2018-01 → present | daily / weekly / monthly per series |
| `bank_audit_balance_sheet` (assets / liabilities / off-balance) | BRSA quarterly PDFs | 2022-Q1 → 2026-Q1 | per-bank |
| `bank_audit_profit_loss` | BRSA quarterly PDFs | same | per-bank |
| `bank_audit_extractions` | extraction log | one row per PDF | 949 PDFs in R2 |
| `bank_types`, `table_definitions`, `download_log` | metadata | — | — |

**Quarterly audit reports**: 32 banks in URL config, 949 PDFs extracted into
D1 (~144k balance-sheet rows + ~62k P&L rows). PDFs themselves live in
R2 at `bddk-audit-reports/<ticker>/<TICKER>_<period>_<kind>.pdf`.

## Bank-type taxonomy

Sector (10001) = Private Deposit (10005) + State Deposit (10006) + Foreign
Deposit (10007) + Participation (10003) + Dev&Inv (10004). The weekly
bulletin uses different code mappings — see METRICS.md §2.

## Storage map

| Bytes | Where | Mutated by |
|---|---|---|
| `evds_series`, `balance_sheet`, `weekly_series`, `bank_audit_*`, … | Cloudflare D1 (`bddk-data`) | weekly + daily cron |
| `<ticker>/<TICKER>_<period>_<kind>.pdf` | Cloudflare R2 (`bddk-audit-reports`) | weekly cron when banks publish |
| `state/bddk_data.db.gz` | Cloudflare R2 (same bucket) | every cron run (state snapshot) |
| `data/banks/audit_report_urls.json` | git | hand-edited via PR |
| `data/banks/bddk_bank_list.json` | git | hand-edited via PR |
| `src/`, `scripts/`, `web/` | git | hand-edited via PR |

## Active workflows

- `.github/workflows/refresh-evds-daily.yml` — Sun–Fri 05:00 UTC. EVDS scrape → D1.
- `.github/workflows/refresh-data.yml` — Sat 03:00 UTC. Monthly + weekly + EVDS + audit-report sync → D1.
- `.github/workflows/deploy-cloudflare.yml` — on push to `web/**`. Build + deploy dashboard.

## Known issues / pending work

- **TSKB 2026Q1** — bank rotated their IR URL; current entry in
  `audit_report_urls.json` 404s. Skip for now; refresh the URL when TSKB
  publishes the next quarter.
- **TAKAS (Takasbank)** — F5 bot mitigation blocks automated downloads.
  User decision to skip; not tracked.
- **A handful of pre-existing partial extractions** (~3% of PDFs flagged
  `success=0` in `bank_audit_extractions`) — mostly FIBA, VAKBN historical
  quarters with layout edge cases. Triable bank-by-bank if needed.
- **Rates dashboard** — 6 panels from the old Dash app aren't ported yet
  (CBRT reserves, gold tons, net funding, residents' FC, expectations).
  EVDS scraper extended to fetch the underlying series; charts can be
  wired once D1 has a few weeks of data.
