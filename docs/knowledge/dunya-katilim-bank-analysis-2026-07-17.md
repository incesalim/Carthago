# Dünya Katılım Bankası (DUNYAK) — fundamental analysis from filings

**Date:** 2026-07-17 · **Status:** 📊 ANALYSIS (read from `data/bank_audit.db`; no code change) · **Memory:** [[project_bank_fundamental_analyses]]

## What prompted it

User question: "how does dünya katılım make so much profit" → broadened to a full
fundamental read. All figures below are pulled from the audit DB
(`bank_audit_profit_loss`, `_balance_sheet`, `_capital`, `_liquidity`,
`_stages`, `_npl_movement`, `_credit_quality`, `_fx_position`, `_profile`),
unconsolidated unless noted, periods 2023Q4–2026Q1. PwC review/audit opinions all
**clean**, no modifications; no free provision (unlike ALBRK — see
[[project_albrk_free_provision_finding]]).

## Bottom line

A **de-novo participation (Islamic) bank** that switched on in late 2023 and is
scaling explosively (assets ₺0.65bn → ₺123bn in nine quarters). The profit is
**real and clean**, but it is (a) one quarter, (b) a *treasury* quarter bolted
onto a lending bank, and (c) nominal — not inflation-adjusted. The number that
actually governs the story is **capital: CAR has fallen 79% → 14.8% in six
quarters**, and retained earnings are now the only thing keeping the growth
inside regulatory limits.

## What it is (2026Q1)

| | 2023Q4 | 2024Q4 | 2025Q4 | 2026Q1 |
|---|---|---|---|---|
| Total assets (₺bn) | 0.65 | 34.6 | 99.7 | **123.0** |
| Loans (₺bn) | 0.0 | 23.0 | 52.3 | 52.8 |
| Collected funds (₺bn) | 0.0 | 23.8 | 76.5 | 83.4 |
| Equity (₺bn) | 0.5 | 7.3 | 9.5 | 11.5 |
| Branches / staff | 1 / — | 17 / 441 | 25 / 509 | 25 / 540 |

- Assets grew ~190× in nine quarters — this single fact drives every ratio.
- Consolidated ≈ solo (consolidated net ₺1.99bn vs solo ₺1.95bn); the ~₺655m
  participation stake is immaterial. The "group" is just the bank.
- No `kap_ownership` row loaded for DUNYAK; parentage not confirmed from our data.

## Where the money comes from — funding-mix arbitrage at startup scale

- **Funding is 75% foreign currency** (₺62.2bn FC of ₺83.4bn collected funds).
  FC participation accounts pay almost nothing.
- **Assets yield ~30%** against a blended funding cost of ~7.8% → **>20pt spread.**
- Loans were **flat** last quarter (₺52.3bn → ₺52.8bn, +1%) while funds grew 9%.
  The inflow went to the **central bank**: CBRT balance ₺15bn → ₺26bn → ₺40.5bn
  over three quarters, now a third of total assets. They earn the spread even on
  the un-lent money.

## Profit is real, but Q1'26 was a treasury quarter

Clean de-cumulated quarterly bridge (revenue lines de-cumulate reliably; 2025
quarterly *net* split is unreliable because filed YTD net was missing for two
quarters — anchor on FY25 = ₺2.06bn and Q1'26 standalone = ₺1.95bn):

| Standalone quarter | NII | Trading | Total revenue | Cost/income |
|---|---|---|---|---|
| 2025Q1 | 0.77 | 0.25 | 1.26 | 56% |
| 2025Q2 | 1.03 | 0.08 | 1.30 | 45% |
| 2025Q3 | 1.42 | 0.20 | 2.00 | 42% |
| 2025Q4 | 2.25 | −0.32 | 2.19 | 37% |
| **2026Q1** | **2.68** | **+1.32** | **4.50** | **32%** |

- **Sustainable engine (NII) compounding ~20%/quarter** purely from balance-sheet
  growth; cost/income falling 56% → 32% (real operating leverage).
- On top: trading **swung ₺1.6bn** (−0.32 → +1.32) in one quarter — an FX/derivative
  windfall (+₺6.1bn FX vs −₺5.0bn derivatives, two legs of one hedge; net FX
  exposure only ₺1.0bn vs ₺11.5bn equity). That swing ≈ the entire q/q profit jump.

**Returns:** FY2025 net ₺2.06bn on ~₺8.5bn avg equity ≈ **24% ROE (middling).**
Q1'26 standalone ₺1.95bn annualizes to **~75% ROE — #2 of 22 banks** vs ~30%
sector median. Truth is between: a genuinely high-return franchise (~32–35%
*real* after ~10% quarterly inflation, which BRSA lets them ignore — net monetary
position line is zero) that had one exceptional treasury quarter.

## The binding constraint — capital

| | 2024Q2 | 2024Q4 | 2025Q4 | 2026Q1 |
|---|---|---|---|---|
| CAR | 79.4% | 46.9% | 18.3% | **14.8%** |
| CET1 | 79.3% | 46.4% | 18.2% | **14.6%** |
| RWA (₺bn) | 8.0 | 15.1 | 48.2 | **72.9** |

- CAR fell from 79% to 14.8% in six quarters; effective floor with buffers ≈ 12%
  → maybe ~1 year of runway before growth must slow or fresh capital comes in.
- **RWA jumped 51% in Q1'26 alone** (₺48bn → ₺73bn) while loans were flat — the
  derivative/FX and market-risk book consuming capital.
- Equity build: ~₺7.27bn paid-in (staged ₺3bn → ₺6bn → ₺7.27bn) + ~₺4bn retained.
  This quarter equity grew ₺1.98bn ≈ net profit ₺1.95bn → **now self-funding growth
  entirely from earnings, no injection** — which is *why* CAR keeps sliding. The
  high ROE isn't a luxury; it's the only capital source keeping expansion legal.

## Asset quality — pristine on paper, unseasoned in reality

- **NPL 0.98%** (₺517m of ₺52.8bn); Stage 2 ~1.1%; reported Stage 3 loss = 0.
- But the whole book is <24 months old — almost nothing has had time to default.
- NPL grew **33% q/q** (₺389m → ₺517m) off a tiny base; ₺157m fresh additions to
  the problem group in one quarter. Cost of risk ~1.2% is a *modeled estimate* on
  an unseasoned portfolio, not an observation. **This is the #1 watch item.**

## Liquidity — comfortable

LCR 175%, NSFR 144% (both well above minimums). Leverage ratio fell 29% → 6.8%
as assets outran capital, still double the 3% floor.

## Open questions / risks

1. **Capital is the whole ballgame** — at current RWA burn, buffer gets tight
   within ~4 quarters.
2. **Unseasoned book** — 0.98% NPL on a 2-year-old portfolio says little about
   through-cycle quality.
3. **₺38bn "other-currency" short** — FX table shows ₺60bn non-USD/EUR liabilities
   vs ₺22bn matching assets, hedged off-balance-sheet. Usually gold accounts for a
   participation bank, but nothing in the extracted statements names precious
   metals — unconfirmed; worth reading the actual note.
4. **Q1'26 flattered by treasury** — the ₺1.32bn trading gain may not repeat; the
   run-rate is the NII line.

## Method notes

- ROE ranking: annualized Q1'26 net (=Q1 standalone) ÷ avg(2025Q4, 2026Q1) equity,
  across all banks with both figures; DUNYAK 74.6%, #2 behind ICBCT 81.8%.
- Inflation basis: EVDS `TP.TUKFIY2025.GENEL`, ~32% y/y to May-2026.
- All amounts ₺'000 in DB; presented in ₺bn (÷1e6).
