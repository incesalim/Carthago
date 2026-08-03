---
name: deep
description: Answer a conceptual or architectural question with a verified deep pass instead of a one-turn answer — frame the question, fan out Explore agents, check every load-bearing claim against the current code, argue the opposite, then recommend. Use when the user runs /deep, or asks "why is X built this way", "should we do A or B", "how does <lane/page/engine> fit together", "evaluate/critique X", "is this the right approach". Not for factual lookups — those stay fast.
---

# Deep pass

The default loop answers in one turn. That is right for a lookup and wrong for a
question where two readings lead to materially different work. This skill is the
slower path: **verified reasoning, not more prose.** Length is not the deliverable.

## 0. Check that this is the right tool

Exit immediately and answer fast if the question is a **factual lookup** — a table
name, whether something shipped, which workflow runs a backfill, what a memory
already records verbatim. Spending twenty tool calls on those is the failure mode
in the other direction.

Stay if answering wrong would send work down the wrong path: design choices,
"A or B", critiques, evaluations, anything spanning more than one lane.

## 1. Frame before searching

Write down, in one or two lines:

- the question actually being asked (often narrower or wider than the words);
- **what decision hangs on it** — if nothing changes either way, say so and stop;
- what would have to be true for each candidate answer to be correct.

This is what makes the search targeted instead of a sweep.

## 2. Treat memory as a map, never as the answer

The memory index is large and cheap to recall, which is exactly why it is
dangerous here: it is a set of point-in-time observations, several of them months
old, and they carry age warnings for that reason. Recall tells you **where to
look**. It does not tell you what is true now.

Precedence, when sources disagree:

```
code  >  docs/PROJECT_STATE.md  >  other docs/  >  memory
```

A memory naming a file, function, table or flag is a hypothesis. Confirm the thing
still exists before repeating it back.

## 3. Fan out

For anything spanning more than one file or lane, launch `Explore` agents — **all
in one message so they run concurrently** — one per independent facet. The
standing "don't call the Agent tool unless requested" does not apply inside this
skill; the deep-pass memory is that request.

Give each agent a facet and a breadth ("medium" / "very thorough"), not the whole
question. Facets that usually partition well here:

| Facet | Where it lives |
|---|---|
| Pipeline / extraction | `src/`, `scripts/`, `tests/` |
| What is actually in the DB | `docs/PROJECT_STATE.md`, `web/migrations/` |
| Dashboard behaviour | `web/` → `web/AGENTS.md` |
| Native app | `mobile/` → `mobile/AGENTS.md` |
| What runs, and when | `.github/workflows/`, `docs/OPERATIONS.md` |
| Prior investigation | `docs/knowledge/` (dated write-ups) |
| Invariants and gates | `scripts/check_*.py` — each one exists because something drifted |

If the question depends on facts **outside** the repo — regulation in force, an
upstream source's terms, what a peer product ships — that is a `WebSearch` /
`WebFetch` lane, not a repo lane. Do not answer those from the training cutoff.

## 4. Verify, then argue the opposite

Every load-bearing claim carries a `file:line`, a command output, or an explicit
"could not verify". Two passes:

- **Confirm** — does the code do what the claim says?
- **Refute** — what would have to be true for the recommendation to be wrong?
  Look for that, deliberately. The highest-value findings in this repo have all
  been *silent-wrong* classes: the validator passed and the number was still
  wrong, the run exited 0 and changed nothing, the aggregate footed and the unit
  had switched. A check that only looks for visible failures will miss them.

## 5. Answer

In this order:

1. **The recommendation**, first, in a sentence. Not a survey of options.
2. The evidence, cited.
3. What was checked and came back clean — negative results are findings.
4. **What could not be verified**, named explicitly, with what it would take.
5. The one open question, if a real fork remains. One, not four.

If the pass produced something worth keeping, it goes to `docs/knowledge/` dated
and status-marked, with a memory pointer — a long answer that only exists in a
terminal scrollback was half-wasted work.

## Cost discipline

Deep **reading** is free. Deep **running** is not, and the standing constraints
hold inside this skill without exception:

- no heavy execution locally — extraction, backfills and D1 pushes are Actions;
- **no D1 writes**, no drops, crons frozen — propose the work, never run it;
- rows written to D1 are ~1000× the price of a read;
- multi-agent **workflows** still need an explicit ask ("use a workflow" /
  "ultracode"). If the question genuinely warrants one, say what it would do and
  roughly what it would cost, then let the user call it.

## Failure modes this skill exists to prevent

- Answering from the memory index alone, fluently and out of date.
- Surveying options instead of recommending one.
- Treating length as depth — five verified lines beat five unverified paragraphs.
- Confirming only. If nothing was checked that could have falsified the answer,
  the pass has not happened yet.
