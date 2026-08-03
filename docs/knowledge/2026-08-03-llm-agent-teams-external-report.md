# LLM agent teams for Carthago — external report, verified against the repo

**Status: received, not adopted. Deep pass run 2026-08-03; supersedes the first
version of this file, which was wrong in two places (noted in §6).** No code or
data changed. Every load-bearing claim below carries a `file:line`, a command
output, or an explicit "not verified".

## 1. Provenance

- *"LLM Agent Teams for Carthago — a practical architecture, implementation plan,
  and use-case roadmap for carthago.app"*, prepared 3 August 2026.
- Google Drive: [Doc][doc] · [PDF][pdf] (identical content, same folder).
- Produced in a ChatGPT session, grounded in the deployed site plus framework
  documentation.

[doc]: https://docs.google.com/document/d/1XYgo-mr1Mk88VscgKt4mQymloW6WHQ-KVf3DrXP2FHM/edit
[pdf]: https://drive.google.com/file/d/1Q0FvH5DpIv6fuQHA4lryWknd85XgHOsV/view

⚠️ **Its founding disclaimer is a search failure, not an access limit.** §1 says
"public searches did not locate an indexed Carthago repository", and everything
hedged downstream — the TypeScript-or-Python framework fork, the twelve-question
§15 repo-audit checklist, the refusal to name a stack — descends from that one
sentence. `gh repo view incesalim/Carthago` returns `"visibility":"PUBLIC"`,
created 2026-04-19. Every file it says it had to guess at was readable.

## 2. What it recommends

One controlled analyst agent with typed read-only tools, not a team. Numbers from
code and data tools, language from the model. Centralized coordinator calling
specialists as tools, then a deterministic validator. First build (§16): a
chart-scoped "Explain" endpoint. Ten read-only tools (§8.1). Four phases (§14):
internal prototype → public chart explainer → specialist agents → checkpointed
ingestion workflow. Explicit no-go list (§5) including unrestricted SQL agents and
autonomous investment recommendations.

Its three research citations were checked and **all resolve, accurately
characterized**: Cemri et al. arXiv:2503.13657 (14 failure modes, 3 categories),
Kim et al. arXiv:2512.08296 (Google/MIT, 260 configurations), Tran & Kiela
arXiv:2604.02460 (single-agent ≥ multi-agent at matched thinking-token budget).
This is not a hallucinated bibliography.

## 3. What repo access falsifies

### 3.1 Phases 1–2 are already in production

The Telegram Q&A bot **is** the proposed architecture, running in the same Worker.

- *"It runs entirely inside the existing Cloudflare Worker (the Next.js dashboard)
  — no separate server"* — `docs/TELEGRAM_BOT.md:5-6`.
- *"The bot is an **agent loop**, not a fixed pipeline: the model queries the live
  DB to explore and verify, sees each result (or SQL error, or `0 rows`),
  self-corrects, and only then answers. It knows no figures on its own"* —
  `TELEGRAM_BOT.md:15-17`. `MAX_STEPS = 6`.
- Provider chain OpenRouter `nvidia/nemotron-3-super-120b-a12b:free` → Groq
  `openai/gpt-oss-120b` → Cerebras `gpt-oss-120b` → Cerebras `gemma-4-31b`
  (`TELEGRAM_BOT.md:79-80`).
- LLM keys are bound to the **web** Worker today — `CEREBRAS_KEY`, `GROQ_API_KEY`,
  `OPEN_ROUTER_API`, `OPENROUTER_API_KEY` (`web/cloudflare-env.d.ts:32-41`), with
  per-chat and global daily caps (`:42-44`), a no-Telegram test harness (`:46`),
  and independent kill switches for the public and mobile APIs (`:52`, `:60`).

### 3.2 The grounding guard is stronger than the proposed validator

§7.3 wants a validator that semantically matches claims to an evidence package.
`bot.ts` does something structurally better and cheaper:

1. `gotData` tracking — a final answer containing a 4+ digit figure while no query
   has returned ≥1 row is **never sent**; the model is pushed back to querying
   (`bot.ts:158-178`).
2. Separators are stripped *first*, so `43.520.620` collapses to bare digits and
   still trips the test instead of reading as three short numbers (`bot.ts:163`).
3. `groupThousands()` re-groups amounts deterministically with lookarounds that
   leave years, periods, decimals and Turkish decimal commas alone; the model
   never touches the digits (`bot.ts:40-48`).

