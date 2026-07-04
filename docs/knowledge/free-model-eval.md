<!--
  Curated findings written on top of the auto-generated evaluation report
  (which is appended below, verbatim from the CI artifact). Regenerate the
  lower section by dispatching .github/workflows/test-free-models.yml and
  downloading the free-model-eval artifact.
-->

# Free LLM models for "The Read" — evaluation notes

**Purpose.** We use paid **Kimi** for the weekly regulations snapshot and are keeping
it there. Separately we're evaluating **free** API models (Groq, Cerebras, Google
Gemini) for a *different, non-critical* job: rewriting the one-sentence editorial
lead ("The Read") that `web/app/lib/insights.ts` generates for each dashboard tab
(**Option 1** — headline only; driver bullets stay deterministic). This is a
*test*; nothing is wired into the dashboard yet.

**No winner is declared.** This document is evidence, not a decision. Two CI runs
on 2026-07-04; the machine report from the second (with the corrected validator)
is appended below.

**→ Round 3 (reliability gauntlet):** repeated adversarial testing of the
Groq + Cerebras finalists (invent-rate, format, stability, number-traps) is in
[`free-model-eval-round3.md`](./free-model-eval-round3.md). Bottom line so far:
`gpt-oss-120b` (Cerebras primary + Groq failover) at **0% real invent-rate**;
`llama-4-scout` and `zai-glm-4.7` rejected.

---

## What we learned

### 1. All three providers work and drop straight into our existing client
Every provider is OpenAI-compatible, so the same `src/news/kimi.py`-shaped client
covers all of them — only `base_url` + key + model differ. Keys live in GitHub
secrets: `GROQ_API_KEY`, `GEMINI_API_KEY`, and **`CEREBRAS_KEY`** (note: not
`CEREBRAS_API_KEY`). This test runs only in CI via
`.github/workflows/test-free-models.yml`.

### 2. The number-lock guardrail works — but must be label-aware
The guardrail (reject any rewrite containing a number that isn't a fact, fall back
to the deterministic template) is the whole reason this is safe. The first run
exposed a false-positive: it flagged every model that wrote **"Stage-2"** as if it
had invented the number `2`. Fixed by ignoring digits glued to a label
(**Stage-2, CET1, Tier-2, Basel III**); only standalone quantities count as claims.
**Lesson for the real integration: the validator must do the same** — banking prose
is full of label-bound digits.

