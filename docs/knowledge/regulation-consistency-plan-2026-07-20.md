# /regulation consistency — root cause and end-to-end plan

**Date:** 2026-07-20 · **Status:** PLAN — not started, awaiting go
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