Fail-closed and structural, versus semantic and expensive.

### 3.3 Its abstention principle is empirically refuted here

§4.1: the agent "should abstain and state the missing input" when evidence is
weak. Measured in `2026-08-02-audit-report-extraction-routing.md:88-90`: three
confidently wrong figures in 80 calls, all with `found=true` — 6,632,553 → 0;
0 → 2,260,614; 449 → 175,010. *"There is no confidence signal to gate on."*
**Abstention must be structural, not behavioral.**

### 3.4 Its release gate assumes a stable score exists

Byte-identical config, temperature 0, fixed seed, calls 2s apart: **22, 21, 20,
17** out of 22 (`:98-100`). *"One benchmark run supports any conclusion."*

### 3.5 Its only extraction use case is the one already tested and closed

§5F proposes LLM extraction of structured fields from filings. Vision: best 53%
of rows exact where 100% is required, failures inconsistent — no error model to
guard against (`:104-107`). Text: 88% on statement rows, and the source of the
three silent errors above. P&L is closed to a model *regardless of score* because
no identity constrains a leaf (`:165`, and the validator hole at `:91-97`).
Meanwhile the routing doc marks most un-extracted **tables** as still belonging to
a parser — the axis is fixed-surface vs unbounded-phrasing, not tables vs text.

### 3.6 Half its governance chapter is a platform binding

§11–12 asks for spend caps, rate limits, retries, model fallback, traces and a
kill switch. Cloudflare AI Gateway provides caching, rate limiting, cost tracking,
retries, provider fallback and logging. Separately: the OpenAI Agents SDK it
recommends runs on Workers with `nodejs_compat`, but has **degraded tracing**
there (limited AsyncLocalStorage support), which undercuts §12's trace-based
release gate on this specific stack.

### 3.7 A Worker failure mode it cannot know

2026-08-01: the webhook ACKs Telegram and runs the loop inside `ctx.waitUntil`.
The model answered successfully, then *"waitUntil() tasks did not complete within
the allowed time and have been cancelled"*, and nothing arrived
(`TELEGRAM_BOT.md:82-90`). Agent loops in a Worker can die **after** succeeding.

### 3.8 Its own citations argue harder than it does

Kim et al. find "tool-heavy tasks appear to incur multi-agent overhead" and
"coordination yields diminishing returns once single-agent baselines exceed
certain performance", with relative change vs single-agent spanning +80.8% on
decomposable financial reasoning to −70.0% on sequential planning. An analyst over
ten typed tools is tool-heavy by construction; a single-agent baseline over
curated data starts high. §5's team use-cases are contradicted by §3.2's own
reference — and the "parallel source gathering" it names is already deterministic
Python in Actions.

## 4. The blind spot neither document has

The report's validator checks claim-against-evidence. It never checks
evidence-against-reality. `2026-08-02-where-wrong-values-concentrate.md:34-45`
measured exactly that exposure — corrupt one stored cell ×1.5, re-run every check
the lane actually gets:

| Lane | Cells tested | Missed |
|---|--:|--:|
| Balance sheet | 2,500 | **0.0%** |
| P&L | 1,291 | **38.7%** |
| OCI | 293 | **52.6%** |
| Cash flow | 1,047 | **79.9%** |

Plus `free_provision`: 580 cells, **no validator at all** (`:62-63`).

An agent over these lanes will report a wrong number with perfect provenance and
full validator approval. The report has no concept of *present-but-unverifiable*,
which is this repo's dominant risk class. It also inverts its rollout advice: §5B
calls the chart explainer "the safest public beta because the context is narrow",
but narrow context is not correct data.

**Consequence — the one new piece of engineering this pass produced:** a tool
layer's most important field is not `source_id`, it is **per-lane blind-spot
coverage**, wired to structural abstention.

## 5. What is genuinely absent

After the above, the residue is small:

1. **The bot is not on the web.** It answers in the question's language, refuses
   ungrounded figures, and is invisible to everyone not on Telegram.
2. **Typed tools vs free SQL.** The bot lets the model write SQL, gated by
   `bot-sql.ts`. Typed tools would close the one class the gate cannot see — a
   valid query that joins wrong and returns a plausible number. **Unmeasured**,
   and §9 shows the migration cost is re-encoding the corpus rules, not the
   endpoints.
