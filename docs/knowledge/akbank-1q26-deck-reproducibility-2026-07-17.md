# Can we reproduce Akbank's 1Q26 earnings deck? — 2026-07-17

**Status: ANALYSIS ONLY — nothing built, nothing changed.** A per-item verdict on
[akbank_earnings_presentation_1q2026.pdf](https://www.akbankinvestorrelations.com/en/images/pdf/earning-presentation/akbank_earnings_presentation_1q2026.pdf)
(29 pages), checked against `data/bank_audit.db` (local snapshot, 2026-07-17) and
`data/bddk_data.db`.

## Headline

**The statutory spine reproduces exactly. The management overlay does not.**

Every figure Akbank takes straight from its BRSA filing ties to our stored rows to the
last digit. Every figure that depends on Akbank's *own* reclassification, MIS, or
bank-only weekly market-share basis is not in our data and cannot be derived from it.

Roughly **60% of the deck is reproducible**, ~15% partially, ~25% not at all.

### The deck is image-only

29 pages, 83–137 embedded images *per page*: the numbers are pixels, not text.
`get_text()` returns ~12k chars of fragments for the whole deck and **zero** numbers on
the balance-sheet / P&L pages. Any lane that reads this deck must render + read
visually — the `faaliyet_franchise` "stray prose numbers" failure mode is exactly what
a text-anchored extractor would produce here. This is a rendering job, not a parsing job.

## Verified tie-outs (exact, not approximate)

Our amounts are **thousand TL**; the deck is **TL mn**.

| Deck item | Deck | Our row | Verdict |
|---|---|---|---|
| NII (p26) | 43,086 | `profit_loss` III. = 43,086,086 | exact |
| Net fees (p26) | 32,402 | `profit_loss` IV. = 32,401,773 | exact |
| HR opex (p13) | 14,804 | `profit_loss` XI. = 14,804,092 | exact |
| Non-HR opex (p13) | 22,041 | `profit_loss` XII. = 22,041,154 | exact |
| Income before tax (p26) | 26,855 | `profit_loss` XVII. = 26,854,593 | exact |
| Tax (p26) | 7,712 | `profit_loss` XVIII. = 7,711,883 | exact |
| **Net income (p6/p26)** | **19,143** | `profit_loss` XIX. = 19,142,710 | exact |
| **Total assets (p25)** | **3,643,975** | Σ assets romans = 3,643,975,000 | exact |
| Deposits (p25) | 2,318,398 | `balance_sheet` liab I. = 2,318,398,125 | exact |
| Equity (p25) | 302,575 | `balance_sheet` liab XVI. = 302,574,628 | exact |
| Repo (p25) | 263,624 | `balance_sheet` liab III. = 263,623,701 | exact |
| CAR (p15/p24) | 16.1 | `capital` cons = 16.12 | exact |
| Tier-1 (p15) | 13.1 | `capital` cons = 13.10 | exact |
| CET-1 (p15) | 11.0 | `capital` cons = 11.04 | exact |
| Stage-2 coverage (p14) | 10.4 | `stages` cons = 10.41% | exact |
| Stage-3 / gross (p24) | 3.5 | `stages` cons = 3.49% | exact |
| **New NPL (p14)** | **17.0bn** | Σ`npl_movement.additions` III+IV+V = 17,047,009 | exact |
| **Collections (p14)** | **5.3bn** | Σ`collections` = 5,312,635 | exact |
| **Write-off & NPL sale (p14)** | **5.3bn** | Σ(`write_offs`+`sold`) = 5,348,822 | exact |
| Net new NPL (p14) | 11.7bn | 17.05 − 5.31 = 11.73 | exact |

`bank_audit_npl_movement` reproduces the whole **New NPL Evolution** chart (p14) — the
one chart on the deck we can rebuild bar-for-bar with no assumptions.

## The blocker: swap cost is a plug we do not hold

The deck's two most-repeated metrics — **Swap adj. NII** and **Swap adj. NIM** — are
**not reproducible**, and the reason is precise rather than a coverage gap.

Akbank moves swap cost out of trading and into NII:

```
our  P&L VI. (net trading)  = −3,476,909
deck Net Trading Gain       = +12,447  →  −3,476,909 + 15,924 = 12,447  ✓
deck NII incl. swap cost    =  27,162  →  43,086 − 15,924     = 27,162  ✓
```

Swap cost (**15,924**) reconciles both lines exactly — so the reclassification is
confirmed, but the figure is **management-defined and appears on no BRSA line**. Our
interest-expense sublines don't carry it (2.3 = 15,641,293 is close but is not it).
Without the bank's own disclosure we cannot derive it, which means: swap-adj NII,
swap-adj NIM (3.3%), the NIM waterfall (p11) and the NIM evolution series all depend on
a number only Akbank publishes. **NIM is the deck's spine and it is the thing we cannot
compute.**

## Per-page verdict

### Reproducible now

- **p6** Revenue/net income bars, ROE, ROA — from `profit_loss` (NII/fees exact; the
  swap-adj split of revenue is not — see above).
- **p14** New NPL Evolution, Stage 2/3 share, Stage 1/2/3 coverage — `npl_movement` +
  `stages`.
- **p15** CAR/Tier-1/CET-1 levels and the 1Q26 solvency table — `capital`.
- **p20** Composition of assets & liabilities — `balance_sheet` romans.
- **p24** Snapshot of Results: ROE, ROA, NPL ratio, Stage 2/3 coverage, CAR/CET-1/Tier-1,
  leverage — all lanes present for 1Q25→1Q26.
- **p25** Balance Sheet Highlights — exact, whole table.
- **p26** Income Statement Highlights — exact except the NII/swap/trading three-way split.

### Partially reproducible

- **p2 Turkish Economy.** FX Deposits: we hold households-only (`TP.HPBITABLO4.4/4.5`)
  plus sector FX deposits in `weekly_series` (TL, convertible via `TP.DK.USD.A`) — near,
  not the printed series. CBRT Net Foreign Assets *excl. swap*: we hold `TP.AB.A02` and
  `TP.BL054`/`TP.BL122`, but the swap stock isn't held, so "excl. swap" can't be
  stripped. Capital Inflows (equities/bonds/swap cumulative since Nov'23): **not held**.
- **p7/p9 Market shares** (15.6% TL loans, 14.9% deposits, 12.7% FX loans…). Basis is
  *bank-only BRSA weekly, among private banks*. Our `weekly_series` is sector/group-level
  (`bank_type_code`), **not per-bank**; our per-bank data is the quarterly audit lane.
  So: computable **quarterly over our 38-bank audited universe** via `market-share.ts`,
  **never** on the deck's weekly private-bank basis. Different number, not a worse one.
- **p13 Opex.** HR vs non-HR: exact (XI./XII.). The 6-way donut (Marketing/Regulatory/
  IT/Depr.) lives in a footnote we don't extract → no.
- **p15 Sensitivities.** The printed bps figures are bank-computed. We hold
  `fx_position` + `repricing`, so an *analogous* NII/CAR sensitivity is derivable
  (`/market-risk` already does this) — but it won't equal Akbank's number.
- **p23 Subsidiaries.** `kap_ownership` §7 gives the subsidiary list; the market shares
  (leasing 12.4%, pension 19.3% AuM) need FKB/EGM data we don't hold.

### Not reproducible

- **p8 Securities breakdown** (TL/FX split, CPI/Fixed/Floating mix, CPI-linker stock
  TL 237bn, 42% corp-bond yield). BS gives securities totals, not the composition.
- **p10 Wholesale funding maturity profile** — bank-only MIS, instrument-level.
- **p11 NIM waterfall & evolution** — swap cost (above).
- **p12 Fee breakdown** (Payment Systems 64% etc.) — footnote-level, not extracted.
- **p14 Restructured share** (3.8%) — separate footnote, not extracted.
- **p19 Business Loan Sectoral Breakdown** — `loans_by_sector` is **annual-only**:
  AKBNK has 2022Q4/2023Q4/2024Q4/2025Q4 and **0 rows for 2026Q1**. The FY view is
  reproducible; the deck's 1Q26 cut is not (the interim report has no such table).
- **p16 ESG / p27 ratings / p22 digital customers** (15.5mn active, 88% penetration) —
  Akbank MIS and third-party ratings; `tbb_digital_stats` is sector-level, not per-bank.
- **p17 Guidance** — forward-looking by definition. The *Results* column reproduces;
  the *Guidance* column is Akbank's.

## Two definitional traps

1. **ROE convention.** Deck ROE 25.3% = annualized quarterly ÷ average equity. Ours
   (`heatmap.ts`, [[reference_roe_ttm_definition]]) = **TTM ÷ 5-pt average equity**.
   Both are right; they are different numbers. Any comparison must state which.
2. **Stage-3 coverage basis.** Deck prints 65.6, which matches our **unconsolidated**
   65.56% — our **consolidated** is 65.37 (→65.4). Stage-2 coverage (10.4) matches both.
   So p14's coverage table is likely bank-only/MIS, not the consolidated statement the
   rest of the deck uses. Don't assume the deck is consolidated throughout.
3. **FX LCR.** Deck's "1Q Avg. FX LCR 187%" is a *quarterly average*; our `lcr_fc` =
   202.06 (cons) / 194.73 (unco) is the reported §4 figure. Different basis, don't tie.

## Data-quality note surfaced by this check

**AKBNK 2026Q1 `item_name` is empty on most P&L and BS rows.** Amounts and `hierarchy`
are correct and complete (everything above ties exactly), but the labels are blank —
the same partition already known to `pl_bottomline` as the empty-label case
([[project_bs_pl_validator_audit]]). Consequence: any consumer reconstructing this deck
must key off `hierarchy` / `bank_audit_pl_roles`, never off `item_name`, and never off a
hardcoded ordinal ([[project_heatmap_hardcoded_romans]]).

## If we wanted to close the gap

Ranked by value ÷ effort:

1. **Nothing.** The statutory spine already reproduces; the rest is Akbank's own
   framing. Reproducing a bank's IR deck is not obviously a goal — our edge is the
   38-bank cross-section, not one bank's slide.
2. **Securities composition** (p8) — plausible from the securities footnote; would
   serve `/market-risk` beyond this deck.
3. **Fee & opex breakdown** (p12/p13) — footnote extraction, fleet-wide value.
4. **Swap cost** — would unlock swap-adj NII/NIM fleet-wide, and it is the single
   metric Turkish bank analysts actually quote. Disclosed in the notes, not the face
   of the P&L. Highest analytical value, highest extraction risk.

Do **not** build a deck-scraper: IR decks are image-only PowerPoint exports with
per-bank layouts and no stable anchors — the exact conditions that produced the
~75%-wrong `faaliyet_franchise` extractor ([[project_franchise_extractor_broken]]).
