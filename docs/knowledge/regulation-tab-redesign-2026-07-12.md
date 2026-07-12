# /regulation, rethought — "The Rulebook"

**Date:** 2026-07-12 · **Status:** PROPOSED (mockup made, not built) ·
**Artefact:** [`docs/design/mockups/2026-07-12-regulation-tab-rulebook.html`](../design/mockups/2026-07-12-regulation-tab-rulebook.html)

Supersedes the earlier `2026-07-12-regulations-tab.html` mockup — see
[What the first mockup got wrong](#what-the-first-mockup-got-wrong).

---

## The premise

`/regulation` is the only tab on the site that does not know what it knows.

Every other tab computes something. This one **counts**. Its vitals band —
the page's signature element, the boldest thing on it — reports four facts about
the *feed*: how many items arrived, when the last one landed, which topic
appeared most, how many are stored. None of those is a fact about *regulation*.

Meanwhile the regime itself — the numbers a bank actually complies with — is
already in the database, already extracted, and printed as bullets in a boxed
card **below the fold**.

### The three defects, with evidence

**1. The headline vital is measuring noise.**

The vital reads *"30 days to the record — 7 instruments."* Anchored on the feed's
newest item (2026-07-09), those seven are:

| Date | Source | Item | Is it regulation? |
|---|---|---|---|
| Jul 9 | TCMB | Replacement of the SSL Certificate of the CBRT Website | no |
| Jul 1 | TCMB | **Press Release on Macroprudential Framework** | **yes — rule change** |
| Jun 30 | TCMB | Memorandum of Understanding with the Hong Kong Monetary Authority | no |
| Jun 22 | BDDK | *Banking and Financial Markets Journal*, issue 39 | no — a magazine |
| Jun 18 | BDDK | March 2026 Quarterly Key Indicators published | no — a data release |
| Jun 18 | TCMB | Summary of the Monetary Policy Committee Meeting | no — comms on a decision already made |
| Jun 11 | TCMB | **Press Release on Interest Rates** | **yes — rate decision** |

Two of seven are regulatory acts. The page counts a magazine and an SSL
certificate as "instruments", and the second vital — *"Latest decision — Jul 9"* —
**points at the SSL certificate.** Across the whole TCMB feed the split is 77
rule/rate items to 187 everything-else; the feed does not distinguish, so neither
does the page.

**2. The rules are readable, but never read.**

`news_items.body_text` holds **258 of 264** TCMB releases (avg 2,639 chars). The
bodies are not prose gestures — they carry the parameters, as tables. The
1 Jul 2026 release, in full:

> - The additional Turkish lira reserve requirement ratio for FX deposits…
>   currently applied at **2.5%**, has been **terminated**.
> - Reserve requirement ratios applied to foreign currency deposits… revised:
>
> | FX deposits/participation funds | Previous | New |
> |---|---|---|
> | Demand & maturities up to 1 month | 30% | **32%** |
> | With longer maturities | 26% | **28%** |
>
> The reserve requirements according to new ratios will be **maintained on July 17, 2026**.

Before value, after value, and the date it binds.

**To be exact about the defect** — `RawFeeds.tsx` ships a `MarkdownTable` renderer, so
clicking that card opens a drawer that *does* display this table. The text is therefore
**readable**. It is never **read**: the page never turns it into state, never compares
32% to the 30% it replaced, never aggregates the 48 rate decisions into a path, and
never lets any of it reach the top of the page. A reader who does not click learns
nothing. The fix is not "surface the text" — the drawer already does — it is
**parse the text into the page's own state**.

The same is true of the rate decisions. Parsing `body_text` across the feed
reconstructs **48 MPC decisions and 24 rate changes** — the entire cycle: 14% →
8.5% (Feb 2023 trough) → 50% (Mar 2024 peak) → 37% today, including the April-2025
re-hike. A complete four-and-a-half-year policy-rate series, sitting in the news
table, never drawn.

And the weekly Kimi briefing (`regulation_briefings`, moonshot-v1-128k, 88 items,
330-day window) **already extracts the regime** — policy rate 37%, O/N lending
40%, O/N borrowing 35.5%, the RRR changes, each with `source_ids`. The page has
the answer and buries it under the feed statistics.

**3. The chronology is wrong, and the page hides it.**

BDDK prints the decision date *and* the board-decision number in the title:

```
(12.03.2026 - 11428) Siemens Finansman A.Ş.'ye faaliyet izni verilmesine ilişkin Kurul Kararı
 └ decision date      └ decision no.
```

We sort by `published_at` — the *scrape* date. Across the 33 numbered decisions
we hold, the gap between decision and publication averages **309 days** and runs
to **629**. So the page presents a decision taken in June 2024 as March 2026 news.

It also shows how thin the archive is: the 33 decisions span numbers **#9238 →
#11434** — 2,197 numbers of sequence. The feed publishes a slice, and the
numbering is right there to say so. (Not every number in that range is a banking
decision — BDDK numbers leasing, factoring, e-money and payment institutions in
the same sequence — so the honest claim is "33 of the 2,197 numbers in range",
not "we are missing 2,164 bank rules".)

### The finding nobody connected

The lag list is not academic. The four worst-lagged licensing decisions are:

| Decision | Taken | Published | Lag | In our `banks` table? |
|---|---|---|---|---|
| #10945 **Enpara Bank** — operating licence | 2024-08-15 | 2026-03-06 | **568d** | yes (onboarded 2026-07-11) |
| #10997 **Colendi Bank** — operating licence | 2024-10-31 | 2026-03-06 | **491d** | yes (onboarded 2026-07-11) |
| #10980 **Ziraat Dinamik** — operating licence | 2024-10-31 | 2026-03-06 | **491d** | yes (onboarded 2026-07-11) |
| #10979 **FUPS Bank** — operating licence | 2024-10-31 | 2026-03-06 | **491d** | no — *licensed, files nothing* |

**The regulator announces the bank universe, and this page was holding the
announcement.** Enpara, Colendi and Ziraat Dinamik were licensed here; we onboarded
them in a separate exercise 16 months later ([[project_new_banks_coverage_gap]]).
The register named them **491–568 days** before we noticed.

That makes the licensing register a *lead indicator we already own*: a BDDK
"faaliyet izni" decision naming an institution absent from `banks` is a computable
flag, not a hand-written one.

**But the rule needs two states, not one.** FUPS Bank — licensed the same day as
Colendi and Ziraat Dinamik — is absent from `banks` **on purpose**: the 2026-07-11
onboarding review assessed it and excluded it because it has **filed zero reports**
(same for Adil Katılım, licensed Sep-2025, pre-launch). So a naive
`licensed ∧ ticker ∉ banks` flag would fire a false alarm on a decision we already
took. The honest rule tests filing status against the BDDK **BdrUyg** registry —
the authority on what was actually filed:

```
licensed(faaliyet_izni) ∧ ticker ∉ banks
    → filed(BdrUyg) ? coverage gap : watch item
```

*Licensed and filing* is a gap worth fixing; *licensed with no filings* is a
quarterly re-check. FUPS is the second — and it is the case that proves the rule
needs the distinction.

---

## The redesign

Keep the Desk skeleton; change what the signature element *is*. The brief stops
describing the feed and starts stating the regime.

**1. The regime in force** — the signature band. Not "how many items arrived" but
"what a bank complies with today": policy corridor (37% / 40% / 35.5%), FX-deposit
reserve requirements (32% / 28%), the terminated 2.5% add-on. Each cell carries
the current value in mono, the value it replaced, **the date it binds**
(17 Jul 2026), and the instrument that set it. The policy-rate cell gets the
48-decision path as its sparkline — drawn from `body_text`.

**2. What changed** — a change register keyed on **decision date**, not
publication date, with the publication lag drawn rather than hidden.

**3. The register knows the banks** — licensing and revocation decisions tagged to
tickers (we already have `bank_tagger.py` + `bank_aliases.json`), with a computed
flag when a licensed institution is missing from `banks`.

**4. What this feed is not** — the honesty panel, in the spirit of
`<Flags showCleared>`: 5 of the last 7 items are not regulation; 33 of 2,197
numbered decisions held; BDDK bodies present for only 162 of 603 items. A page
that prints its own gaps is more trustworthy than one that prints a tidy count.

**5. Depth** — one of the two existing sections survives; the other dissolves. See
below, because this is the decision most likely to be got wrong.

## The snapshot and the feed — do we still need them?

The page has exactly two sections today: the **weekly snapshot** (the Kimi briefing,
boxed cards) and the **raw feeds** (two 50-item card columns + a drawer). The
carry-over contract says a redesign never deletes analytical content — but it does
not say a page must state the same fact twice.

### The feed: **keep it, and give it more than it has now**

It is load-bearing, for three reasons:

- It is the **only** place the 867 instruments live. Nothing else on the site holds them.
- Its **drawer already renders the parameter tables** (`MarkdownTable` in
  `RawFeeds.tsx`). That is the single best component on the page — the one place a
  reader can see the rule in the regulator's own words. Deleting it would destroy the
  page's only primary-source view.
- Once the band cites its instruments, the archive becomes the **destination of every
  citation**: "TCMB macropru · 1 Jul" has to land somewhere, and it lands here.

What changes is its *shape*, not its existence. Two columns of news cards become one
**archive table keyed on the decision date**, carrying the decision number, the
publication lag, and an `is_instrument` mark — so the SSL certificate is visibly
*present but not counted*, rather than silently inflating a headline. Worth noting: the
current page fetches only **50 + 50 of 867**, and never says so.

### The snapshot: **do not keep it as a section**

Its two principal categories — *Monetary Policy Stance* and *Reserve Requirements* —
are, after this redesign, **literally the band at the top of the page**. Printing them
again 1,200px lower does not add evidence; it makes the page restate its own headline
in weaker form. That is the duplication defect the per-bank redesign was built to kill.

So it dissolves into the page rather than sitting in it:

- its **regime bullets become the band** (with the figures re-sourced — see below);
- its **licensing/structure output feeds the register**;
- whatever it finds that **no cell models** (payments, open banking, structure) is
  listed as a short *residue* — so the dissolve is lossless, and a category that keeps
  reappearing there is the signal to promote it to a cell of its own;
- its **provenance** (moonshot-v1-128k, 88 items, 330-day window, generated date) moves
  to the colophon, where automation honesty requires it.

### The rule that makes the dissolve safe: figures compiled, narrative written

**The band's numbers must not come from the LLM.** Kimi's bullets are currently the only
structured form of the regime — which is exactly why it is tempting to wire them
straight into the signature band. Don't: that promotes an LLM's output to the boldest
figure on the page, and one hallucinated ratio becomes the headline.

Both figure sources are regular enough to parse deterministically:

- the corridor sentence — *"keep the policy rate (the one-week repo auction rate) at 37
  percent … overnight lending rate and the overnight borrowing rate at 40 percent and
  35.5 percent"* — parses with one regex across all 48 releases;
- the reserve-requirement table is a **markdown pipe table**, and `RawFeeds.tsx` already
  contains a parser for exactly that shape (`isTableBlock` / `MarkdownTable`).

So the numbers are **compiled from `body_text`**; the briefing keeps the prose and the
coverage. This is the same split the rest of the site already honours
([[feedback_extractors_no_api]] — extraction is deterministic; the free-model lane is
for headlines, not figures) and it is what "compiled, not written" means on this page.

## What the first mockup got wrong

`2026-07-12-regulations-tab.html` (PROPOSED, never published) is marked
**SUPERSEDED**. It is a well-made page for a **different product**: a bank's
internal compliance workflow. It proposes an "Implementation calendar", per-item
"High / Medium / Low impact" ratings, and an "Action horizon" assigning owners —
*"Treasury · confirm reserve mix"*, *"Compliance · deploy onboarding controls"*,
*"Finance · submit revised capital return"*, with sign-off state.

Two problems:

- **It is entirely invented.** The page labels its own content "sample" or
  "illustrative" seven times. We hold no impact ratings, no owners, no sign-off
  state, and no effective dates as data. That violates the automation-honesty
  rule in `web/DESIGN.md` — flags print their rule, and figures are computed.
- **There is no such user.** Carthago is a sector-analysis site read by analysts.
  It has no Treasury team to assign a task to.

The one idea worth keeping is **the effective date** — and the good news is that
it *is* recoverable ("maintained on July 17, 2026" is in the body text), just not
as a column today. So the new mockup shows the binding date where the body states
it, and says plainly that extracting it fleet-wide is the extraction work this
design implies.

## What building it would require

| Need | Have it? | Work |
|---|---|---|
| Policy corridor + RRR parameters | **yes** — `regulation_briefings` bullets + `body_text` | promote to the brief; a small parser for the corridor |
| Policy-rate path (48 decisions) | **yes** — parse `body_text` | one regex pass; consider persisting to a table |
| Decision date + decision no. | **yes** — in the BDDK title | parse at ingest; store as columns |
| Rule vs. non-rule classification | partly — `news-tags.ts` keywords | add an `is_instrument` rule; the SSL/journal/MoU cases are the test set |
| Effective / binding date | **in the text, not a column** | extractor work — the honest gap |
| Licensing → ticker link | **yes** — `bank_tagger.py`, `bank_aliases.json` | tag the licensing decisions; diff against `banks` |

None of it needs a new source. The page already receives everything above.

## Related

- [[project_new_banks_coverage_gap]] — the six banks onboarded 2026-07-11; BDDK
  had licensed three of them 491–568 days before we noticed.
- [[project_free_model_lane]] — Kimi (moonshot-v1-128k) is the regulations
  summarizer and stays; this design leans on it rather than replacing it.
- `web/DESIGN.md` — the Desk; the carry-over contract and automation honesty.
</content>
