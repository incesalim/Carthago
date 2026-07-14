# The prose audit — "compiled, not written" was only true of the figures

**Date:** 2026-07-14 · **Status:** ✅ SHIPPED (all six commits landed; two CI gates strict)

## What prompted it

The user asked a simple question about the redesigned pages: *"these texts — are they regex or LLM? are they automated?"* The first answer was wrong. The honest one:

> **Almost all the numbers are computed. Almost all the words were typed by hand.**

There is no place on the site where a sentence is assembled from a vocabulary. Every English clause was written once and committed. What the code automated was (a) the *figures* interpolated into those clauses and (b) *which* of two or three hand-written variants a threshold selected.

The colophon on every page — *"Compiled, not written — every figure computed from source series"* — was precise and defensible. The prose was not.

## The audit

Roughly 500 visible strings, in three buckets:

| Bucket | Count | Can it go false? |
|---|---|---|
| **Timeless** — axis descriptions ("tl loans ÷ tl deposits, %, weekly"), methodology, definitions | ~300 | No. Safe. |
| **Guarded** — a ternary/threshold picks between hand-written variants, so it re-selects as data moves | ~170 | Only if the guard tests the wrong quantity — and 6 did. |
| **Unguarded claims** — a hand-typed direction, level or ranking with nothing checking it | **41** | **Yes. Several already had.** |

The root cause was a single missing primitive: **nothing in the repo turned a signed delta into a direction word.** The only verb logic was a non-exported `let verb` block inside `seriesFinding`. Every one of the 41 sat downstream of that gap, which is why they collapsed into six shapes rather than 41 rewrites.

## What was actually broken (not "would go stale" — wrong)

- The homepage told Google **"32 banks' audited BRSA financials"**. The universe has been 38 since TAKAS.
- `/asset-quality` rendered **`+₺-42bn`, in red**, when net NPL formation went negative — the *good* case.
- `/capital`'s chart title said **"Every ownership group fell together"**, off a step detector that picks by `Math.abs` and returns a signed delta. An upward step would have been called a fall. And "every group" was never tested — against `carAll`, the chart's own `data` prop.
- `/liquidity` would print **"Real appreciation of −4.3 over 12 months is what makes holding lira pay"** — the noun typed, the sign computed.
- `/credit` printed **"negative for 0 consecutive weeks"** once real growth turned positive, and coloured a book that *grew* in real terms red.
- `/deposits` claimed **"Every deposit-taking group funds its loan book below the 100% line"** off a guard that only tested the **sector** — while the Standings table on the same page already toned a group red when it breached.
- `/profitability`'s cost/income guard tested the **direction** while the sentence claimed a **level**.
- `/rates` said **"policy cuts reach deposit pricing first"**. In a hiking cycle that is backwards — and `policyYoY`, computed 200 lines above, always knew.
- Five hand-typed `Ahead` schedules (~17 rows). "JUL 23" had nine days left on it.
- `insights.ts` compared equity growth to a typed **"~40% nominal balance-sheet cycle"** with the thresholds 30 and 25 pinned to it — while `assetsYoY`, the actual cycle, was already fetched on the same page.

## The fix

**`web/app/lib/prose.ts`** — the missing primitive.

| Export | Why |
|---|---|
| `direction(delta, words, bands)` | A sign + a scale-aware band picks a word. Null delta → null: it never invents a sign. |
| `VERBS` / `UP_WORDS` / `DOWN_WORDS` | The **closed** vocabulary. Not decoration — the regression gate can only be decisive if the words are enumerable. |
| `claim(holds, then, otherwise?)` | **Three-valued.** An unknown prints *neither* branch. That is how `deposits:920` came to claim a universal off a sector guard. |
| `firstClaim(...)` | The ladder: every rung tests the fact its own sentence states. |
| `signed(v, fmt)` | One sign, in front of the magnitude. Kills the `+{fmt(x)}` class — and puts the minus *outside* the currency symbol. |
| `everyOf(xs, test)` | **FALSE on an empty list**, unlike `Array.every`. A universal claim needs members behind it. |
| `toneClass(v, good)` | The colour follows the sign, so it cannot contradict the number beside it. |

Plus `latestByGroup` / `deltaByGroup` / `leaderOf` in `desk.ts` — which needed **no new data fetch**: the per-group series was already the chart's `data` prop.

`chart-findings.ts` became a client of `direction()`, and **its test passed unmodified** — the refactor's proof.

## The gates (both strict in CI)

1. **`web/app/lib/prose-regression.test.ts`** — the real one. Feeds every insight builder a fixture where every series rises, asserts no falling word comes out; then inverts it. It reads the **output text**, not the code path, so it does not care whether a word came from `direction()` or was typed. *Verified by sabotage:* re-introducing `"— rising, but slowly"` makes it fail; removing it makes it pass.
   - **Known blind spot:** it cannot check words about a *derived* gap or spread — a uniform ramp leaves every difference at zero. (This is why "easing" had to stop meaning "the funding gap narrows": one word cannot mean a falling rate in one sentence and a closing gap in another and remain checkable.)
   - It sees `lib/`, not page TSX. That is deliberate — it forces each claim into a pure, testable function.
2. **`scripts/check_prose_claims.py`** — the cheap net, for what lives in TSX. R1 a hardcoded sign; R2 a `title=` literal asserting a direction/level/ranking; R3 a hardcoded bank count. Escape hatch `prose-ok: <reason>` — **zero in force**. It found three sign bugs the manual audit missed.
3. **`scripts/check_calendar_fresh.py`** — `MPC_DATES` is the only hand-typed forward date left. Fails CI under 90 days of runway, so it cannot quietly run out the way the `Ahead` blocks did. Also ages out `BBVA_BASELINE` at 18 months.

## Decisions worth remembering

- **`/economy`: compute or delete, never quote.** Claims we hold the series for are now ours and recompute. Claims that were causal ("disinflation decelerated *even before the conflict*"), an elasticity ("every 10% rise in energy prices costs ~0.3–0.4% of GDP"), or a report's judgment ("the report flags worsening employment quality") were **deleted**, not attributed. We do not fabricate, and a dated quotation in a `description` prop still reads as methodology.
- **`Ahead` derives, except MPC.** BDDK monthly lands ~day 12 of record+2 (the rule *reproduces the hand-typed row exactly*, which is how we know it's right). The BRSA filing window comes from the KAP lag that already happened — the observed 35–38 days puts Q2 in early August, not the "AUG–SEP" that was typed. Suppressed below 3 observed filings: a window we cannot support is a window we do not print.
- **Fail closed, always.** `null` means "the data supports no sentence I know how to write", and the caller prints the **topic**, not a finding.
- **Don't neuter the voice.** The short declarative claim *is* the product. The fix was to make each claim earn itself, not to replace it with a caption.

## Not done

- The regression suite covers `lib/`, not rendered pages. A claim typed straight into a page's `<p>` body is caught by R2 only if it sits in a `title=`.
- `bank_earnings` holds just 5 `results_filing` rows (one quarter, listed banks only), so the filing window is thin. It states its own basis and `n`.
- Stale counts survive in **code comments** (`bank-brief.ts:14` "8 of 36 banks", `heatmap.ts:78` "30 banks"). They mislead the next reader but tell the user nothing; R3 deliberately skips comment lines.
