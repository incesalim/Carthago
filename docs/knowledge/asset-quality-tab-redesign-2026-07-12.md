# /asset-quality redesign — rationale + mockup

**Date:** 2026-07-12 (v2 corrected 2026-07-13) · **Status:** PROPOSED — build v2, not v1

> ## ⚠ Correction (2026-07-12, same day): the original headline was wrong
>
> The first version of this doc and the mockup led with *"the ratio is the
> denominator's story — the growing loan book hides 1.06pp of NPL ratio."*
> **That claim is overstated by ~10× and must not be built.**
>
> An NPL ratio is `N / L`. Deflate both legs by CPI and it is **unchanged** — a ratio
> is deflator-invariant. Inflation therefore does *not* mechanically flatter it. What
> dilutes it is the denominator growing in **real** terms, and that was only **+3.3%**.
>
> | Counterfactual | Ratio would be | "Hidden" |
> | --- | --- | --- |
> | Loan book frozen in **nominal** terms *(what the mockup used)* | 3.97% | 1.07pp |
> | Loan book merely keeps pace with CPI (**0% real growth**) | 3.01% | **0.11pp** |
>
> A nominally-frozen book in a 32% inflation economy is not a baseline, it is a
> fiction. The honest dilution is **~0.1pp**. Worse, the additive split is
> order-dependent (Laspeyres −1.07pp / Paasche −0.59pp / Shapley −0.83pp) and the
> mockup happened to use the convention most flattering to its own argument.
>
> There *is* a real inflation bias in Turkish NPL ratios — the numerator is **stale**
> (a loan that defaulted two years ago sits at its origination principal) while the
> denominator **refreshes** at today's prices. Sizing it needs origination-vintage
> data we do not have. **Do not put a number on it.**
>
> **The corrected thesis is the iceberg** (§2 below), which is stronger anyway and
> needs no counterfactual: what the ratio prints is Stage 3 at 3.1%; loans actually
> classified as deteriorated are 12.3% — **4.0×** — and the watchlist carries 9.8%
> cover against Stage 3's 62.3%. The pipeline behind it is still filling.
>
> **The mockup has been rebuilt (v2, 2026-07-13)** and now leads with the waterline:
> the whole book to scale (Stage 1 / 2 / 3), then the problem book magnified with
> provisions held drawn inside each stage. The two-ratio chart and the +1.76 / −1.06
> strip are **gone**. Loan-growth dilution survives only as a footnote at its honest
> size (~0.1pp), next to a footnote on the two ratio bases.
**Artefact:** [`docs/design/mockups/2026-07-12-asset-quality-tab.html`](../design/mockups/2026-07-12-asset-quality-tab.html) (+ desktop/mobile PNGs)
**System:** The Desk ([web/DESIGN.md](../../web/DESIGN.md)) — a re-*think*, not a re-skin.

Every figure below is real, computed from D1 (BDDK weekly + monthly bulletin to
W/E 2026-07-03, BRSA audited §7 TFRS-9 to 2026Q1 n=37, TÜİK CPI).

---

## The defect

`/asset-quality` leads with **NPL ratio 2.69%** — a calm number. Three things in the
page's own data say it is not calm, and the page never composes any of them.

### 1. The ratio is the denominator's story

The bad-loan **stock** grew **+79.8% y/y** (**+34.9% in real terms**) while the printed
ratio moved only **+0.70pp**. The ratio barely moved because its denominator is
inflating:

| | |
| --- | --- |
| NPL ratio, 52w ago | 2.21% |
| Bad loans alone would have taken it to | **3.97%** (+1.76pp) |
| A loan book growing 36.6% took back | **−1.06pp** |
| Printed today | **2.90%** (weekly implied; 2.69% published) |

**The growing book hides 1.06pp of NPL ratio.** And that loan growth is not real
credit — [/credit](credit-tab-redesign-2026-07-12.md) showed the book *shrank 2.1%* in
real, constant-FX terms. Like-for-like (both CPI-deflated): bad loans **+34.9%** real
against a loan book **+3.3%** real.

The page already half-knows this — it carries a "Gross NPL stock y/y" vital whose
caption reads *"fast off a low base — /credit grows the denominator"*. That is the
finding, demoted to a caption, on a vital with no sparkline.

### 2. What the ratio prints is the tip

TFRS-9 staging, audited, 2026Q1 (n=37):

| Stage | Share of gross loans | Book | Covered |
| --- | --- | --- | --- |
| Stage 1 (performing) | 87.7% | — | — |
| Stage 2 (**the watchlist**) | **9.2%** | ₺2,411bn | **9.8%** |
| Stage 3 (the NPL — what the ratio prints) | 3.1% | ₺817bn | 62.3% |

Problem loans (S2+S3) are **12.3% — 4.0× the headline NPL**. The page draws Stage 2 and
Stage 3 as two lines on one chart and never says this.