3. **Per-lane trust in the answer path** (§4 above).
4. ~~Two live gaps in the bot's numeric chain, plus `bot_queries` missing from
   `DENY_TABLES`.~~ **Fixed 2026-08-03** (commit follows this doc): the
   forced-final path now runs the figure check and drops an ungrounded answer
   rather than sending it; the check accumulates every number from every
   successful query (`seenNumbers`) instead of comparing against the last query's
   rows alone, which was producing false positives that burned the single
   correction round; and `bot_queries` — every user's question text — is denied
   at the SQL gate with a test. ⚠️ **Still open:** only figures ≥1000 are checked
   (`bot-sql.ts:560`), so ratios and percentages remain unverified.
5. ⚠️ **All drift detection is currently off.** `healthcheck.yml` is frozen with
   no `review_by`, and it is what runs `check_bot_schema.py` (prompt facts vs
   data), `check_bot_answers.py` (recipes vs correct numbers) and the webhook
   liveness check. A new model lane would ship with nothing watching it.

## 6. Corrections to the first version of this file

Both were assertions I did not check before committing.

- **`check_prose_claims.py` does not structurally forbid generated prose.** It is
  a static-string linter with three narrow rules — a hardcoded `+` before a
  formatter, a non-interpolated `title=` literal asserting direction/level/
  ranking, a hardcoded bank count — and it explicitly does not check "whether a
  static description is accurate" (`check_prose_claims.py:32-38`). Runtime-
  generated prose is not a string literal in a `.tsx` file and passes it
  untouched. The real guarantee is `prose.ts`'s fail-closed `claim()`/`direction()`
  plus `prose-regression.test.ts`.
  ⚠️ Note what the gate's own docstring says it exists for: **41 hand-typed human
  sentences** asserting the opposite of the chart beneath them, including *"32
  banks' audited BRSA financials"* when the universe has been 38 since TAKAS
  (`:7-16`). The measured failure mode on this site is static human prose going
  stale.
- **`registry.json` already carries computation semantics.** The first version
  claimed it holds only disclosure/reproducibility fields and that §6.1's registry
  would be new work. Wrong: each entry carries `formula`, `derivation`,
  `decomposes_into`, `unit`, `caveats`. ROE: `formula` = "net_income / avg_equity
  = roa × equity_multiplier (DuPont)"; `derivation` = "net_income (P&L XXV.→XIX.)
  / equity (BS XVI.); annualize YTD ×(4/quarter). Sector: financial_ratios Table
  15." It also carries `examples[]` — bank, period, the bank's **own published
  value**, its source, and `ours` (AKBNK 2026Q1 ROE 25.3 vs ours 25.3; HALKB 17.4
  vs ours 17.2) — the seed of the §12 golden eval set in machine-readable form,
  which the report never imagines.

  ⚠️ **Measured population, not generalised from ROE** (162 metrics):
  `definition` 100% · `unit` 100% · `caveats` 59% · **`formula` 46%** ·
  `derivation` 36% · **`examples` 18% (29 metrics)** · `decomposes_into` 8%.
  Absent `formula` is largely *correct*: the empty set is dominated by primitives
  that are read rather than computed (`interest_income`, `total_assets`,
  `personnel_expense`, `tax_expense`). But the eval seed is **29 metrics, not a
  corpus** — enough to bootstrap a golden set, not enough to be one.

## 7. Doc bug found in passing

`docs/PROJECT_STATE.md:10` says the registry holds **153** metrics. The artifact
holds **162** (`ConvertFrom-Json` over `data/metric_knowledge/registry.json`). Per
AGENTS.md, the code wins and the doc is the bug.

## 8. Use cases, ordered by what only this repo can do

Taken as open research rather than as what survives current doctrine; where a case
requires breaking a standing rule, the rule is named.

1. **Classify the qualification corpus.** 976 opinions, **552 modified (57%)**,
   basis paragraph captured verbatim on **545** (`PROJECT_STATE.md:43`) — and none
   of it classified (`routing:144`). Nobody knows what the sector is qualified
   *about*. Closed answer set, nothing returned is a figure: squarely inside the
   admissible zone the routing rule already defines.
2. **Key audit matters, subsequent-event type, and the 28 accounting-policy
   notes** — all marked MODEL, all untaken (`routing:147,170-175`). ECL
   methodology carries DPD thresholds and scenario weights inside sentences;
   comparable policy across 38 banks has never existed.
