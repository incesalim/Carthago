# BBVA / Garanti BBVA Research — Türkiye Economic Outlook (quarterly)

Distillations of the **quarterly macro outlook** (sibling of the monthly *Banking
Sector Outlook* that the Liquidity tab adapts). One file per edition, keeping the
numbers and scenario assumptions that the dashboard **cannot** reproduce — market
pricing, positioning flows, proprietary indices, and BBVA's own forecasts — so the
context survives even where the data doesn't.

> ⚠️ **This is NOT a data source for any dashboard.** Nothing here feeds `data/`,
> D1, or R2. It's background reading for discussion, same role as
> [`../newsletter-507yedi/`](../newsletter-507yedi/) and
> [`../external-reports/`](../external-reports/).

## How this relates to the dashboard

The **/economy** tab reproduces the report's reproducible macro core from TCMB
EVDS (GDP, IP, labor, CPI + expectations + real rate, USD/TRY, REER, current
account, fiscal balances — see `docs/METRICS.md` §14), and embeds each edition's
**baseline scenario table** (`BBVA_BASELINE` in `web/app/lib/economy.ts` — update
it from the new edition's final table). Credit growth lives on **/weekly**,
loan/deposit rates and sterilization on **/rates**, dollarization and reserves on
**/liquidity**. Everything else — CDS, OIS, yield curves, BIST, carry/positioning,
nowcast, FCI, scenario sensitivities — is only here.

## Editions

- [1Q26 — March 2026](2026-03-1q26.md) (conflict-in-Iran edition; PDF:
  <https://www.bbvaresearch.com/wp-content/uploads/2026/04/1Q26_Turkiye_Economic_Outlook_Mar26.pdf>)

**Update routine** (each quarter, ~Mar/Jun/Sep/Dec): add the new edition file
here, refresh `BBVA_BASELINE`, and revisit METRICS.md §14 if BBVA changed chart
definitions.
