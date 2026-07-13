# Profitability tab — redesign rationale + build spec

**Date:** 2026-07-13 · **Status:** PROPOSED (mockup built, deploy-ready, not yet built)
**Artefact:** [mockup](../design/mockups/2026-07-13-profitability-tab.html) ·
[artifact](https://claude.ai/code/artifact/4c842228-30b3-4f0d-ad7e-7d19dbb19b8e)

## The premise

`/profitability` already says returns are negative in real terms (ROE 24.7% vs a
32.1% CPI hurdle). What it never says is **where the return comes from**.

**The margin is not earned on the loan book. It is collected on the deposits the
sector does not pay for.**

| | |
|---|---|
| Demand deposits | **36.9%** of the base, paying nothing |
| Paid on the deposits it *does* pay for | **33.1%** |
| Blended deposit cost | **20.9%** — i.e. **12.2pp of free funding** |
| The demand book, priced at 33.1% | **₺3.19 trn a year** |
| Sector net profit (annualized) | **₺1.01 trn** |
| → the free money is worth | **3.1× the entire profit of the banking system** |

Stable, not a one-off: the ratio has run **2.6×–4.5× for eighteen months**.

Applied to the published ROE (24.7%), paying the demand book at the sector's own
rate would cost **81pp** of it (₺3.19trn against ₺3.92trn of equity) → **−56.4%**.

## Two theses I tested and threw away

Both were plausible and both are **false**. Building on real series killed them
before they shipped:

1. *"The published ROE is a YTD average; the run-rate is below it."* — It is not.
   De-cumulated monthly ROE swings **21%–44%** with no trend; the gap flips sign
   month to month.
2. *"A depositor earns more than a shareholder."* — Also false: the blended
   deposit cost is 20.9% against a 24.7% ROE.

## Why it is deploy-ready

Everything is computed from tables already in D1 and refreshed by the monthly
bulletin cron. Nothing here needs a new source.

| Input | Table | Selector |
|---|---|---|
| Interest paid to depositors | `income_statement` | `item_order = 16` |
| Net interest income | `income_statement` | `item_order = 24` |
| Specific provisions | `income_statement` | `item_order = 25` |
| Non-interest income (fees etc.) | `income_statement` | `item_order = 34` |
| Non-interest expense (opex) | `income_statement` | `item_order = 45` |
| Trading / FX / other, net | `income_statement` | `item_order = 50` |
| Tax | `income_statement` | `item_order = 52` |
| Net profit | `income_statement` | `item_order = 53` |
| Demand / time / total deposits | `balance_sheet` | `a) Vadesiz Mevduat`, `b) Vadeli Mevduat`, `Mevduat (Katılım Fonu)***` |
| Equity | `balance_sheet` | `TOPLAM ÖZKAYNAKLAR` |
| CPI hurdle | `evds_series` | `TP.TUKFIY2025.GENEL` |

All filtered `bank_type_code='10001' AND currency='TL'`.

### The income statement is CUMULATIVE year-to-date

Net profit runs 0.09 → 0.17 → 0.29 → 0.36 through 2026. **Every ratio the page
prints today (ROE, ROA, NIM, OPEX) is that YTD figure annualized.** The monthly
bridge therefore de-cumulates: `month(m) = ytd(m) − ytd(m−1)`, with **January =
the YTD** (the year resets). Get this wrong and every monthly number is garbage.

What the de-cumulation buys: in May, net interest income rose **+₺98bn y/y** and
the profit **still fell** — costs (−₺55bn) and trading (−₺42bn) took it. A YTD
average cannot show that.

### The reconciliation gate (this is the deploy requirement)

The bridge is assembled from **fixed `item_order` positions**. If BDDK renumbers
a line, the sum drifts silently and the page lies with a straight face. So the
page must **reconcile the bridge against the reported net-profit line (item 53)
on every render**:

```
|nii − prov + fees − opex + other − tax  −  net_profit|  >  0.001 trn
   → print a data-quality flag INSTEAD of the chart
```

Today it reconciles to **₺0.0000 trn**. A page that must survive a cron has to
fail loudly, not quietly. (Same discipline as the credit tab's contributions.)

### The counterfactual's caveats — print them, don't bury them

The demand-book valuation is a **sizing device, not a forecast**, and the page
says so on the sheet:

- demand deposits are **not literally free** — servicing them (branches,
  payments, cards) is inside the **54.8%** cost/income the page now prints;
- if the sector paid market rates on them, the balance sheet would not stay the
  same. The arithmetic only says what the free funding is **worth** at the
  sector's own paid rate.

### One metric, one basis

My first build printed a **home-made ROE** (net profit ÷ average equity = 25.8%)
next to the **BDDK published ratio** (24.7%) in the vitals band — two different
numbers for the same thing on one page. The counterfactual is now applied as a
**cost in pp against the published figure**, never as a rival ROE. (Promoted to
`web/DESIGN.md`.)

## What changes on the page

- **Brief** gains Movers (incl. cost/income — the classic efficiency ratio the
  page never printed), the "engine → the return" transmission, four printed rules
  (three fire) and Standings vs the CPI hurdle.
- **The engine** (new signature section): the deposit-cost chart (paid-on-time vs
  blended vs CPI) and the free-book-vs-profit bars.
- **The month's P&L**: the de-cumulated bridge — replaces the six `Stat` boxes of
  "the return equation", which only restated the vitals.
- **Kept**: ROE/ROA/NIM/OPEX/fees by group, the ROE-vs-CPI real-returns chart,
  and the NIM components section.

## Ship order

1. `app/lib/profitability.ts` — pure: de-cumulate, the engine, the bridge, the
   reconciliation. Unit tests pin the YTD reset and the reconciliation gate.
2. Page: brief rows + the engine section + the bridge (replacing the Stat boxes).
3. Evidence layer: convert the remaining charts to `plain` + `ChartFoot`.