3. **The model as the extractor's auditor.** Point it at cash-flow cells with the
   PDF page as ground truth — not to write a value, but to *disagree*. A
   disagreement is a human stop. The only proposal that attacks the 79.9%.
4. **Cross-source contradiction.** BDDK publishes nothing per-bank; TBB excludes
   participation banks. Sector aggregate vs Σ per-bank filings vs TBB vs KAP is a
   reconciliation nobody publishes; the gaps are the product.
5. **Regulation → measured effect.** Join the Rulebook's regime-in-force to the
   balance-sheet response. Neither half is novel; the join has no competitor.
6. **The English unlock as a stored artifact, not a live agent** — a generated,
   verified, versioned bilingual ontology over every line item, note and
   regulatory term.
7. **The bot on the web** (§5.1).
8. Already designed, not built: the product-benchmark refresh agent over a
   change-detector spine (`PROJECT_STATE.md:26`), and per-bank credit memos, which
   are the actual deliverable of the credit/DFI actors the audience research named.

## 9. `/api/v1` is already an agent-framed tool contract — over the wrong lane

`web/app/api/v1/route.ts` is a self-describing index: endpoints, code grammar,
worked examples, and live coverage read from `api_series`. The OpenAPI route
describes itself as *"OpenAPI 3.1 schema — **register as a ChatGPT Action / Custom
GPT**, or feed to Postman, Swagger UI or a client generator"* (`:57-58`). The
report's §8 tool layer is not merely partly built; the built part was designed for
model consumption.

It also encodes three of the report's §4.1 principles machine-readably (`:73-81`):
*"A null observation means BDDK filed no figure for that period. It does not mean
zero"*; *"Units — per series… Never assume"*; and month-end dating, with the
reason. `authentication: "None"`, made safe by the `PUBLIC_API_DISABLED` kill
switch; unknown codes land in `meta.unknown` rather than failing the request
(`series/route.ts:15-17`).

Verdicts across the whole `web/app/lib` surface, not just `/api/v1` —
**4 EXISTS · 5 PARTIAL · 1 ABSENT**:

| Proposed tool | Status |
|---|---|
| `evaluate_flag` | **EXISTS** — the most mature of the ten. `bankFlags()` (`bank-brief.ts:281`), 6 rules each returning its own literal rule string (`"Δcar_qoq < −1pp AND buffer < 8pp"`); sector flags already on the wire with `rule` + `operands` (`api/app/v1/overview/route.ts:210-223`); `engineGate()` explains *absence* |
| `get_release_calendar` | **EXISTS**, already public — `aheadDates()` (`ahead.ts:189`), `Slot = {when, date, rule}`; a kind whose date can't be established is omitted, never printed stale |
| `calculate_change` | **EXISTS**, over-supplied — `period-math.ts:36/51/70`, `desk.ts:17-141`, `economy.ts:58/72`, `real-terms.ts:30` (Fisher, not subtraction), `series.ts:65/101` |
| `get_metric_series` | **EXISTS** but fragmented — five entry points, three period formats, two ₺ scales; no dispatcher |
| `get_metric_definition` | **PARTIAL** — 21 metrics typed in `METRIC_DEFS` (`heatmap.ts:86`) with a printable `rule`; the 162-metric registry is Python-only, never imported by `web/`, not in D1, no route. Content done, accessor missing |
| `compare_entities` | **PARTIAL** — `peerStat()` (`bank-brief.ts:121`) is licence-class aware and reports which universe it used; no bank-A-vs-bank-B, no group-vs-group |
| `get_rankings` | **PARTIAL** — `leagueTable()` (`market-share.ts:204`), `peerStat().rank`; no generic `rankBy` |
| `get_data_freshness` | **PARTIAL** — `getHealthReport()` (`admin-health.ts:254`) is schedule-aware and probe-backed, but has **no HTTP surface** |
| `get_source_record` | **PARTIAL, split by lane** — news/KAP/IR exist; audit filings absent |
| `get_source_excerpt` | **ABSENT** — the only one needing genuinely new plumbing: PDFs are in R2, `fitz` cannot run in a Worker, and the Worker holds no R2 binding |

