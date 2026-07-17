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
confirmed, but the figure is **management-defined and appears on no BRSA line**.

### Confirmed against the source, not inferred (2026-07-17)

Checked the full AKBNK 2026Q1 consolidated report (`data/eye/`, 91pp):

- **No swap-cost line exists.** The interest-expense notes (§IV.b, p81) cover exactly
  four things — loans used, associates/subsidiaries, issued securities, and deposits by
  maturity. None isolates swap.
- **The P&L face stops one level short.** VI. Ticari Kâr/Zarar splits only into
  6.2 Türev Finansal İşlemlerden K/Z (−33,317,470) and 6.3 Kambiyo İşlemleri K/Z
  (+25,513,987). Swap cost is spread across *both*, commingled with forwards, options
  and all other FX activity. No note decomposes either by instrument.
- **The report names the concept but prints no number** — p91 guidance says
  "Net Faiz Marjı (**Swap düzeltilmiş**) ~ %4". So Akbank uses the measure in a
  regulated filing while disclosing only the *adjusted result*, never the adjustment.
- The 10 swap mentions in the report are all derivative *notional/fair-value* tables
  (pp. 9, 17, 19, 54, 60, 75) and hedge-accounting policy — balance sheet, not P&L.
- A promising `15.924.782` on p50 turned out to be a substring of `315.924.782` in the
  NSFR table. Coincidence, not the figure.

**Verdict: swap cost is published only in the IR deck / KAP disclosure, never in the
audit report.** It cannot be extracted fleet-wide from the filings, and it cannot be
derived — which puts swap-adj NII, swap-adj NIM (3.3%), the NIM waterfall (p11) and the
NIM evolution series permanently out of reach from our source. **NIM is the deck's spine
and it is the one thing we cannot compute.** The only route is per-bank IR decks, i.e.
image-only PowerPoint — see the warning at the foot of this doc.

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

## Correction: p17 Guidance IS in the audit report (found 2026-07-17)

This doc's first draft said the guidance column was "forward-looking by definition …
Akbank's". **That was wrong**, and the same check that settled the swap-cost question
found it. The report's closing section (pp. 90–91, §"Diğer Açıklamalar") prints:

1. **The complete 2026 guidance table** — all nine lines, identical to deck p17:
   TL loan growth >%30, FX loan growth >%10, ROE "Yüksek %20'li seviye", NIM (swap adj.)
   ~%4, fee growth >%30, opex growth "Düşük %30'lu", cost/income "Düşük %40'lı",
   NPL ~%3,5, net CoC ~200bp. It is a **structured table in a quarterly filing for every
   bank**, not deck-only prose.
2. **"Başlıca Finansal Oranlar"** — the bank's *own* printed ratios: ROE 25,3 / ROA 2,2 /
   CAR 16,1 / NPL 3,5 / loans-to-assets 55,6 / deposits-to-assets 63,6 / EPS 0,03683.
   So deck p24's headline ratios need **no** recomputation and no convention-matching —
   the filer states them.
3. **A Q1 evaluation paragraph** — gross profit 26.855mn, tax 7.712mn, net 19.143mn,
   CAR %16,12, assets 3.644bn, loans 2.024bn, deposits 2.319bn, NPL %3,5.

> ### ⛔ RETRACTED 2026-07-17 — the census says AKBNK-only. Do not build this.
>
> This section originally called a guidance + self-reported-ratio lane "the best
> follow-up this analysis produced", caveated as AKBNK-only-verified. **The census ran
> and killed it.** Over all 26 fetchable 2026Q1 filings: the guidance table is
> **AKBNK ONLY (1/26)**, and a ratio table exists for only **AKBNK / GARAN / DUNYAK** —
> under three different headings with three different ratio sets. §7 is a per-bank
> grab-bag, not a schema, so "guidance-vs-actual across 38 banks" would be a one-bank
> lane.
>
> Worse, the first census pass *said* 12/26 and was almost all false positives:
> `ileriye yönelik beklentiler` is **IFRS-9 ECL boilerplate**, not guidance. A marker
> that matches is not a marker that means.
>
> Full workings + what replaced this as the real finding:
> [garanti-1q26-deck-and-section7-census-2026-07-17.md](garanti-1q26-deck-and-section7-census-2026-07-17.md).
> The caveat below was the right instinct; the census is why it stayed a caveat and not
> a wasted lane.

**Caveat before anyone builds it:** verified on AKBNK only. Whether every filer prints
this section, under this heading, in this shape is **unknown** — a census across the
fleet comes first ([[feedback_understand_reports_first]]).

## Definitional traps

0. **Group's profit ≠ period net profit.** The report's own p90 summary prints net
   profit **19.152**; the deck prints **19,143**. Both are right and we hold both:
   XXV. (period net) = 19,142,710 = the deck; 25.1 (group's share) = 19,151,711 = the
   report; 25.2 (minority) = −9,001. Only 9mn TL apart here, but the fork is real and a
   consumer must choose deliberately.
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

1. ~~The guidance + self-reported-ratio table~~ — **struck 2026-07-17 by the census.**
   AKBNK-only (1/26). Would be a one-bank lane. See the retraction box above.
2. **Securities composition** (p8) — plausible from the securities footnote; would
   serve `/market-risk` beyond this deck.
3. **Fee & opex breakdown** (p12/p13) — footnote extraction, fleet-wide value.
4. ~~Swap cost~~ — **struck**, but the reasoning needs amending. It is genuinely *not in
   the filings at all*. This doc then said the only source is "image-only PowerPoint",
   which is true of AKBNK and **false of GARAN** — Garanti's deck is a real text layer
   and prints `Swap Cost -11,432` outright. So it is reachable for some filers, not
   none. Still not a lane (per-bank layouts, no stable anchors), but "impossible" was
   too strong. See the Garanti doc.

**Build nothing.** The statutory spine already reproduces, and reproducing a bank's IR
deck is not obviously a goal — our edge is the 38-bank cross-section, not one bank's
slide. Item 1 looked like the exception and the census proved it wasn't. The real output
of this pass is two documentation/coverage defects, both recorded in the Garanti doc:
`PROJECT_STATE.md:32`'s "the stats audit reports don't carry [ATM/POS/customer/card]"
is false for GARAN, and `bank_audit_profile` stores GARAN branches 794 / personnel NULL
where the filer prints 795 / 23,376.

Do **not** build a deck-scraper: IR decks are image-only PowerPoint exports with
per-bank layouts and no stable anchors — the exact conditions that produced the
~75%-wrong `faaliyet_franchise` extractor ([[project_franchise_extractor_broken]]).
