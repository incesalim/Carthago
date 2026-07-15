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

**And if the mockup sets a rule, promote the rule into [`web/DESIGN.md`](../../web/DESIGN.md)
in the same change.** This file is an archive: a future session reads it only if
it thinks to look. What gets read while a chart is actually being built is
DESIGN.md and the component's own header. A rule that lives only in a mockup is
a rule that will be broken by the next person who reaches for the component — so
the rule goes in the law, and the law links back here for the worked example.
(First one done this way: the composition chart → DESIGN.md "Choosing the mark"
+ the `StackedArea.tsx` header.)

Status vocabulary: **SHIPPED** (built, live) · **PROPOSED** (made, not built) ·
**NOT CHOSEN** (lost a bake-off) · **SUPERSEDED** (overtaken by a later design) ·
**EXPLAINER** (teaching artefact, not a UI proposal).

---

## 2026-07-15 — the admin control center

The last page still built entirely from the legacy `Card`/`Stat`/`Section`
evidence surfaces — boxed tiles, pill badges, three-deep equal-weight scroll,
no summary. Argued into the Desk.

| Artefact | Status | Local | Link |
|---|---|---|---|
| **Control center** (`/admin`) — the pipeline-health / triggers / traffic console redesigned into a Desk two-layer page | **PROPOSED 2026-07-15** — mockup only; the live page (`web/app/admin/page.tsx` + `PipelinePanel`/`TrafficPanel`/`coverage/*` + `web/app/lib/admin-health.ts`) is unchanged. Premise: `/admin` is the one surface never converted to the Desk — it is still boxed `Stat` tiles with pill freshness badges and the framing "freshness per source, **against expected refresh cadence**", the exact age-vs-cadence logic that produced the daily false "stale" alarm on the monthly bulletin (now fixed in code: freshness asks BDDK if the next month is published rather than estimating a due date). The redesign keeps **every** byte of function — the six data-health sources, the coverage matrix + per-cell re-extract, all pipeline triggers, traffic, the PDF deck, the password gate — and restyles: the six sources become the **vitals band** (the one bold element per Desk rule 8), a computed status **Read** leads ("Every source is current. The monthly bulletin holds *May 2026* — the latest BDDK has published; June is not out yet, so nothing is late."), freshness prints BDDK's real answer ("June not yet published") not a calendar guess, Fresh/Late/Stale stay green/amber/red as **semantic state** (separate from the blue link accent), and controls become mono-caps ink-underline affordances — blue reserved for links that navigate. Build cost if chosen: convert `page.tsx` + `SourceCard` to `DeskHeader`/`SecHead`/`Vitals` + a `Colophon`; the section content (coverage/pipeline/traffic) is already computed, so it is a restyle, not a rebuild. | [html](mockups/2026-07-15-admin-page.html) | [artifact](https://claude.ai/code/artifact/f439323e-3a7f-4ea9-a1a5-ab773bdc0003) |

---

## 2026-07-14 — deletions

The user proposed **deleting** two pages. This is the register of what was argued back.

