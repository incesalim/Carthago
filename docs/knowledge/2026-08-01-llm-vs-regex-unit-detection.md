# Can an LLM read a filing's reporting unit better than a regex?

**Date:** 2026-08-01 · **Status:** ANSWERED — a properly tuned Nemotron **ties**
the regex at 22/22 and never beats it. Keep extraction deterministic; an LLM is
worth it only on the regex's `UNKNOWN` branch.
**Evidence:** `scripts/scratch_bench_unit_detection.py` via `test-openrouter.yml`.
Round 1 — [30715235995](https://github.com/incesalim/Carthago/actions/runs/30715235995)
(DeepSeek), [30715365345](https://github.com/incesalim/Carthago/actions/runs/30715365345)
(Nemotron), [30715083033](https://github.com/incesalim/Carthago/actions/runs/30715083033)
(inventory). Round 2, Nemotron tuning —
[30715899607](https://github.com/incesalim/Carthago/actions/runs/30715899607) (6-variant sweep),
[30716578444](https://github.com/incesalim/Carthago/actions/runs/30716578444) (isolation),
[30716838564](https://github.com/incesalim/Carthago/actions/runs/30716838564) (stability),
[30717074829](https://github.com/incesalim/Carthago/actions/runs/30717074829) (enum-only).

## The problem this was testing

**Every bank switched to millions in 2026Q2.** Not just TEB — 11/11 filings, both
bases, Turkish and English alike:

| | 2026Q1 | 2026Q2 |
|---|---|---|
| AKBNK, GARAN, YKBNK, KLNMA, ENPARA, TEB | `bin Türk Lirası` (11 filings) | `milyon Türk Lirası` (11 filings) |

TEB was not an outlier, it was **first**. Extracted as printed, every 2026Q2
figure lands 1000× small, and **no validator can see it** — every BS/P&L check is
an internal identity (assets = liabilities, subtotal = Σchildren) and a uniform
scale change leaves all of them footing. Only a cross-period anchor catches it.

Local extraction confirms both halves — the failure and the fix:

| bank | Q1 stored (thousands) | Q2 raw | ratio | Q2 × 1000 | QoQ |
|---|---:|---:|---:|---:|---:|
| AKBNK | 3,419,802,978 | 3,727,680 | 917 | 3,727,680,000 | +9.0% |
| GARAN | 4,016,807,351 | 4,412,331 | 910 | 4,412,331,000 | +9.8% |
| YKBNK | 3,402,258,902 | 3,572,390 | 952 | 3,572,390,000 | +5.0% |
| KLNMA | 203,223,408 | 214,557 | 947 | 214,557,000 | +5.6% |
| ENPARA | 284,348,069 | 301,791 | 942 | 301,791,000 | +6.1% |
| TEB | 799,241,647 | 840,756 | 951 | 840,756,000 | +5.2% |

The ratio is ~950 rather than exactly 1000 because the banks also grew; scaled,
QoQ growth lands at +5% to +9.8%, which is what a Turkish bank quarter looks like.

## The bench

22 filings (6 banks × 2026Q1/Q2 × both bases). **2026Q1 is the control** — a
detector that always answers MILLION would still score 100% on Q2 alone.

The model is asked for a **label from a closed set** (THOUSAND / MILLION /
BILLION / UNKNOWN) plus the verbatim phrase it read, and never for a figure.
That is the only shape of this problem that does not collide with AGENTS.md's
"no LLM sets a number" — unit detection is a classification, not a measurement.

| arm | agreement | cost | latency |
|---|---|---|---|
| **regex** (`UNIT_RE`, 8 front pages) | **22/22** | $0 | ~0s, offline |
| `deepseek/deepseek-v4-flash-0731` | 19/22 | $0.012 | 6.2s median |
| `nvidia/nemotron-3-super-120b-a12b:free` | 16/22 | $0 | 7.2s median |

## The finding that matters

**Both models read the filing correctly every single time. Both lose on output
discipline.** Not one failure was a comprehension failure:

- DeepSeek's 3 misses returned `{"unit": "", "evidence": "aksi belirtilmediği
  müddetçe milyon Türk Lirası cinsinden hazırlanmıştır"}` — the right phrase,
  quoted exactly, with the actual answer field left blank.
- Nemotron's 6 misses all hit `finish_reason: length`, having spent the budget
  narrating (`"We need to output JSON with unit and evidence. The text includes
  phrase: …"`). Its visible thinking quotes the correct phrase every time.

So the LLM is not worse at *reading* than the regex. It is worse at *returning*,
and that is the part a regex cannot get wrong. Against a baseline that is already
perfect, free and offline, there is nothing left for a model to add here.

**⚠️ The first run scored 8/22 and that number was a lie.** `max_tokens: 200`
starved the reasoning models — they spent the whole allowance thinking and
returned JSON truncated mid-string, which the bench counted as wrong. Raising the
cap to 1200 moved DeepSeek 8 → 19 with no prompt change. A reasoning model
*budgets* its thinking against `max_tokens`, so any cap tuned on a non-reasoning
model reads back as "this model is bad at the task". `finish_reason` is now
surfaced so `TRUNCATED` never again scores as `UNPARSEABLE`.

## Model inventory on this key (2026-08-01)

Correcting [openrouter-deepseek-eval-2026-07-19.md](openrouter-deepseek-eval-2026-07-19.md),
which found no `:free` variants: that is true of `deepseek/*` specifically, but
**14 `:free` models are visible**, including 6 Nemotron —
`nvidia/nemotron-3-{nano-30b-a3b, super-120b-a12b, ultra-550b-a55b}:free`,
`nemotron-nano-{9b-v2, 12b-v2-vl}:free`, `nemotron-3.5-content-safety:free` —
plus `google/gemma-4-{26b-a4b,31b}-it:free`, `openai/gpt-oss-20b:free`,
`inclusionai/ling-3.0-flash:free`, `cohere/north-mini-code:free`,
`poolside/laguna-{s,xs}-2.1:free`.

Note `deepseek/deepseek-v4-flash` resolved to **`deepseek-v4-flash-0731`** — the
dated id. Discover from `GET /models`; never hardcode.

## Round 2 — tuning Nemotron properly (nemotron only)

The round-1 score was a badly-configured model, so the levers were checked
against `GET /models` rather than guessed. The **free** endpoint advertises
`structured_outputs`, `response_format`, `reasoning`, `reasoning_effort`,
`include_reasoning`, `seed`, `tools`, `tool_choice` (262K ctx; the paid variant
is 1M and adds `logit_bias`/`top_k`/`min_p`). Nemotron 3 Super also gates its
chain-of-thought on a `/no_think` system directive.

Twelve variants over the same 22 filings:

| variant | score | out tokens | median |
|---|---|---:|---:|
| v0 baseline | 20/22 | 13,852 | 6.6s |
| v1 strict json_schema | 19/22 | 12,728 | 5.9s |
| v2 `/no_think` | 20/22 | 16,356 | 8.6s |
| v4 schema + `/no_think` | 19/22 | 14,400 | 7.3s |
| v3 `reasoning.effort=none` | 22/22 → 21 → 20 → 17 | ~1,900 | 0.9s |
| **v10–v12 enum-only + schema + effort=none** | **21 / 22 / 22** | **~205** | **0.6s** |

**`reasoning.effort=none` is the lever; the schema and `/no_think` did nothing
on their own.** Output tokens fell 13,852 → ~205 (67×) and latency 6.6s → 0.6s.
`/no_think` in the system prompt had no measurable effect through OpenRouter —
use the API parameter, not the directive.

**⚠️ Do not trust a single benchmark run of this endpoint.** `effort=none` scored
**22, 21, 20 and 17 out of 22 on byte-identical configs** at `temperature: 0`
with a fixed `seed`, calls spaced 2s apart so the rate limiter was not the cause.
One sample would have supported any conclusion you like.

**What was actually breaking it: the free-text `evidence` field.** Two failure
shapes, one cause — `INVALID:MILLIONS OF TURKISH LIRA (TL)` (the phrase written
into the enum field) and `TRUNCATED` with `<unk><unk><unk>` spew, the tokenizer
choking on quoted Turkish and then running to the cap. Dropping the field and
constraining to a bare enum gives **22/22 twice and 21/22 once — where the single
miss was `Upstream error from Nvidia: ResourceExhausted`, an infrastructure
failure rather than a wrong answer.** Answer-for-answer that is 65/65.

So a properly configured Nemotron **ties** the regex. It never wins, and getting
there cost three levers, twelve variants and six CI runs — while the regex was
right the first time. It also gives up the `evidence` field, which was the only
thing making an LLM answer auditable, and it still fails ~1 call in 66 to a free
upstream that owes us nothing.

**One wrong answer, worth naming:** `v6_schema_effort` returned `THOUSAND` for
YKBNK 2026Q2 while its own evidence read *"expressed in millions of Turkish
L…"*. A confidently wrong label contradicting its own quote is exactly the
failure a 1000× scale decision cannot absorb.

## Fine-tuning: available, and not justified here

- **Nemotron 3 Super is open-weight** (Hugging Face), so LoRA/QLoRA is possible;
  full fine-tuning of 120B is not a laptop job.
- **Hosted customization exists** — AWS SageMaker AI serverless customization
  covers Nemotron 3 Nano and Super with SFT / RLVR / RLAIF, and NVIDIA NeMo
  Customizer does the same on NVIDIA infrastructure.
- **OpenRouter cannot serve it on this plan.** Its Private Models beta (May 2026)
  routes to your own fine-tuned endpoints but is **Enterprise-only**; BYOK exists
  for provider keys, not for hosting a checkpoint.

None of it is worth doing for this task. **The ceiling is 22/22 and a regex
already reaches it for free, offline, deterministically.** Fine-tuning would buy
GPU hours and an MLOps dependency to match fifteen lines of `re`.

## What to do instead

Unit detection belongs in the extractor as a deterministic step. The detector is
already written and validated 22/22 — `UNIT_RE` + `regex_unit()` in
`scripts/scratch_bench_unit_detection.py`, ~15 lines, no dependencies.

**The unresolved part is not detection, it is application.** A scale factor has
to reach every amount across ~14 lanes whose columns are named differently
(`amount_tl` / `amount_fc` / `amount_total`, `amount`, `stage{1,2,3}_amount`,
`total_amount`, `ecl_amount`, `closing_balance`, `provision`, `net_balance`) while
never touching the ratios, coverage fractions, branch and personnel counts, or
per-share values sitting in the same rows. That needs a per-lane, per-field
allowlist, and getting it wrong is a silent 1000× error of exactly the kind this
whole document is about. Do not infer the field list — enumerate it against
`src/audit_reports/schema.py` and assert on a bank whose Q1 is known.

**Do not re-bench this** unless the question changes. The regex cannot be beaten
on a task it already scores 22/22 on for free.

**Where an LLM would still earn its place: the `UNKNOWN` branch.** The regex is
22/22 on filings that state the unit in a phrasing we have seen. It returns
`UNKNOWN` — honestly — on anything else, and a bank that rewords the declaration,
or states it only in a statement header, is a matter of time. Calling
enum-only Nemotron *only when the regex returns `UNKNOWN`* costs nothing in the
common case, is free, adds ~0.6s on the exception, and round 2 shows it answers
that question correctly. That is the hybrid worth building if this ever needs
more than the regex — not an LLM in the default path.

If it is built: `reasoning: {"effort": "none"}`, strict `json_schema` with the
unit as an `enum` and **no free-text field**, `provider: {"require_parameters":
true}`, and treat a disagreement with the regex as a hard stop for a human, never
as a value to store.
