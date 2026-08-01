# Five-lens team evaluation — 2026-08-01

**Status: report only. No code was changed.** A five-agent review team
(engineering, analyst methodology, banking domain, design, product strategy)
evaluated the system independently, then cross-examined each other's findings.
This document records what survived the cross-examination.

> Companion to [2026-08-01-project-evaluation.md](2026-08-01-project-evaluation.md)
> (single-model engineering audit, DeepSeek V4 Flash). Where the two disagree,
> the disagreement is recorded below with evidence — that audit's four headline
> claims were re-verified and one is overstated.

## Why the format matters here

Every finding below was written by one lens and then attacked by another. Nine
claims died in that process, including two of the review's own headline
recommendations and one of the team lead's. The corrections are recorded in §4
because they are the most useful part: a single-pass review would have shipped
all nine.

The clearest case: the analyst lens found NIM is not swap-adjusted — correct, and
material — and proposed adding P&L `6.2 + 6.3`, which reordered the league table
and appeared to show a structural conventional-vs-participation split. The
banking lens pulled the underlying trading sub-lines and showed that split is an
**artifact** of which side of a near-cancelling pair dominated in one quarter.
Shipping it would have corrupted precisely the comparison §3 identifies as the
product's differentiated asset. Neither lens could have reached that alone.

Claims marked **[verified]** were checked directly against the code by the team
lead, independently of the agent that raised them.

## Scores

| Lens | Score | One-line verdict |
|---|---|---|
| Engineering | 7/10 | High craft at the file level, thin at "is it running, and would we know" |
| Analyst methodology | 6.5/10 | Ratio construction beats most sell-side models; NIM is unusable |
| Banking domain | 7.5/10 | Extraction better than commercial vendors; interpretation states two wrong regulatory conclusions |
| Design & UX | 7/10 | Best-disciplined solo design system seen; fails WCAG 2.2 AA today |
| Product strategy | 5.5/10 | Engineering 9, strategy 3 — one rare asset under 33 thin routes |

## 1. Live wrong claims — fix before anything else

These are not code smells. Each one currently prints something false to a
reader, or removes a stated safety guarantee.

### 1.1 CET1 judged against the 12% total-capital target **[verified]**

`web/app/capital/page.tsx:125` defines a single `CAR_MIN = 12`, and `:202`
reuses it as the CET1 test. The rendered sentence at `:384` reads *"N of M banks
hold CET1 below the 12% **total-capital** minimum"* — the copy names the right
instrument and applies it to the wrong one. Same constant drives the rule line
in `CapitalByBank.tsx:18,40,81,98` and the "below the 12% it must meet" claim at
`:372`.

Running the flag's own arithmetic over 2026Q1 `bank_audit_capital`: **18 of 37
peer banks trip it** — Halkbank 8.44, VakıfBank 9.41, Yapı Kredi 10.81, Akbank
11.71, İş 11.74, Ziraat 11.94, QNB 11.97.

BRSA's 12% is the *hedef rasyo* for **total** capital — a permissions and
dividend threshold. The CET1 requirement is 4.5% + 2.5% conservation + D-SIB
(+CCyB) ≈ 8.0–9.0% for the systemic group, ~7% otherwise. **Every one of those
18 banks clears its actual stack.** The page tells a reader that two-thirds of
the Turkish banking system is short of common equity.

Fix: split `CAR_MIN` into `CET1_MIN` / `TIER1_MIN` / `CAR_LEGAL_MIN` (8%) /
`CAR_TARGET` (12%) plus the per-bank D-SIB buffer; re-word `thin-cet1` and
`hybrid-buffer`. Keep buffer-to-target as the analytical frame — it is the right
frame for Türkiye — but label it "BRSA target ratio" and show 8% legal and 12%
target as two lines. **~half a day.**

### 1.2 NIM ignores the FX-swap funding cost **[verified: definition]**

`web/app/lib/heatmap.ts:99` states the rule as *"TTM net interest ÷ 5-quarter
avg assets"* — no swap adjustment, and struck on total assets rather than
interest-earning assets. Turkish banks fund TL assets by swapping FX; that cost
lands in P&L `VI.` (derivative `6.2` + FX `6.3`), never in `II.`

**The defect is real. The obvious fix is not, and the review nearly shipped it.**