| Artefact | Status | Local | Link |
|---|---|---|---|
| **Bank Actions** (`/actions`) — the page that replaces `/earnings` **and** `/disclosures` | **SHIPPED 2026-07-15** — built deploy-ready and fully automated: `web/app/actions/page.tsx` + `web/app/lib/kap-actions.ts` (deterministic classifier, no LLM) + `kap-actions.test.ts` (16 real-KAP fixtures, locks coupon≠issuance and unknown→visible). Every figure computed at request time from `news_items`; the daily news cron already feeds it, so **zero new infrastructure**. `/earnings` + `/disclosures` now redirect (`?ticker=` preserved); nav collapses two slots to one "Actions"; sitemap + pipeline-graph + all cross-links updated. tsc + eslint + 294 tests + webpack build + pipeline-sync all green. Original premise: both pages were **feeds, not pages** — neither states anything, and the site's whole claim is *compiled, not written*. `/earnings` is a link directory whose vitals count **our own scraper** (decks collected, filings archived); `/disclosures` is reverse-chronological KAP, of which **27% (120 of 442 rows) is coupon-payment plumbing** ("the 103rd coupon payment on ISIN TRSSKBKA2716 has been made") and another 44 rows are company-info-form boilerplate. **But the same feed hides a finding no other page on this site can make:** six of the eleven listed banks filed **67 debt-issuance approvals in ten weeks** — AKBNK 18, GARAN 15, VAKBN 14, ISCTR 14, TSKB 4, HALKB 2 — Garanti and Vakıfbank repeatedly offshore, İşbank for **Tier-2 capital**, TSKB back abroad. Turkish banks have **reopened the offshore funding tap**, and one bank went the other way (**SKBNK rights issue**, board 7 May → CMB 3 Jun). `/capital` gives you the CAR *ratio*; **nothing on the site tracks what banks DO to their capital.** So: one page, classified by **act** (funding · capital events · ratings · results season), routine notices **counted and suppressed**, deterministic classifier over KAP form types — **no LLM, no new source, two nav slots → one**. Declared gap, printed on the page: we hold title+summary only, so it **counts acts, it does not measure them** — amounts/maturities/coupons need `src/news/kap.py` to scrape the detail form; and KAP's window only reaches back to **5 May 2026**. | [html](mockups/2026-07-14-actions-page.html) | [artifact](https://claude.ai/code/artifact/e469d447-6a18-4296-b5de-652c5c96c971) |

---

## 2026-07-13 — second passes

A page can be right about its defect and still be the wrong page. These are redesigns
of pages we had *just shipped*.

| Artefact | Status | Local | Link |
|---|---|---|---|
| Regulation — **Where the rules bite** (v2) | **SUPERSEDED** by v3 — it is the *Liquidity* tab wearing a Regulation badge: reserves, transmission and KKM are balance-sheet analysis and belong next door. Its findings are real and worth building **there**. Two visuals survive in v3, demoted. Original premise: Supersedes the *signature* of the Rulebook (shipped hours earlier; its parsers, archive, licensing register and coverage caveat all survive). Premise: the Rulebook fixed the right defect — the page **counted announcements** instead of **stating the regime** — and then **stopped**. It says the reserve requirement is *32%* and nothing about what 32% **does**. That is a rulebook, and you can get a rulebook from the regulator's website. **Carthago holds the sector's balance sheet, weekly, back to 2019, and the regulation page never touched it.** So: every rule drawn against the number it moves. (1) **The reserve requirement is ₺4.06trn** — **13.6% of every lira deposited in Türkiye** sits at the CBRT, neither lent nor invested, because a rule says so; and the *lira* ratio was **0.02% in Jan 2022** vs 6.8% now — it was built from nothing, while FX barely moved (21.3→24.5%). (2) **The corridor says 37%. Nobody pays 37%** — the saver is paid **49.0%**, the borrower pays **61.7%**: a **24.7pp** wedge, so printing "37%" as *the regime* is true and deeply misleading. (3) **A rule built ₺3.41trn and dissolved it** — FX-protected deposits (KKM) peaked at a **fifth of the deposit base** (Aug 2023) and are now **exactly zero**. Checked and **not** built: the credit-growth-cap chart — 4-week growth swings **0.3–4.7%** with no ceiling effect, so "growth pins at the cap" would be an invented finding. Drops the decision-lag comb and the 30-day ✓/✕ list (both about *us*, not the regime). **No new source, no new cron, no LLM.** Rationale: [knowledge](../knowledge/regulation-tab-redesign-v2-2026-07-13.md) | [html](mockups/2026-07-13-regulation-tab-where-rules-bite.html) · [desktop](mockups/2026-07-13-regulation-tab-where-rules-bite-desktop.png) · [mobile](mockups/2026-07-13-regulation-tab-where-rules-bite-mobile.png) | [artifact](https://claude.ai/code/artifact/edb95ab0-55c8-4d2e-87ef-d9ab4fdcf8be) |
| Regulation — **the rulebook** (v3) | **SUPERSEDED** by v4 — a taxonomy where the reader wanted a changelog; and its central claim ("the caps are not machine-readable") turned out to be **false**. Premise: Corrects v2 (which drifted into the Liquidity tab) *and* reverses my 07-12 decision to dissolve the Kimi snapshot — that call was **wrong**: the compiled band carries only the **six** parameters a parser can read, and we had already proved **9 rule changes in force have no machine-readable numbers at all**. The overlap was never the point; the **coverage** was. **Three declared tiers, each labelled on the page:** **Compiled** (parsed + reconciled against EVDS — *no model ever sets a figure*), **Synthesized** (the snapshot — moonshot-v1-128k over 88 instruments; *every bullet links to its instrument*), **Absent** (2 of 7 sections have **no source** — CARs and Credit Cards live in BDDK Tebliğ/Resmî Gazete; forced to write them the model **fabricated credit-card tier tables**, so they are shown **empty on purpose**. An empty section you can see beats a plausible one you can't check). **The LLM is not a shortcut — it is the only tool that works:** the 23 May release is the one we hold **342 characters** of, and the model reads its caps out of the prose (**3%/8wk** general-purpose & vehicle, **4.5%** commercial, **0.5%** FX) — binding constraints that are otherwise **invisible to this site**. Checked and **not** drawn: growth-vs-cap — the caps exempt export/investment/agriculture/KOSGEB/CGF and bind bank-by-bank while our series is the whole book, so naively the sector "breaches" in **42–49 of 49 weeks**: an artefact of the base, not a finding. **Stated, not charted.** Build cost ≈ 0 new infrastructure. Rationale: [knowledge](../knowledge/regulation-tab-redesign-v3-2026-07-13.md) | [html](mockups/2026-07-13-regulation-tab-rulebook-v3.html) · [desktop](mockups/2026-07-13-regulation-tab-rulebook-v3-desktop.png) · [mobile](mockups/2026-07-13-regulation-tab-rulebook-v3-mobile.png) | [artifact](https://claude.ai/code/artifact/16dc5276-cae1-4699-b665-8bbeb787d0c8) |
| Regulation — **what changed** (v4) | **SUPERSEDED** by v5 — the artefact argued its own design *inside the page* (a “the model got this wrong, and the citation caught it” essay). Findings below all stand; the commentary does not ship. Premise: Re-spines v3's content as a dated **changelog**: the briefing's bullets carry `source_ids`, those resolve to instruments, and instruments have dates — **28 of 28 resolve**. So the same LLM content, sorted by *when the rule changed*, newest first,each  entry linked to the instrument that made it. The taxonomy survives below as a reference layer; the v3 "tier legend" is gone (provenance is **shown, not preached**). **THE FINDING — the citation caught the model.** The caps cite the 18 Jun MPC Summary, which we hold in full. The instrument says *"from 5% to 4.5% in **TL loans to SMEs**, and from 3% to 2% in **non-SME** enterprises"*. The model reported *"**commercial loans (excluding overdraft)** … 4.5%, down from 5%"* — it **relabelled the category** and **dropped the non-SME cap entirely**. Not an argument against the model; **the argument for making it cite**. **AND IT OVERTURNS MY OWN BLOCKER:** I had asserted in shipped copy, three docs and a commit that the caps are "not machine-readable" (the macropru release ships no table — we hold 342 chars). **False.** The MPC Summary recaps all four caps in one regular sentence, in a document we already store — an 8,000-char document my classifier calls *"not regulation"*. So the caps move **compiled**, and the parser now checks the model: **✓ 5 of 28 agree, ✗ 1 does not**. Thesis: **a model you can check is worth more than a parser that sees nothing.** Still not drawn: growth-vs-cap (exempt base). Zero new infrastructure. Rationale: [knowledge](../knowledge/regulation-tab-redesign-v4-2026-07-13.md) | [html](mockups/2026-07-13-regulation-tab-changelog-v4.html) · [desktop](mockups/2026-07-13-regulation-tab-changelog-v4-desktop.png) · [mobile](mockups/2026-07-13-regulation-tab-changelog-v4-mobile.png) | [artifact](https://claude.ai/code/artifact/a706157a-a633-4984-8e6d-6186a2175164) |
| Regulation — **buildable** (v5) | **SHIPPED 2026-07-13** — `7c1b329`, live. All four caps parse; changelog reads ✓5/✗1; the conflict renders on the offending row; MPC Summary reclassified as a rule; absent sections render empty. **Same design as v4, with every word of design-commentary removed** — the page exactly as it would ship. No rationale, no first person, no arguing the architecture at the reader: a model/parser conflict is not an essay but a **computed chip** on the offending changelog row (`✗ instrument: TL loans to SMEs, 5% → 4.5%`), and the caps table is simply authoritative and complete. Structure: **state today** (6 compiled cells) · **loan growth caps** (4 caps parsed from the MPC-summary sentence, + the reader-facing caveat that sector growth is *not comparable* with them — exempt base, bank-by-bank enforcement, so sector growth exceeds them in 42 of 49 weeks without a breach) · **what changed** (28 dated rule changes, newest first, each source-linked; **✓ 5** match the parsed parameter, **✗ 1** conflicts) · two charts (policy path; reserves ÷ deposits) · **in force, by section** (reference; capital-adequacy and credit-card sections shown **empty — no source**, BDDK Tebliğ/Resmî Gazete not ingested) · what binds next · newly licensed banks · related (links to Liquidity/Rates/Deposits) · archive. Page copy verified free of self-reference. Rationale: [knowledge](../knowledge/regulation-tab-redesign-v4-2026-07-13.md) | [html](mockups/2026-07-13-regulation-tab-v5-buildable.html) · [desktop](mockups/2026-07-13-regulation-tab-v5-buildable-desktop.png) · [mobile](mockups/2026-07-13-regulation-tab-v5-buildable-mobile.png) | [artifact](https://claude.ai/code/artifact/8519fc87-aa18-4a68-aad6-5447bedfad89) |

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
| Profitability tab | **SHIPPED** — `6cddabd` (mockup 2026-07-13). Premise held: the page already says returns are negative in real terms; it never says **where the return comes from**. **The margin is not earned on the loan book — it is collected on the deposits the sector does not pay for.** Demand deposits are **36.9%** of the base and pay nothing; the sector pays **33.1%** on the deposits it *does* pay for, so its blended cost is only **20.9%** — **12.2pp of free funding**. Priced at that same rate the demand book is worth **₺3.19trn a year** against **₺1.01trn** of total sector profit: **3.1×**, and stable at **2.6×–4.5× for 18 months**. Applied to the published ROE (24.7%) it is worth **81pp** — a **sizing device, not a forecast**, and the page prints the caveats (demand deposits carry servicing costs, inside the **54.8%** cost/income it now shows). Second: the income statement is **cumulative YTD**, so the new bridge **de-cumulates** it — in May, NII rose **+₺98bn y/y and the profit still fell** (costs −₺55bn, trading −₺42bn); a YTD average cannot show that. **Two theses tested and thrown away**: the run-rate is *not* below the YTD print (it swings 21–44% with no trend), and a depositor does *not* out-earn a shareholder (20.9% vs 24.7%). Deploy gate: the bridge **reconciles against the reported net-profit line every render** (today ₺0.0000trn) and prints a data-quality flag instead of the chart if BDDK renumbers an item. Rules promoted to DESIGN.md: *one metric one number* (I nearly shipped a home-made 25.8% ROE beside BDDK's published 24.7%), *de-cumulate a cumulative source*, *derived aggregates reconcile and fail loudly*. Spec: [knowledge](../knowledge/profitability-tab-redesign-2026-07-13.md) | [html](mockups/2026-07-13-profitability-tab.html) · [desktop](mockups/2026-07-13-profitability-tab-desktop.png) · [mobile](mockups/2026-07-13-profitability-tab-mobile.png) | [artifact](https://claude.ai/code/artifact/4c842228-30b3-4f0d-ad7e-7d19dbb19b8e) |

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
