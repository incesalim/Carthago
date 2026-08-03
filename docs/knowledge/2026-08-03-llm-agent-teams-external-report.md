# LLM agent teams for Carthago — external report, reconciled

**Status: received, not adopted.** An outside architecture report, recorded here
with a reconciliation against what this repo actually does. No code was changed
and nothing below is a decision — it is the report plus the diff against
reality, so the decision can be made on facts.

## Provenance

- *"LLM Agent Teams for Carthago — a practical architecture, implementation plan,
  and use-case roadmap for carthago.app"*, prepared 3 August 2026.
- Google Drive: [Doc][doc] · [PDF][pdf] (identical content, same folder).
- Produced in a ChatGPT session. **Written without repository access** — the
  report says so itself in §1: no GitHub connector was exposed and public search
  found no indexed Carthago repo, so it "avoid[s] guessing the current language,
  database schema, deployment provider, or directory structure" and offers both
  a TypeScript and a Python route. Its evidence base is the deployed
  `carthago.app` site plus framework documentation.

[doc]: https://docs.google.com/document/d/1XYgo-mr1Mk88VscgKt4mQymloW6WHQ-KVf3DrXP2FHM/edit
[pdf]: https://drive.google.com/file/d/1Q0FvH5DpIv6fuQHA4lryWknd85XgHOsV/view

## What it recommends

**Thesis.** Start with *one* controlled analyst agent holding typed, read-only
tools — not a team. Numbers come from code and data tools; language comes from
the model. Every answer carries as-of date, period, entity, unit, source lineage.
Add an agent only when it brings a distinct capability, information boundary,
independent check, or parallel workstream that can be *measured*.

It grounds the anti-team argument in three papers: Cemri et al. (arXiv:2503.13657)
on 14 recurring multi-agent failure modes; Google Research (arXiv:2512.08296) on
gains for parallelizable tasks but degradation on sequential ones, with
centralized coordination containing error propagation better than independent
agents; Tran & Kiela (arXiv:2604.02460) on single agents matching or beating
multi-agent systems at equal thinking-token budget.

**Topology.** Centralized coordinator calling specialists as tools, then a
deterministic validator — for the public query path. An explicit workflow graph
with checkpoints, retries and human approval — for ingestion/publication.

**First build (§16).** A chart-scoped "Explain" endpoint: browser sends question
plus chart context → server validates the context and calls one or two read-only
metric tools → a single analyst agent drafts → a deterministic validator checks
every numeric claim, unit, period and source → UI renders with source and as-of
badges → traces and feedback feed an eval pipeline. Only after that passes an
accuracy gate does a coordinator get to invoke specialists.

**The ten read-only tools (§8.1).** `get_metric_definition`, `get_metric_series`,
`compare_entities`, `get_rankings`, `calculate_change`, `evaluate_flag`,
`get_source_record`, `get_source_excerpt`, `get_data_freshness`,
`get_release_calendar`.

**Roadmap (§14).** Phase 1 internal prototype — five read-only tools, one analyst
agent, 50 golden questions, full traces, no write capability. Phase 2 public chart
explainer with shadow testing. Phase 3 specialists for deep research. Phase 4
checkpointed ingestion/publication workflow with human approval.

**Explicit no-go list (§5).** Autonomous investment recommendations, an
unrestricted SQL agent over production data, a public agent that freely browses
the web and blends unsourced commentary with Carthago figures, debate-style teams
per query, and any agent that edits published metrics without approval.

## Reconciliation with this repo

### Already true — the report is describing us, not proposing a change

