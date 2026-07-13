# /regulation v4 — "What changed": the changelog, and the model that gets checked

**Date:** 2026-07-13 · **Status: SHIPPED 2026-07-13** (`7c1b329`) as the v5 (buildable) composition ·
> **Why:** v4's artefact argued its own design *inside the page* — a block headed *“The model got
> this wrong, and the citation caught it”*, and a paragraph explaining that *“a model you can check
> is worth more than a parser that sees nothing.”* **None of that would ship.** In the built page a
> model/parser conflict is not an essay, it is a **computed chip** on the offending row
> (`✗ instrument: TL loans to SMEs, 5% → 4.5%`), and the caps table is simply authoritative.
> **v5 is the same design with the commentary removed** — the page exactly as it would be built.
> The reasoning lives here, in the knowledge doc, which is where it belongs.
>
**Artefact:** [claude.ai](https://claude.ai/code/artifact/a706157a-a633-4984-8e6d-6186a2175164) ·
[html](../design/mockups/2026-07-13-regulation-tab-changelog-v4.html)
**Supersedes:** [v3 — the rulebook](regulation-tab-redesign-v3-2026-07-13.md)

---

## What v3 got wrong

v3 got the *content* right and the *question* wrong. It presented the regime as a **taxonomy** —
five BBVA sections, 28 bullets of equal weight, a rule from January sitting beside one from July.

Nobody opens a regulation page to browse a taxonomy. They open it asking:

> **What changed since I last looked?**

v3 could not answer that. It also opened with a **tier legend** — three chips explaining our
epistemology (*compiled / synthesized / absent*) before the reader saw any content. That is us
talking about ourselves, again.

## v4: the changelog is the spine

The briefing's bullets carry `source_ids`. Those resolve to instruments, and instruments have
**dates** — **28 of 28 resolve, none orphaned**. So the *same LLM content*, re-sorted by **when
the rule changed**, becomes a real changelog: newest first, grouped by month, every entry dated,
category-tagged, and linked to the instrument that made it.

The taxonomy survives **below**, as a reference layer — which is what a taxonomy is for.

The tier legend is gone. Provenance is **shown, not preached**: every claim carries its source
link, the ✓/✗ marks carry the cross-checks, the empty sections speak for themselves, and the
compiled/synthesized/absent split is stated once, in the colophon.

## The finding: the model was wrong, and the citation caught it

This is the important part, and it happened **because I clicked the citation the model supplied.**

The snapshot's *Loan Growth Caps* bullets cite `tcmb:ANO2026-24` — the **18 Jun MPC Summary**,
which we hold in full (8,000 chars). The instrument says:

> growth limits imposed for eight-week periods were **reduced from 4% to 3%** in general purpose
> and vehicle loans extended to consumers, **from 2% to 1%** in overdraft account limits extended
> to consumers, **from 5% to 4.5% in Turkish lira loans extended to SMEs**, and **from 3% to 2% in
> Turkish lira loans extended to non-SME enterprises.**

The model reported:

> "The 8-week growth limit for **commercial loans (excluding overdraft)** has been adjusted to
> 4.5%, down from 5%."

Two errors:

1. **It relabelled the category.** The instrument says *TL loans to **SMEs***. "Commercial loans
   excluding overdraft" is a different, wider set.
2. **It dropped a cap entirely.** *TL loans to **non-SMEs**, 3% → 2%* — in the instrument, absent
   from the snapshot.

**This is not an argument against the model. It is the argument for making it cite.** A wrong claim
that links to its source is one click from being caught. A wrong claim with no source is just
content.

## Which overturns my own blocker

I had been asserting — in the shipped page, in three design docs and in a commit message — that
the loan-growth caps are **not machine-readable**: the macroprudential release ships no table and
we hold **342 characters** of it, so *"only the model can read them."*

That was **wrong, and I should have checked instead of repeating it.** The caps are recapped in
the **MPC Summary**, in a regular sentence, in a document we already hold in full. One regex gets
all four:

| 8-week growth limit | Was | Now |
|---|---|---|
| General-purpose & vehicle | 4% | **3%** |
| Consumer overdraft | 2% | **1%** |
| TL loans to SMEs | 5% | **4.5%** |
| TL loans to non-SMEs | 3% | **2%** |

So the caps move from the **synthesized** tier to the **compiled** tier — where the model can be
checked against them. Which is exactly how the error above surfaced.

**Lesson, and it is the same one as the `[^.]` regex and the `İş Bankası` substring: I asserted a
limitation without testing it, and the assertion propagated into shipped copy.** The tell was
available the whole time — an 8,000-character document classified as "not regulation".

## The architecture

| Tier | What | The rule |
|---|---|---|
| **Compiled** | Corridor (reconciled against EVDS), FX reserve ratios, **and now the four loan-growth caps** | No model sets a figure here |
| **Synthesized** | The changelog — 28 dated rule changes, moonshot-v1-128k over 88 instruments | **Every claim links to its instrument.** Where a figure is also compiled, the parser checks it: **✓ 5 of 28 agree**, **✗ 1 does not** |
| **Absent** | CARs, Credit Cards — no source in any feed we scrape | Shown empty, with the reason. Forced to write them, the model **fabricated credit-card tier tables** |

**A model you can check is worth more than a parser that sees nothing.** That sentence is the
page's thesis, and the caps are its proof — in both directions.

## Still not drawn

**Growth vs the cap.** The caps exempt export, investment, agriculture, tradesmen, KOSGEB and CGF
lending and bind **bank by bank**; `weekly_series` is the **whole book**. Drawn naively the sector
"breaches" every cap in **42 of 49 weeks** — an artefact of the base, not a finding. Stated, not
charted.

## Build cost

Unchanged from v3: **no new infrastructure.** The changelog is the briefing's own bullets joined
to `news_items` on `source_ids`. The caps parser is one regex over a body we already store. The
cross-check is a comparison between two things the page already holds.

## Follow-up this creates

- **Parse the caps** (`app/lib/regulation.ts`): regex the MPC Summary's growth-limit sentence;
  add them to the compiled band; ship the ✓/✗ cross-check against the briefing.
- **Reclassify the MPC Summary.** `classifyInstrument` calls it `other` ("comms about a decision
  already made"). It is 8,000 characters and contains binding parameters no other document
  exposes. That classification is what hid the caps for three design iterations.

---

## Shipped

`7c1b329`, live at https://carthago.app/regulation. Verified in the browser, not by a 200.

**Built:** `parseGrowthCaps` / `deriveGrowthCaps` / `buildChangelog` / `reserveRatioSeries` in
`app/lib/regulation.ts`; `ReserveRatio.tsx`; `page.tsx` rebuilt to the v5 composition. 205 tests.

**Live behaviour, confirmed:**

- all four caps parsed from the MPC summary (3% / 1% / 4.5% / 2%);
- the changelog reads **✓ 5 match the parameter parsed from the instrument · ✗ 1 conflicts**;
- the conflict renders on the offending row, exactly as designed:
  *"The 8-week growth limit for **commercial loans (excluding overdraft)** has been adjusted to
  4.5%, down from 5%."* → `✗ instrument: TL loans to SMEs, 5% → 4.5%`;
- the MPC Summary now classifies as a **rule** and appears as one in the archive;
- capital-adequacy and credit-card sections render **empty, with their reason**.

**The same trap, a second time.** `parseGrowthCaps` was first written with `[^.]` to "stay in the
sentence" — and a cap of **4.5%** contains a full stop, so it returned **two** caps instead of four.
Identical to the bug that ate a third of the policy-rate path. Both are now pinned by tests. The
lesson is not "avoid `[^.]`"; it is that **a parser that silently returns fewer rows than it should
looks exactly like a parser that works.** Compare the count you classified with the count you
parsed, every time.

**Dropped in this ship:** the decision-lag comb chart and the 30-day ✓/✕ list — both were about the
pipeline, not the regime.
