---
name: research
description: Produce a source-backed, dated research report that outlives the conversation. Use only when the user explicitly asks to research, survey, compare, or write a report. Covers repository and external evidence, gives an answer-first summary, and writes one document under docs/knowledge. For a conceptual question whose deliverable is only a chat answer, use deep instead.
---

# Deep research

Use this skill only when the requested deliverable is a durable research
artifact. A broad-sounding question is not enough by itself.

## Confirm the deliverable

Establish:

- the precise question and intended reader;
- the decisions the report should support;
- the minimum useful section structure;
- what evidence would falsify the likely conclusion.

If the user only wants an answer in chat, use `deep`. If the request is
ambiguous and the artifact would materially expand the work, ask whether they
want a report before creating one.

## Gather current evidence

Separate repository evidence from external evidence.

For repository claims, use this precedence:

```text
current code and configuration
  > docs/PROJECT_STATE.md
  > other current repository docs
  > dated investigations, summaries, and memory
```

Treat prior notes and memory as retrieval hints, never as proof. Re-open the
current source before repeating a claim about code, data state, schedules,
costs, or deployed behavior.

For external claims, use current primary or authoritative sources wherever
possible. Record the page title, URL, access date, and the exact claim it
supports. Clearly separate sourced facts, repository observations, and
inference. Say when a source could not be accessed or a premise could not be
verified.

Use parallel agents only when the investigation genuinely partitions into
independent facets and the current request plus active agent policy authorize
delegation. Invoking this skill does not itself authorize agents or a workflow.
Collect the evidence before synthesizing; do not edit the report piecemeal as
results arrive.

## Test the emerging conclusion

Deliberately look for:

- evidence that the recommendation is wrong;
- a different project, period, population, or definition hidden in a source;
- silent-success cases where a job exits cleanly without producing the expected
  data;
- identities that can pass with the wrong unit, source, or interpretation;
- negative findings that narrow the decision.

Do not evaluate an external proposal until checking whether the repository
already implements some or all of it.

## Write one durable report

Create `docs/knowledge/YYYY-MM-DD-<slug>.md`. Begin with a status blockquote
that states what was investigated, the evidence date, and whether anything in
the repository was changed.

Recommended structure:

1. answer or recommendation;
2. decision context and scope;
3. evidence and findings;
4. counter-evidence and alternatives;
5. limitations and unverified claims;
6. recommended next action;
7. sources.

Use repository file references and direct source URLs close to the claims they
support. Keep the report useful without the chat transcript.

Write the report once after synthesis. Do not update auto-memory or create a
memory pointer. Do not stage, commit, push, deploy, dispatch a workflow, or fix
adjacent code unless the user separately asks for those actions.

## Deliver in chat

The final reply must stand on its own. Lead with the headline finding, then
summarize the decisive evidence, the most important limitation, and the report
path. Do not make the user open the file to learn the answer.

## Operational boundaries

- Research is read-only apart from the requested report file.
- Heavy extraction, backfills, and production data movement belong in GitHub
  Actions and are outside a research request.
- Never assume schedules or deployment state from an old note; inspect current
  workflows and operations documentation.
- Do not write to D1, R2, production caches, or external systems as part of a
  research pass.