| Report recommendation | Where it already lives |
|---|---|
| "Numbers come from code and data tools; language comes from the model" (§4.1) | `AGENTS.md` — *No LLM sets a number*; CI-gated by `scripts/check_prose_claims.py` |
| No unrestricted SQL agent (§5, §8.2) | `web/app/lib/bot-sql.ts` read-only gate on the Telegram Q&A bot |
| Distinguish observed / calculated / flagged / interpreted (§4.1) | The perspective layer (`insights.ts`) is editorial-only over computed rows |
| `null` ≠ missing ≠ 0 in every answer | `AGENTS.md` — *`null` is not `0`*, enforced extractor → validator → API → both UIs |
| Deterministic pipelines produce trusted data; agents interpret over them (§2.2) | The whole Python ingestion lane; extractors are deterministic `fitz` anchors, never an API agent |
| Release-calendar awareness (§8.1) | `scripts/check_calendar_fresh.py` plus the release-calendar lane |

So the report's *hardest* recommendation — the one it spends most of its
credibility on — is already the standing rule here, backed by a CI gate rather
than by a prompt. That is worth knowing before treating this as a work plan.

### Genuinely new

1. **A typed read-only tool layer.** Ten small, enumerated, source-linked tools
   is the real deliverable. Nothing today exposes metric access to a model
   through a typed contract with unit/period/source/freshness in the return
   envelope.
2. **The chart-scoped "Explain" endpoint.** The UI already knows each chart's
   data payload, so the agent receives a bounded evidence package instead of
   searching a database. This is the cheapest safe surface and the report is
   right that it is the correct first cut.
3. **A golden evaluation set.** 100–200 questions with numeric-exactness and
   citation-precision thresholds as a release gate, plus a mandatory comparison
   of any multi-agent design against a single-agent baseline *at equal budget*.
   We have per-lane validators; we have no eval harness for generated prose.
4. **The metric registry it wants is not the metric registry we have.** Ours
   (`data/metric_knowledge/registry.json`, loader `scripts/metric_knowledge.py`,
   162 metrics) records *disclosure and reproducibility* semantics — availability,
   cadence, standardization, whether we can reproduce it and from which dataset.
   The report's §6.1 registry wants *computation* semantics — formula, numerator,
   denominator, annualization, allowed comparisons, source priority. Overlapping
   but not the same object. A tool layer needs the second one.

### Doesn't apply as written

- **§15's twelve-question repository audit** is answerable immediately from
  `AGENTS.md` + `docs/ARCHITECTURE.md` + `docs/PROJECT_STATE.md`. The report only
  asks because it could not see the repo.
- **Framework selection (§13)** assumes the stack is unknown. It is not: Python
  ingestion, Next.js 16 on Cloudflare Workers, D1 + R2, GitHub Actions as the only
  scheduler. Its "if Python-first → LangGraph, if TS → OpenAI Agents SDK" fork
  collapses to a straight decision, and neither option accounts for the Workers
  runtime constraint that already killed Cloudflare cron for the extraction lane
  (498 MB + `fitz`).
- **§14 Phase 4** (checkpointed ingestion with human approval) describes a
  scheduler and a state store we deliberately do not own — everything scheduled
  runs in GitHub Actions.
- **Cost/latency budgets** are absent from the report; the D1 write economics
  that dominate every design decision here (rows written ≈ 1000× a read) are not
  a factor it considers.

## Open decisions

1. Build the typed tool layer at all, or leave model access at the current
   editorial boundary?
2. If yes — where does it live given Workers runtime limits, and does it read D1
   directly or go through the existing API surface?
3. Does the "Explain" endpoint ship public, or internal-only behind `/admin`
   first? The report argues public-with-shadow-testing; the no-D1-writes freeze
   and the cost profile both argue internal-first.
4. Does the computation-semantics registry get built as a second file, or does
   `registry.json` grow the formula fields?

## Not related to this document

`docs/knowledge/EVENT-DRIVEN-AGENTS-DESIGN.md`, sitting untracked in the working
tree, is **a different project's design** despite the similar subject. It
describes `vhunter-proxy/src/detectors/`, Polygon bars, equity tickers, Modal
endpoints, a `signal_events` table, auto-trade conviction thresholds and a Graph
Brain — none of which exist here. `vhunter`, `polygon`, `signal_events` and
`InvestigationResult` appear in no other file in this repo. It is misfiled and
should be moved to whichever repo it belongs to, not merged with this.