The analyst lens recomputed 2026Q1 TTM adding `6.2 + 6.3` and the league table
reordered — QNBFB 6.07%→3.54% (#2→#8), YKBNK 5.75%→3.01% (#4→#9), KUVEYT
5.80%→6.72% (#3→#1) — with deltas systematically negative for conventional banks
and positive for participation banks. The banking lens then pulled the actual
trading sub-lines (2026Q1 unconsolidated, ₺ thousands):

| bank | 6.2 derivative | 6.3 FX | 6.2+6.3 |
|---|---|---|---|
| AKBNK | −33,711,401 | +25,474,945 | −8,236,456 |
| GARAN | −24,719,080 | +15,687,039 | −9,032,041 |
| **KUVEYT** (participation) | **−42,624,355** | **+47,383,916** | **+4,759,561** |
| ALBRK (participation) | −4,795,295 | +4,911,769 | +116,474 |

Three conclusions, in ascending order of importance:

- **Net the pair, never the derivative leg alone.** 6.2 and 6.3 are two sides of
  the same book and near-perfectly offsetting; stripping one half produces a
  wildly over-corrected number.
- **But the sum still over-corrects, and it is unstable.** It contains genuine
  customer FX and client-derivative revenue (real spread, largest at the
  corporate franchises), plus FX revaluation on the structural long position most
  banks run to protect the FX leg of their capital ratio — a *systematically
  positive* item across 2022–2026. And the published figure would be the
  difference of two nearly-cancelling 25–47bn legs netting to 5–9bn, so a small
  timing shift in either swamps the net. A ranking built on it is unlikely to
  reproduce next quarter.
- **The participation asymmetry is an artifact, and it is the claim to pull.**
  KUVEYT has the *largest* derivative loss in the sample — −42.6bn, bigger in
  absolute terms than AKBNK's or GARAN's. Participation banks demonstrably do run
  large FX-hedging books; Shari'ah-compliant structures still book derivative-line
  entries under TFRS. What drives the positive deltas is simply which side of the
  offset dominated in one quarter: KUVEYT's net is *+4.76bn*, so adding it raises
  NIM — **folding trading profit into a margin metric**, a category error in the
  opposite direction from the one being fixed.

Since §3 identifies conventional-vs-participation as the product's differentiated
asset, shipping a metric whose asymmetry across that split is an artifact would
be worse than shipping nothing.

**"Match the market" is not available.** Akbank, Garanti BBVA, İş and Yapı Kredi
all publish *swap maliyetine göre düzeltilmiş marj* — net interest income minus
swap cost, over average interest-earning assets — but the swap cost comes from
their own treasury books. **It is not a P&L line and is not derivable from the
filing.** The honest options are: caveat headline NIM; publish a clearly-labelled
*proxy* that states it is not the bank's swap-adjusted figure; or ingest the
decks' disclosed swap cost as a separate lane.

**What is unambiguously right, and ships regardless:** the denominator. NIM is
struck on **total assets**, which is wrong by every convention, market and
academic — no proxy, no judgement call — and it is computable from rows already
stored (total assets less fixed, intangible, tax, subsidiary and other assets).
It systematically understates NIM, most for banks with large non-earning bases.

**Recommended:** definition note first; denominator fix second; then surface
trading and FX as *its own line beside* NIM — "net trading & FX contribution to
revenue" — rather than folding it in. That exposes the true finding underneath
the recomputation (QNBFB's and YKBNK's margins are more trading-dependent than
AKBNK's) without asserting a number the filings cannot support. **Do not ship the
recomputed league table.**

**The cheap fix is disclosure, and it is separable from the rebuild.** Three
definitions here are non-standard, not wrong: NIM is unadjusted and struck on
total assets; cost/income uses BRSA gross operating profit `VIII.`, which
includes provision reversals where brokers strip them, so the figure reads
structurally low; and unconsolidated is the default everywhere
(`audit-ratios.ts:22`) while brokers model consolidated. A professional who
cannot reconcile our NIM against one they know concludes **our data is wrong
rather than our definition different** — and does so before reaching any of the
differentiated lanes. A visible definition note converts the former into the
latter for the cost of a paragraph. That is the launch prerequisite; the
swap-adjusted metric is ordinary work that follows.

### 1.3 The deploy is not gated by CI, and AGENTS.md says it is **[verified]**

`deploy-cloudflare.yml:8-13` fires on `push` to master under `web/**`.
`ci.yml:5-7` fires on the same push. No `needs:`, no `workflow_run:` — the two
jobs race. Branch protection returns 404; rulesets are `[]`.

AGENTS.md ("All three are `ci.yml` jobs, and red CI blocks the deploy") and
web/AGENTS.md ("CI gates deploy") are both false. The deploy also runs
`wrangler d1 migrations apply bddk-data --remote` (`:47`) before any check has
passed.

A documented safety rule that does not exist is worse than a known gap, because
it has been trusted. Fix: `on: workflow_run` with a success condition, or a
ruleset requiring the CI check on master. **~1 hour.**

### 1.4 The compressed BRSA P&L template mislabels participation filers

`bank_audit_pl_roles` proves the roman ordinals move: DUNYAK 2024Q1–2025Q2 and
TOMK 2023Q4 put `net_op` at **XII**, `pretax` at **XVI**, `period_net` at
**XXIV**. `web/app/lib/standard_lines.ts:226-249` and
`web/app/lib/pl-sankey.ts:196-224` hardcode XIII/XVII/XIX/XXV.

Rendered for DUNYAK 2024Q4: row **XII carries ₺1.616bn of net operating profit
under the label "Other Operating Expenses" with `contra: true`** — a profit
printed as a ₺1.6bn expense — while XVII (tax, ₺262m) reads "Pre-tax Profit" and
XXV, the bottom line, renders blank.

`heatmap.ts:293` was already fixed by joining `bank_audit_pl_roles`. These two
were not. **This hits participation banks only** — which is the case where no
reader has a second source to catch it against (§3).

### 1.5 CI reports green while pages fail WCAG 2.2 AA **[verified]**

`scripts/check_contrast.py:152` matches `\btext-([a-z][a-z0-9-]*)\b`, which
structurally cannot see `text-[#b07a18]`. That hex ships as body and label text
at 11 call sites across `/products` — **3.72:1** on the sheet, **3.34:1** on its
own `/10` tint (`ProductMatrix.tsx:280`). Tinted chips have the same blind spot:
`badge.tsx:14` `text-negative` on `bg-negative/12` = 4.34:1; `:15`
`text-warning` on `bg-warning/15` = 4.24:1. All fail AA while CI passes.

The gate's own docstring claims a safety net it does not have — *"If a chart
colour is ever used AS text, rule 1 above will notice"* — and rule 1 **is** the
blind regex.

Fix: extend the regex to reject arbitrary hex as text outright, and add
`bg-<token>/NN` blends to `PAIRS`. **~30 lines**, and it converts this class from
"someone must notice" to "CI fails". Cheapest structural win in the repo.

### 1.6 `total_tl` / `total_fx` erase every zero BDDK reports — 19,139 in one table

The prior audit flagged `_save_loans`' `get_val("ToplamTp") or get_val("Tp")`
(`bddk_api_scraper.py:257-259`) as a falsy-zero bug; the engineering lens rated it
"true but mis-described" and could not establish whether it fires. **It fires,
and the corpus quantifies it exactly.**

BDDK's raw feed (`raw_api_responses`, 12,995 responses stored verbatim) sends the
integer `0` — never null, never empty, never a dash — across tables 3/4/5/7. What
landed in `loans`:

| column | zeros stored | nulls stored |
|---|---|---|
| `short_term_tl` | 4,987 | 93,878 |
| `short_term_fx` | 5,853 | 93,878 |
| `medium_long_tl` | 5,110 | 93,878 |
| `medium_long_fx` | 5,697 | 93,878 |
| **`total_tl`** | **0** | 63,246 |
| **`total_fx`** | **0** | 77,199 |

The maturity-split columns preserve zeros perfectly — 4,987 and 5,853 match the
raw feed counts exactly. `total_tl` and `total_fx` contain **zero zeros in the
entire corpus** while the feed reports tens of thousands, and the null side
matches exactly: table 4 raw `Yp` zeros = 19,139, stored `total_fx IS NULL` =
**19,139**; table 7 = 570 and 570. The loader demonstrably *can* store a zero —
it does so in four other columns. This is a column-specific defect, not a design
choice. Signature inside a single row: all 398 rows with `total_amount = 0` have
both legs NULL — "the total is zero, and we don't know either leg".

**Why this is the opposite of cosmetic.** The largest block — table 4's 19,139
lost zeros in the FX column — is the **consumer loan** table. Individuals in
Türkiye are prohibited from borrowing in FX or FX-indexed form (Decree 32
restrictions on FX borrowing by residents without FX income). "Consumer vehicle
loans, YP = 0" is not missing data — **it is the law**, and it is one of the
most structurally important facts in the Turkish consumer-credit table. Storing
it as NULL erases a legal prohibition and re-presents it as ignorance. Any "FX
share of consumer lending" view renders blank where the honest answer is a hard
zero.

`SUM()` is unaffected (it skips NULL and 0 identically), so sector totals are
safe. What breaks is anything counting reporting rows, averaging, forming a
denominator from non-null cells, rendering a per-cell table — and every "is this
category zero or unknown?" read a user makes. Which is precisely the rule
AGENTS.md leads with.

Fix: scope to `total_tl` / `total_fx` in the loans loader; the other four columns
are the reference implementation. Note the lane has no tests at all (§2.8).

## 2. Serious, not yet false on screen

| # | Finding | Evidence |
|---|---|---|
| 2.1 | **Freeze blindness.** 10 workflows `disabled_manually`, including `healthcheck` — the only monitor. State lives in GitHub, not in files, so every gate passes while the YAML schedules are fiction, and nothing enforces the 2026-08-11 re-enable. The one lane deliberately left running has no failure alert. | `gh workflow list --all`; `docs/OPERATIONS.md:632-651` |
| 2.2 | **`/api/v1` is unbounded, and its claimed mitigation does not exist.** `_shared.ts:23-29` says s-maxage "keeps repeat traffic off D1 entirely" — live check returns **no `CF-Cache-Status` header at all** on `/api/v1` while `/favicon.ico` returns `HIT`. The 12h KV cache doesn't apply either: every v1 route uses the uncached `allDirect` path by design. No limiter; CORS `*`; `MAX_LIMIT=25000`. | `_shared.ts:16-20`; `serieList/route.ts:36`; `db.ts:35,59-67` |
| 2.3 | **The peer median is the whole licensed universe.** `bank-brief.ts:82-85` filters only on period and non-null. 2026Q1 universe CAR median 17.1% (n=37) vs big-7 deposit-bank median 15.3% — so every large bank reads "below the field" on capital while sitting at its true peers' median. Dev & inv and new digital banks set the level (max CAR 85.2%). | `BANK_TYPE_BY_TICKER` already holds the grouping |
| 2.4 | **Real ROE uses a subtraction the project already ruled wrong** **[verified]**. `banks/[ticker]/page.tsx:706` does `roeNow - cpi12m`. `real-terms.ts:16-27` documents that shortcut as "1.2–1.8pp adrift" at ~32% CPI and exists specifically to replace it; the fix was applied to `/` and not here. `realRate()` is exported and unused at this call site. | one-line fix |
| 2.5 | **Sector FX net open position nets long against short, then is read as hedging.** `market-risk.ts:100-118` sums *signed* `net_position` and concludes "a small ratio means the sector is well-hedged" — a +₺50bn long and a −₺50bn short cancel to zero. The per-bank heatmap correctly uses \|NOP\| / capital. | BRSA's ratio is per-bank, absolute, weekly-averaged |
| 2.6 | **One LCR/NSFR floor applied to a population it doesn't uniformly bind.** Sub-100 prints at 2026Q1 are EXIM NSFR 92.63, PASHA LCR 93.36, TAKAS NSFR 92.69 — all non-deposit-taking. Also flagged against an *asset-weighted sector average*, which is not a regulatory object. | `liquidity/page.tsx:246,528-545` |
| 2.7 | **`/economy` is a second design system in the first one's shell.** Raw hex from the retired "Editorial" palette across 5 pages + 2 chart components; amber `#f5c518` = 1.63:1, grey 2.54:1, orange 2.71:1 against the sheet — below 1.4.11's 3:1 for a meaningful graphic. | `economy/*/page.tsx`; `BopFlowChart.tsx:70-74` |
| 2.8 | **The aggregate scraper lane has zero tests.** `bddk_api_scraper.py` produces everything `/api/v1` publishes and most of what the sector pages read, with five copy-pasted `_save_*` methods and per-row exceptions swallowed into a `print` — so a systematic parse break returns a low row count and exits 0. | `:164,195,226,269,308`; `:190,221,264` |
| 2.9 | **Charts are mouse-only; no skip link.** `TrendChart.tsx:296-301` drives series isolate/pin entirely via `onMouseEnter`/`onContextMenu` — no focus, no keyboard, no touch. `layout.tsx:106` puts a ~35-link rail before content with no bypass. | WCAG 2.1.1, 2.4.1 |
| 2.10 | **The categorical chart ramp fails a colour-vision check — and rendered, it is worse than the token values suggest.** Recomputed from source (Vienot 1999, CIE76): dark normal-vision chart-1~chart-2 ΔE 11.8; dark deuteranopia c2~c5 7.7 — under the ~15 categorical floor. But multi-series *lines* use hero+context (2 colours), so the real exposure is **stacked areas**, which render every band at `fill-opacity 0.55` over `#171B21`, roughly halving separation again. As rendered on `/deposits`: adjacent 1–3m\|3–6m ΔE **8.9 at normal vision**; 3–6m\|6–12m ΔE **4.7** deuteranopia; the upper four bands were not separable by eye. **And the legend swatches draw at full opacity while the bands are 55%** — the only key on a stacked area is a different colour from the mark it keys. The mobile layer sidesteps all of this by being single-series by construction; the web ships the ramp across 22 render sites. | `globals.css:75-82,126-131`; verified live on `/deposits` |
| 2.12 | **The sticky bank-page header is frosted app chrome in a document-sheet system.** The wrapper is `rgba(0,0,0,0)` with two children at 90%/95% white and `blur(8px)`, so dense content ghosts through behind the bank name. Confirmed in a live capture. A design-language break rather than a defect — but the constitution is "a white sheet on paper ground", and this is the one place the product reads like an app. | `banks/[ticker]/page.tsx:1289` |
| 2.13 | **65 sub-10px text nodes on one page fail as reading, not as contrast.** 18 at 8px, 20 at 8.5px, 26 at 9.5px — all `--faint` mono **caps** with 0.07–0.12em tracking. All-caps at 8.5px removes ascender/descender cues, so it reads as texture to skip rather than a line to read. No WCAG size minimum exists, so this is a legibility finding, not an accessibility one — reclassified accordingly. | verified live on `/banks/AKBNK` |
| 2.11 | **The 45 "Şekil N" labels on `/economy` are a dangling citation naming the wrong organisation.** Not leftover strings — the numbering is non-sequential (budget renders Şekil 1, 5, 4, 3, 2 in DOM order; `METRICS.md:1006-1020` has gaps at 4 and 5), so it is a real reference. `chart-specs.catalog.json` records the referent per chart: **Albaraka Türk's Turkish macro research notes** — not TCMB, not TÜİK, both of which use "**Grafik N**" and never "Şekil N". So the page prints a Turkish figure number above a TÜİK/Treasury source footer and a reader infers a TÜİK reference that does not exist. Several charts also consolidate a *range* ("Şekil 2–6"), and the notes are periodic, so a bare number isn't stable across editions. Fix: plain-English title; full citation in the footer generated from the catalog — *"Chart after Albaraka, Ödemeler Dengesi (Apr 2026), Şekil 2 · Data: TÜİK"*. `lang="tr"` marks up a reference that still doesn't resolve; translating destroys a real one. | `chart-specs.catalog.json`; `budget/page.tsx:285-347` |

**Accessibility verdict, stated plainly: this product would not pass a WCAG 2.2
AA review today.** Failing with cause: 2.4.1, 2.1.1, 1.4.1 (`delta-badge.tsx:52-53`
hides direction in an `aria-hidden` glyph and passes the screen reader
`Math.abs`), 1.3.1 (h2→h5 heading skips), 1.4.3, 1.4.11, 2.4.7
(`Register.tsx:298` kills the outline with no replacement), 3.1.2 (45 Turkish
figure labels in a `lang="en"` document, no `lang="tr"` anywhere).

## 3. What the strategy work concluded

The wedge argument was rebuilt twice under challenge and ended somewhere better
than it started.

**BDDK is not a competitor — it is corroboration.** BDDK's FAQ states it
publishes only aggregated data, deliberately, *"to prevent identification of the
institution it belongs to"*, and directs readers to the independent audit reports
for per-bank figures. The regulator is explicitly saying the PDFs are the only
per-bank source it offers. (Qualifier from the domain lens: BDDK's **BdrUyg**
portal is a per-institution *filing repository* — this repo already sources
Takasbank from it — so the distinction is aggregated *statistics* vs
per-institution *filings*.)

**TBB is a real competitor for about a third of the surface.** It publishes
per-bank financial statements as a structured Excel set, quarterly, back to at
least 2018 — which the repo's own external-reports note does not mention — plus
per-bank maturity ladder, interest-rate sensitivity and currency-risk tables.

**But TBB excludes participation banks entirely**, and vendors don't fill the
gap: Fintables, Finnet, Matriks and the broker terminals are built around
BIST-listed issuers sourced from KAP, so **only 11 of 38 banks are covered at
all**. The other ~27 — every state katılım bank, the foreign subsidiaries,
Eximbank, Kalkınma, every digital entrant — are absent from those platforms.

So the defensible position is **"the only structured series for the 27 Turkish
banks no vendor carries"**, on one basis, quarterly, 2022→now. Not "per-bank BRSA
data nobody publishes clean", which is too broad and partly false.

Two consequences the team converged on:

- **The launch claim should be a quantum, not a prevalence.** "57% of filings
  carry a modified opinion" reads as naive to a Turkish banking professional —
  the free-provision qualification is routine boilerplate, and
  `PROJECT_STATE.md:43` already says so. The news is one layer down and already
  in the database: *"₺X of reported Turkish bank profit is discretionary reserve
  movement, per bank, per quarter"* — 581 free-provision rows, 503 holding, 78
  explicit zero, 111 hand-transcribed, 545 captured basis paragraphs. ALBRK's
  ₺7.85bn reversal becomes the worked example, not the headline.
- **Errors on participation banks are uncorrectable by the reader**, because
  there is no second source to check against. That moves §1.4 up the queue well
  above its apparent size.

**Cut list** (nothing here touches a footnote or participation lane): `/funds`
+ 4 TEFAS tables · `/non-bank` ×2 (≈2.9% of banking, two pages for a rounding
error) · `/economy/*` sub-pages, frozen to the ~15 series the banking pages cite
· `/products` unless the change-detector ships — a 2026-07-22 snapshot presented
as current is the one place the project's own honesty standard is violated at
the product level · the BIST/Yahoo lane, on legal grounds ·
`/lab/chart-loading` · the two parked `_` routes.

**Legal, plainly:** TCMB and TBB both permit publication with attribution but
require written permission for commercial use. **Yahoo forbids redistribution
outright and prohibits automated access — that is a live defect today, not a
monetisation one**, and the precedent is already set: the Yahoo tape was stripped
from the mobile app and `/api/app/v1` before the Play listing. Four source
terms pages remain unread — **BDDK, KAP, TEFAS, TKBB** — and `/api/v1` is
BDDK-only, so the single highest-stakes page is one of the unread ones.

**A derivative-work question surfaced that is separate from the data terms.**
`chart-specs.catalog.json` documents, in this repo, that a set of `/economy`
charts reproduces Albaraka Türk's research-note figures — same charts, sometimes
the same numbering and order. The underlying EVDS/TÜİK series are ours to use
with attribution; the **selection and arrangement** of which figures to publish
is another house's editorial work. Worth assessing alongside the BDDK/TCMB/BIST
review — and it is a second, independent reason to fix §2.11.

**`/api/v1` is not a commitment.** No keys, no registered consumers, no SLA, no
evidence anyone has called it — and it serves none of the wedge, being BDDK-only
sector aggregates. Flipping `PUBLIC_API_DISABLED` is an acceptable response to
abuse. Build no limiter yet; add the counter that would tell you abuse is
happening, since *unmonitored* is the actual defect. If one is built later, a
token bucket rather than an API key — a key destroys the `openapi.json` →
ChatGPT Action discoverability path, which is the only real distribution
property the API has.

## 4. Claims that died under cross-examination

The point of the exercise. Each of these would have shipped from a single-pass
review.

| Claim | Raised by | Outcome |
|---|---|---|
| "A concrete bug will break every admin dispatch" (stale repo name in `github.ts:11`) | prior audit | **Overstated.** GitHub keeps the rename redirect — verified 301 to the repo id — and fine-grained PATs bind to repo id, so token scope survives a rename. Real hygiene issue, not a breakage. POST path left explicitly unverified rather than inferred from the GET result. |
| `parse_amount` returning `0.0` for a dash violates "null is not 0" | engineering | **Withdrawn by its author, then fully refuted on domain grounds.** The BRSA templates are a uniform chart of accounts: every line is printed by every bank whether or not it has a balance, so a dash is an *affirmative nil from the filer*, and `0.0` is the faithful transcription. The code doesn't merely assume it — `extractor.py:240-258` reconstructs a dropped dash only when the row's own identity confirms it (TL + FC = Total foots, roman subtotal = Σ children foots) and returns `None` otherwise. See below: the project already implements the correct three-tier rule. |
| `_save_loans` falsy-zero "falls through to a different column" | prior audit | **True but mis-described.** `ToplamTp` appears nowhere else in the repo, so the operative term is `get_val("Tp")` and a numeric `0` yields **NULL, not another column's value** — the safer direction. Still a rule violation. Whether it fires at all depends on whether BDDK cells arrive numeric or as strings; unverified. |
| "A single scraper is a bigger cost event than a year of readers" | product | **Retracted with arithmetic.** ~18 billion rows read to match the $18 write overage; a serieList scan touches ~20k rows, so ~10 req/s sustained for a day. A deliberate campaign, not a stray crawler. Correct framing: unbounded and unmonitored, with *availability* as the risk — same D1 instance as the dashboard. |
| "Per-bank BRSA data nobody else publishes clean" is the wedge | repo's own strategy doc | **Partly false.** ~⅓ of the per-bank surface duplicates TBB's Excel set. Repricing ladder and FX position are published per-bank by TBB — and the repricing lane is 30/38, missing 8 of the 9 participation banks, so it duplicates almost exactly where TBB covers and is absent almost exactly where TBB doesn't. |
| "57% of filings carry a modified opinion" is the launch story | product | **Would land as naive.** Free-provision qualification is routine and known; the repo's own `PROJECT_STATE.md:43` says the practice is sector-wide and all three firms qualify over it. Replaced with the quantum. |
| Ship swap-adjusted NIM as `6.2 + 6.3`; the conventional-vs-participation asymmetry is structural | analyst methodology | **The defect is real; the fix is not, and the asymmetry is an artifact.** KUVEYT carries the largest derivative loss in the sample (−42.6bn, exceeding AKBNK's and GARAN's) — participation banks run large FX-hedging books too. The positive deltas reflect which side of a near-cancelling pair dominated in one quarter, i.e. trading profit folded into a margin metric. The proxy also over-corrects (customer FX revenue, structural-position revaluation) and is the difference of two 25–47bn legs netting to 5–9bn, so it won't reproduce. Market-standard swap cost is a treasury disclosure, not a P&L line — not derivable from filings at all. What survives: the **denominator** fix (interest-earning, not total, assets), which needs no judgement call. |
| The sticky bank-page header likely obscures focused elements (WCAG 2.4.11) | design | **Retracted after a live check.** 15 content focusables parked above the fold and scrolled back; 0 landed under the 151px pinned band. Passing — though incidentally: `scroll-padding-top` is unset, so it is Chrome's sticky-aware scrolling doing the work, not the page. The live check found a different issue instead (§2.12) and showed the ramp is worse than the token values implied (§2.10). |
| Repricing covers "exactly the 9 participation banks" | analyst methodology | **30/38, and 8 missing — DUNYAK is a participation bank that does file it.** The argument stands and slightly strengthens: the participation lane is the thinnest-covered and least checkable by a reader. |
| `heatmap.ts` is a third roman-ordinal bypass, and a co-occurrence rule is the gate | **team lead** | **Wrong on both counts.** `heatmap.ts:276-281` documents the ordinal keying as deliberate and corpus-verified (1050/1050 partitions), routing only the demonstrably unstable roles through the table. The co-occurrence gate would have passed the two real offenders' worst sibling and taught the wrong lesson. Replaced with the inventory + stability design in §6. |

Two further self-corrections worth recording: the design lens reported ΔE 11.8
where the repo's note said ~6.1 and identified the cause as a metric difference
(CIE76 vs ΔE2000) rather than claiming the note was wrong; and the domain lens
found `standard_lines.ts:144-153` claims verification "across all six
participation banks" when there are now nine — comment stale, code correct for
all nine.

## 5. What the team credited

Not flattery — each of these was checked.

- **BRSA groups vs IFRS stages, never conflated.** `credit_quality.py:251-267`
  carries III/IV/V positionally with Stage 3 = `total_amount` and the comment
  *"NEVER read npl_brsa_*.stage1_amount as Stage 1."* Most data products flatten
  exactly this, and the flattening is invisible downstream.
- **Takasbank carried but not counted** — excluded at the point rows become one
  number (`peersOnly`/`peerExclusionSql`), not at the fetch, so `/banks/TAKAS`
  still shows its own real ratios. Correct call, correct choke point, reasoning
  written down.
- **Capital aggregation matches coverage per component** (`audit-ratios.ts:57-102`),
  fixing a real published error (CET1 10.56% vs true 11.79%).
- **Participation profit-share is not forced into an interest shape.** Verified at
  both places it could be: labels name "Interest / Profit Share" and "Deposits /
  Funds Collected", and the margin engine keys sub-codes 1.1/2.1 which align
  line-for-line across the two templates through 2.6.
- **The screen-reader chart alternative is derived from the chart's own data**
  (`chart-csv.tsx:28-76`), so it cannot drift from what is drawn — the defect
  hand-written alt text has by construction. Capped at 60 rows with the reasoning
  written in.
- **Dispatch injection hardening done end to end** — closed-set validation, then
  `env:` into a bash array, with the reason in the comment. Most repos splice
  `${{ inputs.x }}` into `run:`.
- **CI that measured its own blind spot** — `ci.yml:22-41` records that 86
  extractor tests had never run because `pymupdf`/`pandas` were absent (308→394
  passing), and fixes it by pinning deps rather than adding a decorative
  `importorskip`.
- **The three-tier nil rule is already implemented correctly, and nobody wrote it
  down.** An *amount* dash → `0.0`, row kept (`parse_amount`, called only from the
  two note-table lanes, never from the BS/P&L face). An *unparseable or absent*
  cell → `None`, and `extractor.py:151,563` drops the row — "skipped, better lost
  than corrupted". A *ratio* dash → `None`, via a separate parser
  (`capital_adequacy.py:160-165`, selected at `:298`). That third tier is the one
  that matters most and the one a careless refactor would destroy: a dash against
  NSFR means "not subject to this regime", and `0.0` there would be a solvency
  statement about a bank that is simply outside the rule. Whoever wrote
  `_parse_ratio` understood the distinction. Documenting the three tiers is the
  real hardening task — not changing any of them.
- **De-cumulation and TTM are correct throughout**, and free-provision-adjusted
  ROE returns null when either endpoint is absent.
- **The mobile app is a re-conception, not a shrunken dashboard** — ~30 routes to
  four questions, hover replaced by a touch-scrub that writes into the headline
  figure rather than a thumb-occluded tooltip.

## 6. Recommended order

1. **Capital thresholds** (§1.1) — half a day, removes the site's most
   consequential false claim.
2. **Gate the deploy on CI** (§1.3) — ~1 hour, makes a documented rule true.
3. **Close the contrast-gate holes** (§1.5) — ~30 lines, converts a whole class
   from vigilance to CI.
4. **Restore the zeros in `total_tl` / `total_fx`** (§1.6) — scoped to two
   columns in the loans loader, with four working columns as the reference.
   19,139 legally-mandated zeros currently render as ignorance. Backfill needs a
   re-derive from `raw_api_responses`, which is already stored verbatim; watch
   the write budget and re-stamp only changed rows.
5. **Join `bank_audit_pl_roles` in `standard_lines.ts` and `pl-sankey.ts`**
   (§1.4) — a day; the exposed filers are the ones with no second source.
   Pair with the fixture check that would actually have caught DUNYAK 2024Q4:
   feed the sankey transform a compressed-template row set and assert no
   `contra: true` node carries a positive profit. ~2 hours, build it first.
6. **A definition note on NIM, cost/income and consolidation basis** (§1.2) — a
   paragraph. Highest credibility-per-word in the list: it converts "their data
   is wrong" into "their definition is different" for any professional who tries
   to reconcile. Do this before any launch.
7. **Strike NIM on average interest-earning assets, not total assets** (§1.2) —
   computable from stored rows, wrong by every convention today, and the one part
   of the NIM finding that needs no judgement call. Do **not** ship a
   `6.2 + 6.3` swap adjustment; surface trading & FX as its own line instead.
8. **Peer-group parameter on `peerStat`** and **`realRate()` at
   `page.tsx:706`** (§2.3, §2.4) — two one-liners.
9. **Read BDDK's terms; pull the Yahoo feed** (§3) — five minutes and a day. The
   terms check may moot other work.
10. **Make schedule state observable** (§2.1) — ~2–3 hours, closes freeze
   blindness permanently rather than for one date.

**A gate for the roman-ordinal class** (§1.4). Two earlier designs failed and
the reason is instructive. A flat literal ban is unworkable — the template
catalog legitimately declares ordinals. A co-occurrence rule ("any file with a
roman literal that queries `bank_audit_profit_loss` must also reference
`bank_audit_pl_roles`") also fails, because `heatmap.ts` does both ten lines
apart *by design*: `:276-281` states that III/VIII/IX stay ordinal-keyed on
purpose — net-interest is III and gross-operating is VIII in 1050/1050
partitions, verified rather than assumed — while the three lines whose ordinals
were *demonstrated* unstable (`period_net`, `opex_personnel`, `opex_other`) are
resolved through the table, with the DUNYAK failure that motivated it recorded at
`:262-274`.

So the tally is **two active bypasses** (`standard_lines.ts`, `pl-sankey.ts` —
hardcoding ordinals whose instability is already proven) **plus one deliberate,
verified, unmonitored exception** (`heatmap.ts`). The defect in the third is not
the literal — it is that *"1050/1050"* is a claim with no expiry. Nothing
re-runs it, the universe went 31→38 during this project, and a single new
compressed-template filer silently invalidates the premise.

Hence: make the verification recurring rather than banning the literal.

- **Part A — inventory gate** (offline, PR CI). Strip comments, scan
  `web/app/lib/**/*.ts` for roman-ordinal literals, diff against a committed
  inventory of `file:line:ordinal` + reason. A *new* literal fails; registering
  one is a deliberate act. False positives are impossible by construction. ~2h.
- **Part B — stability gate** (live D1, in the audit workflow). For every ordinal
  in that inventory, assert against `bank_audit_pl_roles` that it maps to exactly
  one role across all partitions. The moment a filer breaks it, CI names the
  bank, the period and the consuming `file:line` — before anything renders. This
  is `heatmap.ts:277`'s "verified, not assumed", re-verified on every audit run
  instead of once. ~3h, and it needs an offline test on synthetic rows, since
  live-D1 gates in this repo currently have none.

Part B is what protects the latent case; Part A exists to keep Part B's input
honest. Build the `pl-sankey` fixture first regardless — it is the only one of
the three that catches the *rendering* bug.

## 7. Open and unverified

- **By how much `6.2 + 6.3` over-corrects.** The direction is established
  (customer FX revenue and structural-position revaluation are both inside it);
  the magnitude cannot be sized from the filings. Relevant only if a labelled
  proxy is ever shipped — §1.2 recommends not shipping one.
- **The BDDK LCR/NSFR *yönetmelik* scope article** behind §2.6 — whether the
  regime formally exempts non-deposit-taking institutions, or merely binds them
  differently. Needs the regulation text, not the repo.
- **Vendor coverage** (11 of 38) is characterised from domain knowledge, not a
  subscription check. It now carries the strategic argument and needs one
  verification before it goes in writing.
- **TBB's Excel set beyond BS/P&L** — JS-gated, could not be opened. OCI,
  cash-flow and equity-change may also be duplicated.
- **Whether 2.4.11 keeps passing.** It passes today (§4), but only because
  Chrome's sticky-aware scrolling does the work — `scroll-padding-top` is unset,
  so nothing in the page guarantees it. Setting it would make the pass
  intentional rather than incidental.
*(Resolved during the review and moved out of this list: whether a printed dash
asserts nil — yes, see §4; whether `_save_loans`' falsy-zero fires — it does,
19,139 times in one table, see §1.6.)*

## 8. Method note

Five agents, one lens each, briefed independently and told their reports would be
attacked by the others. Cross-examination was routed by the team lead rather than
broadcast, so no agent saw another's thesis before forming its own. Load-bearing
claims were sent back to their authors for primary-source verification —
which is how the BDDK correction, the TBB Excel discovery and three of the six
retractions in §4 were produced.

The pattern worth keeping: **agents defend claims they should retract when asked
"are you sure", and retract them when asked "go check the primary source."** Every
retraction in §4 came from the second kind of question.

The team lead's own framing was corrected once, by the engineering lens, on the
roman-ordinal gate — recorded in §4 alongside the rest. A review where only the
reviewers are checkable is missing its most load-bearing participant.