### 3. A plausible story that is FALSE — and worth killing

The obvious suspicion in Turkish banking is that the ratio is *managed down* by
write-offs and NPL sales. **It is not.** In 2025, exits were **77% collections**;
write-offs + sales were only ~21% of exits. Meanwhile formation was **₺673bn — 2.2×**
2024's ₺304bn — with **net formation +₺404bn**.

So the deterioration is genuine, and the ratio is diluted by loan growth, not by
disposals. The mockup states this explicitly, because a reader who knows the market
will otherwise assume the wrong mechanism.

---

## The redesign

1. **New signature — "The ratio is the denominator's story."** One chart, one axis, two
   lines: the printed NPL ratio, and the **constant-book ratio**
   (`npl_stock(t) ÷ loans(t−52w)` — today's bad loans against last year's book). The
   shaded gap between them *is* the dilution. A numeric strip states the split:
   bad loans **+1.76pp**, the bigger book **−1.06pp**, net **+0.70pp**.
2. **The stress ladder** (new): the loan book as one bar — Stage 1 / 2 / 3 — with each
   stage's book and coverage beside it. Makes "the tip vs the watchlist" and the
   coverage asymmetry (9.8% vs 62.3%) visible at a glance.
3. **Formation vs exits** promoted out of the chart bin, with the caption that kills the
   disposal theory (77% collections).
4. **Attribution**: where the ₺0.34trn of new bad loans came from — commercial 60.9%
   (of which **SME 42.8%**), cards 21.8%, GPL 17.1%, housing 0.1%, auto 0.1%. Sums to
   100%. SME is drawn *inside* commercial: it carries **61% of commercial bad loans on
   36% of its loans**.
5. **Flags** print their rules; **Movers** show each segment's NPL ratio Δ over 52w.
6. **Depth reordered by question** — *Is the ratio telling the truth? → What is coming?
   → Where is it? → Who holds it?* All existing charts carried over, none removed.
   (This tab is also one of the five still on the pre-contract evidence layer — boxed
   `Stat` cards and boxed `Takeaway` — so the conversion is due anyway.)

## Traps found while building this (read before implementing)

- **The `takipteki_alacaklar` item_ids do NOT mirror `krediler`.** `2.0.4` is **SME**
  (not housing); `2.0.6` is **specific provisions** (not GPL); `2.0.11` is **auto** (not
  SME). Mapping them positionally produces a beautiful, wrong page — it gave auto an
  NPL ratio of 1068% and segment shares summing to 204%. The correct map:
  housing `2.0.10`, auto `2.0.11`, GPL `2.0.12`, retail cards `2.0.3`, commercial
  `2.0.5`, SME (memo, ⊂ commercial) `2.0.4`. Those five disjoint segments reconcile to
  `2.0.1` at **100.00%** — use that as the gate.
- **Do not quote "if Stage 2 were covered like Stage 3" as a gap.** That arithmetic
  (₺1,265bn) is alarmist: Stage 2 is *not* impaired, so lower cover is expected, not a
  shortfall. The honest sizing device is the page's existing migration scenario —
  5/10/20% of Stage 2 migrating costs +₺63/127/253bn.
- **Do not colour the denominator effect green.** It lowers the ratio, but that is
  dilution, not improvement; green would smuggle in the exact misreading the page
  exists to prevent. Neutral ink.
- **Never mix the two NPL-ratio bases in one argument.** The published ratio
  (`financial_ratios` t15, monthly, 2.69% @ May) and the weekly-implied ratio
  (`takipteki 2.0.1 ÷ krediler 1.0.1`, 2.90% @ 3 Jul) differ by a **stable ~0.10pp**
  (0.06–0.11 across the last 8 month-ends) — it is definitional, not noise. The first
  mockup printed 2.69% in the lede and 2.90% in its chart. Pick ONE basis per
  arithmetic; show the other as context, labelled.
- **"4× the headline" must be 12.3% ÷ 3.1%, both audited** — S2+S3 over S3 from the
  same TFRS-9 source. Dividing by the *published* 2.69% mixes sources and inflates the
  multiple to 4.6×.
- **Do not compare CPI-deflated NPL growth against /credit's real constant-FX loan
  figure.** The NPL stock was never FX-adjusted, so that is apples-to-oranges. Compare
  like with like (both CPI-deflated), and cross-reference /credit separately.

## If built

The bridge-style decomposition, ladder and attribution are new components; every chart
and the migration scenarios reuse existing wiring (`ratioNpl`, `ratioCoverage`,
`weeklySeries`, `sectorStageShares`, `nplFormationAnnual`,
`provisionMigrationScenarios`). The genuinely new series is the **constant-book ratio** —
two series the page already fetches, divided across a 52-week offset. No new
extraction, no schema change.

Related: [[project_desk_redesign]], [[reference_design_system]],
[[feedback_rationale_before_narrative]].
