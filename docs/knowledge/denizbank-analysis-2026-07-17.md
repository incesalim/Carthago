# Denizbank (DENIZ) — fundamental analysis from filings

**Date:** 2026-07-17 · **Status:** 📊 ANALYSIS (read from `data/bank_audit.db`; no code change) · **Memory:** [[project_bank_fundamental_analyses]]

## What prompted it

User: analyze Denizbank, then "go deeper on everything." All figures pulled from
the audit DB (`bank_audit_profit_loss`, `_balance_sheet`, `_capital`,
`_liquidity`, `_stages`, `_npl_movement`, `_credit_quality`, `_loans_by_sector`,
`_fx_position`, `_profile`), unconsolidated unless noted, periods 2022Q1–2026Q1.

## Bottom line

A **mature, deposit-funded, capital-self-sufficient universal bank with two
engines**: a domestic SME/agri/retail bank running a widening rate-cycle margin,
and a large foreign financial subsidiary contributing ~30% of profit via the
equity method. ~30% nominal ROE (≈ flat real vs ~32% inflation). Enormous capacity
to absorb credit losses. The subject that matters is **asset quality**, now back
to its 2022 highs (5.5% NPL) with thinner coverage (62% vs 80%) — a *cycle*, not
a cliff, and one the bank can comfortably out-earn.

## ⚠️ Correction logged (I got this wrong first, then fixed it)

