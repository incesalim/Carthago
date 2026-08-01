# Can an LLM read a filing's reporting unit better than a regex?

**Date:** 2026-08-01 · **Status:** ANSWERED — no. Regex 22/22, free, offline.
Keep extraction deterministic.
**Evidence:** `scripts/scratch_bench_unit_detection.py` via `test-openrouter.yml`
runs [30715235995](https://github.com/incesalim/Carthago/actions/runs/30715235995)
(DeepSeek) and [30715365345](https://github.com/incesalim/Carthago/actions/runs/30715365345)
(Nemotron), plus [30715083033](https://github.com/incesalim/Carthago/actions/runs/30715083033)
(model inventory).

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