⚠️ **The finding that decides the open question.** `bot-schema.ts` (~450 lines) is
where the corpus's hardest rules are written, and they are properties of *the
data*, not of the schema: take `MAX(amount_total)` across **both** balance-sheet
legs (reading only `assets` put ISCTR at ₺2.72tn instead of ₺4.94tn, 7th instead
of 3rd, in a ranking that showed every bank); JOIN `bank_audit_pl_roles`, never
label-match (AKBNK files a blank `item_name`); `10001` is already the sector,
summing the ten codes reported it 3.84× too high and looked plausible; filter
`currency='TL'` but read `amount_total`, not `amount_tl` (a ~39% error that looks
fine). **Any typed tool over the same tables must re-encode every one of these.**
Typed tools do not inherit the scar tissue for free — that is the real cost of
the migration, not the endpoints.

⚠️ **Scope inverts the build question.** `/api/v1` covers BDDK monthly tables 1–17
and the weekly bulletin — public aggregates anyone can pull from BDDK. It does
**not** cover the audit lanes, EVDS, TBB or TKBB. Typed tools therefore exist for
the data that matters least competitively and are absent for the per-bank BRSA
extraction nobody else holds — which is precisely where the bot reaches by free
SQL, and where §4's blind spots live.

## 10. The open question

**Free SQL or typed tools?** Gated free SQL is proven in production. Typed tools
would close the wrong-join class the gate cannot see, and nobody has measured how
often that happens. Sampling `bot_queries` (`web/migrations/0033_bot_queries.sql`)
for wrong-join answers is the cheap experiment that decides it, and needs no new
code.

Given §9, the build itself is not greenfield: **extending the `/api/v1` pattern to
the audit lanes IS the typed-tool layer**, with a working precedent to copy, and it
puts a schema in front of the lanes where a wrong join is both most likely and most
damaging.

## 11. Cost and the real limits (measured, not estimated)

D1 is **not** the cost centre for an agent query: ≤6 SELECTs each capped at 201
rows ≈ **$0.00012** typical, **$0.0096** pathological; writes ~32 billed rows
≈ **$0.000032**. Even scanning all ~1.6M rows costs $0.0016. Reads are $0.001/M
against writes at $1.00/M, and `rowsWritten` carries a measured **3.6×** index
multiplier (`OPERATIONS.md:486-496`).

The binding constraints are elsewhere:

1. **The `waitUntil` allowance.** `RUN_BUDGET_MS = 20_000`, `CALL_TIMEOUT_MS =
   12_000` (`bot.ts:46,50`). ⚠️ **A page render has no equivalent escape** — the
   webhook affords 20s only because it ACKs Telegram 200 first. On a page this
   must be an API route the client calls, not a server component.
2. **Free-tier provider rates** — Cerebras ~5 req/min against a loop making
   several calls per question.
3. **Tokens, if you leave free models.** `bot-schema.ts` is ~32 KB ≈ **8k tokens**
   of system prompt, resent on each of up to 7 calls over an accumulating
   history — roughly **70–100k input tokens per question**, about 100× the D1
   spend on a metered model.

CPU is never the constraint: LLM calls are I/O wait, and a paid Worker has 30s CPU
with no hard wall-clock limit on HTTP requests.

## 12. Process note

Five `Explore` agents were dispatched across the facets of this pass. Their
reports did not reach the orchestrating session for roughly twenty minutes — only
idle notifications arrived, through three rounds of requests.

⚠️ Two earlier versions of this section were wrong in sequence: the first recorded
the agents as having "contributed nothing", the second as their reports having
"never reached" the caller. Both were claims about an inbox stated as claims about
the work. **The cause was a protocol mismatch**: an `Explore` agent is told its
final text *is* its return value, while the teammate transport requires an
explicit `SendMessage` call — so each wrote a complete report as plain text, went
idle, and delivered nothing. Naming the tool explicitly fixed it immediately and
all five delivered in full, materially sharpening §5, §9 and §11 above.

The lesson generalises past this session: the failure was neither capability nor
coordination logic, but **an unstated assumption about how a result gets
returned** — Cemri et al.'s inter-agent-misalignment category, and the single
cheapest thing to specify explicitly in any agent design.

## Not related to this document

`docs/knowledge/EVENT-DRIVEN-AGENTS-DESIGN.md`, untracked in this tree, is **a
different project's design** — `vhunter-proxy/src/detectors/`, Polygon bars,
equity tickers, Modal endpoints, a `signal_events` table, a "Graph Brain".
`vhunter`, `polygon`, `signal_events` and `InvestigationResult` appear in no other
file in this repo. It is misfiled and should be moved, not merged with this.
