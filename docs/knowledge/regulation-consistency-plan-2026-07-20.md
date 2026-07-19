# /regulation consistency — root cause and end-to-end plan

**Date:** 2026-07-20 · **Status:** ✅ EXECUTED — see §5 for what actually happened
(the diagnosis below was **half right**; the rest was found during execution)
**Origin:** chasing run-to-run variance in the weekly briefing (23/30/32 bullets on
identical input). Related: [openrouter-deepseek-eval-2026-07-19.md](openrouter-deepseek-eval-2026-07-19.md),
[regulation_followups.md](../regulation_followups.md).

---

## 1. The finding: it is not the model. The feed is missing its numbers.

The variance investigation kept pointing at the LLM — temperature, provider,
model choice. All of that was downstream of a data bug.

**`body_text` for TCMB press releases scraped before 2026-05-29 has no tables.**
Table extraction landed that day (`f875a47`), and the body backfill only fetches
rows where `body_text IS NULL OR length(body_text) < 30`. A body that is *present
but truncated* is never re-fetched, so every pre-fix row is frozen without its
table. `sync_news.py --refresh-bodies` exists for exactly this ("Use after a
fetch_body change, e.g. adding table extraction") and has evidently never been run.

**Proven, not inferred.** Re-extracting the live pages with today's code:

| release | stored | re-fetched | what was missing |
|---|---:|---:|---|
| 2026-05-23 Macroprudential Framework | 342 | 679 | the **loan growth limits table** — general purpose 4%→3%, vehicle 4%→3%, overdraft 2%→1%, SME 5%→4.5%, non-SME 3%→2% |
| 2025-12-02 Macroprudential Framework | 673 | 1291 | an **11-row FX reserve-requirement ratio table** by maturity |
| 2026-01-31 Macroprudential Framework | 353 | 553 | **FX loan growth limit cut 1%→0.5%**, new **2% overdraft cap** |
| 2026-01-24 Macroprudential Framework | 714 | 835 | prose tail |

Across the 38 pre-fix TCMB items in the 330-day window: 7 grow materially, and the
material growth is **concentrated entirely in the Macroprudential Framework
releases** — the sole source for *Loan Growth Caps*, *Regulations on RRs* and
*TL Deposit Share*.

**That is exactly where the variance lives.** Those three sections swung
(1–6, 3–8, 3–4) while `Monetary Policy Stance` — fed by prose-only "Press Release
on Interest Rates" items that lose nothing to the bug — sat stable at 5–6 across
every run and every model. The model was not being inconsistent; it was being
asked to report numbers that were not in its context, and it improvised
differently each time.

**Corollary: fix the data before touching the prompt.** Restructuring the lane
first would "fix" a variance whose cause is upstream, on evidence that would then
be uninterpretable.

### Secondary findings

- **Signal-to-noise is ~17%.** Of 87 feed items, ~15 are regulatory (Interest
  Rates ×7, Macroprudential ×6, TL Liquidity, FX Forwards, FX-Protected Deposits).
  The rest: 35 BDDK single-bank licensing decisions, 7 MPC summaries, cleaning-staff
  recruitment ×3, a university paper contest, ceremonial MoUs, data notices. The
  prompt lists these exclusions in prose and asks the model to apply them by
  judgement, five times per run, independently.
- **BDDK adds nothing here.** All 453 BDDK bodies have zero tables, and its
  non-licensing items in the window are journal/HR/data notices. Actual BDDK rules
  live in Tebliğ/Resmî Gazete, which is not scraped — already tracked as
  follow-up (B).
- **The baseline is splittable.** `Monetary Policy for 2026` has `Annex 1` with
  Tables 1–6 mapping near-1:1 onto the section taxonomy (Table 1 → Monetary Policy
  Stance, Table 3 → Deposits, Table 5 → Loans, Table 6 → Credit Programs). ⚠️ The
  tables appear **out of order in the extracted text** (4 before 3), so a splitter
  must cut on *positions*, not table numbers.
- **`moonshot-v1-128k` is a floating alias.** Moonshot can change the weights
  underneath with no commit on our side.

---

## 2. Plan

Four phases with a **decision gate after Phase 1**. Phases 3 and 4 are conditional
on what Phase 1's measurement shows.

### Phase 0 — Measurement harness (prerequisite, ~1h)

Nothing below is interpretable without a baseline and an objective score.

1. **Golden capture.** Freeze the current briefing (D1 `regulation_briefings`) and
   the current 87-item feed as fixtures, so every later change is a diff.
2. **Fact checklist** — the real success metric. From the recovered source tables
   we now know ground truth, so assert *facts*, not bullet counts:
   - general-purpose loan cap **3%**, vehicle **3%**, overdraft **1%**, SME **4.5%**, non-SME **2%**
   - FX loan growth limit **0.5%**
   - FX RR demand/≤1-month **32%**, longer **28%**
   - policy rate **37%**, O/N lending **40%**, borrowing **35.5%**
   - one-week repo auctions **suspended** (2026-03-01)
   A briefing that misses these is wrong regardless of how many bullets it has.
3. **Variance protocol.** 3 runs, same input, count per section + fact-checklist
   hits. This is the number Phase 1 must move.

### Phase 1 — Fix the data (the actual fix, ~2h + CI)

4. **Add `--refresh-bodies --dry-run`** to `sync_news.py`: report per-item
   old/new length and table-char delta, write nothing. Measure before mutating.
5. **Add a shrink guard** to `update_body`: never replace a body with a materially
   shorter one; log every skip. (My 38-item probe saw no shrinkage, but a mass
   overwrite of 717 rows deserves the guard, and a page that changes shape later
   must not silently truncate what we hold.)
6. **Back up** the 717 `(source, external_id, body_text)` rows to R2 before the
   first write. Cheap insurance on the one destructive step in this plan.
7. **Add a `refresh_bodies` input** to `refresh-news-daily.yml` (it has
   `workflow_dispatch: {}` with no inputs today). Verified: `update_body` stamps
   `fetched_at`, and `push_to_d1` windows `news_items` on `fetched_at`, so
   refreshed rows **do** reach D1 on the existing `--hours 30` push.
8. **Run TCMB first (264 rows), verify, then BDDK (453).** Staged, not one shot.
9. **Re-run the briefing.** No `--force` needed: bodies change → `input_hash`
   changes → it regenerates on its own.
10. **Re-measure variance and the fact checklist.**

**Decision gate.** If the fact checklist now passes and per-section variance
collapses, Phase 3 is unnecessary — stop, and keep the cheap wins. If variance
persists, continue with evidence about *what* is still varying.

### Phase 2 — Cheap determinism (~1h, do regardless)

11. `temperature: 0.2 → 0` — sampling on an extraction task buys nothing.
12. Add a fixed `seed` (OpenAI-compatible; supported by Moonshot and DeepSeek).
13. **Pin the model** off the floating `moonshot-v1-128k` alias to a dated
    snapshot if Moonshot publishes one. Silent weight drift is the scariest item
    on this page and the fix is free.
14. Bump `PROMPT_VERSION` (it feeds `input_hash`, so it forces one regeneration).

### Phase 3 — Deterministic routing (~1 day, ONLY if Phase 1 leaves variance)

15. **`src/news/regulation_router.py`** — classify each feed item:
    `_junk` (licensing / HR / ceremonial / data notices) · a named section ·
    or **unmatched**. ⚠️ Must normalise Turkish first — dotless ı/İ folding, as
    `bank_tagger.py` already does. I hit exactly this bug writing throwaway rules:
    two `yayımlanmıştır` items matched a rule that should have caught them and
    survived anyway.
16. **Baseline splitter** — cut `Annex 1` into Tables 1–6 by position, map to
    sections, drop Annex 2 (MPC calendar).
17. **Per-section context** = that section's items + that section's annex table.
    Context falls ~34k → ~3–5k per section: roughly **10× cheaper**, much faster,
    and the model's job narrows from "decide what belongs" to "render this set".
18. **`Other Regulatory Actions` = the residual** — deterministic by construction.
    The worst-varying section stops being a judgement call.
19. **Unmatched items are logged and alerted, never dropped.** The allowlist
    failure mode is a new TCMB release type vanishing silently; after this week,
    it should page instead.
20. Rewrite `PER_CATEGORY_SYSTEM` for a pre-filtered set; bump `PROMPT_VERSION`;
    validate against the Phase 0 golden **section by section**, not all at once.

### Phase 4 — Guardrails (~2h, do regardless)

21. **Alert when a section that had bullets last week has none now.** Today a
    zero-bullet section is dropped with no error and `SystemExit` fires only if
    *every* section is empty — a partial provider failure ships a quietly shorter
    briefing. Third instance of this shape found in two days.
22. **Body-staleness check** in `healthcheck.yml`: sample N recent items, compare
    live-page extraction length against stored, alert on material divergence.
    This is the check that would have caught the present bug in May.

---

## 3. Risks

| risk | mitigation |
|---|---|
| Mass body overwrite degrades a good row | shrink guard + dry-run + R2 backup + staged TCMB→BDDK |
| 717 fetches trip TCMB rate limiting | existing 8-worker path, one-off, staged; back off on non-200 |
| Prompt restructure regresses quality (this lane is at v13 because that has happened) | Phase 3 is gated on Phase 1's result; validate per section against golden; `PROMPT_VERSION` bump makes the change auditable |
| Fixing data changes the briefing users see | it is currently *wrong* — missing published caps and ratios; the change is the point |
| Phase 3 allowlist silently drops a new release type | unmatched → residual section **and** an alert |

**Rollback:** every code change is a revert. The only destructive step is the body
overwrite, mitigated by backup + shrink guard + the fact that bodies are
re-fetchable from source.

**Cost:** trivial throughout — well under $5 of LLM spend across all phases,
dominated by variance runs (3 × 5 sections). The expensive resource is review time,
which is why the plan is ordered to make Phase 3 possibly unnecessary.

---

## 4. Recommendation

**Do Phase 0 + 1 + 2 + 4. Hold Phase 3 behind the gate.**

Phase 1 is the actual bug and is cheap, provable, and independently valuable — the
`/regulation` page is currently missing published rules. Phase 2 is nearly free.
Phase 4 closes a silent-failure class that has now bitten three times in two days.

Phase 3 is a day of work built on a hypothesis (that judgement-noise is the
remaining driver) which **Phase 1 may well falsify**. Building it first would be
the same mistake as blaming the model: acting on the most interesting explanation
rather than the measured one.

---

## 5. What execution actually found (2026-07-20)

The plan's diagnosis was **half right and half wrong**, and building it in the
planned order is what exposed the wrong half. Recording both.

### 5.1 The instrument had to be built before the fix — and it moved the answer twice

`scripts/check_briefing_facts.py` scores a briefing against figures traced to the
release that published them. Its first version asked only *"is the correct number
present?"* and scored the live briefing **92%** — apparently refuting the whole
premise. Reading the actual bullets showed why that was wrong:

> • "8-week growth limit of **5%** for SME loans, **3%** for non-SME, **4%** for
>   general-purpose, **4%** for vehicle; **1%** for FX loans."
> • "**2.5%** monthly growth limit for SME loans, **1.5%** for other commercial…"
> • "Growth limits reduced to **3%** for general-purpose and vehicle, **1%** for
>   overdraft, **4.5%** for SME loans."

Three generations of the same cap, all printed as if in force. **The defect is
contradiction, not omission** — and a checklist that only looks for the right
number scores that perfect. Scoring both the current *and* the superseded value,
per bullet (so "reduced from 4% to 3%" still passes), the real score was **62%**.

### 5.2 The actual root cause: the baseline is a changelog, not a state

`Annex 1: Monetary Policy Decisions Made in 2025` is a **dated decision log** —
its own Table 5 records the FX limit falling 1.5% → 1% → 0.5% across three
entries. The context introduced the whole document as *"annex tables list every
rule in force"*, so the model transcribed log rows as policy. Bullet 2 above is
Table 5, verbatim. The model was doing exactly as instructed.

**Fix:** `split_baseline()` cuts Annex 1 out into a separately-labelled
`DECISION HISTORY (NOT CURRENT)` block, and the prompt gains a
one-value-per-rule rule. Verified against the real document: the 2.5% trap lands
in history, Annexes 2–4 stay in the framework, and the framework's footnote
cross-references still point at the history where they help.

### 5.3 Measured effect — the whole arc, including two steps backwards

Every row is 3 flash runs, Baidu-pinned, on the read-only bench.

| stage | fact score | sections | note |
|---|---|---|---|
| baseline (6 stored briefings) | **46–77%** | 5 | 31-point swing |
| **v14** history split + temp 0 + seed | **85 / 85 / 85** | 5 | swing *vanished* |
| + body refresh (tables restored) | 77 / 92 / 77 | 5 | ⬇ **worse** — see below |
| **v15** pre-baseline feed cutoff | 92 / 100 / 77 | **4** ⚠️ | section silently deleted |
| **v16** decision-log reframe | 92 / — / — | **4** ⚠️ | did not restore it |
| **v17** cutoff reverted | **77 / 92 / 92** | **5** ✅ | **FINAL** — mean 87% |
| v18 worked examples in prompt | 77 / 77 / 92 | 5 | not better → reverted |

**v14 is the win.** The 31-point swing collapsed to zero purely from labelling
the decision log correctly and dropping temperature. Everything after is smaller,
and two steps were negative.

**The body refresh lowered the score and was still right.** Restoring the
2025-12-02 FX reserve-requirement table handed the model a second, older,
equally complete-looking ratio table, and it began printing 30%/26% beside the
current 32%/28%. The stored bodies now match their sources; the briefing has to
learn to prefer the later of two authoritative tables. **Fixing data can expose a
reasoning weakness that missing data was hiding.**

**v15 is the cautionary one.** Cutting pre-baseline feed items scored the best
facts of any stage — and deleted `Regulations for TL Deposit Share` outright. The
baseline does not carry those rules: `Annex 1 Table 3. Decisions Regarding
Deposits` extracts as a bare header, so that section has always been fed by 2025
releases and nothing else. The fact checklist asserts no deposit-share fact, so it
**could not see the loss** and scored the regression 100%.

> A metric that cannot observe a regression will certify it. The checker now
> scores section coverage separately and exits non-zero on an empty expected
> section.

**v18 is a recorded negative result.** Spelling the two supersession traps out as
worked examples is the obvious next move; it measured no better (mean 82% vs 87%,
inside the noise at n=3) and was reverted rather than kept on the theory that it
*ought* to help. Noted so it is not retried on intuition.

(Bullet counts still move run to run — providers do not reliably honour `seed`.
The *facts* are what stabilised, which is what matters.)

### 5.4 What the plan got wrong

- **"~83% of the feed is noise" was wrong, and acting on it would have caused a
  regression.** The 7 MPC Meeting Summaries were classified as noise to exclude.
  They are currently the **only** carrier of the correct loan caps — the
  macroprudential release that published them is truncated, and the summary
  narrates the change in prose. Excluding them would have deleted the right
  answers while looking like a cleanup. **Phase 3's classifier must treat MPC
  summaries as a source, not noise.**
- **The truncated bodies are real but were not the main driver.** They cost the
  authoritative dated tables; the MPC prose compensated. After the history split,
  the *only* two remaining failures — `loan_nonsme` and `loan_fx` — are precisely
  the facts whose primary source is a truncated body, identically across all three
  runs. That is the clean prediction Phase 1b tests.

### 5.5 Shipped

| | |
|---|---|
| `check_briefing_facts.py` | fact checklist; contradiction-aware, per bullet |
| `split_baseline()` + prompt v14 | the fix — changelog no longer read as policy |
| `temperature 0` + `BRIEFING_SEED` | removes sampling noise from an extraction task |
| section-regression alert | a section that had bullets and now has none pages you |
| `check_body_freshness.py` | daily probe; would have caught the table bug in May |
| `update_body` shrink guard | a shorter re-fetch never overwrites a longer body |
| `refresh-news-daily.yml` inputs | `refresh_bodies` + source selector + R2 backup |

**Phase 3 (deterministic router) remains behind its gate, and the gate has
tightened:** the fact score sits at a mean 87% and the residual is attributable to
a known data bug, so the case for a day of routing work is weaker than when the
plan was written — and §5.4 shows the classifier as designed would have made
things worse.

---

## 6. The validation gate (2026-07-20, after "the page is essential")

**Bar changed** from "most runs are right" to **nothing wrong ever ships**. That
second bar is reachable; "every run is perfect" is not, because the model must
resolve supersession across a 34k context and instruction does not make that
reliable (v18 tried; measured worse).

**`src/news/briefing_validate.py`** detects a section stating two values for one
rule. `summarize_regulations.py` regenerates such a section once; if it still
contradicts, it keeps **last week's verified text** and the Telegram post names
the held-back section. A self-contradicting rule cannot reach the page.

**Verified on 3 live runs — the gate fired on every one:**

| run | outcome |
|---|---|
| 1 | `Regulations on RRs` contradiction → retry → still bad → **kept last week's 4 bullets** |
| 2 | contradiction → **clean on retry** |
| 3 | contradiction → retry → still bad → **kept last week's** |

All three published 5 sections with zero contradictions.

### ⚠️ Open: the gate fires *every* run on `Regulations on RRs`

Which means that section never updates — permanently stale, correct but frozen.
Cause: the body refresh restored the 2025-12-02 FX ratio table, superseded by
2026-07-01, and the model prints both. The gate contains the damage; it does not
fix it.

### Two dead ends, recorded so they are not retried

1. **Pre-baseline feed cutoff** removes the 2025-12-02 table and fixes this
   cleanly — and deletes `Regulations for TL Deposit Share`, whose rules exist
   nowhere else (§5.4). Already tried and reverted.
2. **Computing the current value per rule from the feed** to inject as a
   supersession note. The subject matcher works on short generated bullets but
   **not on long source bodies**: run against the real feed it returned
   `loan:vehicle → 39.3, 45.9, 64.1` — market statistics from an 8,000-char MPC
   summary, picked up by the ±90-char proximity window. Any note built on those
   values would confidently assert nonsense.

**What is computable and correct is PRECEDENCE, not value.** The same pass
correctly identifies `rr:fx-short → tcmb:ANO2026-26 (2026-07-01)` as the newest
source. A note that says *"for FX reserve-requirement ratios the latest source is
ANO2026-26 dated 2026-07-01; prefer it over earlier statements"* asserts no
figure and cannot be wrong in the way (2) is. **That is the recommended next
step** — not built, because it needs its own measurement round rather than being
bolted on at the end of this one.

### 6.1 Third instrument bug — the ruler, again

The gated runs scored `policy_rate` and `on_lending` MISSING while the briefing
correctly said *"the policy rate is 37.0%"*. The matcher compared the value as
text with a lookahead, so **"37.0" did not satisfy "37"**. Now tokenised and
compared by magnitude.

That is three instrument bugs in one session — scoring a contradicting briefing
92%, blindness to a deleted section, and this. Every one initially read as a
briefing defect. **When a measurement disagrees with the artefact, suspect the
measurement first.**