Initial read compared consolidated net (₺19.12bn) to solo net (₺19.08bn), saw
they matched, and wrongly concluded the subsidiaries "add nothing to profit."
They match **by construction** — the solo P&L already books subsidiary profit via
the equity-method line (P&L line **XV**, "profit from associates by equity
method"). Consolidation just replaces that line with a line-by-line gross-up.

**Actual contribution — a structural ~30% of pretax, every year:**

| | 2023 | 2024 | 2025 | 2026Q1 |
|---|---|---|---|---|
| Equity-method income (₺bn) | 9.3 | 15.6 | 19.9 | 5.6 |
| Share of pre-tax profit | 27% | 30% | 30% | 24% |

On the balance sheet: ₺128.6bn subsidiaries (line IV), of which ₺123.1bn are
*non-consolidated financial* subs and ₺80.6bn is FC → a **foreign banking
subsidiary** carried at ₺123bn equity value, ~16% return on carrying, bringing
₺343bn of its own assets on full consolidation (group ₺2,250bn vs solo ₺1,907bn).

## What it is (2026Q1)

- **₺1.91tn assets** solo / **₺2.25tn** consolidated
- **₺1.10tn deposits**, **₺1.12tn loans** (LDR ≈ 102%), **₺227.7bn equity**
- **578 branches, ~12,000 staff** — established full-service bank
- Growth is **nominal, not real**: assets 3.6× over 3yrs (₺526bn→₺1,907bn) ≈ flat
  after ~32% y/y inflation. The job here is earn-a-real-return, not expand.
- No `kap_ownership` row loaded; Emirates NBD parentage is public but not in our data.

## 1. Margin engine — NII surging on disinflation

Q1'26 interest decomposition (standalone, ₺bn):

| Interest income | | Interest expense | |
|---|---|---|---|
| Loans | 69.7 | Deposits | 55.9 |
| Securities | 10.2 | Borrowings | 4.4 |
| Reserves at CBRT | 7.9 | Money market | 0.4 |
| Banks | 2.9 | Issued securities | 0.8 |
| **Total** | **92.7** | **Total** | **61.8** |

- **NIM expanded ~5.25% (FY25) → ~6.79% (Q1'26 annualized).** Classic disinflation
  trade: expensive time deposits reprice down faster than the loan book.
- Loan yield ~26.2%, blended deposit cost ~21.4% → **~4.8pt spread** (blended —
  38% of deposits are FC paying near-zero, so TL deposits pay 30%+).
- 90% of interest cost is deposits — cheapest, stickiest funding. **Margin is
  cyclical, not structural**: a disinflation stall compresses it.

## 2. Asset quality — a cycle, not a cliff (the real subject)

| | 2022Q4 | 2023Q4 | 2024Q4 | 2025Q4 | 2026Q1 |
|---|---|---|---|---|---|
| NPL ratio | 5.54% | 4.24% | 3.77% | 5.18% | **5.45%** |
| Stage 3 gross (₺bn) | — | — | 27.7 | 52.3 | 60.8 |
| Coverage | 80% | 68% | 60% | 63% | **62%** |
| Stage 2 (watchlist) | — | — | 10.1% | 11.0% | 10.4% |

- **Not unprecedented** — ran 5.54% in 2022; the 2024 dip to 3.77% was inflation
  flattering the denominator. ~5% is Denizbank's normal-to-elevated baseline.
- **Coverage eroded 80% → 62%** — the subtler risk signal: same NPL level as 2022
  but a thinner cushion.
- Fresh formation ~₺21bn/quarter (₺19bn into "substandard", the leading edge) vs
  ₺8.5bn collections + ₺4bn write-offs → net ~₺8.5bn/quarter, accelerating.
- **Where (Stage 3 by sector, 2025Q4):** retail/other ₺20.8bn (~40%), **agriculture
  ₺11.1bn** (disproportionate), services ₺10.1bn, manufacturing ₺8.4bn. Stage 2
  pipeline heaviest in agri (₺24.7bn), services (₺23bn), hospitality (₺13.6bn).
  This is Denizbank's DNA — *the* agri/SME bank ("Üretici Kartı"). The fat yield
  and the high NPL are two sides of the same strategy.

## 3. Cost-of-risk vs earnings — huge absorption capacity

- **Pre-provision operating profit ≈ ₺27.6bn/quarter** + ₺5.6bn equity-method =
  **~₺33bn/quarter (~₺133bn annualized) pre-provision capacity.**
- Provisions took **₺9.3bn — just 28% of capacity.** CoR ~3.3% (up from ~2.8%).
- Provisions would have to **~triple** (₺37bn → ₺130bn/yr) to erase pretax profit.
  Entire ₺60.8bn NPL stock ≈ two quarters of pre-provision earnings.
- → NPL trend decides whether 2026 earnings **grow or stall**, NOT solvency. Risk
  case = margin compresses (disinflation stalls) *while* NPLs keep forming.

## 4. Funding, FX, and the ₺1.7tn derivative book

- Deposit-led (LDR ~102%), plus ₺300bn wholesale borrowing **99.7% FC**, ₺59bn FC
  bonds, ₺15.8bn FC subordinated. ~41% of assets / ~44% of funding is FC.
- **Net FX position ≈ ₺2bn vs ₺228bn equity — effectively flat** despite ₺769bn
  gross FC assets vs ₺833bn FC liabilities on-balance-sheet:

| Currency | On-BS net | Off-BS net (deriv) | Net |
|---|---|---|---|
| EUR | +186bn | ~−195bn | ~−9bn |
| USD | −138bn | ~+139bn | ~+1bn |
| Other | −112bn | ~+122bn | ~+10bn |
| **Total** | **−64bn** | **~+66bn** | **~+2bn** |

- **₺1,727bn derivatives**, entirely trading-classified (zero hedge accounting —
  normal for TR banks): ₺999bn currency/interest swaps, ₺395bn options, ₺160bn
  forwards. This machinery converts FC funding into usable lira. It's **why the
  trading line is always negative** (−₺7.7bn FX vs +₺5.0bn derivatives = ~₺3bn net
  swap cost) — the mirror image of the fat NII. Nothing speculative.

## 5. Capital — thin nominal, enormous retained, one ugly quarter

- **Paid-in capital only ₺19.6bn vs ₺227.7bn equity** — the other ₺208bn is
  retained (₺155bn extraordinary reserves + profit + ₺28bn OCI). Decades of
  self-compounded capital; never leaned on the shareholder.
- **87% CET1** (₺220.6bn of ₺252.6bn total; no AT1, ₺32bn Tier 2) — high quality.

| | 2024Q4 | 2025Q4 | 2026Q1 |
|---|---|---|---|
| CAR | 19.4% | 19.6% | **16.8%** |
| CET1 | 17.2% | 17.2% | **14.7%** |
| RWA (₺bn) | 868 | 1,230 | **1,504** |

- **RWA jumped 22% in one quarter** while capital grew ~5% → CAR −2.8pt. Loans grew
  10%, so RWA outran lending: FX-inflated risk weights on the ₺779bn FC book +
  derivative counterparty exposure. Still > ~12% requirement, but the buffer
  thinned fast *heading into* a rising-NPL phase — squeezed from both ends.

## 6. Securities book — government anchor with OCI sensitivity

- **~₺218bn government securities (11.4% of assets):** ₺139bn FVOCI, ₺75bn
  amortized cost (all TL govt paper — shielded from mark-to-market), ₺4bn FVTPL.
- **₺18bn of equity is reclassifiable OCI** that moves with bond prices — the
  channel through which a yield spike touches capital (through equity, not P&L).
  Modest vs ₺228bn equity, but it's the sensitivity to watch.

## Synthesis — what to watch, in order

1. **Asset quality back to 2022 highs (5.5%) with thinner coverage (62%)** — the
   SME/agri book that drives the margin is also the stress source; formation still
   accelerating.
2. **Margin is cyclical** — wide today on disinflation; a stall reverses the biggest
   tailwind.
3. **Capital thinned fast in Q1'26** (19.6% → 16.8%) on FX-inflated RWA, just as the
   cycle turns — adequate but no longer generous.
4. **A third of profit sits in a foreign subsidiary** we can't see in the solo
   statements — concentration risk worth understanding.

Counterweight: pre-provision earnings (~₺133bn/yr) dwarf the provision run-rate
(~₺37bn) and the entire NPL stock (₺61bn). A deteriorating loan book the bank can
comfortably out-earn — the data poses a question about the **trajectory of
returns**, not solvency.

## Method notes

- Quarterly figures de-cumulated within each fiscal year (Q1 = as filed).
- NIM = NII×4 ÷ avg(2025Q4, 2026Q1) total assets; yield/cost same avg basis.
- PPOP = P&L VIII (gross) − XI (personnel) − XII (opex) − X (other prov).
- Equity-method = P&L line XV; consolidated vs solo gap from summed BS romans.
- Inflation basis: EVDS `TP.TUKFIY2025.GENEL`, ~32% y/y. All ₺bn (DB is ₺'000).
