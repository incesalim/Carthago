<!--
  Curated findings on top of the auto-generated reliability-gauntlet report
  (appended verbatim below). Regenerate the lower section by dispatching
  .github/workflows/test-free-models.yml and downloading the
  free-model-gauntlet artifact.
-->

# Round 3 — reliability gauntlet (Groq + Cerebras)

Round 3 measured the **downside** of using a free model for "The Read": across
**7 finalists × 11 Reads (8 real + 3 number-traps) × 3 repeats at temperature 0**
(231 samples), how often does each model break the number-lock or the format, and
how stable is it? (Gemini excluded — not free for us. Full method + every output
in the machine report below.)

## Headline results

| model | real invent-rate | reliability | length fit | speed | verdict |
|---|--:|---|---|--:|---|
| **cerebras · gpt-oss-120b** | **0%** | clean | 94% in 30–45w | 0.8s | **primary candidate** |
| **groq · openai/gpt-oss-120b** | **0%** | 1 timeout (3%) | 100% in-range | 7.4s* | **failover (same model)** |
| cerebras · gemma-4-31b | 0% | clean | 73% in-range | 0.2s | fast lightweight backup |
| groq · llama-3.1-8b-instant | 0% | clean | 67% in-range | 0.4s | backup |
| groq · llama-3.3-70b | 0% | clean | **9%** (writes short) | 0.9s | faithful but under-synthesises |
| cerebras · zai-glm-4.7 | 0% | **18% hard errors** | 44% | 3.3s | ❌ unreliable |
| groq · llama-4-scout | **~12%** | invents derived figures | 70% | 0.6s | ❌ rejected |

\* Groq's gpt-oss-120b was unusually slow this run (7.4s vs ~1–2s before); Cerebras
serves the *same model* at 0.8s and more consistently.

## What we learned

1. **The number-lock is robust.** 5 of 7 models invented **zero** real numbers across
   33 adversarial samples each, and at temp 0 they were near-identical run-to-run
   (stable week-to-week — what a cached headline needs).

2. **Rounding trap → everyone passed.** No model rounded 39.7→40 or 49.8→50; several
   wrote "nearly a third" for 33.4 (no digit, so safe).

3. **Derived-figure trap → the real discriminator, and only `llama-4-scout` failed.**
   Given CARs + minimum but not the buffer, it computed and stated `18.1−12 = 6.1`
   **and** `14.3−12 = 2.3` on all 3 tries; it also computed the real-ROE spread
   `34.2−31.9 = 2.3`. This is the dangerous mode — a plausible, authoritative,
   invented number — so llama-4-scout is out.

4. **`zai-glm-4.7` is out on reliability** — 18% of calls returned a message with no
   `content` (hard failure), concentrated on two of the three traps.

5. **Validator false-positive #2 found & fixed.** The Market Risk "invented `1`" flags
   were the `1` in **"1-year"** (a duration label), same family as round 2's "Stage-2".
   The check now skips digits glued to a label on *either* side (`Stage-2`, `1-year`),
   so `cerebras/gpt-oss-120b`'s true invent-rate is **0%**. **The real integration's
   guardrail must do the same** — banking prose is full of label-bound digits.

## Where this leaves us (evidence, not a final call)

The data points clearly at **`gpt-oss-120b`**: **Cerebras as primary** (0% invention,
0.8s, 94% on-length, best synthesis), **Groq's `openai/gpt-oss-120b` as failover**
(identical model, different provider → single-model quality with provider redundancy),
and **`cerebras/gemma-4-31b`** as a fast lightweight backup. Each step still gated by
the number-check → deterministic template. No winner is *declared* — but if we ship
Option 1, this is the stack the evidence supports.

---

# Machine report (reliability gauntlet)


*Run 2026-07-04 19:09 UTC · commit `d0d2eec8` · Groq + Cerebras · 7 models × 11 Reads × 3 repeats · temperature 0.0*

Gemini is excluded (not free for us). This round measures the **downside**: how often each model breaks the number-lock or the format, and how stable it is when called repeatedly at the temperature we'd ship.

## Scorecard — ranked by reliability (lower invent-rate is better)

