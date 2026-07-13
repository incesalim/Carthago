# /regulation v3 — "The rulebook": compiled, synthesized, absent

**Date:** 2026-07-13 · **Status:** PROPOSED (artefact made, not built) ·
**Artefact:** [claude.ai](https://claude.ai/code/artifact/16dc5276-cae1-4699-b665-8bbeb787d0c8) ·
[html](../design/mockups/2026-07-13-regulation-tab-rulebook-v3.html)
**Supersedes:** [v2 "Where the rules bite"](regulation-tab-redesign-v2-2026-07-13.md) — which
drifted into another tab's job.

---

## Two corrections

### 1. v2 was the Liquidity tab wearing a Regulation badge

v2's spine was ₺4.06trn of reserves, the policy-transmission wedge (37% → 49% → 62%) and the
KKM unwind (₺3.41trn → 0). Every one of those is **good analysis** and **not this page's job**.
They are *balance-sheet consequences*, and they belong on **Liquidity**, **Rates** and
**Deposits** — each linking back to the rule that caused it.

**`/regulation` answers one question: what are the rules?** A regulation page that re-analyses
the balance sheet is a worse copy of the tab next door.

The visuals survive, **demoted**: two marks that illustrate an *instrument* rather than the
sector — the corridor's **path** (a policy rate is not a level, it is 25 changes deep) and
**what the reserve rule actually holds** (the effective ratio; the lira leg was built from
**0.02%** in Jan-2022 to 6.8% now). They sit beside the rules, not above them.

### 2. Dissolving the snapshot was wrong, and I should not have done it

On 2026-07-12 I argued the Kimi snapshot duplicated the compiled band and dissolved it into a
"residue" list. That reasoning was wrong on the facts I had *already established*:

- the compiled band carries **six parameters** — the ones a parser can read out of an
  instrument;
- we had already proved that **9 rule changes in force have no machine-readable numbers at
  all** (TCMB ships most macropru releases without a parseable table; BDDK announces several
  rules with no body text).

The overlap between the snapshot and the band was never the point. **The coverage was.**

## The LLM is not a shortcut here — it is the only tool that works

The proof is the credit growth caps. The 23 May release is the one we hold **342 characters**
of: heading, then footer, no table. The parser sees nothing. The model reads it:

> - an **8-week growth limit of 3%** for general-purpose and vehicle loans (down from 4%)
> - overdraft limits to **1%** (from 2%)
> - commercial loans (ex-overdraft) to **4.5%** (from 5%)
> - **FX loans to 0.5%** (from 1%)
>
> — `regulation_briefings`, category *Loan Growth Caps*, sourced to `tcmb:ANO2026-24` / `ANO2026-14`

Those are binding constraints on every bank in Türkiye, and without the model they are
**invisible to this site**. That is not a convenience; it is the difference between covering
the regime and not.

## The three tiers, and the page says which is which

This is the design. Every claim on the page belongs to exactly one tier, and wears its label.

| Tier | What it is | The rule |
|---|---|---|
| **Compiled** | The six parameters parsed out of the instruments and **reconciled against EVDS** (policy 37% agrees with `TP.PY.P02.1H`) | **No model ever sets a figure here.** A disagreement between sources raises a flag rather than picking a winner |
| **Synthesized** | The regulatory snapshot — the rules in force, in the sections of a BBVA-style report, written by **moonshot-v1-128k** from 88 instruments over a 330-day window | **Every bullet carries its instrument.** One click reaches the regulator's own words. The model may write a sentence; it may never set a figure in the band |
| **Absent** | 2 of the 7 sections — **Regulations for CARs**, **Regulations on Credit Cards** | **Named, never invented** (see below) |

### The empty sections are the trust

`scripts/summarize_regulations.py` holds `UNSOURCED_CATEGORIES = {"Regulations for CARs",
"Regulations on Credit Cards"}`. Those rules live in **BDDK Tebliğ / Resmî Gazete**, which we do
not ingest. Forced to write them anyway, the model **leaked reserve-requirement rules into the
CAR section and fabricated credit-card tier tables** — so the summarizer skips them.

The v3 page **shows the empty sections**, with the reason. An empty section a reader can see
beats a plausible one they cannot check — and it is the strongest available evidence that the
sections which *are* filled were sourced.

(Note: that missing Resmî Gazete / Tebliğ source is the **same** gap as the macropru-table
blocker. **One source closes both.** See `docs/regulation_followups.md`.)

## What I checked and did NOT draw

With the caps finally readable, the tempting chart is **actual loan growth vs the 8-week cap**.
**It would be wrong.**

The caps apply to a **restricted base** — export, investment, agriculture, tradesmen, KOSGEB and
CGF loans are exempt (the model's own bullets say so) — and they bind **bank by bank**. Our
`weekly_series` is the **whole book**. Drawn naively, the sector "breaches":

| | Cap (8wk) | Actual 8-week growth | "Over cap" |
|---|---|---|---|
| General-purpose (İhtiyaç), TL | 3.0% | 2.1% – 9.9% | **44 of 49 weeks** |
| Commercial (Ticari), TL | 4.5% | 4.1% – 7.2% | **42 of 49 weeks** |
| Commercial, FX | 0.5% | 1.8% – 6.2% | **49 of 49 weeks** |

That is an artefact of the base, not a finding — and it is exactly the class of confident,
well-formatted wrong answer this project keeps tripping over. **The caps are stated, not
charted**, until the exempt base can be isolated. The page says so, in the reader's terms.

## Structure

1. **The tier legend** — compiled / synthesized / absent, stated once at the top.
2. **The parameters** `Compiled` — the six-cell band, reconciled. Followed by the honest line:
   *six numbers is not a regime*.
3. **The regulatory snapshot** `Synthesized` — **the centrepiece.** Five live sections, every
   bullet source-cited; two sections visibly empty.
4. **Two rules, drawn** — the corridor's path; what the reserve rule actually holds.
5. **Why there is no "growth vs the cap" chart** — the caveat above, in the reader's terms.
6. **What binds next** · **Where Türkiye's newest banks appear first** · **Consequences live
   elsewhere** (links out to Liquidity / Rates / Deposits).
7. **The archive** + drawer, keyed on the decision date.

## Build cost

Nothing new is needed. `regulation_briefings` is already generated weekly by the Sunday cron;
`latestRegulationBriefing()` already exists in `app/lib/news.ts`; the compiled band, archive,
licensing register and reconciliation all shipped on 2026-07-13. **v3 is a re-composition of
parts we already have**, plus rendering the absent sections instead of hiding them.
