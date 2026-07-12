# /credit redesign — rationale + mockup

**Date:** 2026-07-12 · **Status:** PROPOSED (mockup only — not built)
**Artefact:** `web/public/artifacts/credit-tab-mockup.html` (+ `credit-tab-desktop.png`, `credit-tab-mobile.png`)
**System:** The Desk ([web/DESIGN.md](../../web/DESIGN.md)) — this is a re-*think*, not a re-skin.

The mockup renders **real figures** pulled from D1 (BDDK weekly bulletin W/E 2026-07-03,
TÜİK CPI, TCMB USD/TRY), computed with the page's own conventions (date-aware 52w
pairing, annualised by `364 / elapsed_days`). Every number below is reproducible.

---

## The defect

`/credit` is already on the Desk, so the problem isn't chrome — it's **what the page
claims**. Three findings, in order of severity.

### 1. The headline number is mostly not credit

The page prints **36.6%** as its biggest figure. That number is almost entirely the lira
and the price level:

| Step | Value |
| --- | --- |
| Nominal loan growth, 52w | **36.6%** |
| − lira depreciation (FX book at base-period USD/TRY) | −7.3pp |
| = FX-adjusted | 29.3% |
| − inflation (CPI 32.1%) | −31.4pp |
| **= real, constant-FX** | **−2.1%** |

**The loan book shrank 2.1% in real, constant-currency terms — and has been negative for
10 consecutive weeks.** The page owns both adjustments already (`nominalVsReal`,
`fxAdjustedYoY`) but shows them as the 2nd and 3rd of three small charts *below* a
nominal hero, and **never composes them**. Neither twin alone reveals the contraction:
real-only says +3.4%, FX-adjusted-only says +29.3%. Only the composition says −2.1%.

### 2. Fifteen charts, and not one says where the money went

Eleven of the 15 charts under `<Depth>` are YoY-% lines. The page cannot answer the first
question a credit analyst asks: *which book grew?* The contributions decompose the
headline **exactly** (they sum to the print, which is the proof the cut is right):

| Segment | Contribution | Book | 52w |
| --- | --- | --- | --- |
| Commercial | **+26.1pp** | ₺20.07trn | 34.2% |
| — of which SME | +12.3pp | ₺7.24trn | 49.5% |
| Retail cards | +5.3pp | ₺3.29trn | 46.6% |
| Gen. purpose | +4.1pp | ₺2.54trn | 46.4% |
| Housing | +1.1pp | ₺0.80trn | 37.3% |
| Auto | −0.1pp | ₺0.04trn | −27.5% |
| **Sector** | **+36.6pp** | ₺26.75trn | 36.6% |

### 3. The page implies SME and Commercial are peers — they are not

Section 05 charts "SME vs Commercial" as two lines. **SME is a subset of commercial**
(₺7.24trn of ₺20.07trn = 36% of it), verified against the data: housing + auto + GPL +
cards + commercial reconciles to the sector total at 100.0%, and SME is not an addend.
Two lines side by side with no stated nesting invites the reader to add them.

---

## The redesign

Same carry-over contract as every Desk conversion: **nothing analytical is deleted.** All
15 existing charts survive, reordered under the question each answers.

1. **New signature — "What the headline is worth."** A bridge: nominal → strip currency →
   strip inflation → real. Nominal stays visible as the *starting* point, in grey context,
   not as the claim. Replaces the nominal-hero framing.
2. **Vitals re-pointed.** The lead vital becomes real constant-FX growth (−2.1%, red);
   nominal demotes to second. "Unsecured retail" is the growth of the **combined** cards +
   GPL book (₺5.83trn, 46.5%) — never the mean of two growth rates, which would weight a
   ₺2.5trn book like a ₺3.3trn one.
3. **New — growth attribution.** The contribution bars above, with SME drawn *inside*
   commercial (solid navy within the lighter bar) so the nesting is visible, not asserted.
   Sums are shown so the reader can check the decomposition.
4. **Flags** (the Desk's computed-rule layer, which `/credit` lacks entirely):
   - `real_fxadj(52w) < 0 for 10 consecutive weeks` → −2.1%
   - `auto_yoy < 0 for 96 consecutive weeks` → −27.5%
   - `cards_yoy > sector AND gpl_yoy > sector for 91 weeks` → 46.6% / 46.4%
5. **Depth reordered by question**, not by topic bucket: *Is the growth real?* → *Who is
   lending?* → *Where is it going?* → *SME, the engine inside commercial.*

## Open questions for the build

- The real twin pairs a **weekly** loan print with a **monthly** CPI print (latest
  available month). The current page already does this; the bridge makes the seam more
  load-bearing, so it should be labelled where it shows.
- FX book is proxied as **all-USD** (BDDK publishes TL-equivalent only) — inherited from
  the existing `fxAdjustedYoY`, and the single biggest modelling assumption in the bridge.
- Auto (₺42.7bn) is ~0.2% of the book. It earns a flag, not a chart.

## If built

Bridge + attribution + flags are new components; the vitals and all Depth charts reuse
existing wiring (`weeklySeries`, `weeklyGrowth`, `nominalVsReal`, `fxAdjustedYoY`,
`creditInsights`). The one genuinely new series is `realFxAdj` — compose the two
adjustments the page already computes; no new extraction, no new table.

Related: [[project_desk_redesign]] (briefs for other pages was the named remainder),
[[reference_design_system]], [[feedback_rationale_before_narrative]].