| model | invent-rate | fmt-bad | empty/err | ≤45w | in 30–45w | avg lat | notes |
|---|--:|--:|--:|--:|--:|--:|:--|
| groq · openai/gpt-oss-120b | 0% (0/33) | 0% | 3% | 100% | 100% | 7.4s | — |
| cerebras · gemma-4-31b | 0% (0/33) | 0% | 0% | 100% | 73% | 0.2s | — |
| groq · llama-3.1-8b-instant | 0% (0/33) | 0% | 0% | 91% | 67% | 0.4s | — |
| cerebras · zai-glm-4.7 | 0% (0/33) | 0% | 18% | 100% | 44% | 3.3s | — |
| groq · llama-3.3-70b-versatile | 0% (0/33) | 0% | 0% | 100% | 9% | 0.9s | — |
| cerebras · gpt-oss-120b | 6% (2/33) | 0% | 0% | 94% | 94% | 0.8s | — |
| groq · meta-llama/llama-4-scout-17b-16e-instruct | 15% (5/33) | 0% | 9% | 93% | 70% | 0.6s | — |

*invent-rate = share of samples containing a number that isn't a fact (= how often we'd fall back to the deterministic template). fmt-bad = preamble/markdown/multi-sentence/multiline. Label digits (Stage-2, CET1) are not counted as invented.*

## Number-trap results (the interesting failures)

Each trap's facts omit a temptingly derivable/roundable figure. A model that stays clean respected the number-lock; a flagged one would be caught and fall back.

### TRAP: rounding

*Values invite rounding (39.7→40, 49.8→50, 33.4→33/'a third'). Any rounded number is invented.*

> template: Credit growth 39.7% y/y, led by state banks (49.8%); FX share 33.4% of the book.

| model | clean? | invented | sample rewrite |
|---|:--:|:--|:--|
| openai/gpt-oss-120b | ✅ | — | Robust 39.7% y/y loan expansion, anchored by a 49.8% surge at state banks, is tempered by a 33.4% FX exposure that could pressure margins as funding c |
| openai/gpt-oss-120b | ✅ | — | Robust loan growth of 39.7% y/y, propelled by a 49.8% surge at state banks, is tempered by a 33.4% FX‑denominated book, signalling heightened earnings |
| openai/gpt-oss-120b | ✅ | — | Robust 39.7% y/y loan expansion, anchored by a 49.8% surge at state banks, is tempered by a 33.4% FX exposure that could pressure margins as funding c |
| llama-3.3-70b-versatile | ✅ | — | Loan growth accelerated to 39.7% y/y, driven by state banks' 49.8% y/y expansion, with FX loans comprising 33.4% of the book. |
| llama-3.3-70b-versatile | ✅ | — | Loan growth accelerated to 39.7% y/y, driven by state banks' 49.8% y/y expansion, with FX loans comprising 33.4% of the book. |
| llama-3.3-70b-versatile | ✅ | — | Loan growth accelerated to 39.7% y/y, driven by state banks' 49.8% y/y expansion, with FX loans comprising 33.4% of the book. |
| meta-llama/llama-4-scout-17b-16e-instruct | ✅ | — | State banks drove loan growth with a 49.8% y/y expansion, outpacing the sector's 39.7% increase, as nearly a third of the book remained in foreign cur |
| meta-llama/llama-4-scout-17b-16e-instruct | — | (error) | ReadTimeout: HTTPSConnectionPool(host='api.groq.com', port=443): Read timed out. (read timeout=120) |
| meta-llama/llama-4-scout-17b-16e-instruct | ✅ | — | State banks drove loan growth with a 49.8% y/y expansion, outpacing the overall 39.7% credit growth, as foreign exchange exposures accounted for 33.4% |
| llama-3.1-8b-instant | ✅ | — | State banks' strong loan growth (49.8% y/y) is driving overall credit expansion (39.7% y/y), with foreign exchange exposure accounting for nearly a th |
| llama-3.1-8b-instant | ✅ | — | State banks' strong loan growth (49.8% y/y) is driving overall credit expansion (39.7% y/y), with foreign exchange exposure accounting for nearly a th |
| llama-3.1-8b-instant | ✅ | — | State banks' strong loan growth (49.8% y/y) is driving overall credit expansion (39.7% y/y), with foreign exchange exposure accounting for nearly a th |
| gpt-oss-120b | ✅ | — | Robust 39.7% y/y loan expansion, driven by a 49.8% surge at state banks, lifts the sector’s credit momentum while a 33.4% FX exposure flags heightened |
| gpt-oss-120b | ✅ | — | Robust 39.7% y/y loan expansion, driven by a 49.8% surge at state banks, lifts the sector’s credit momentum while a 33.4% FX exposure flags heightened |
| gpt-oss-120b | ✅ | — | Robust 39.7% y/y loan expansion, propelled by a 49.8% surge at state banks, underscores the sector’s reliance on a 33.4% FX‑denominated book, and pote |
| zai-glm-4.7 | — | (error) | KeyError: 'content' |
| zai-glm-4.7 | — | (error) | KeyError: 'content' |
| zai-glm-4.7 | — | (error) | KeyError: 'content' |
| gemma-4-31b | ✅ | — | Loan growth of 39.7% y/y remains driven by a stronger expansion in state banks at 49.8%, while the FX share of the book stands at 33.4%. |
| gemma-4-31b | ✅ | — | Loan growth of 39.7% y/y remains driven by a stronger expansion in state banks at 49.8%, while the FX share of the book stands at 33.4%. |
| gemma-4-31b | ✅ | — | Loan growth of 39.7% y/y remains driven by a stronger expansion in state banks at 49.8%, while the FX share of the book stands at 33.4%. |

