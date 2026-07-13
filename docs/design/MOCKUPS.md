# Design artefact register

Every mockup, concept and prototype made for Carthago, with what happened to it.
Design work is expensive to redo and cheap to forget — this file exists so a
future session (or a future you) can find the thinking behind a shipped page, or
reuse a concept that was made but never built.

The design system these all serve is `web/DESIGN.md` ("The Desk"). This file is
the *archive*; DESIGN.md is the *law*.

## Where artefacts live

| What | Where | Why |
|---|---|---|
| Mockup source (standalone HTML) | `docs/design/mockups/YYYY-MM-DD-<slug>.html` | Open with `file://` — no server needed |
| Screenshots | `docs/design/mockups/YYYY-MM-DD-<slug>-{desktop,mobile}.png` | So the archive reads without rendering |
| Published copy (shareable link) | claude.ai artifact — URL recorded below | Viewable on a phone, sendable to someone |
| Design critiques / audits | `docs/knowledge/*.md` (dated) | Prose analysis, not artefacts |

**Never put mockups in `web/public/`.** That directory is served by Next.js, so
anything in it ships in every production deploy and is publicly reachable on
carthago.app. Six mockups were live there by accident until 2026-07-12.

Rules for a new artefact: date-prefix the filename, publish it if it needs to be
shared, and **add a row here in the same change** — an unrecorded artefact is a
lost one.

Status vocabulary: **SHIPPED** (built, live) · **PROPOSED** (made, not built) ·
**NOT CHOSEN** (lost a bake-off) · **SUPERSEDED** (overtaken by a later design) ·
**EXPLAINER** (teaching artefact, not a UI proposal).

---

## 2026-07-12 — tab-by-tab redesigns

Each page of the site taken back to a mockup and rebuilt against the Desk brief.

