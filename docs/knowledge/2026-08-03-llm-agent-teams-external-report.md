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
   valid query that joins wrong and returns a plausible number. **Unmeasured.**
3. **Per-lane trust in the answer path** (§4 above).

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
  vs ours 17.2). That is the seed of the §12 golden eval set, in machine-readable
  form, which the report never imagines.

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

## 9. Not verified

Five Explore agents were dispatched and idled without delivering; the above rests
on direct reads. Still open: whether `/api/v1`'s five routes (`categories`,
`series`, `serieList`, `openapi.json`, root) already satisfy any of the ten
proposed tools — note that a published `openapi.json` is itself a machine-readable
tool contract; and the per-tool EXISTS/PARTIAL/ABSENT mapping. None of this
changes the recommendation; all of it changes the size of the build.

## 10. The open question

**Free SQL or typed tools?** Gated free SQL is proven in production. Typed tools
would close the wrong-join class the gate cannot see, and nobody has measured how
often that happens. Sampling `bot_queries` (`web/migrations/0033_bot_queries.sql`)
for wrong-join answers is the cheap experiment that decides the architecture, and
it needs no new code.

## Not related to this document

`docs/knowledge/EVENT-DRIVEN-AGENTS-DESIGN.md`, untracked in this tree, is **a
different project's design** — `vhunter-proxy/src/detectors/`, Polygon bars,
equity tickers, Modal endpoints, a `signal_events` table, a "Graph Brain".
`vhunter`, `polygon`, `signal_events` and `InvestigationResult` appear in no other
file in this repo. It is misfiled and should be moved, not merged with this.