### 3. ⚠️ Google/Gemini hit a MONTHLY SPENDING CAP mid-test — needs your attention
In the second run, the first ~2 Gemini calls succeeded and then **every subsequent
call returned `HTTP 429: "Your project has exceeded its monthly spending cap"`**
(AI Studio). Quality was good when it answered (flash-lite is tight and clean), but
**the key is currently unusable** beyond a call or two. This is a *billing/quota*
block, not a rate limit — to use Gemini we'd need to raise/reset the spending cap
in Google AI Studio. Until then, treat Gemini as unavailable. **Decision
(2026-07-04): Gemini is EXCLUDED from the candidate set — the user won't lift the
cap (won't pay). All further testing runs on Groq + Cerebras free models only.**

### 4. Avoid reasoning models that don't get their reasoning stripped
- **`qwen/qwen3.6-27b` (Groq):** leaks `<think>` blocks, blows the 2048-token
  completion budget, and once produced a degenerate counting dump (`1,2,3,…`).
  Unreliable — do not use raw.
- **`openai/gpt-oss-20b` (Groq):** once returned an **empty** answer — its reasoning
  consumed the whole token budget before writing content. Risky without a larger
  `max_tokens`.
- **`gpt-oss-120b` (Groq & Cerebras)** and **`zai-glm-4.7` (Cerebras)** ARE reasoning
  models too, but the provider strips the reasoning channel, so the returned content
  is a clean single sentence. These are fine — just heavier on tokens/latency.
- Plain instruct models (**llama-3.3-70b, llama-4-scout, llama-3.1-8b, gemma-4-31b,
  gemini flash-lite**) emit ~50–90 tokens, no reasoning overhead — fastest and
  cheapest.

### 5. Performance (precompute job, so latency barely matters — but for the record)
- **Cerebras is fastest:** `gpt-oss-120b` ~0.4–0.6s at **~1,600–1,900 tok/s**;
  `gemma-4-31b` ~0.2s.
- **Groq** instruct models ~0.3–0.7s.
- **Gemini flash-lite / 3.1-flash-lite** ~0.7–0.8s (when not capped).
- **Avoid `gemini-2.5-flash` and `gemini-flash-latest`** — 5–23s (default "thinking")
  for no quality gain over flash-lite.

### 6. Rate limits (measured from response headers)
| Provider | Requests | Tokens | Binding constraint |
|---|---|---|---|
| **Groq** | 14,400/day | **6,000/min** | tokens-per-minute (≈6–12 of our calls/min) |
| **Cerebras** | 5/min · 150/hr · 2,400/day | 30k/min · 1M/day | 5 req/min |
| **Google** | not exposed on the OpenAI endpoint | — | **monthly spending cap (see #3)** |

### 7. Effectiveness: capacity is a non-issue
The real use is a **precompute cron**, not live per-request. `insights.ts` has **8
Reads**; regenerating all of them weekly with a fallback retry is **~2 calls/day**.
Every measured limit is 2–3 orders of magnitude above that. The real constraints are
**quality, the determinism gate, and provider reliability** — not volume. (Gemini's
spending cap is the one live reliability problem right now.)

---

## Candidate shortlist (for later — NOT a decision)

Reliable + clean + good synthesis, roughly in order of how often they nailed the
"connect 2–3 threads causally, no invented numbers" brief:

1. **`gpt-oss-120b`** — available on **both Cerebras and Groq** (nice for failover);
   consistently the fullest, most causal synthesis; clean numbers. Cerebras variant
   is dramatically faster.
2. ~~**`gemini-flash-lite-latest` / `gemini-3.1-flash-lite`**~~ — **EXCLUDED** (not
   free for us; cap will not be lifted). Was excellent/tight when it answered.
3. **`cerebras/zai-glm-4.7`** — strong synthesis, clean; token-heavy/slower.
4. **`cerebras/gemma-4-31b`** and **`groq/llama-3.3-70b-versatile`** — fast, clean,
   slightly less ambitious synthesis. Good "safe" picks.

**Suggested pattern when we build it:** primary = `gpt-oss-120b` (Cerebras), fall
through to `gpt-oss-120b` (Groq), then to another Groq/Cerebras instruct model
(e.g. `llama-3.3-70b`), then to the deterministic template — each step also gated by the number-check. Costs nothing,
removes single-provider risk. Optionally, since volume is free, generate from 2–3
models and keep the one that passes the check and best matches the target length.

---

## How to reproduce
Dispatch the throwaway workflow, then download the report:
```
gh workflow run test-free-models.yml
gh run download <run-id> -n free-model-eval
```
Harness: `scripts/scratch_test_free_models.py` (edit `SCENARIOS` / `PROVIDERS` to
change Reads or models). Both the harness and workflow are throwaway — delete once a
direction is chosen.

---

# Machine report (second run, corrected validator)


*Run 2026-07-04 18:40 UTC · commit `8b83c544` · 14 models × 4 Reads · temperature 0.4*

> **No winner is declared here.** This is the raw evidence — outputs, performance, rate limits — so the choice can be made deliberately.

## How this was tested

Each model is asked to rewrite a **deterministic** template lead (what `web/app/lib/insights.ts` already emits) into one synthesized sentence, **using only the numbers in the facts**. The output is then machine-checked: every number in the sentence must match a fact (±0.01) or it is flagged `NEW#`. That is the exact guardrail the real integration relies on — a flagged output would be rejected and the deterministic template shown instead.

> **Validator note:** the number-check ignores digits bound to a label (Stage-2, CET1, Tier-2, Basel III) — only standalone quantities count as claims. Learned the hard way: an earlier pass flagged every model that wrote “Stage-2” as if it had invented a number. The real integration must do the same.

**System prompt:**

```
You write the one-sentence editorial lead ('The Read') for a Turkish banking-sector dashboard, in the terse, analytical voice of BBVA Research. You are given the deterministic facts and the current template lead. Rewrite it as ONE flowing sentence (about 30-45 words) that SYNTHESIZES the vitals into a 'so what' — connect them causally where the facts support it (e.g. funding repricing lifting margins). Do NOT merely list every number; pick the 2-3 threads that tell the story. HARD RULE: use ONLY numbers that appear in the facts. Never invent, round, or compute a new figure. Output ONLY the sentence — no preamble, no markdown, no reasoning.
```

**Legend:** `✅` numbers clean · `⚠️ NEW#[…]` invented a number (would be rejected) · `🧠` leaked a reasoning block · `in/out` = prompt/completion tokens · `tok/s` = completion tokens per second.

## Rate limits (measured from response headers)

Captured live from each provider's last response this run — authoritative for *this account/tier*.

**groq**

| header | value |
|---|---|
| `x-ratelimit-limit-requests` | 14400 |
| `x-ratelimit-limit-tokens` | 6000 |
| `x-ratelimit-remaining-requests` | 14399 |
| `x-ratelimit-remaining-tokens` | 5510 |
| `x-ratelimit-reset-requests` | 6s |
| `x-ratelimit-reset-tokens` | 4.9s |

**cerebras**

| header | value |
|---|---|
| `x-ratelimit-limit-requests-day` | 2400 |
| `x-ratelimit-limit-requests-hour` | 150 |
| `x-ratelimit-limit-requests-minute` | 5 |
| `x-ratelimit-limit-tokens-day` | 1000000 |
| `x-ratelimit-limit-tokens-hour` | 1000000 |
| `x-ratelimit-limit-tokens-minute` | 30000 |
| `x-ratelimit-remaining-requests-day` | 2397 |
| `x-ratelimit-remaining-requests-hour` | 149 |
| `x-ratelimit-remaining-requests-minute` | 4 |
| `x-ratelimit-remaining-tokens-day` | 982783 |
| `x-ratelimit-remaining-tokens-hour` | 983278 |
| `x-ratelimit-remaining-tokens-minute` | 13278 |

**google**
- (no rate-limit headers returned on the OpenAI-compatible endpoint — see provider docs)

## Effectiveness — can we actually use this within the limits?

The real use is **precomputed on a schedule, not live per request** — a cron
regenerates a Read's headline only when its as-of period advances, writes it to
D1, and the server component reads the cached string (falling back to the
deterministic template on any mismatch).

- `insights.ts` has **8 Reads** (Overview, Credit, Deposits, Asset Quality,
  Capital, Profitability, Liquidity, Market Risk).
- Worst case, regenerate **all 8 every week** = ~32/month. With a
  primary→fallback retry that is at most ~64 calls/month — **about 2 a day.**
- Every free tier measured here allows *dozens of requests per minute* and
  hundreds-to-thousands per day. **Volume is a non-issue by three orders of
  magnitude.** The constraint is never the rate limit — it is quality,
  determinism-gating, and provider reliability.

**How to use the headroom well** (options, not decided):
- **Primary + cross-provider fallback**: one model writes; if it errors, is
  rate-limited, or trips the number-check, fall through to a second provider,
  then to the deterministic template. Costs nothing, removes single-provider
  risk.
- **Ensemble/vote for free**: since volume is free, generate from 2-3 models and
  keep the one that (a) passes the number-check and (b) is closest to the target
  length. Quality win at zero marginal cost.
- **Regeneration gate**: reuse the summarizer's input-hash trick so a Read is
  only rewritten when its numbers actually change — keeps output stable week to
  week and avoids gratuitous drift.

## Results by Read

### Overview — as of 2026-05

**Deterministic template (the thing being rewritten):**
> As of 2026-05: the sector is growing (assets +38.5% y/y) and profitable (ROE 34.2%), with NPL at 1.81% and capital comfortably above the minimum at 18.1%.

| provider · model | latency | in/out tok | tok/s | numbers |
|---|--:|--:|--:|:--|
| groq · llama-3.3-70b-versatile | 0.6s | 498/47 | 83 | ✅ |
| groq · openai/gpt-oss-120b | 2.5s | 538/898 | 366 | ✅ |
| groq · openai/gpt-oss-20b | 0.7s | 538/499 | 737 | ✅ |
| groq · meta-llama/llama-4-scout-17b-16e-instruct | 0.7s | 474/67 | 98 | ✅ |
| groq · qwen/qwen3.6-27b | 4.1s | 530/1934 | 477 | ✅ 🧠 |
| groq · llama-3.1-8b-instant | 0.7s | 498/78 | 113 | ✅ |
| cerebras · gpt-oss-120b | 0.4s | 538/592 | 1599 | ✅ |
| cerebras · zai-glm-4.7 | 3.1s | 470/2729 | 887 | ✅ |
| cerebras · gemma-4-31b | 0.2s | 546/67 | 375 | ✅ |
| google · gemini-2.5-flash-lite | 0.7s | 530/56 | 82 | ✅ |
| google · gemini-flash-lite-latest | 0.8s | 530/85 | 108 | ✅ |
| google · gemini-2.5-flash | 0.3s | — | — | ❌ HTTP 429: [{   "error": {     "code": 429,     "message": "Your project has exceeded its monthly spending cap. Please go to AI Studio at https://ai.st |
| google · gemini-3.1-flash-lite | 0.1s | — | — | ❌ HTTP 429: [{   "error": {     "code": 429,     "message": "Your project has exceeded its monthly spending cap. Please go to AI Studio at https://ai.st |
| google · gemini-flash-latest | 0.1s | — | — | ❌ HTTP 429: [{   "error": {     "code": 429,     "message": "Your project has exceeded its monthly spending cap. Please go to AI Studio at https://ai.st |

**Outputs:**

- **groq · llama-3.3-70b-versatile**  
  > The sector's 38.5% y/y asset growth, driven by 42.1% loan expansion, fuels a 34.2% ROE, as a widening 4.35% NIM supports profitability.
- **groq · openai/gpt-oss-120b**  
  > Assets rose 38.5% y/y, loans 42.1% and deposits 36.0%, fueling a 34.2% ROE and a NIM of 4.35% (+0.07pp), while a stable 1.81% NPL and 18.1% capital ratio (6.1pp over the 12% floor) keep funding comfortable at an 88% loan‑to‑deposit ratio.
- **groq · openai/gpt-oss-20b**  
  > Assets grew 38.5% y/y, loans 42.1% and deposits 36.0%, sustaining a 1.81% NPL and 18.1% CAR, while a 4.35% NIM (+0.07pp) and 34.2% ROE confirm margin expansion on a 88% LDR.
- **groq · meta-llama/llama-4-scout-17b-16e-instruct**  
  > Turkish banks report strong balance sheet growth (assets +38.5% y/y) with comfortable funding (LDR 88%) and stable asset quality (NPL 1.81%), driving profitability (ROE 34.2%) through widening margins (NIM +0.07pp to 4.35%).
- **groq · qwen/qwen3.6-27b**  
  > Loan growth of 42.1% outpaces deposit expansion of 36.0% within a comfortable 88% LDR, supporting a 34.2% ROE as net interest margin widens 0.07pp to 4.35% against 1.81% NPLs and an 18.1% capital ratio.
- **groq · llama-3.1-8b-instant**  
  > As the Turkish banking sector continues to expand its balance sheet with assets growing 38.5% y/y, loans outpacing deposits, and capital comfortably above the minimum at 18.1%, its profitability remains robust, reflected in a 34.2% ROE and widening NIM at 4.35%, despite a stable NPL ratio of 1.81%.
- **cerebras · gpt-oss-120b**  
  > The sector’s balance sheet surged 38.5% y/y, driven by 42.1% loan growth that outpaced 36.0% deposit expansion, lifting NIM to 4.35% (+0.07pp) and underpinning a 34.2% ROE, while capital remains at 18.1%—6.1pp above the 12% floor—and NPL stays low at 1.81% (+0.04pp).
- **cerebras · zai-glm-4.7**  
  > Robust expansion with 42.1% loan growth drives strong profitability with ROE at 34.2% and NIM at 4.35%, while asset quality remains stable at 1.81% and capital buffers comfortable at 18.1%.
- **cerebras · gemma-4-31b**  
  > Strong balance sheet expansion, led by 42.1% loan growth, is driving a 34.2% ROE as NIM widens to 4.35%, while capital remains robust at 18.1% and asset quality stays stable with an NPL ratio of 1.81%.
- **google · gemini-2.5-flash-lite**  
  > Robust loan growth of 42.1% alongside a 36.0% deposit expansion drives a widening NIM to 4.35%, supporting a strong ROE of 34.2% with NPLs remaining stable at 1.81%.
- **google · gemini-flash-lite-latest**  
  > The banking sector maintains robust momentum with assets expanding 38.5% y/y and a 34.2% ROE, supported by a widening 4.35% NIM and a comfortable 88% loan-to-deposit ratio, while asset quality remains stable at 1.81% NPL and capital adequacy sits 6.1pp above the 12% minimum.

### Asset Quality — as of 2026-05

**Deterministic template (the thing being rewritten):**
> Headline asset quality is still benign — NPLs at 1.81% — with coverage at 74.2% and slipping; the pockets to watch are consumer cards books.

| provider · model | latency | in/out tok | tok/s | numbers |
|---|--:|--:|--:|:--|
| groq · llama-3.3-70b-versatile | 0.5s | 475/52 | 107 | ✅ |
| groq · openai/gpt-oss-120b | 1.5s | 514/408 | 264 | ✅ |
| groq · openai/gpt-oss-20b | 2.6s | 514/2048 | 793 | ✅ |
| groq · meta-llama/llama-4-scout-17b-16e-instruct | 0.5s | 455/61 | 133 | ✅ |
| groq · qwen/qwen3.6-27b | 3.1s | 485/1578 | 509 | ✅ 🧠 |
| groq · llama-3.1-8b-instant | 0.5s | 475/70 | 138 | ✅ |
| cerebras · gpt-oss-120b | 0.6s | 514/1142 | 1961 | ✅ |
| cerebras · zai-glm-4.7 | 2.9s | 446/1532 | 535 | ✅ |
| cerebras · gemma-4-31b | 0.2s | 504/70 | 302 | ✅ |
| google · gemini-2.5-flash-lite | 0.1s | — | — | ❌ HTTP 429: [{   "error": {     "code": 429,     "message": "Your project has exceeded its monthly spending cap. Please go to AI Studio at https://ai.st |
| google · gemini-flash-lite-latest | 0.1s | — | — | ❌ HTTP 429: [{   "error": {     "code": 429,     "message": "Your project has exceeded its monthly spending cap. Please go to AI Studio at https://ai.st |
| google · gemini-2.5-flash | 0.1s | — | — | ❌ HTTP 429: [{   "error": {     "code": 429,     "message": "Your project has exceeded its monthly spending cap. Please go to AI Studio at https://ai.st |
| google · gemini-3.1-flash-lite | 0.2s | — | — | ❌ HTTP 429: [{   "error": {     "code": 429,     "message": "Your project has exceeded its monthly spending cap. Please go to AI Studio at https://ai.st |
| google · gemini-flash-latest | 0.2s | — | — | ❌ HTTP 429: [{   "error": {     "code": 429,     "message": "Your project has exceeded its monthly spending cap. Please go to AI Studio at https://ai.st |

**Outputs:**

- **groq · llama-3.3-70b-versatile**  
  > Headline asset quality remains benign with NPLs at 1.81%, but pockets of stress are emerging, notably in consumer cards with a 3.6% NPL ratio, as NPL stock grows 46.0% y/y.
- **groq · openai/gpt-oss-120b**  
  > Despite a low 1.81% NPL ratio, the 46% YoY surge in NPL stock and a 0.5pp dip in coverage to 74.2% signal emerging pressure, amplified by a rising 8.4% stage‑2 watchlist and elevated 3.6% card‑NPLs versus 2.9% SME.
- **groq · openai/gpt-oss-20b**  
  > 
- **groq · meta-llama/llama-4-scout-17b-16e-instruct**  
  > Turkish banks' asset quality remains broadly stable with an NPL ratio of 1.81%, but pockets of stress emerge in consumer cards with 3.6% NPL, as stage-2 loans migrate upward to 8.4% and provision coverage slips to 74.2%.
- **groq · qwen/qwen3.6-27b**  
  > Headline NPLs hold at 1.81%, yet rapid NPL stock growth of 46.0% year-on-year is eroding provision coverage to 74.2%, while Stage-2 loans climb to 8.4%, signaling migration risk concentrated in cards at 3.6%.
- **groq · llama-3.1-8b-instant**  
  > Turkish banks' asset quality remains benign, with NPLs at 1.81%, albeit coverage slipping to 74.2% as the book seasons, while a growing 46.0% y/y NPL stock and rising stage-2 loans at 8.4% highlight pockets of stress in consumer cards and SME loans.
- **cerebras · gpt-oss-120b**  
  > Turkey’s NPL ratio stays low at 1.81% (+0.04pp m/m), yet the 46% y/y surge in NPL stock and a 0.3pp rise in stage‑2 loans to 8.4% signal pressure, while coverage slips to 74.2% (‑0.5pp) and retail card NPLs hit 3.6% versus 2.9% for SMEs.
- **cerebras · zai-glm-4.7**  
  > Headline asset quality remains benign at 1.81%, but rapid NPL stock growth of 46.0% and rising Stage-2 exposure at 8.4% are pressuring coverage to 74.2%, with stress concentrated in consumer cards at 3.6%.
- **cerebras · gemma-4-31b**  
  > While the 1.81% NPL ratio remains benign, rising Stage-2 loans to 8.4% and a 46.0% y/y surge in NPL stock signal mounting pressure, particularly within retail cards where NPLs reached 3.6% as coverage slipped to 74.2%.

### Profitability — as of 2026-05

**Deterministic template (the thing being rewritten):**
> The sector earns 34.2% on equity — roughly at inflation (+2.2pp real) — with NIM at 4.35% and widening.

| provider · model | latency | in/out tok | tok/s | numbers |
|---|--:|--:|--:|:--|
| groq · llama-3.3-70b-versatile | 0.5s | 430/58 | 107 | ✅ |
| groq · openai/gpt-oss-120b | 2.4s | 470/983 | 411 | ✅ |
| groq · openai/gpt-oss-20b | 1.7s | 470/766 | 447 | ✅ |
| groq · meta-llama/llama-4-scout-17b-16e-instruct | 1.2s | 409/74 | 63 | ✅ |
| groq · qwen/qwen3.6-27b | 4.0s | 443/2048 | 512 | ⚠️ NEW#['1', '30', '-45', '2', '-3', '12', '2', '1', '2', '3', '38', '30', '-45', '3', '1', '2', '3', '4', '6', '7', '8', '9', '10', '11', '12', '13', '14', '15', '16', '17', '18', '19', '20', '21', '22', '23', '24', '25', '26', '27', '28', '29', '29', '30', '-45', '30', '30', '1', '2', '3', '4', '6', '7', '8', '9', '10', '11', '12', '13', '14', '15', '16', '17', '18', '19', '20', '21', '22', '23', '24', '25', '26', '27', '28', '29', '29', '35', '29', '30', '1', '2', '3', '4', '6', '7', '8', '9', '10', '11', '12', '13', '14', '15', '16', '17', '18', '19', '20', '21', '22', '23', '24', '25', '26', '27', '28', '29', '30', '-35', '30', '30', '-45', '30', '3'] |
| groq · llama-3.1-8b-instant | 0.3s | 430/61 | 242 | ✅ |
| cerebras · gpt-oss-120b | 0.4s | 470/602 | 1693 | ✅ |
| cerebras · zai-glm-4.7 | 2.2s | 401/1710 | 790 | ✅ |
| cerebras · gemma-4-31b | 1.0s | 454/57 | 59 | ✅ |
| google · gemini-2.5-flash-lite | 0.2s | — | — | ❌ HTTP 429: [{   "error": {     "code": 429,     "message": "Your project has exceeded its monthly spending cap. Please go to AI Studio at https://ai.st |
| google · gemini-flash-lite-latest | 0.1s | — | — | ❌ HTTP 429: [{   "error": {     "code": 429,     "message": "Your project has exceeded its monthly spending cap. Please go to AI Studio at https://ai.st |
| google · gemini-2.5-flash | 0.2s | — | — | ❌ HTTP 429: [{   "error": {     "code": 429,     "message": "Your project has exceeded its monthly spending cap. Please go to AI Studio at https://ai.st |
| google · gemini-3.1-flash-lite | 0.1s | — | — | ❌ HTTP 429: [{   "error": {     "code": 429,     "message": "Your project has exceeded its monthly spending cap. Please go to AI Studio at https://ai.st |
| google · gemini-flash-latest | 0.1s | — | — | ❌ HTTP 429: [{   "error": {     "code": 429,     "message": "Your project has exceeded its monthly spending cap. Please go to AI Studio at https://ai.st |

**Outputs:**

- **groq · llama-3.3-70b-versatile**  
  > The sector earns 34.2% on equity, barely positive in real terms at +2.2pp versus 32.0% CPI, as NIM widens to 4.35% with a 0.07pp monthly increase, driven by funding repricing.
- **groq · openai/gpt-oss-120b**  
  > ROE at 34.2%—just 2.2pp above the 32.0% CPI—delivers strong nominal returns but limited real gain, while NIM’s 0.07pp monthly rise to 4.35% from funding repricing partly offsets a 0.03pp rise in operating costs to 2.05% of assets, leaving ROA at 3.1%.
- **groq · openai/gpt-oss-20b**  
  > Sector ROE sits at 34.2%, just 2.2pp above 32% CPI, while NIM widens to 4.35% (+0.07pp) as funding reprices, yet operating costs climb to 2.05% of assets (+0.03pp), tempering the 3.1% ROA.
- **groq · meta-llama/llama-4-scout-17b-16e-instruct**  
  > Turkish banks' 34.2% ROE outstrips inflation by a mere 2.2pp, as widening NIMs (+0.07pp) to 4.35% help offset rising operating costs (2.05% of assets, +0.03pp), with ROA at 3.1% reflecting underlying earnings power.
- **groq · qwen/qwen3.6-27b**  
  > <think>
Here's a thinking process:

1.  **Analyze User Input:**
   - **Role:** Write a one-sentence editorial lead ('The Read') for a Turkish banking-sector dashboard.
   - **Voice:** Terse, analytical, BBVA Research style.
   - **Length:** About 30-45 words.
   - **Task:** Synthesize vitals into a 'so what', connect causally where facts support it. Pick 2-3 threads. Do NOT list every number.
   - **HARD RULE:** Use ONLY numbers from the facts. Never invent, round, or compute a new figure.
   - **Output:** ONLY the sentence. No preamble, markdown, or reasoning.
   - **Facts:** roe: 34.2, roe_real_pp: 2.2, cpi: 32.0, nim: 4.35, nim_delta_pp: 0.07, roa: 3.1, opex: 2.05, opex_delta_pp: 0.03
   - **Context/Drivers:** ROE 34.2% nominal, +2.2pp vs 12m-avg CPI (32.0%), barely positive in real terms. NIM 4.35% (+0.07pp m/m) — margins widening as funding reprices down. ROA 3.1%. Opex 2.05% (+0.03pp m/m).
   - **Current Template:** The sector earns 34.2% on equity — roughly at inflation (+2.2pp real) — with NIM at 4.35% and widening.

2.  **Identify Key Threads & Causal Links:**
   - Thread 1: NIM widening (+0.07pp to 4.35%) due to funding repricing.
   - Thread 2: This margin expansion supports a 34.2% ROE, which sits +2.2pp above 32.0% CPI.
   - Thread 3: ROA holds at 3.1% despite a slight 0.03pp uptick in operating costs (2.05%).
   - Need to connect causally: Funding repricing lifts NIM to 4.35% (+0.07pp), underpinning a 34.2% ROE that clears 32.0% inflation by 2.2pp, while a 3.1% ROA absorbs a 0.03pp rise in operating costs to 2.05%.
   - Check word count: ~38 words. Good.
   - Check numbers used: 4.35, 0.07, 34.2, 32.0, 2.2, 3.1, 0.03, 2.05. All from facts.
   - Check voice: Terse, analytical, BBVA Research style.
   - Check constraints: One sentence, 30-45 words, causal link, only given numbers, no markdown/preamble.

3.  **Draft Construction (Mental Refinement):**
   Funding repricing lifts NIM to 4.35% (+0.07pp), underpinning a 34.2% ROE that clears 32.0% CPI by 2.2pp, while a 3.1% ROA absorbs a 0.03pp operating cost uptick to 2.05%.
   Word count check: 
   Funding(1) repricing(2) lifts(3) NIM(4) to(5) 4.35%(6) (+0.07pp),(7) underpinning(8) a(9) 34.2%(10) ROE(11) that(12) clears(13) 32.0%(14) CPI(15) by(16) 2.2pp,(17) while(18) a(19) 3.1%(20) ROA(21) absorbs(22) a(23) 0.03pp(24) operating(25) cost(26) uptick(27) to(28) 2.05%.(29) -> 29 words. A bit short. Need 30-45.
   Let's adjust slightly to hit the range while maintaining tone.
   "Funding repricing pushes NIM to 4.35% (+0.07pp), underpinning a 34.2% ROE that clears 32.0% CPI by 2.2pp, while a 3.1% ROA absorbs a 0.03pp operating cost drift to 2.05%." (30 words) - exactly 30. Let's count carefully.
   Funding(1) repricing(2) pushes(3) NIM(4) to(5) 4.35%(6) (+0.07pp),(7) underpinning(8) a(9) 34.2%(10) ROE(11) that(12) clears(13) 32.0%(14) CPI(15) by(16) 2.2pp,(17) while(18) a(19) 3.1%(20) ROA(21) absorbs(22) a(23) 0.03pp(24) operating(25) cost(26) drift(27) to(28) 2.05%.(29) -> 29. I'll add "sector" or adjust phrasing to hit ~32.
   "Funding repricing pushes NIM to 4.35% (+0.07pp), underpinning a 34.2% ROE that clears 32.0% CPI by 2.2pp, while a 3.1% ROA absorbs a 0.03pp operating cost drift to 2.05%." -> Let's count words properly. Sometimes numbers with % count as one. I'll aim for ~35.
   "Funding repricing lifts NIM to 4.35% (+0.07pp), underpinning a 34.2% ROE that clears 32.0% CPI by 2.2pp, while a 3.1% ROA absorbs a 0.03pp operating cost uptick to 2.05%." (29)
   Let's expand slightly: "Funding repricing lifts NIM to 4.35% (+0.07pp), underpinning a 34.2% ROE that clears 32.0% CPI by 2.2pp, while a 3.1% ROA absorbs a 0.03pp operating cost uptick to 2.05%." I'll add "sector" and adjust: "Funding repricing lifts sector NIM to 4.35% (+0.07pp), underpinning a 34.2% ROE that clears 32.0% CPI by 2.2pp, while a 3.1% ROA absorbs a 0.03pp operating cost uptick to 2.05%." (30)
   Let's count exactly: Funding(1) repricing(2) lifts(3) sector(4) NIM(5) to(6) 4.35%(7) (+0.07pp),(8) underpinning(9) a(10) 34.2%(11) ROE(12) that(13) clears(14) 32.0%(15) CPI(16) by(17) 2.2pp,(18) while(19) a(20) 3.1%(21) ROA(22) absorbs(23) a(24) 0.03pp(25) operating(26) cost(27) uptick(28) to(29) 2.05%.(30)
   I'll add "nominal" or "real" to be precise, or just rephrase slightly to hit 32-35.
   "Funding repricing lifts NIM to 4.35% (+0.07pp), underpinning a 34.2% ROE that clears 32.0% CPI by 2.2pp, while a 3.1% ROA absorbs a 0.03pp operating cost uptick to 2.05%." -> I'll just accept ~30. The constraint says "about 30-45 words". 30 is fine.
   Let's check the causal link: "Funding repricing lifts NIM... underpinning ROE... while ROA absorbs opex uptick." This connects the dots well.
   Check numbers: 4.35, 0.07, 34.2, 3
- **groq · llama-3.1-8b-instant**  
  > Profitability in the Turkish banking sector remains fragile, with nominal returns barely outpacing inflation, but a widening net interest margin of 4.35% (+0.07pp m/m) and stable return on assets of 3.1% offer some respite amidst deteriorating operating efficiency.
- **cerebras · gpt-oss-120b**  
  > ROE 34.2% barely outpaces 32.0% CPI, delivering only 2.2pp real gain, while NIM widens to 4.35% (+0.07pp) as funding reprices, yet operating costs rise to 2.05% (+0.03pp), tempering ROA at 3.1%.
- **cerebras · zai-glm-4.7**  
  > Nominal ROE of 34.2% yields only a +2.2pp real return over inflation, as funding repricing lifts NIM to 4.35% while operating costs deteriorate to 2.05%.
- **cerebras · gemma-4-31b**  
  > Sector profitability remains marginally positive in real terms with an ROE of 34.2% (+2.2pp vs CPI), as a slight NIM expansion to 4.35% offsets a modest deterioration in operating costs to 2.05% of assets.

### Liquidity — as of 2026-05

**Deterministic template (the thing being rewritten):**
> Funding is manageable: TL loan-to-deposit 96% (private) / 118% (public), FC deposits 39.5% of the base, and LCR at 148%.

| provider · model | latency | in/out tok | tok/s | numbers |
|---|--:|--:|--:|:--|
| groq · llama-3.3-70b-versatile | 0.4s | 412/47 | 131 | ✅ |
| groq · openai/gpt-oss-120b | 1.1s | 451/395 | 347 | ✅ |
| groq · openai/gpt-oss-20b | 2.0s | 451/807 | 403 | ✅ |
| groq · meta-llama/llama-4-scout-17b-16e-instruct | 0.9s | 391/75 | 84 | ✅ |
| groq · qwen/qwen3.6-27b | 4.0s | 432/2048 | 511 | ⚠️ NEW#['1', '2', '1', '2', '3', '30', '-45', '1', '42', '40', '40', '40', '40', '30', '-45', '40', '1', '2', '3', '4', '6', '7', '8', '9', '10', '11', '12', '13', '14', '15', '16', '17', '18', '19', '20', '21', '22', '23', '24', '25', '26', '27', '28', '29', '30', '31', '32', '33', '34', '35', '36', '37', '38', '39', '39', '11'] |
| groq · llama-3.1-8b-instant | 0.5s | 412/60 | 130 | ✅ |
| cerebras · gpt-oss-120b | 0.4s | 451/622 | 1514 | ✅ |
| cerebras · zai-glm-4.7 | 1.8s | 383/1173 | 634 | ✅ |
| cerebras · gemma-4-31b | 0.2s | 449/63 | 386 | ✅ |
| google · gemini-2.5-flash-lite | 0.2s | — | — | ❌ HTTP 429: [{   "error": {     "code": 429,     "message": "Your project has exceeded its monthly spending cap. Please go to AI Studio at https://ai.st |
| google · gemini-flash-lite-latest | 0.2s | — | — | ❌ HTTP 429: [{   "error": {     "code": 429,     "message": "Your project has exceeded its monthly spending cap. Please go to AI Studio at https://ai.st |
| google · gemini-2.5-flash | 0.2s | — | — | ❌ HTTP 429: [{   "error": {     "code": 429,     "message": "Your project has exceeded its monthly spending cap. Please go to AI Studio at https://ai.st |
| google · gemini-3.1-flash-lite | 0.1s | — | — | ❌ HTTP 429: [{   "error": {     "code": 429,     "message": "Your project has exceeded its monthly spending cap. Please go to AI Studio at https://ai.st |
| google · gemini-flash-latest | 0.1s | — | — | ❌ HTTP 429: [{   "error": {     "code": 429,     "message": "Your project has exceeded its monthly spending cap. Please go to AI Studio at https://ai.st |

**Outputs:**

- **groq · llama-3.3-70b-versatile**  
  > A comfortable liquidity position is maintained, with a wide 148% LCR cushion and ₺320bn net CBRT funding surplus, as dollarization unwinds, evidenced by a 39.5% foreign currency deposit share.
- **groq · openai/gpt-oss-120b**  
  > Public TL loan‑to‑deposit at 118% versus 96% in private signals excess lending, yet a 148% LCR and a ₺320 bn net CBRT funding surplus provide a robust liquidity buffer as FC deposits slip to 39.5% of the base, down 2.1 pp year‑on‑year.
- **groq · openai/gpt-oss-20b**  
  > Public TL loan‑to‑deposit 118% versus private 96% signals over‑lending, yet the 39.5% FC deposit share (down 2.1pp) and 148% LCR, coupled with a 320bn net CBRT funding surplus, keep liquidity manageable.
- **groq · meta-llama/llama-4-scout-17b-16e-instruct**  
  > Turkish banks' liquidity remains robust, with a 148% LCR and ₺320bn surplus parked at the CBRT, while declining dollarization (FC deposits: 39.5%, down 2.1pp y/y) and diverging TL funding trends (public: 118%, private: 96% LDR) point to manageable funding costs.
- **groq · qwen/qwen3.6-27b**  
  > <think>
Thinking Process:

1.  **Deconstruct the Facts & Drivers:**
    *   `tl_ldr_public`: 118 (Public TL LDR is 118%, meaning >100%, so public sector is fully leveraged/lent).
    *   `tl_ldr_private`: 96 (Private TL LDR is 96%, slightly below 100%).
    *   `fc_dep_share`: 39.5 (FC deposits are 39.5% of base).
    *   `fc_dep_delta_pp`: 2.1 (FC deposits dropped 2.1pp y/y, indicating de-dollarization/unwinding).
    *   `lcr`: 148 (LCR is 148%, well above the 100% floor, indicating strong liquidity buffer).
    *   `net_cbrt_funding_bn`: 320 (Net CBRT funding surplus of ₺320bn, meaning excess liquidity parked at central bank).

2.  **Identify the "So What" / Narrative Threads:**
    *   *Thread 1: Liquidity is abundant.* LCR is 148%, and there's a ₺320bn surplus at CBRT. This suggests the system is flush with TL liquidity.
    *   *Thread 2: Funding structure is shifting/stable.* FC deposits are falling (39.5%, -2.1pp), which is good for currency risk but might imply a shift to TL. Public sector is highly leveraged (118%), private is tight (96%).
    *   *Synthesis:* The system has ample liquidity (LCR 148%, ₺320bn surplus) while de-dollarization continues (FC 39.5%, -2.1pp), though the public sector remains fully leveraged (118%) compared to the private sector (96%).
    *   *Causal connection:* The surplus at CBRT and high LCR suggest liquidity isn't a constraint. The drop in FC deposits might be contributing to TL liquidity abundance, or at least co-occurring. The public LDR at 118% shows where the TL is going (fully lent to public), while private is at 96%.

3.  **Drafting the Lead (Iterative refinement for voice and constraints):**
    *   *Voice:* BBVA Research style. Terse, analytical, causal. No fluff.
    *   *Constraint:* ONE sentence. 30-45 words. ONLY numbers from facts. No new numbers.
    *   *Draft 1:* Liquidity remains ample with an LCR of 148% and a ₺320bn net CBRT surplus, even as de-dollarization accelerates with FC deposits falling 2.1pp to 39.5%, while the public TL book stays fully leveraged at 118% versus 96% for private.
        *   *Word Count:* 42 words.
        *   *Numbers:* 148, 320, 2.1, 39.5, 118, 96. All present.
        *   *Flow:* Good. Connects liquidity (LCR/Surplus) to currency shift (FC drop) and structural lending (LDR split).
        *   *Critique:* "accelerates" might be an inference not strictly in facts, though "-2.1pp" implies a drop. "Falling" is safer. "Fully leveraged" is an interpretation of 118%, which is supported by the driver text "public TL book more than fully lent". The prompt allows connecting causally where facts support it. The driver explicitly says "public TL book more than fully lent", so using that language is safe.
        *   *Refinement:* "Liquidity remains ample with an LCR of 148% and a ₺320bn net CBRT surplus, as de-dollarization persists with FC deposits down 2.1pp to 39.5%, while the public TL book remains fully leveraged at 118% against 96% for private."
        *   *Word Count:* 40 words.
        *   *Numbers:* 148, 320, 2.1, 39.5, 118, 96.
        *   *Check:* "down 2.1pp" uses the delta. "to 39.5%" uses the share. "118%" and "96%" used. "148%" used. "320bn" used.
        *   *Voice Check:* "Liquidity remains ample..." is a bit generic. BBVA might be more direct. "System liquidity is robust..." or "Funding conditions are buoyant..."
        *   *Better phrasing:* "System liquidity is robust with an LCR of 148% and a ₺320bn net CBRT surplus, supported by de-dollarization as FC deposits decline 2.1pp to 39.5%, while the public TL book stays fully leveraged at 118% versus 96% for private."
        *   *Word Count:* 40 words.
        *   *Causal link:* "supported by de-dollarization" might be a stretch causally? The facts show FC dropping and TL surplus rising. It's plausible, but the prompt asks to connect causally *where facts support it*. The facts show both. The driver mentions "system parks TL", implying TL abundance. The drop in FC usually increases TL liquidity. This is a standard banking mechanic. Connecting them is likely acceptable as a synthesis.
        *   *Result:* "System liquidity is robust with an LCR of 148% and a ₺320bn net CBRT surplus, as de-dollarization continues with FC deposits down 2.1pp to 39.5%, while the public TL book remains fully leveraged at 118% versus 96% for private."
        *   *Word Count:* 40 words.
        *   *Numbers:* 148, 320, 2.1, 39.5, 118, 96.
        *   *Structure:* One sentence. Flowing. Synthesizes vitals. "So what" is liquidity is robust despite structural imbalances in LDR.
        *   *Final Polish:* "System liquidity is robust with an LCR of 148% and a ₺320bn net CBRT surplus, as de-dollarization proceeds with FC deposits down 2.1pp to 39.5%, while the public TL book remains fully leveraged at 118% versus 96% for private."
        *   *Word Count:* 40 words.
        *   *Numbers Check:* 148 (yes), 320 (yes), 2.1 (yes), 39.5 (yes), 118 (yes), 96 (yes).
        *   *No invented numbers:* Yes.
        *   *No rounding:* Yes.
        *   *One sentence:* Yes.
        *   *30-45 words:* 40 words. Yes.
        *   *Output format:* ONLY the sentence. No markdown.

    *   *Result Text:* System liquidity is robust with an LCR of 148% and a ₺320bn net CBRT surplus, as de-dollarization proceeds with FC deposits down 2.1pp to 39.5%, while the public TL book remains fully leveraged at 118% versus 96% for private.

    *   *Wait, let me check the word count carefully.*
        "System liquidity is robust with an LCR of 148% and a ₺320bn net CBRT surplus, as de-dollarization proceeds with FC deposits down 2.1pp to 39.5%, while the public TL book remains fully leveraged at 118% versus 96% for private."
        System (1) liquidity (2) is (3) robust (4) with (5) an (6) LCR (7) of (8) 148% (9) and (10) a (11) ₺320bn (12) net (13) CBRT (14) surplus, (15) as (16) de-dollarization (17) proceeds (18) with (19) FC (20) deposits (21) down (22) 2.1pp (23) to (24) 39.5%, (25) while (26) the (27) public (28) TL (29) book (30) remains (31) fully (32) leveraged (33) at (34) 118% (35) versus (36) 96% (37) for (38) private. (39)
        39 words. Perfect.
        Numbers: 148, 320, 2.1, 39.5, 11
- **groq · llama-3.1-8b-instant**  
  > A manageable funding profile is sustained by a 39.5% FC deposit share, a 148% LCR, and a ₺320bn net CBRT funding surplus, which in turn supports a private TL loan-to-deposit ratio of 96% and public ratio of 118%.
- **cerebras · gpt-oss-120b**  
  > Public TL loan‑to‑deposit at 118% versus 96% in private banks signals tighter domestic funding, yet a 148% LCR and a ₺320 bn net CBRT surplus provide ample liquidity, while FC deposits, now 39.5% of the base and down 2.1 pp, reflect a modest dollarisation unwind.
- **cerebras · zai-glm-4.7**  
  > Robust liquidity buffers, with LCR at 148% and a ₺320bn surplus at the central bank, offset public sector tightness of 118% as dollarization unwinds by 2.1pp to bring FC deposits to 39.5%.
- **cerebras · gemma-4-31b**  
  > Liquidity remains robust with an LCR of 148% and ₺320bn in net CBRT funding, as the unwinding of dollarization leaves FC deposits at 39.5% of the base despite public TL loan-to-deposit ratios reaching 118%.

## Model catalogues visible to each key

**groq** (17): `allam-2-7b`, `canopylabs/orpheus-arabic-saudi`, `canopylabs/orpheus-v1-english`, `groq/compound`, `groq/compound-mini`, `llama-3.1-8b-instant`, `llama-3.3-70b-versatile`, `meta-llama/llama-4-scout-17b-16e-instruct`, `meta-llama/llama-prompt-guard-2-22m`, `meta-llama/llama-prompt-guard-2-86m`, `openai/gpt-oss-120b`, `openai/gpt-oss-20b`, `openai/gpt-oss-safeguard-20b`, `qwen/qwen3-32b`, `qwen/qwen3.6-27b`, `whisper-large-v3`, `whisper-large-v3-turbo`

**cerebras** (3): `gemma-4-31b`, `gpt-oss-120b`, `zai-glm-4.7`

**google** (55): `antigravity-preview-05-2026`, `aqa`, `deep-research-max-preview-04-2026`, `deep-research-preview-04-2026`, `deep-research-pro-preview-12-2025`, `gemini-2.0-flash`, `gemini-2.0-flash-001`, `gemini-2.0-flash-lite`, `gemini-2.0-flash-lite-001`, `gemini-2.5-computer-use-preview-10-2025`, `gemini-2.5-flash`, `gemini-2.5-flash-image`, `gemini-2.5-flash-lite`, `gemini-2.5-flash-native-audio-latest`, `gemini-2.5-flash-native-audio-preview-09-2025`, `gemini-2.5-flash-native-audio-preview-12-2025`, `gemini-2.5-flash-preview-tts`, `gemini-2.5-pro`, `gemini-2.5-pro-preview-tts`, `gemini-3-flash-preview`, `gemini-3-pro-image`, `gemini-3-pro-image-preview`, `gemini-3-pro-preview`, `gemini-3.1-flash-image`, `gemini-3.1-flash-image-preview`, `gemini-3.1-flash-lite`, `gemini-3.1-flash-lite-image`, `gemini-3.1-flash-lite-preview`, `gemini-3.1-flash-live-preview`, `gemini-3.1-flash-tts-preview`, `gemini-3.1-pro-preview`, `gemini-3.1-pro-preview-customtools`, `gemini-3.5-flash`, `gemini-3.5-live-translate-preview`, `gemini-embedding-001`, `gemini-embedding-2`, `gemini-embedding-2-preview`, `gemini-flash-latest`, `gemini-flash-lite-latest`, `gemini-omni-flash-preview`, `gemini-pro-latest`, `gemini-robotics-er-1.5-preview`, `gemini-robotics-er-1.6-preview`, `gemma-4-26b-a4b-it`, `gemma-4-31b-it`, `imagen-4.0-fast-generate-001`, `imagen-4.0-generate-001`, `imagen-4.0-ultra-generate-001`, `lyria-3-clip-preview`, `lyria-3-pro-preview`, `lyria-realtime-exp`, `nano-banana-pro-preview`, `veo-3.1-fast-generate-preview`, `veo-3.1-generate-preview`, `veo-3.1-lite-generate-preview`