| Artefact | Status | Local | Link |
|---|---|---|---|
| Per-bank page, rethought | **SHIPPED** — `9f918d3` five tabs, no duplication | — | [artifact](https://claude.ai/code/artifact/4b7dd17d-ba99-43c3-b10a-409b840e37d0) |
| Financials tab, rethought | **SHIPPED** — `896d4f5` four lenses + shape layer + flow | — | [artifact](https://claude.ai/code/artifact/be778eab-6c4d-48a4-94aa-a13418e65146) |
| Banks (the register) | **SHIPPED** — `75a28f5`, `a08ef55` | — | [artifact](https://claude.ai/code/artifact/084362b4-20ff-4914-9ff3-1cdd0e8c3905) |
| Overview — the depth layer, realigned | **SHIPPED** — `e081959` evidence layer speaks the brief's language | — | [artifact](https://claude.ai/code/artifact/41bca20a-36e0-46a4-9d0b-bfedb94628e3) |
| Compare — redesign proposal | **PROPOSED** — not built | — | [artifact](https://claude.ai/code/artifact/97ada54b-e315-4a80-80cc-c4d4716726c6) |
| Regulations tab (first pass) | **SUPERSEDED** — by the Rulebook, below. Built on invented data (labels itself "sample"/"illustrative" 7×) and designed for a different product: an internal bank-compliance workflow with impact ratings, sign-off state and action owners ("Treasury · confirm reserve mix"). We hold none of those, and Carthago has no Treasury team reading it. Its one real idea — the effective date — survives into the Rulebook | [html](mockups/2026-07-12-regulations-tab.html) · [desktop](mockups/2026-07-12-regulations-tab-desktop.png) · [mobile](mockups/2026-07-12-regulations-tab-mobile.png) | — |
| Regulation tab — **the Rulebook** | **SHIPPED 2026-07-13** (PR 1 + PR 2 of its ship order; PR 3 needs a new source). Premise: `/regulation` is the only tab that doesn't know what it knows — it **counts** the feed instead of **stating** the regime. Its "Latest decision — Jul 9" is an **SSL-certificate replacement**; of the 7 items in its headline count, **5 are not regulation** (a magazine, an MoU, a data release…). Meanwhile the rules sit unread in `body_text` (**258 of 264** TCMB releases, avg 2,639 chars) *with before/after parameter tables and the date they bind* — and the Kimi briefing **already extracts them**, then prints them as bullets in a box below the fold. Signature = **the regime in force** (corridor 37/40/35.5; FX-deposit RRR 30→**32**% and 26→**28**%, binding 17 Jul; the 2.5% add-on **terminated**), with the **48-decision policy path parsed out of the press releases** as its mark. Corrects the clock too: BDDK prints the decision date *and number* in the title, we sort by scrape date — mean lag **309d**, worst **629d**, **29 of 33** decisions dumped in one two-week batch in Mar 2026. Kicker: that register **already named the banks** — it licensed Enpara, Colendi and Ziraat Dinamik **491–568 days** before we onboarded them by hand. (Careful with the flag: FUPS Bank is licensed and absent from `banks` **on purpose** — zero filings, excluded by the 2026-07-11 review — so the rule needs two states, gap vs watch, tested against BdrUyg.) **DEPLOY-READY pass 2026-07-13** — the page must survive a cron, not a screenshot, so: the hand-written thesis became a **computed takeaway** (`insights.ts` slots — a thesis that critiques the page it replaces is nonsense the day it ships); the band grew a **gap strip directly beneath it**; the build spec moved off the sheet. **Verdict: the spine automates, the reserve band does not.** `body_text` carries the *rate* decisions cleanly (48/48 parse; EVDS `TP.PY.P02.1H` independently agrees at 37%) but **10 of the last 12 macroprudential releases ship no parameter table** — all re-fetched 12 Jul with the table-aware extractor, so this is structural: TCMB doesn't publish them as HTML. A rule in force is therefore missing from the band **right now** (23 May credit *"Growth Limits (For Eight Weeks)"* — we hold 342 chars: heading, then footer). Hence `is_rule ∧ params = 0 → print the gap`, and a **3-PR ship order: spine → read+gap counter → reserve parameters (needs a new source; do not start here)**. Rationale + build spec: [knowledge](../knowledge/regulation-tab-redesign-2026-07-12.md) | [html](mockups/2026-07-12-regulation-tab-rulebook.html) · [desktop](mockups/2026-07-12-regulation-tab-rulebook-desktop.png) · [mobile](mockups/2026-07-12-regulation-tab-rulebook-mobile.png) | [artifact](https://claude.ai/code/artifact/28deafca-749b-4027-a0ad-995563f5a9cf) |
| Credit tab | **SHIPPED** — `7ffa75a`. Premise held: the headline is mostly *not* credit. Strip lira + CPI and the book **shrank 2.1%**. Built with the bridge, growth attribution (contributions reconcile to the print), SME nested inside commercial, and computed flags | [html](mockups/2026-07-12-credit-tab.html) · [desktop](mockups/2026-07-12-credit-tab-desktop.png) · [mobile](mockups/2026-07-12-credit-tab-mobile.png) | — |
| Deposits tab | **SHIPPED** — `d4de0e6`. Premise held: the page never stated its own finding — **~91% of the book reprices inside three months**. Brief gained Movers/Flags/Standings/Ahead (it had none); evidence layer converted to the Overview contract; `Flags showCleared` added so a rule prints whether or not it fires | [html](mockups/2026-07-12-deposits-tab.html) · [desktop](mockups/2026-07-12-deposits-tab-desktop.png) · [mobile](mockups/2026-07-12-deposits-tab-mobile.png) | [artifact](https://claude.ai/code/artifact/77a1403c-ef5a-4899-8605-e264b5ace793) |
| Asset Quality tab | **SHIPPED** — `ed39fd0`. v1's thesis ("the growing loan book hides 1.06pp of NPL ratio") was **retracted**: an NPL ratio is deflator-invariant, so inflation does not flatter it — only *real* book growth (+3.3%) dilutes, worth **~0.1pp**. **Built as v2 — the waterline:** the ratio prints the **3.1%** Stage-3 tip, but loans the banks classify as deteriorated are **12.3% — 4×**; **75%** of that ₺3.2trn problem book is the watchlist, at **9.8%** cover vs Stage 3's 62.3%. Pipeline still filling: formation **2.2×** (₺673bn, net +₺404bn), exits **77% collections** — real deterioration, not disposals. SME drove **42.8%** of new bad loans. The retracted claim is now pinned by a deflator-invariance unit test. [knowledge](../knowledge/asset-quality-tab-redesign-2026-07-12.md) | [html](mockups/2026-07-12-asset-quality-tab.html) · [desktop](mockups/2026-07-12-asset-quality-tab-desktop.png) · [mobile](mockups/2026-07-12-asset-quality-tab-mobile.png) | [artifact](https://claude.ai/code/artifact/02583087-eae5-4b10-826c-dee7c9a32fd0) |
| Liquidity tab | **SHIPPED** — `072a367`. Premise held: the page **derived** net reserves and the swap stock — the most careful arithmetic on the site — then drew them as one line among three and said nothing. Read out: gross **$159.7bn** → net **$52.2bn** → net excl. swaps **$34.5bn** (22% of the headline); **$107.5bn** of "gross" is the *banks'* own FX at the CBRT, **$17.7bn** is swapped in. Second finding, from two series the page never compared: residents hold **$138.3bn** in FX + gold, **3.1×** the CBRT's net reserves (same-date). The mark had to change because the data said so: a stacked decomposition would **lie** — the CBRT's own net FX is negative in **42 of 150 weeks** (−$68.6bn at worst) — so `ReserveBuffer.tsx` is three lines with the gaps shaded. Also fixed on the way: `quarterLabel` never parsed the audit lane's `2026Q1` format (every §4 reference printed "latest quarter"), and the Movers week pair read "05 Jun → 05 Jun" (long-form `.at(-2)` is the same week's other group) | [html](mockups/2026-07-12-liquidity-tab.html) · [desktop](mockups/2026-07-12-liquidity-tab-desktop.png) · [mobile](mockups/2026-07-12-liquidity-tab-mobile.png) | [artifact](https://claude.ai/code/artifact/27299533-1ade-441e-8b18-a9617bf0b4a1) |
| Capital tab | **SHIPPED** — `48b57e1` (mockup 2026-07-13). Premise held: **the ratio didn't drift, it stepped.** CAR went **19.69% → 16.77% between December and January** — a −2.92pp move in one month, the largest in **76 months** of record, and *every* ownership group fell together (−2.7 to −5.4pp). The live page calls this "eased to 16.3% (−1.2pp over 12m)" and then **extrapolates that average to a floor date**. Split the year and it is the step (−2.92pp) **plus everything else (+1.75pp)** — ex-step the sector *built* capital through 2025. The redesign prints the split, extrapolates only the **post-step** slope (−1.28pp/yr) and says the step is **unattributed** (no rule in our regulation window; RWA density barely moved, so it came through capital, not risk). Second finding: the buffer over the 12% minimum is **4.02pp** but the AT1 + Tier-2 stack is **4.23pp** — strip the instruments and the ratio is **11.79%**, below the minimum; **17 of 34** banks hold CET1 under 12%. Contrast with /liquidity: here a **stacked area is the right mark** (all components positive, sum to total capital by construction). **Also found and FIXED (`96c381b`): the site was publishing CET1 10.56% when the true figure is 11.79%** — ISCTR reports no CET1 while carrying 10.6% of sector RWA, and the Σ/Σ aggregation counted its RWA anyway | [html](mockups/2026-07-13-capital-tab.html) · [desktop](mockups/2026-07-13-capital-tab-desktop.png) · [mobile](mockups/2026-07-13-capital-tab-mobile.png) | [artifact](https://claude.ai/code/artifact/7773859e-8e75-438d-b1f7-7d6837b974e5) |

## 2026-07-12 — chart-class redesigns

Not a page — a *mark*. One chart component, taken apart wherever it appears.

| Artefact | Status | Local | Link |
|---|---|---|---|
| The composition chart (`StackedArea` — 11 instances across credit, deposits, asset-quality, digital, non-bank) | **PROPOSED** — not built. Premise: the stack cannot draw its own headline. The deposits chart is titled "the book shrank **₺0.40 trn** in the week" — **1.3% of one band, ~3px** — while the shape it *does* draw (nominal ×2.86 since May 2023) is mostly the lira: deflated, the same book is **9.2% smaller** than it was, and every group shrank (State **−11.8%** real). Proposes four marks off the same four series — **mix** (100% share, inflation-neutral, the default), **levels** (kept, demoted, with its real twin named), a **Δ strip** (the title, drawn: State −0.46 vs the rest +0.06), a **nominal-vs-real index**, and **flat-baseline small multiples** (a stack gives only the bottom band a readable trend). Also fixes a real bug it found: the weekly bulletin's bank-type codes fall through the *monthly* palette map, so **State is painted in Dev & Inv's grey** and Domestic in Participation's purple — the same group is a different colour on the monthly charts. Interaction: a **readout rail** replaces the floating tooltip (populated at rest, never occluding) + the hover crosshair shipped in `1a88522` | [html](mockups/2026-07-12-composition-chart.html) · [desktop](mockups/2026-07-12-composition-chart-desktop.png) · [mobile](mockups/2026-07-12-composition-chart-mobile.png) | [artifact](https://claude.ai/code/artifact/59175350-27a4-4a90-b817-d30aaa3f2df2) |

## 2026-07-11 — the identity bake-off

Seven whole-site identities, built as rival concepts and judged against each
other. **The Desk won** and became the design system; the other six are kept
because their ideas are still harvestable.

| Concept | Status | Link |
|---|---|---|
| **The Desk** | **SHIPPED** — became `web/DESIGN.md`; white sheet on paper ground, hairlines, mono figures | [artifact](https://claude.ai/code/artifact/5bc55305-0e5e-425c-abaf-e08924c6099b) |
| The Desk — full sector suite | **SHIPPED** — the winner extended across all six sector tabs | [artifact](https://claude.ai/code/artifact/28b72bb4-fade-433b-a2dc-aff39e31860e) |
| The Bulletin | NOT CHOSEN | [artifact](https://claude.ai/code/artifact/c2ae9467-7410-4715-b873-224696548292) |
| The Bulletin v2 | NOT CHOSEN — second pass at the Bulletin | [artifact](https://claude.ai/code/artifact/d738a135-2021-4449-b9d3-a282b34977c6) |
| The Ledger | NOT CHOSEN | [artifact](https://claude.ai/code/artifact/3dab3040-e321-4e30-be9d-27ebe673fb9f) |
| The Terminal | NOT CHOSEN | [artifact](https://claude.ai/code/artifact/eef04b57-2b80-4af8-a576-7a20cc5f27fe) |
| The Folio | NOT CHOSEN | [artifact](https://claude.ai/code/artifact/8647d9fc-72c5-4c6c-97a1-acca96be78a6) |
| The Atlas | NOT CHOSEN | [artifact](https://claude.ai/code/artifact/4fc6c5e9-b207-4f67-b4b3-c0057e881df3) |
| The Observatory | NOT CHOSEN | [artifact](https://claude.ai/code/artifact/49a81608-c246-41a1-a5e1-80a783ac3c60) |

## 2026-07-10 — the pre-Desk round

Came out of the design critique (`docs/knowledge/design-critique-2026-07-10.md`,
`design-system-audit-2026-07-10.md`), which is what triggered the bake-off above.

| Artefact | Status | Link |
|---|---|---|
| Overview redesign prototype | SUPERSEDED — by the Desk identity a day later | [artifact](https://claude.ai/code/artifact/74fc9bd1-cb5e-4c85-a9ec-a942e9052083) |
| By bank — capital adequacy (preview) | SUPERSEDED — preview of the by-bank treatment | [artifact](https://claude.ai/code/artifact/9410c8ae-b4ef-404a-8f2d-35b43541921d) |

## 2026-07-04

| Artefact | Status | Link |
|---|---|---|
| Reading a Turkish Bank Audit Report | **EXPLAINER** — how a BRSA report is structured; not a UI proposal | [artifact](https://claude.ai/code/artifact/f21baa76-ed53-432b-bb2f-6c3832bdc3dd) |

---

## Open design debt

- **Compare, Regulation, Liquidity, Asset Quality** are mocked but unbuilt — four ready
  designs waiting on implementation. (Credit shipped 2026-07-12 `7ffa75a`; Deposits
  `d4de0e6`; Overview `e081959`.) Asset Quality's signature panel needs the **corrected**
  premise — read its rationale doc before building.
- **Regulation implies extraction work, not just UI.** The Rulebook mockup needs three
  parsers, all over data we already receive: the **decision date + board-decision number**
  out of the BDDK title (they are printed there; we sort by scrape date instead), an
  **`is_instrument`** rule so an SSL certificate and a magazine stop counting as
  regulation, and the **binding date** out of the release prose ("maintained on
  17 July 2026") — the one field the design shows that is not yet a column. Licensing
  decisions should also be tagged to tickers with `bank_tagger.py`: the register named
  Enpara, Colendi and Ziraat Dinamik **491–568 days** before we onboarded them. Test
  filing status against **BdrUyg** before flagging, though — *licensed ∧ not in `banks`*
  alone would false-alarm on FUPS Bank, which is excluded deliberately (zero filings).
- **The composition chart** is mocked but unbuilt — and one of its findings is a live bug:
  the weekly charts paint each ownership group in another group's colour (`seriesColor()`
  keys on a code whose meaning differs between the weekly and monthly bulletins). Cheap to
  fix independently of the redesign.
- **Four sector tabs still run the pre-contract evidence layer** (capital,
  profitability, market-risk, and the economy pages) — asset-quality's was converted
  on 2026-07-13 (`98516e5`), a step the brief-only ship had *missed*: boxed `Stat` cards,
  boxed `Takeaway`, charts in `ChartCard` chrome. `web/DESIGN.md` → "the evidence
  layer speaks the brief's language" is the contract to convert them against.
- Credit and the superseded first Regulations pass exist **only** as local files; publish
  them if they need to be reviewed away from the repo.
