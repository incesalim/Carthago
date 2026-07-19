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

## The real task: regulation briefing — **flash beat pro on accuracy AND cost**

Run via `test-openrouter.yml task=regulation`, which repoints the three env vars
`kimi.py` already reads at OpenRouter — production prompt, context builder,
retries and leak guards all unchanged. Section: *Monetary Policy Stance*, same
87-item feed (~32k tokens of context), all three providers on one context
([pro+Kimi](https://github.com/incesalim/Carthago/actions/runs/29699263056),
[flash](https://github.com/incesalim/Carthago/actions/runs/29699366247)).

| | bullets | with figures | latency | $/section | $/yr (5 sections × 52 wk) |
|---|---:|---:|---:|---:|---:|
| `v4-flash` | 5 | **4** | 14.1 s | **$0.0039** | **~$1.0** |
| `v4-pro` | 3 | 2 | 45.1 s | $0.0364 | ~$9.5 |
| Kimi `moonshot-v1-128k` (incumbent) | 5 | 2 | 10.5 s | — | ~$7 (documented) |

**Pro made a hard factual error that flash caught.** On the one-week repo auctions:

- flash: *"The CBRT **suspended** one-week repo auctions effective March 1, 2026."* ✅
- pro: *"The CBRT **conducts** one-week repo auctions as its primary funding operation."* ❌

The source is in both models' context window — TCMB, 2026-03-01, *Press Release on
Turkish Lira Liquidity Management*: **"it has been decided to suspend the one-week
repo auctions for a period of time."** Pro stated a live operational regime that
had been suspended four months earlier. It did read that date (it reported the
FX-forward release correctly, verified against the 2026-03-01 *TL-Settled FX
Forward Selling Transactions* release) — it just inverted the repo half.

**Kimi made no error but carried almost no information.** Three of its five
bullets are CBRT boilerplate — "tight stance until price stability",
"meeting-by-meeting", "macroprudential measures if needed". It missed **both**
March-1 regime changes. Flash caught both and dated the June 11 hold.

**This inverts the price-list intuition.** Pro is the stronger model on paper and
4.4× the posted rate, but on a 32k-token input-dominated task it cost **9.3×**
flash and was wrong where flash was right. Bigger ≠ better when the job is
"transcribe what these 87 press releases actually say" rather than "reason".

⚠️ **Caveat: one section, one run each.** Not a statistical result. But pro's
error is a hard, source-checkable contradiction, not a stylistic preference —
that is worth more than a win rate on taste.

> ⚠️ **Read the retraction below before using the section tables.** The
> single-section and single-run comparisons in this document were revised twice as
> more runs came in. Flash's output on this task is dominated by run-to-run
> variance, so per-section counts here are illustrative, not a ranking. The claims
> that survived repetition: DeepSeek is far cheaper, OpenRouter routes across many
> providers with very different behaviour, and Kimi never dropped a section.

### Full five-section run: flash **dropped an entire section** (⚠️ not reproducible)

The one-section result did not survive contact with the full task
([run](https://github.com/incesalim/Carthago/actions/runs/29701424488), all five
sections, same 87-item feed + baseline):

| section | flash | flash w/ figures | Kimi 19:31 | Kimi 19:43 |
|---|---:|---:|---:|---:|
| Monetary Policy Stance | 5 | 5/5 | 6 | 5 |
| Regulations for TL Deposit Share | 6 | 4/6 | 3 | 3 |
| Loan Growth Caps | 3 | 3/3 | 7 | 6 |
| Regulations on RRs | 4 | 4/4 | 3 | 4 |
| **Other Regulatory Actions** | **0** ❌ | — | 11 | 5 |
| **total** | **18 / 4 sections** | **16/18 (89%)** | 30 / 5 | 23 / 5 |

`Other Regulatory Actions` returned **zero bullets** — no exception, no parse
failure in the log, just nothing usable — and `main()` appends a section only
`if kept`, so it **vanished from the briefing silently**. Cost $0.0052/section
(~$0.026/run, **~$1.35/yr** against Kimi's ~$7), latency 140s vs Kimi's 34–71s.

**This is the fidelity/inference split again, and it predicts the failure.** The
four sections flash won are *transcription* asks — a rate, a cap, a ratio, each
tied to a dated release; flash carried a figure in **89%** of its bullets against
Kimi's ~40%. "Other Regulatory Actions" is the catch-all: it asks what *else*
matters, which is a judgment call with no anchor to transcribe. That is exactly
where the less-clever model has nothing to fall back on — and it produced nothing
rather than something wrong, which is at least the safer failure.

**So: not a drop-in replacement.** The right reading is not "flash beats Kimi" or
the reverse — it is that they fail in different places, which is an argument for a
**failover chain**, not a swap.

### What the OpenRouter dashboard showed (and what it corrects)

The per-call activity view — readable only from the account, not from an
inference key (`/activity` is 403) — reframes several claims above.

**Eight different upstream providers served one model in one hour:** Weights &
Biases, DigitalOcean, Venice, AkashML, StreamLake, NovitaAI, GMICloud, Fireworks.
Routing spread is far wider than the two-provider sample earlier in this doc
suggested.

**Output length for an identical prompt ranged 7 → 4,436 tokens.** The five-section
run (33.9k input each, timings map 1:1 onto the section sequence in the job log):

| section | provider | out tok | cost | result |
|---|---|---:|---:|---|
| Monetary Policy Stance | StreamLake | 3,599 | $0.00398 | 5 bullets |
| TL Deposit Share | AkashML | 329 | $0.00485 | 6 bullets |
| Loan Growth Caps | DigitalOcean | 279 | $0.00387 | 3 bullets |
| Regulations on RRs | Venice | 4,436 | $0.00591 | 4 bullets |
| **Other Regulatory Actions** | DigitalOcean | **7** | $0.00380 | **empty** |
| ↳ retry | Weights & Biases | **7** | $0.00475 | **empty** |

**On the dropped section — ⚠️ RETRACTED. A second full run refutes it.** Seven
output tokens is about the length of `{"bullets": []}` with `finish_reason: stop`,
and two *independent* providers returned it inside one run, so this doc first
concluded the emptiness was model/prompt behaviour. **A second five-section flash
run on identical input produced all five sections**, `Other Regulatory Actions`
included. The zero was a draw, not a property.

| section | run A (19:52) | run B (20:08) |
|---|---:|---:|
| Monetary Policy Stance | 5 | 6 |
| Regulations for TL Deposit Share | **6** | **1** |
| Loan Growth Caps | 3 | 8 |
| Regulations on RRs | 4 | 4 |
| Other Regulatory Actions | **0** | **1** |
| total | 18 / **4 sections** | 20 / **5 sections** |
| wall clock | 140 s | 295 s |

**The real finding is instability, and it is a bigger deal than any capability
story.** Individual sections swing 6→1 and 3→8 between runs on the same input, and
one run silently lost a section. Kimi over three runs varied 23/30/32 bullets but
never dropped a section. So on current evidence flash is **cheaper and less stable**,
and no section-level ranking in this document should be trusted — including the
"89% of bullets carry figures" comparison, which came from a single run.

**Empty answers are not cheap.** The two 7-token non-answers cost **$0.00855** —
about a third of the whole run — because 34k of input is billed regardless. On this
task cost is input-dominated, so provider choice barely moves the bill while moving
output enormously. That is the argument for pinning `provider.order`.

**Also:** the smoke tests show `App: carthago` while the regulation runs show
`Unknown` — `scratch_test_openrouter.py` sends `HTTP-Referer`/`X-Title` and
`src/news/kimi.py` does not. Cosmetic, but it is why the lane's spend is
unattributed in the dashboard.

### ⚠️ Third silent-degradation bug found today (in the lane, not the model)

A section that yields no bullets is dropped from the briefing with no error, and
`SystemExit` fires only when **every** section is empty. So a partial provider
failure ships a quietly shorter briefing — the same shape as the missing baseline
and as `notify()`'s silence-means-success. Not fixed; it is a real defect
independent of which model runs, since Kimi can return an empty section too.
Suggested: fail (or alert) when a section that produced bullets in the previous
briefing produces none now.

### Why the smaller model won — the mechanism, not the luck

Counted over the same 330-day feed both models read:

| signal in context | count |
|---|---:|
| releases saying *"the policy rate (**the one-week repo auction rate**) at 37 percent"* | **7** |
| releases saying *"it has been decided to **suspend** the one-week repo auctions"* | **1** |

Seven prominent, repeated statements imply the one-week repo auction is the
CBRT's live instrument; one short two-sentence release contradicts them. Pro did
exactly what a reasoning model is built to do — weigh the conflict, resolve it,
state the general truth — and wrote the 7. Flash didn't adjudicate: it scanned
for dated events and copied them out. Less clever, and right.

**Pro did not fail from lack of capability; it failed because of it.** This task
rewards *fidelity*, not *inference*. The correct behaviour is to transcribe the
anomaly even when seven other documents imply otherwise, and the more a model is
tuned to synthesize, the more likely it is to smooth that anomaly away. Extra
reasoning is extra opportunity to talk yourself out of a fact. The same instinct
shows in the shape of the answers: pro emitted 3× the reasoning tokens and
compressed to 3 bullets where flash kept 5 — and compression drops facts.

This is a failure class this repo has already met twice: the round-3 gauntlet
rejected `llama-4-scout` for **deriving** figures
([free-model-eval-round3.md](free-model-eval-round3.md)), and the npl_movement
lane's lesson was recorded as *transcribe, don't derive*. Same shape, new model.

**Diagnostic that generalizes:** pro's wrong bullet was the **only** bullet in
the run carrying neither a date nor a figure. Every flash bullet carried one. An
uncited bullet is the inferred one — the same discipline `web/app/lib/prose.ts`
already enforces on the dashboard: *a claim is computed or it does not print.*

**The rule to carry forward** — not "flash beats pro", which is n=1 and false in
general (pro leads on what it's marketed against: math, code, multi-step
reasoning, none of which this job needs):

> Match the model to whether the task rewards **inference** or **fidelity**.
> Extraction/transcription over a corpus you supply → prefer the *less clever*
> model. Open-ended reasoning → prefer pro.

Which is the same reasoning that keeps the extraction spine on deterministic
`fitz` anchors and not an LLM at all ([[feedback_extractors_no_api]]).

### Incidental production finding: the briefing has no baseline

Every run logged `WARNING: no baseline — run scripts/ingest_policy_baseline.py`,
including the **live weekly runs** of 2026-07-05, -07-12 and -07-19. The
`regulation_baseline` table is empty in the R2 snapshot, so the grounding
scaffold that commit f04778b introduced — the TCMB annual *Monetary Policy for
YYYY* regime the per-category prompts are supposed to build on — has not been in
the context for at least three weeks. The A/B above is still fair (all three
providers saw the same degraded context), but the production briefing is running
on the feed alone. Not fixed here.

## Which provider to pin (18 serve `deepseek-v4-flash`)

From `GET /api/v1/models/deepseek/deepseek-v4-flash/endpoints` (public, no auth),
costed on a real weekly run — 5 sections × ~34k input + ~2k output:

| provider | quant | uptime 1d | $/run | $/yr | vs cheapest |
|---|---|---:|---:|---:|---:|
| DeepInfra | **fp4** | 99.9 | 0.0171 | **0.89** | 1.0× |
| StreamLake | fp8 | 98.5 | 0.0184 | 0.95 | 1.1× |
| GMICloud | fp8 | 98.0 | 0.0186 | 0.97 | 1.1× |
| **Baidu** | **fp8** | **100.0** | 0.0187 | **0.97** | 1.1× |
| DigitalOcean | ? | 99.8 | 0.0213 | 1.11 | 1.2× |
| Venice | ? | 99.6 | 0.0262 | 1.36 | 1.5× |
| AkashML / Novita / WandB / Parasail / Fireworks / DeepSeek | mixed | 97.6–99.4 | 0.0266 | 1.38 | 1.6× |
| **Io Net** | fp8 | 99.9 | 0.0465 | 2.42 | 2.7× ⚠️ **no `response_format`** |
| **Ambient** | fp4 | 99.2 | 0.0930 | 4.84 | **5.4×** |

**Cost is not the deciding factor — reliability is.** The entire 18-provider spread
is $0.89–$4.84/yr, and even the worst is cheaper than Kimi's ~$7. So pin for
quality, not price.

**Unpinned routing was already overpaying ~40%.** Charged amounts match list prices
exactly (WandB 33,949 tok × $0.140/M = $0.00475, charged $0.00475), and the default
router put us on the $0.112–0.140 tier — DigitalOcean, AkashML, WandB, Novita —
never on the $0.090–0.098 tier.

**Two landmines in leaving it unpinned:**
- **Io Net does not support `response_format`.** This lane calls with
  `json_object=True`; land there and the model returns prose, `extract_json` throws,
  the retry burns, and the section drops. A *plausible* mechanism for an empty
  section — though not the one that bit us, since DigitalOcean and WandB both do
  support it.
- **Ambient is 5.4× the price** for the identical model.

**Recommendation: `provider: {order: ["Baidu", "StreamLake"], allow_fallbacks: false}`.**
Baidu is the only endpoint at **100% uptime on both the 1-day and 30-minute
windows**, is fp8 rather than aggressively-quantized fp4, advertises
`structured_outputs`, and costs within 10% of the cheapest. StreamLake as the
second is near-cheapest, fp8, and produced the best full answer we saw (3,599
tokens, complete section). `allow_fallbacks: false` keeps a bad draw from silently
substituting a 5.4× or JSON-incapable provider — with ~100% uptime and the lane's
new failure alert, failing loudly is the better trade.

⚠️ **Unmeasured:** `throughput_last_30m` and `latency_last_30m` come back **0** from
this endpoint (they populate only the web UI), so this ranking has **no speed
component**. Baidu's throughput is unknown here; verify before committing if the
5-minute job runtime matters.

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
- **The regulation briefing is a real candidate — on `v4-flash`, not pro.**
  Measured ~$1/yr vs Kimi's ~$7/yr, and in the one section tested it was strictly
  more informative: it caught two March-2026 regime changes Kimi missed entirely
  and one that pro got backwards. Before switching, run the remaining four
  sections and fix the missing baseline (both above) — a provider swap on top of
  a degraded context would be measuring the wrong thing.
- **Do not use pro for this.** It costs 9.3× flash on this input shape and
  produced the run's only factual error.
- **Never for the extraction spine** — see `feedback_extractors_no_api`.

## Reproducing

`gh workflow run test-openrouter.yml` (optional `model_id` input to bench a
specific model). Scratch infrastructure — `test-openrouter.yml` +
`scripts/scratch_test_openrouter.py` — kept only while an OpenRouter lane is
under consideration; delete both once that's decided (recoverable from git).
