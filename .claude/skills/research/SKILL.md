---
name: research
description: Run a wide investigation whose deliverable is a dated write-up that outlives the conversation — surveys, competitive scans, external-report evaluations, "what do X do and can we do it", multi-source sweeps. Fans out agents across repo and web, answers in chat FIRST, then writes one knowledge doc. Requires an explicit ask ("research X", "make a report on X", "survey X") — never entered on inference. For a conceptual question about our own system, use `deep` instead.
---

# Deep research

The heavy path. This skill exists to produce a **document someone reads later**,
and it costs accordingly — a wide fan-out, web sources, a dated write-up in
`docs/knowledge/`, and a memory pointer.

## 0. Entry is explicit, and the answer still comes first

**Only enter on an explicit ask.** "Research X", "make a report on X", "survey
X", "do a deep research on X", "compare us to Y and write it up". A question that
merely *sounds* broad is not an entry ticket — a conceptual question about our own
system is `deep`, and `deep` is the default.

If unsure which one the user wants, ask in one line before spending anything:
*"answer in chat, or a written report?"*

**And even here, the answer comes first.** The chat reply is a real summary that
stands on its own — findings, recommendation, what could not be verified — not
"see the doc". The document is the durable copy, not the delivery mechanism. A
research pass that ends in "written to `docs/knowledge/...`" and nothing else has
delivered nothing.

## 1. Frame the deliverable

Before searching, write down:

- the question, and **who reads the output** — that decides depth and language;
- what a *useful* answer contains, as a section list;
- what would make the write-up wrong, so §4 has something to attack.

If the honest section list is three bullets, this was a `deep` question. Say so
and drop back.

## 2. Fan out — repo and web are different lanes

Launch agents **all in one message** so they run concurrently. Give each a facet
and a breadth ("medium" / "very thorough"), not the whole question.

| Lane | Tool | Typical facets |
|---|---|---|
| This repo | `Explore` | pipeline `src/`+`scripts/`, DB state `PROJECT_STATE.md`+`web/migrations/`, dashboard `web/`, app `mobile/`, schedules `.github/workflows/`, prior work `docs/knowledge/`, gates `scripts/check_*.py` |
| Outside | `WebSearch` / `WebFetch` | regulation in force, upstream terms, what a peer product ships, papers and their actual claims |

Never answer an outside-the-repo fact from the training cutoff. Fetch it, and cite
what you fetched — including when the fetch failed.

**Collect, then write once.** Agent results arrive as separate turns. Hold them.
Do not edit the document as each lands, and do not commit per arrival — that
turns one write-up into a commit log and loses the thread. One synthesis, one
write, one commit, at the end.

Multi-agent **workflows** (the `Workflow` tool) are a further step up and still
need their own explicit ask ("use a workflow" / "ultracode"). If the question
genuinely warrants one, say what it would do and roughly what it would cost, then
let the user call it.

## 3. Precedence and provenance

```
code  >  docs/PROJECT_STATE.md  >  other docs/  >  memory
```

Memory is a map to where to look, never the answer — the entries are point-in-time
and carry age warnings for that reason. Every load-bearing claim in the write-up
carries a `file:line`, a URL, a command output, or an explicit "could not verify".

⚠️ Check the premise before evaluating an external document. Two of these have
already turned out to describe things we **already ship**, and one was about a
different project entirely — see `project_llm_agent_teams_external_report` and
`reference_unrelated_event_driven_agents_doc`.

## 4. Argue the opposite

What would have to be true for the recommendation to be wrong? Look for it
deliberately. The highest-value findings in this repo have all been *silent-wrong*
classes: the validator passed and the number was still wrong, the run exited 0 and
changed nothing, the aggregate footed and the unit had switched.

## 5. Deliver, then persist

**In the chat, in one message:**

1. The recommendation or headline finding, first, in a sentence.
2. The evidence, cited.
3. What came back clean — negative results are findings.
4. What could not be verified, and what it would take.
5. The one open question, if a real fork remains.

**Then, once:** write `docs/knowledge/YYYY-MM-DD-<slug>.md`, opening with a
`> **Status: …**` blockquote saying what was measured and whether anything
changed. Add a one-line `MEMORY.md` pointer and a memory file if the finding is
one a future session must not rediscover. Stage explicit paths — another session
may be committing in this worktree.

Nothing else ships. A research pass does not fix the bugs it finds, refactor what
it read, or open the adjacent work it surfaced — it *reports* them, and the user
picks what happens next.

## Cost discipline

- no heavy execution locally — extraction, backfills and D1 pushes are Actions;
- **no D1 writes**, no drops, crons frozen — propose the work, never run it;
- **Budget: one fan-out round, plus roughly 40 tool calls for verification and
  the write-up.** If that is spent, deliver what is verified and name the gaps.

## Failure modes this skill exists to prevent

- Being entered for a question that wanted an answer, not a report. §0.
- The document replacing the reply. §0, §5.
- Editing and committing the write-up as each agent reports in. §2.
- Evaluating an external document without checking whether we already ship it. §3.
- Fixing things along the way. The deliverable is the report.