### TRAP: derive real ROE

*ROE and CPI given, real spread NOT given. Computing 34.2-31.9=2.3 and stating it is invention.*

> template: The sector earns 34.2% on equity against 31.9% inflation, with NIM at 4.35%.

| model | clean? | invented | sample rewrite |
|---|:--:|:--|:--|
| openai/gpt-oss-120b | ✅ | — | With a real ROE of 34.2%—well above the 31.9% inflation rate—and a stable NIM of 4.35%, the banking sector is generating robust equity returns that ou |
| openai/gpt-oss-120b | ✅ | — | With a real ROE of 34.2%—well above the 31.9% inflation rate—and a stable NIM of 4.35%, the banking sector is generating robust equity returns that ou |
| openai/gpt-oss-120b | ✅ | — | With a real ROE of 34.2%—well above the 31.9% inflation rate—and a stable NIM of 4.35%, the banking sector is generating robust equity returns that ou |
| llama-3.3-70b-versatile | ✅ | — | The sector's 34.2% ROE outpaces 31.9% inflation, supported by a 4.35% NIM. |
| llama-3.3-70b-versatile | ✅ | — | The sector's 34.2% ROE outpaces 31.9% inflation, supported by a 4.35% NIM. |
| llama-3.3-70b-versatile | ✅ | — | The sector's 34.2% ROE outpaces 31.9% inflation, supported by a 4.35% NIM. |
| meta-llama/llama-4-scout-17b-16e-instruct | ✅ | — | Turkish banks' 34.2% ROE outstrips inflation at 31.9%, with a 4.35% NIM suggesting funding repricing and stable margins are contributing to the sector |
| meta-llama/llama-4-scout-17b-16e-instruct | ❌ | 2.3 | Turkish banks' 34.2% ROE outstrips inflation at 31.9%, with a 4.35% NIM suggesting funding repricing is lifting profitability, but real returns are tr |
| meta-llama/llama-4-scout-17b-16e-instruct | ✅ | — | Turkish banks' 34.2% ROE outstrips 31.9% inflation, suggesting real returns, while a 4.35% NIM supports the sector's profitability, indicating funding |
| llama-3.1-8b-instant | ✅ | — | The Turkish banking sector's 34.2% return on equity is supported by a 4.35% net interest margin, which in turn benefits from the relatively contained  |
| llama-3.1-8b-instant | ✅ | — | The Turkish banking sector's 34.2% return on equity is supported by a 4.35% net interest margin, which in turn benefits from the relatively contained  |
| llama-3.1-8b-instant | ✅ | — | The Turkish banking sector's 34.2% return on equity is supported by a 4.35% net interest margin, which in turn benefits from the relatively contained  |
| gpt-oss-120b | ✅ | — | With a real ROE of 34.2%—still outpacing 31.9% inflation—and a stable NIM of 4.35%, the banking sector’s profitability remains robust, suggesting that |
| gpt-oss-120b | ✅ | — | With real ROE at 34.2% outpacing inflation‑driven CPI of 31.9% and a stable NIM of 4.35%, the banking sector’s profitability remains robust, suggestin |
| gpt-oss-120b | ✅ | — | With a real ROE of 34.2%—still outpacing 31.9% inflation—and a stable NIM of 4.35%, the banking sector’s profitability remains robust, suggesting that |
| zai-glm-4.7 | — | (error) | KeyError: 'content' |
| zai-glm-4.7 | — | (error) | KeyError: 'content' |
| zai-glm-4.7 | — | (error) | KeyError: 'content' |
| gemma-4-31b | ✅ | — | The sector maintains a positive real return with an ROE of 34.2% slightly outpacing CPI at 31.9%, supported by a NIM of 4.35%. |
| gemma-4-31b | ✅ | — | The sector maintains a positive real return with an ROE of 34.2% slightly outpacing CPI at 31.9%, supported by a NIM of 4.35%. |
| gemma-4-31b | ✅ | — | The sector maintains a positive real return with an ROE of 34.2% slightly outpacing CPI at 31.9%, supported by a NIM of 4.35%. |

