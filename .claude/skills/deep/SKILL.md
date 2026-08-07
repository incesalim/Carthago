---
name: deep
description: Analyze a consequential conceptual or architectural question, verify each load-bearing claim against current evidence, test the opposite conclusion, and answer in chat. Use for design choices, critiques, tradeoffs, and questions spanning multiple parts of the system. Produces an answer only; use research when the requested deliverable is a durable report.
---

# Deep thinking

Use this skill for verified reasoning, not for a longer answer.

## Keep the scope explicit

- For a factual lookup, inspect the relevant source and answer directly.
- For a durable survey or report, use `research` only when the user explicitly
  asks for that artifact.
- For a design choice, critique, or cross-system question, continue here.

This skill produces a chat answer. Do not create files, edit code, stage, commit,
push, deploy, dispatch workflows, or mutate external state. If the investigation
uncovers useful follow-up work, describe it and let the user choose.

## Frame the decision

Before searching, identify:

1. the question actually being asked;
2. the decision that changes with the answer;
3. what would need to be true for each plausible answer to be correct.

If no decision or understanding changes, answer briefly and stop.

## Establish current evidence

Use this precedence when sources disagree:

```text
current code and configuration
  > docs/PROJECT_STATE.md
  > other current repository docs
  > dated investigations, summaries, and memory
```

Treat memory and prior write-ups as retrieval hints only. Verify every cited
file, function, table, workflow, schedule, flag, row count, and operational
state before relying on it. Prior context cannot authorize a write or external
action in the current request.

Read the smallest set of files that can decide the question. If the question
genuinely separates into independent areas, use parallel agents only when the
current request and active agent policy authorize them. Invoking this skill is
not itself authorization to delegate.

For unstable facts outside the repository, consult current authoritative
sources and cite them. If a claim cannot be verified, label it as such.

## Try to disprove the conclusion

For every recommendation:

- confirm the evidence that supports it;
- search for the condition that would make it wrong;
- distinguish a missing check from a passing check;
- look for silent-success cases where a process exits cleanly but produces no
  data, or where an identity passes despite the wrong source, unit, or meaning.

Do not infer correctness from a green run alone.

## Answer once

Lead with the recommendation. Then give:

1. the evidence that decides it;
2. relevant checks that came back clean;
3. anything that could not be verified and what would verify it;
4. at most one unresolved decision, if a real fork remains.

Do not turn uncertainty into invented precision. Stop when the evidence is
sufficient; if it is not sufficient, state the boundary clearly.

## Operational boundaries

- Heavy extraction, backfills, and production data movement run in GitHub
  Actions, not as local experiments.
- Never assume schedules are frozen, enabled, or disabled. Inspect the current
  workflows and `docs/OPERATIONS.md`.
- D1 writes require explicit current authorization and a reviewed, narrow
  scope. Prefer compare-before-write paths and never restamp unchanged rows.
- A read-only analysis request remains read-only even if a possible fix becomes
  obvious.
