# OpenRouter key + DeepSeek — does it work, and what does it cost?

**Date:** 2026-07-19 · **Status:** VERIFIED WORKING — no lane consumes it yet
**Evidence:** `.github/workflows/test-openrouter.yml` runs
[29698794833](https://github.com/incesalim/Carthago/actions/runs/29698794833) +
[29698842435](https://github.com/incesalim/Carthago/actions/runs/29698842435)

The `OPEN_ROUTER_API` secret was added 2026-07-05 and **no code in this repo had
ever read it** — so "we have an OpenRouter key" was an untested claim for two
weeks. It works. Details below, plus one finding that matters more than the price.

## The key

| | |
|---|---|
| Secret name | `OPEN_ROUTER_API` — ⚠️ no `_KEY` suffix, unlike every other provider secret |
| Auth | ✅ `sk-or-v1-…`, 73 chars, `is_free_tier=false` |
| Key cap | none (`limit: null` = pay-as-you-go) |
| **Account balance** | **$20 purchased, $0.289 used → $19.71 remaining** |

`limit: null` on `/key` means no cap was set *on the key* — it says nothing about
the account. The balance that actually runs out is at `/credits`.

### What the $0.289 bought — not answerable with this key

`/credits` reports **dollars only**. The per-model, per-day token breakdown lives
at `/activity`, which returns **`403 "Only management keys can fetch activity for
an account"`** — a management/provisioning key is a separate credential from an
inference key. Read it at <https://openrouter.ai/activity> instead.

What *is* measured: this key's own three probe calls cost **$0.000280 for 1,495
tokens** (823 + 672; prompt 568, completion 927) — a blended **$0.187/Mtok**,
completion-heavy because reasoning tokens are billed as output. The $0.289 was
spent **before this key's first call** (key usage was $0.00 while the account
already showed $0.289) — i.e. by the website or another key, on an unknown model.
At v4-flash rates that would be ~1.5M tokens; on a frontier model, ~50k.

## DeepSeek models visible (11, all paid — **no `:free` variants on this key**)

| id | $/Mtok in | $/Mtok out | ctx |
|---|---:|---:|---:|
| **`deepseek/deepseek-v4-flash`** | **0.098** | **0.196** | 1,048,576 |
| `deepseek/deepseek-chat` | 0.200 | 0.800 | 131,072 |
| `deepseek/deepseek-chat-v3.1` | 0.250 | 0.950 | 163,840 |
| `deepseek/deepseek-v3.2` | 0.269 | 0.400 | 163,840 |
| `deepseek/deepseek-v3.2-exp` | 0.270 | 0.410 | 163,840 |
| `deepseek/deepseek-v3.1-terminus` | 0.270 | 1.000 | 131,072 |
| `deepseek/deepseek-chat-v3-0324` | 0.270 | 1.120 | 163,840 |
| `deepseek/deepseek-v4-pro` | 0.435 | 0.870 | 1,048,576 |
| `deepseek/deepseek-r1-0528` | 0.500 | 2.150 | 163,840 |
| `deepseek/deepseek-r1` | 0.700 | 2.500 | 163,840 |
| `deepseek/deepseek-r1-distill-llama-70b` | 0.800 | 0.800 | 128,000 |

Never hardcode these ids — OpenRouter renames/retires DeepSeek releases often
enough that a literal id becomes a future 404. Discover from `GET /models`.

## Quality: it passes our own guardrails

The probe ran a real "The Read" rewrite (the `SYSTEM` prompt + validators from
`src/news/free_llm.py`) with a **derived-figure trap** — the facts give CAR 18.1%
and a 12.0% requirement but never the 6.1pp buffer, which is exactly what got
`llama-4-scout` rejected in the [round-3 gauntlet](free-model-eval-round3.md).

`deepseek-v4-flash`, both runs: `well_formed=True`, `invented_numbers=none`, trap
avoided. Output was on-voice and correctly causal:

> "A 5.2pp decline in deposit costs to 41.5% expanded net interest margin by
> 0.6pp to 4.2%, lifting sector ROE 3.1pp to 28.4%."

## flash vs pro — the price list understates the gap 3×

`v4-pro` run on the identical prompt/harness
([29699115986](https://github.com/incesalim/Carthago/actions/runs/29699115986)):

| | `v4-flash` | `v4-pro` | ratio |
|---|---:|---:|---:|
| List price ($/Mtok in / out) | 0.098 / 0.196 | 0.435 / 0.870 | **4.4×** |
| Completion tokens (same prompt) | 388 | 1,161 | 3.0× |
| Reasoning emitted | 1,226 chars | 3,668 chars | 3.0× |
| **Actual cost per call** | $0.000148 | $0.001859 | **12.5×** |
| Latency | 8.5 s | 23.4 s | 2.8× |
| Guardrails (well-formed, no invented numbers, trap avoided) | ✅ | ✅ | — |

**A reasoning model's headline price is not its cost ratio.** Pro is 4.4× the
posted rate but **12.5× the actual spend**, because it also emits ~3× the
reasoning — and reasoning bills as output tokens you never display. Any
"cheapest model" comparison done on the price list alone will be wrong by the
model's thinking multiplier. Measure a real call.

⚠️ **This task cannot tell you whether pro is *better*.** A 30-word lead over
five given facts has no headroom — flash scored perfect on all three of its
runs, so there is nothing for pro to improve on, and both produced the same
sentence in different words. The result above is a **cost/latency** finding
only. Ranking the two on capability needs a task flash actually fails; not run.

## ⚠️ The finding that matters: provider routing is non-deterministic

The two runs used the **same model at temperature 0** and produced **different
sentences** — because OpenRouter routed them to different upstream providers
(`StreamLake` then `Fireworks`). Cost differed too ($0.000148 vs $0.000105).

OpenRouter is a broker, not a provider. Temperature 0 buys determinism *within*
one upstream, not across the routing decision. Any lane that cares about a stable
output must pin the route:

```jsonc
"provider": { "order": ["Fireworks"], "allow_fallbacks": false }
```

This does not affect the existing Read lane's correctness — the `det_hash` gate
plus number validation already means a drifted rewrite falls back rather than
prints wrong. But it does mean "same model, same temp" ≠ "same answer" here.

## Cost + latency vs the incumbent free chain

| | v4-flash (OpenRouter) | Cerebras gpt-oss-120b (current) |
|---|---|---|
| Actual cost / call | $0.000148 | $0 |
| Latency | **8.0–8.5 s** | ~0.4–0.8 s |
| Reasoning | separate field, 1.2–1.5k chars, **billed as output** | stripped by provider |

At ~$0.15 per 1,000 calls, cost is a non-issue for anything this repo does — the
Read lane is 8 calls/week (**≈$0.06/year**). The real trade is **10× the
latency**, and that most of the completion tokens are reasoning you pay for but
never see (388–539 completion tokens for a ~30-word sentence).

## So what

- **The key is good and has $19.71** — safe to build on.
- **Don't swap the Read lane onto it.** Cerebras is free, 10× faster, and already
  gauntlet-validated; DeepSeek's win is capability, and a 30-word headline
  doesn't need capability.
- **Where it would actually pay:** jobs that are hard, batchy, and latency-
  insensitive, where the free tiers' quality or rate limits bite — the
  [regulation briefing](../../scripts/summarize_regulations.py) currently on
  **paid Kimi** is the obvious candidate (`v4-flash` is likely far cheaper), and
  the 1M context window suits long filings. Not evaluated here.
- **Never for the extraction spine** — see `feedback_extractors_no_api`.

## Reproducing

`gh workflow run test-openrouter.yml` (optional `model_id` input to bench a
specific model). Scratch infrastructure — `test-openrouter.yml` +
`scripts/scratch_test_openrouter.py` — kept only while an OpenRouter lane is
under consideration; delete both once that's decided (recoverable from git).
