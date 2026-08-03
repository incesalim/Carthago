---
name: deep
description: Think hard about a conceptual or architectural question and answer it in chat — frame the question, verify every load-bearing claim against the current code, argue the opposite, then recommend. Use when the user asks "why is X built this way", "should we do A or B", "how does <lane/page/engine> fit together", "evaluate/critique X", "is this the right approach", "think harder about this". Produces an ANSWER, never a file. Not for factual lookups — those stay fast. Not for surveys whose deliverable is a document — that is `research`.
---

# Deep thinking

The default loop answers in one turn. That is right for a lookup and wrong for a
question where two readings lead to materially different work. This skill is the
slower path: **verified reasoning, not more prose.** Length is not the deliverable.

## 0. This skill produces an answer, not an artifact

**Hard rule: a deep-thinking pass writes no file and makes no commit.** Not a
knowledge doc, not a memory, not a scratch note that becomes one. The whole
output is the reply in the terminal.

If the pass turns up something worth keeping, *say so in one line at the end and
let the user decide*. Do not write it and mention it afterwards.

This rule is not a style preference. It exists because the first version of this
skill said the opposite — "a long answer that only exists in a terminal
scrollback was half-wasted work" — and its first run produced 9 commits to one
document, two unrelated code fixes, and a user asking "what was my question" two
hours later. See `docs/knowledge/2026-08-03-instruction-drift-session-audit.md`.

## 1. Check that this is the right tool

Three ways out, all cheap:

| If… | Then |
|---|---|
| It is a **factual lookup** — a table name, whether something shipped, which workflow runs a backfill, what a memory records verbatim | Exit and answer fast. Twenty tool calls here is the failure in the other direction. |
| The deliverable is a **document that outlives the conversation** — a survey, a competitive scan, a dated write-up someone reads later | That is `research`, and it needs an explicit ask. Say so and stop. |
| Answering wrong would **send work down the wrong path** — design choices, "A or B", critiques, anything spanning more than one lane | Stay. |

The test for the middle row: *what does the user walk away holding?* An
understanding → think. A file → research. When it is genuinely both, think first
and offer the file at the end.

## 2. Frame before searching

Write down, in one or two lines:

- the question actually being asked (often narrower or wider than the words);
- **what decision hangs on it** — if nothing changes either way, say so and stop;
- what would have to be true for each candidate answer to be correct.

This is what makes the search targeted instead of a sweep.

## 3. Treat memory as a map, never as the answer

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

## 4. Read, and fan out only if the question genuinely spans lanes

Most thinking questions are answered by reading three or four files well. Reach
for agents when the question truly covers separate areas — then launch **at most
three `Explore` agents, all in one message** so they run concurrently. The
standing "don't call the Agent tool unless requested" does not apply here; the
deep-pass memory is that request.

Facets that partition well in this repo:

| Facet | Where it lives |
|---|---|
| Pipeline / extraction | `src/`, `scripts/`, `tests/` |
| What is actually in the DB | `docs/PROJECT_STATE.md`, `web/migrations/` |
| Dashboard behaviour | `web/` → `web/AGENTS.md` |
| Native app | `mobile/` → `mobile/AGENTS.md` |
| What runs, and when | `.github/workflows/`, `docs/OPERATIONS.md` |
| Prior investigation | `docs/knowledge/` (dated write-ups) |
| Invariants and gates | `scripts/check_*.py` — each one exists because something drifted |

**Collect, then answer once.** Agent results arrive as separate turns. An arrival
is *not* a task. Do not act on one when it lands — hold it, wait for the rest,
spend them all in a single answer at §6. Servicing completions one at a time is
how a question turns into a commit log with no answer in it.

A fact from **outside** the repo — regulation in force, an upstream source's
terms, what a peer ships — is a bounded `WebSearch`/`WebFetch` lookup, one or two
calls. Do not answer it from the training cutoff, and do not let it turn the pass
into a survey. If it needs more than that, the question was a research question.

## 5. Verify, then argue the opposite

Every load-bearing claim carries a `file:line`, a command output, or an explicit
"could not verify". Two passes:

- **Confirm** — does the code do what the claim says?
- **Refute** — what would have to be true for the recommendation to be wrong?
  Look for that, deliberately. The highest-value findings in this repo have all
  been *silent-wrong* classes: the validator passed and the number was still
  wrong, the run exited 0 and changed nothing, the aggregate footed and the unit
  had switched. A check that only looks for visible failures will miss them.

## 6. Answer — to the user, in the reply, in one message

1. **The recommendation**, first, in a sentence. Not a survey of options.
2. The evidence, cited.
3. What was checked and came back clean — negative results are findings.
4. **What could not be verified**, named explicitly, with what it would take.
5. The one open question, if a real fork remains. One, not four.

Then, optionally, one closing line: *"worth keeping as a knowledge doc?"* — and
stop. The user answers that, not you.

## Cost discipline

Deep **reading** is free. Deep **running** is not, and the standing constraints
hold inside this skill without exception:

- no heavy execution locally — extraction, backfills and D1 pushes are Actions;
- **no D1 writes**, no drops, crons frozen — propose the work, never run it;
- rows written to D1 are ~1000× the price of a read;
- multi-agent **workflows** still need an explicit ask ("use a workflow" /
  "ultracode").

**Budget: one fan-out round and roughly 25 tool calls after it.** If that is spent
and the question is still open, answer with what is verified and name what is
still unknown (§6.4). A pass that has run an hour without a reply has failed,
however good the reasoning is.

## Failure modes this skill exists to prevent

- Answering from the memory index alone, fluently and out of date.
- Surveying options instead of recommending one.
- Treating length as depth — five verified lines beat five unverified paragraphs.
- Confirming only. If nothing was checked that could have falsified the answer,
  the pass has not happened yet.
- **Answering the file instead of the user.** §0. This is the one that actually
  happened.
- Quietly escalating into `research` because the question was interesting.
