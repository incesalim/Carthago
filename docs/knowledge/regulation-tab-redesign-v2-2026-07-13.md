# /regulation, second redesign — "Where the rules bite"

**Date:** 2026-07-13 · **Status:** PROPOSED (artefact made, not built) ·
**Supersedes the signature of:** [the Rulebook](regulation-tab-redesign-2026-07-12.md)
(shipped this morning — its parsers, archive and licensing register all survive)

---

## Why redesign a page we shipped six hours ago

The Rulebook fixed the right defect: the page **counted announcements** instead of
**stating the regime**. It now states the regime — policy corridor 37 / 40 / 35.5,
FX-deposit reserve ratios 32% and 28%, binding 17 Jul.

And then it stops. It tells you the reserve requirement is **32%** and says nothing
about what 32% *does*.

That is a rulebook, and a rulebook is a thing you can get from the regulator's own
website. It floats free of the rest of the site. **Carthago holds the sector's
balance sheet** — weekly, back to 2019 — and the regulation page never touches it.
The one question a reader actually has, an analyst most of all, is not *"what is the
rule?"* but:

> **Is it biting, and what is it costing?**

That question is answerable from data we already hold, and answering it makes
`/regulation` the only page on the site that connects the regulator's instruments to
the sector's balance sheet. That is Carthago's unique asset, and it is currently
unused on the page that most needs it.

## The premise

**A rule is a number on the balance sheet.** Every instrument on this page gets drawn
against the thing it moves.

### 1. The reserve requirement is ₺4.06 trillion

The page says *32%*. Here is what 32% means:

| | Reserves at the CBRT | Deposit base | Effective ratio |
|---|---|---|---|
| **Total** | **₺4.06trn** | ₺29.87trn | **13.6%** |
| FX | ₺2.80trn | ₺11.44trn | 24.5% |
| TL | ₺1.26trn | ₺18.44trn | 6.8% |

**₺4.06 trillion — 13.6% of every lira deposited in Türkiye — is not lent and not
invested. It sits at the central bank because a rule says so.** That is the reserve
requirement, and it is a bigger number than anything else on the page.

And the history is a policy story the ratio alone cannot tell: **the lira reserve
requirement was effectively zero in January 2022 (0.02%)** and is **6.8%** today,
peaking at 8.2% in May 2025. It was built from nothing in four years. The FX ratio
moved far less (21.3% → 24.5%). *The instrument the CBRT actually reached for was the
lira one.*

Source: `weekly_series` item `5.0.4` (Zorunlu Karşılıklar) ÷ `4.0.1` (Mevduat),
`bank_type_code = 10001`, weekly since 2019. **Already in D1. No new source.**

### 2. The corridor is 37%. Nobody pays 37%.

| | |
|---|---|
| Policy rate (1-week repo) | **37.00%** |
| What a saver is paid (TL deposit, 1–3m) | **48.97%** |
| What a borrower pays (consumer loan) | **61.65%** |

The policy rate is the boldest figure on the current page, and **it is not the price
of money in Türkiye**. Banks fund at ~49% — *twelve points above the policy rate* —
and lend to households at 61.7%. A page that prints "37%" as the regime and stops has
told the reader something true and deeply misleading.

The wedge is the story: **24.7pp** between the policy rate and the household borrower.
Drawn as three lines, it is immediately obvious that the corridor is a floor the
deposit market left behind.

Source: EVDS `TP.PY.P02.1H`, `TP.TRY.MT02`, `TP.KTFTUK`. **Already in D1.**

### 3. A rule built ₺3.4 trillion, then dissolved it

FX-protected deposits (*Kur Korumalı Mevduat*) were a regulatory instrument, not a
market product. The scheme:

- peaked at **₺3.41trn** (18 Aug 2023) — roughly **a fifth of the entire deposit base**;
- **₺2.58trn** Jan 2024 → **₺1.11trn** Jan 2025 → **₺7bn** Jan 2026;
- **₺0 today.**

A rule created a liability class the size of a fifth of Turkish banking, and then
unwound it to exactly nothing. **You can watch it happen, week by week** — and the
regulation page has never mentioned it.

Source: `weekly_series` item `4.0.12`. **Already in D1.**

## What I checked and did NOT build

**The credit-growth caps do not visibly bind.** The obvious fourth pairing was TCMB's
loan growth limits against actual loan growth — the classic "growth pins at the cap"
chart. The data does not support it: 4-week growth in general-purpose loans swings
between **0.3% and 4.7%** over the last 26 weeks, with no ceiling effect; commercial
runs 1.0–3.9%. Drawing a cap line through that would be inventing a finding.

It is also blocked at the source: the cap *values* are only in TCMB releases whose
tables we cannot parse (see the Rulebook's Blocker 1). So the honest position is: no
cap chart until we have a source for the caps, and no story about caps binding until
the data shows one.

## What the redesign keeps, changes, and drops

**Keeps** — everything the Rulebook built that was right:
- the regime band (corridor + reserve ratios), and the reconciliation behind it;
- the coverage caveat (rules in force we cannot show);
- the licensing register (where Türkiye's newest banks appear first);
- the archive, keyed on the decision date, with the drawer;
- the parsers (`app/lib/regulation.ts`) — untouched.

**Changes** — the signature. The band stops being the whole story and becomes the
*left-hand column* of a pairing: **the rule, and the number it moves.**

**Drops** — two things that were about *us*, not the regime:
- the **decision-lag comb chart**. That BDDK publishes 348 days late is a fact we
  discovered while building, and it earns one line in the archive's meta — not a chart
  the size of the policy path. It is a fact about *publishing*, not about *regulation*.
- the **30-day ✓/✕ list**. It exists to prove a point about the page it replaced. A
  reader wants to know what changed, not to audit our classifier.

## Automation

Every figure above is a pure function of rows already arriving weekly (`weekly_series`)
or daily (`evds_series`). **No new source, no new cron, no LLM.** The three pairings
are arithmetic on series we refresh anyway; the derived ratios (effective RRR,
transmission wedge) are two divisions and a subtraction.

## Related

- [The Rulebook](regulation-tab-redesign-2026-07-12.md) — the first redesign, shipped
  2026-07-13. Its Blocker 1 (macropru releases ship no parseable tables) is unchanged
  and is why there is no cap chart here.
- [[reference_weekly_total_heal]] — `weekly_series` TOTAL ≡ TL + FX; pair by date, never
  by row offset.