### TRAP: derive buffer

*CARs and minimum given, buffer NOT given. Computing 18.1-12=6.1 and stating it is invention.*

> template: Sector CAR 18.1% and CET1 14.3%, both above the 12% minimum.

| model | clean? | invented | sample rewrite |
|---|:--:|:--|:--|
| openai/gpt-oss-120b | ✅ | — | With a CAR of 18.1% and CET1 ratio of 14.3%, well above the 12% regulatory floor, Turkish banks enjoy a robust capital buffer that underpins resilienc |
| openai/gpt-oss-120b | ✅ | — | With a CAR of 18.1% and CET1 ratio of 14.3%—both comfortably above the 12% regulatory floor—the sector enjoys a robust capital buffer that underpins r |
| openai/gpt-oss-120b | ✅ | — | With a CAR of 18.1% and CET1 ratio of 14.3%, well above the 12% regulatory floor, Turkish banks enjoy a robust capital buffer that underpins resilienc |
| llama-3.3-70b-versatile | ✅ | — | Sector capital buffers, with a CAR of 18.1% and CET1 of 14.3%, remain comfortably above the 12% minimum. |
| llama-3.3-70b-versatile | ✅ | — | Sector capital buffers, with a CAR of 18.1% and CET1 of 14.3%, remain comfortably above the 12% minimum. |
| llama-3.3-70b-versatile | ✅ | — | Sector capital buffers, with a CAR of 18.1% and CET1 of 14.3%, remain comfortably above the 12% minimum requirement. |
| meta-llama/llama-4-scout-17b-16e-instruct | ❌ | 6.1, 2.3 | Turkish banks' 18.1% CAR and 14.3% CET1 ratios provide a comfortable 6.1% and 2.3% buffer, respectively, above the 12% minimum requirement, signaling  |
| meta-llama/llama-4-scout-17b-16e-instruct | ❌ | 6.1, 2.3 | Turkish banks' 18.1% CAR and 14.3% CET1 ratios provide a comfortable 6.1% and 2.3% buffer respectively above the 12% minimum, indicating a solid capit |
| meta-llama/llama-4-scout-17b-16e-instruct | ❌ | 6.1, 2.3 | Turkish banks' 18.1% CAR and 14.3% CET1 ratios provide a comfortable 6.1% and 2.3% buffer, respectively, above the 12% minimum requirement, indicating |
| llama-3.1-8b-instant | ✅ | — | The Turkish banking sector's robust capital position, with a CAR of 18.1% and CET1 ratio of 14.3%, comfortably exceeds the 12% minimum threshold, unde |
| llama-3.1-8b-instant | ✅ | — | The Turkish banking sector's robust capital position, with CAR at 18.1% and CET1 at 14.3%, comfortably exceeds the 12% minimum threshold, underscoring |
| llama-3.1-8b-instant | ✅ | — | The Turkish banking sector's robust capital position, with CAR at 18.1% and CET1 at 14.3%, comfortably exceeds the 12% minimum threshold, underscoring |
| gpt-oss-120b | ✅ | — | With a CAR of 18.1% and CET1 of 14.3%—both comfortably above the 12% regulatory floor—the sector enjoys a robust capital buffer that underpins resilie |
| gpt-oss-120b | ✅ | — | With a CAR of 18.1% and CET1 of 14.3%—both comfortably above the 12% regulatory floor—the sector enjoys a robust capital buffer that underpins resilie |
| gpt-oss-120b | ✅ | — | With a CAR of 18.1% and CET1 of 14.3%—both comfortably above the 12% regulatory floor—the sector enjoys a robust capital buffer that underpins earning |
| zai-glm-4.7 | ✅ | — | With CAR at 18.1% and CET1 at 14.3% comfortably clearing the 12% minimum, the sector preserves a substantial capital buffer that reinforces its capaci |
| zai-glm-4.7 | ✅ | — | With CAR at 18.1% and CET1 at 14.3% comfortably clearing the 12% minimum, the sector preserves a substantial capital buffer that reinforces its capaci |
| zai-glm-4.7 | ✅ | — | With CAR at 18.1% and CET1 at 14.3% comfortably clearing the 12% minimum, the sector preserves a substantial capital buffer that reinforces its capaci |
| gemma-4-31b | ✅ | — | The sector maintains a robust solvency position with a CAR of 18.1% and CET1 of 14.3%, providing a comfortable capital buffer above the 12% minimum re |
| gemma-4-31b | ✅ | — | The sector maintains a robust solvency position with a CAR of 18.1% and CET1 of 14.3%, providing a comfortable capital buffer above the 12% minimum re |
| gemma-4-31b | ✅ | — | The sector maintains a robust solvency position with a CAR of 18.1% and CET1 of 14.3%, providing a comfortable capital buffer above the 12% minimum re |

