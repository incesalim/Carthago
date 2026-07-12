# /asset-quality redesign — rationale + mockup

**Date:** 2026-07-12 (v2 corrected 2026-07-13) · **Status:** **SHIPPED** as v2 (`ed39fd0`)

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

### 1. The headline is the tip of an iceberg

What the ratio prints is **Stage 3**. Loans the banks themselves classify as
deteriorated are four times as much — see §2, which is now the page's lead.

The bad-loan **stock** grew **+79.8% y/y (+34.9% real)** while the printed ratio moved
only **+0.70pp**, so the ratio is a slow summary of a fast-moving stock. But note what
this does **not** license: an NPL ratio is `N/L`, and deflating both legs by CPI leaves
it **unchanged**, so inflation does *not* flatter it. Only **real** book growth dilutes,
and that was +3.3% — worth **~0.1pp**. Lead with the stock and the pipeline, not with a
counterfactual. (See the correction banner above for the arithmetic.)

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

## The redesign (v2)

1. **Signature — the waterline.** The whole loan book to scale (Stage 1 87.7% /
   Stage 2 9.2% / Stage 3 3.1%), with a tick marking Stage 3 alone: *the ratio prints
   only this*. Beneath it the **problem book, magnified** (₺3.23trn), split Stage 2 (75%
   of it) vs Stage 3 (25%), with **provisions held drawn inside each stage** — so the
   9.8%-vs-62.3% coverage asymmetry is a picture, not a footnote. Needs no counterfactual.
2. **Vitals** re-pointed to stock / pipeline / cover: problem loans 12.3% (hero), cover on
   the problem book 23.1%, NPL stock +34.9% real, net formation +₺404bn, the published
   ratio 2.69% (16 straight rises), SME NPL 3.85%.
3. **The pipeline behind the tip** — formation vs exits as grouped bars, with the caption
   that kills the disposal theory (77% collections), beside the migration sizing.
4. **Attribution**: where the ₺0.34trn of new bad loans came from — commercial 60.9%
   (of which **SME 42.8%**), cards 21.8%, GPL 17.1%, housing 0.1%, auto 0.1%. Sums to
   100%. SME is drawn *inside* commercial: **61% of commercial bad loans on 36% of its
   lending**.
5. **Flags** print their rules; **Movers** show each segment's NPL-ratio Δ over 52w.
6. **Two footnotes carry the honesty**: why we do *not* claim inflation flatters the
   ratio, and why the published (2.69%) and weekly-implied (2.90%) ratios are never
   mixed inside one calculation.
7. **Depth reordered by question** — *What is coming? → Is the stock or the ratio moving?
   → Where is it? → Who holds it?* All existing charts carried over, none removed. (This
   tab is also one of the five still on the pre-contract evidence layer — boxed `Stat`
   cards and boxed `Takeaway` — so the conversion is due anyway.)

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

## As built (`ed39fd0`) — the implementation map

**No new series at all.** v2 needs nothing the page does not already fetch — the
constant-book ratio that v1 invented is gone with it. What is needed is *exposure*:
`credit-risk.ts` already aggregates stage amounts + ECL (only the shares are exported)
and already reads the NPL movement table (only formation-vs-exits is exported).

| Element | How |
| --- | --- |
| Header, section heads, vitals, colophon | `desk.tsx` — reuse |
| Movers (segment NPL ratio, 52w ago → now) | `desk.tsx` `Movers` — its `{prev, curr, fmt}` shape fits exactly |
| Flags with printed rules | `desk.tsx` `Flags showCleared` |
| Migration sizing (5/10/20% → +₺63/127/253bn) | `desk.tsx` `Transmission`, replacing the boxed `Stat` cards |
| Every carried-over chart | `TrendChart` / `StackedArea` / `BarByBank` — reuse |
| **Attribution bars (SME nested in commercial)** | **promote** `app/credit/Attribution.tsx` → `app/components/Attribution.tsx` (2 routes now ⇒ belongs in `components/` per web/CLAUDE.md); add a `unit` prop — credit passes pp, asset-quality passes % share |
| Generic series helpers | **move** `toMap` / `baseFor` / `deflate` / `sumSeries` / `contributions` / `trailingRun` out of `app/lib/credit.ts` → `app/lib/series.ts` (they are not credit-specific; `contributions()` already does the disjoint-reconciliation job) |
| **The waterline** | **new**, route-local `app/asset-quality/Waterline.tsx` — hairlines and type, no Recharts |
| **Formation vs exits** | **new**, route-local `app/asset-quality/FormationBars.tsx` — there is *no* grouped-bar component in the library (`BarByBank` is horizontal-by-bank; `TimeSeriesChart` has no bars), and the page currently draws four annual flows as *lines*, which is the wrong mark |

Data in a new `app/lib/asset-quality.ts` (pure, mirroring `credit.ts`), with
`asset-quality.test.ts` gating the three things that would silently rot:

1. **Segment reconciliation == 100%** — the guard against the item-ID trap below.
2. **Deflator invariance** — assert `ratio(N, L) == ratio(N/π, L/π)`. That test *is* the
   documentation for why we do not claim an inflation dilution; it stops a future
   session reintroducing the v1 mistake.
3. **`exits == collections + write_offs + sold`**, and the disposal share.

Also rewrite `assetQualityInsights()` in `insights.ts` — it currently leads with the
ratio.

Related: [[project_desk_redesign]], [[reference_design_system]],
[[feedback_rationale_before_narrative]].