## Failure log — every invented / empty / mis-formatted sample (core Reads)

**Market Risk**
- `meta-llama/llama-4-scout-17b-16e-instruct` — invented ['1']: With a contained net open position at 3.2% of capital, Turkish banks' market risk hinges on their sizeable negative 1y repricing gap of -12.5%, which should con
- `gpt-oss-120b` — invented ['1']: With FX net open position at 3.2% of capital—well inside the 20% ceiling—and a 1‑year repricing gap of –12.5% of assets, the bank’s earnings are set to rise as 
- `gpt-oss-120b` — invented ['1']: With FX net open position at 3.2% of capital—well inside the 20% ceiling—and a 1‑year repricing gap of –12.5% of assets, the bank’s earnings are set to rise as 

## One representative rewrite per model (Overview)

- **groq · openai/gpt-oss-120b**  
  > Robust loan expansion (42.1% y/y) fuels asset growth (38.5%) while an 18.1% CAR, 1.81% NPL, a 0.07pp NIM lift and an 88% LDR underpin a 34.2% ROE, confirming a high‑margin, well‑capitalised sector.
- **groq · llama-3.3-70b-versatile**  
  > The sector's 38.5% y/y asset growth, driven by 42.1% loan expansion, fuels a 34.2% ROE, while NIM rises 0.07pp to 4.35% and capital remains robust at 18.1%.
- **groq · meta-llama/llama-4-scout-17b-16e-instruct**  
  > Turkish banking sector growth accelerates with assets up 38.5% y/y, driven by loan growth of 42.1%, while deposits rise 36.0%, and despite a slight NPL increase to 1.81%, profitability improves with NIM rising 0.07pp to 4.35% and ROE at 34.2%.
- **groq · llama-3.1-8b-instant**  
  > The Turkish banking sector's growth momentum, driven by a 42.1% y/y increase in loans and a 38.5% y/y expansion in assets, is underpinned by a solid capital position, with a 6.1pp buffer above the minimum CAR, and a 34.2% ROE, despite a 1.81% NPL ratio and a 4.35% NIM that has lifted by 0.07pp.
- **cerebras · gpt-oss-120b**  
  > Rapid asset (+38.5% y/y) and loan (+42.1%) expansion, coupled with a modest NIM rise (+0.07pp to 4.35%), underpins a robust ROE of 34.2% while a 1.81% NPL and 18.1% CAR keep risk comfortably contained.
- **cerebras · zai-glm-4.7**  
  > Driven by loan growth of 42.1% y/y and a NIM of 4.35%, the sector delivers a strong ROE of 34.2% while maintaining a capital buffer of 6.1pp despite NPLs reaching 1.81%.
- **cerebras · gemma-4-31b**  
  > Strong balance sheet growth, led by a 42.1% increase in loans, supports a 34.2% ROE and a slight NIM expansion to 4.35%, while a 6.1pp capital buffer and stable 1.81% NPLs maintain sector resilience.

## Rate limits (measured this run)

**groq**: `x-ratelimit-limit-requests`=14400, `x-ratelimit-limit-tokens`=6000, `x-ratelimit-remaining-requests`=14397, `x-ratelimit-remaining-tokens`=5665, `x-ratelimit-reset-requests`=18s, `x-ratelimit-reset-tokens`=3.35s

**cerebras**: `x-ratelimit-limit-requests-day`=2400, `x-ratelimit-limit-requests-hour`=150, `x-ratelimit-limit-requests-minute`=5, `x-ratelimit-limit-tokens-day`=1000000, `x-ratelimit-limit-tokens-hour`=1000000, `x-ratelimit-limit-tokens-minute`=30000, `x-ratelimit-remaining-requests-day`=2397, `x-ratelimit-remaining-requests-hour`=148, `x-ratelimit-remaining-requests-minute`=4, `x-ratelimit-remaining-tokens-day`=983005, `x-ratelimit-remaining-tokens-hour`=983381, `x-ratelimit-remaining-tokens-minute`=13381
