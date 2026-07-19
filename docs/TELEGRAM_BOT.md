# Telegram Q&A bot

A public Telegram bot that answers natural-language questions about the Turkish
banking sector by running **read-only SQL** against the live D1 database and
answering from the rows it gets back. It runs entirely inside the existing
Cloudflare Worker (the Next.js dashboard) — no separate server.

> The bot only ever **reads**. Every query is gated by a sanitizer
> (`web/app/lib/bot-sql.ts`) that rejects anything that isn't a single
> `SELECT`/`WITH` statement, so a prompt-injected or hallucinated write is
> impossible. The whole dataset is already public via the dashboard.

## Flow

The bot is an **agent loop**, not a fixed pipeline: the model queries the live DB
to explore and verify, sees each result (or SQL error, or `0 rows`), self-corrects,
and only then answers. It knows no figures on its own.

```
Telegram → POST /api/telegram/webhook   (verify secret header, ACK 200)
        → ctx.waitUntil:
            /start|/help → welcome  ·  >500 chars → reject  ·  rate-limit (bot_usage)
            runAgent() — loop, at most MAX_STEPS = 6 query/refine rounds:
              │
              ├─ model emits a ```sql block
              │     → sanitizeSelect()  read-only gate + row cap
              │     → D1 execute
              │     → feed back the rows, the SQL error, or "0 rows" ──┐ loop
              │                                                        │
              └─ model emits plain text = its final answer             │
                    → grounded (a query returned ≥1 row)? → send       │
                    → ungrounded? → reject, force it to query ─────────┘

            out of steps → ONE forced final call (no further queries allowed)
            finalize(): strip code fences / * / `, dot-group thousands, escape HTML
        → sendMessage — prose only
```

Files:

| Piece | File |
|---|---|
| Webhook route | `web/app/api/telegram/webhook/route.ts` |
| Agent loop | `web/app/lib/bot.ts` (`runAgent`) |
| SQL gate + helpers | `web/app/lib/bot-sql.ts` (+ `bot-sql.test.ts`) |
| Agent system prompt | `web/app/lib/bot-schema.ts` (`AGENT_SYSTEM`, wrapping `SCHEMA_PROMPT`) |
| LLM client (Groq→Cerebras) | `web/app/lib/llm.ts` |
| Env accessor | `web/app/lib/cf-env.ts` |
| Telegram API helpers | `web/app/lib/telegram.ts` |
| Test harness (no Telegram) | `web/app/api/admin/bot-ask/route.ts` |
| Webhook self-register | `web/app/api/admin/telegram-register/route.ts` |
| Rate-limit table | `web/migrations/0020_bot_usage.sql` |
| Query log | `web/migrations/0033_bot_queries.sql` |
| Webhook setup CLI | `scripts/setup_telegram_webhook.py` |

### Grounding guard — why the bot can't make numbers up

The failure mode of an LLM over a database is a confident, invented figure. Three
mechanisms in `bot.ts` prevent it:

1. **No query, no numbers.** `runAgent` tracks `gotData` — whether any query has
   returned ≥1 row. A final answer containing a 4+ digit figure or a `{placeholder}`
   while `gotData` is false is treated as a hallucination: it is **never sent**. The
   model is pushed back to querying and the loop continues (`bot.ts:158-178`).
2. **Separators stripped before that check.** A grouped number like `43.520.620` is
   collapsed to bare digits *first*, so it still trips the 4+ digit test rather than
   reading as three short numbers (`bot.ts:163`).
3. **Amounts are formatted deterministically, never by the model.** `groupThousands()`
   (`bot.ts:40-48`) re-groups bare integers with Turkish dot separators using
   lookarounds that leave years (`2026`), periods (`2026Q1`), decimals (`8.06`) and
   Turkish decimal commas (`40,75`) alone. The digits are never altered.

The system prompt reinforces this ("You know NO figures on your own"), also forbids
guessing a reporting period (it must be `SELECT`ed, never assumed to be Q4), and
requires the answer be in **the same language as the question**.

## LLM provider chain

`llm.ts` tries, in order: **Groq `openai/gpt-oss-120b` → Cerebras `gpt-oss-120b` →
Cerebras `gemma-4-31b`**. Groq is first because it serves the same `gpt-oss-120b`
model at a much higher free-tier rate limit (Cerebras is ~5 req/min), and the agent
loop makes several calls per question.

> This **intentionally differs** from the Python "The Read" headline lane
> (`src/news/free_llm.py`), which is Cerebras-first and falls back to a deterministic
> template rather than a third model. That lane makes one call per run and is not
> rate-limit bound. Don't "resync" them.

A whole-chain failure is retried up to **3 passes** with 2s/4s backoff to ride out
transient 429s (`chatComplete`, `llm.ts`). Keys are read from Worker secrets:
`GROQ_API_KEY` (or `GROQ_API_TOKEN`), `CEREBRAS_KEY` (or `CEREBRAS_API_KEY`).

## One-time setup

You need a bot from [@BotFather](https://t.me/BotFather) (`/newbot` → token).

1. **Generate a webhook secret** (a shared string Telegram echoes back and we
   verify on every request):

   ```bash
   python scripts/setup_telegram_webhook.py gen-secret
   ```

2. **Set the Worker secrets** (from `web/`, needs `CLOUDFLARE_API_TOKEN` or an
   interactive `wrangler login`):

   ```bash
   cd web
   wrangler secret put TELEGRAM_BOT_TOKEN        # paste the BotFather token
   wrangler secret put TELEGRAM_WEBHOOK_SECRET   # paste the secret from step 1
   wrangler secret put GROQ_API_KEY              # primary provider
   wrangler secret put CEREBRAS_KEY              # fallback; reuse the reads-lane key
   ```

   Optional caps (defaults 20/chat/day, 300 global/day):
   `wrangler secret put BOT_PER_CHAT_DAILY` · `BOT_GLOBAL_DAILY`.

3. **Deploy** so the route + `bot_usage` table exist. Pushing any `web/**`
   change to `master` triggers `deploy-cloudflare.yml` (which also runs
   `wrangler d1 migrations apply`). Or deploy manually: `cd web && npm run deploy`.

4. **Register the webhook** (points Telegram at the Worker). Two ways:

   **a. From the browser (no local token needed) — easiest.** The Worker already
   holds the token+secret, so it can register itself. Log into `/admin`, then
   open `/api/admin/telegram-register` in the same browser. It calls setWebhook
   and returns the Telegram response. Check it with `/api/admin/telegram-register?info`.

   **b. From the CLI.** The script prompts for the token + secret on a hidden
   input, so nothing lands in shell history or the environment (or set the
   `TELEGRAM_BOT_TOKEN` / `TELEGRAM_WEBHOOK_SECRET` env vars to skip the prompts,
   e.g. in CI). `WORKER_URL` overrides the target Worker:

   ```bash
   python scripts/setup_telegram_webhook.py set
   python scripts/setup_telegram_webhook.py info     # verify url + pending_update_count
   python scripts/setup_telegram_webhook.py delete   # unregister
   ```

Message the bot `/start` — it should reply with examples.

## Testing without Telegram

`GET /api/admin/bot-ask?key=<BOT_TEST_KEY>&q=<question>` runs the full agent loop
over one question and returns the reply **plus the query trace** (every SQL the model
ran and how many rows came back) as JSON. This is the only surface that exposes the
trace — the Telegram reply never shows SQL.

It is gated by the `BOT_TEST_KEY` Worker secret and returns **404 when that secret is
unset**, so the endpoint doesn't exist unless you deliberately enable it:

```bash
cd web && wrangler secret put BOT_TEST_KEY    # any long random string
```

Note the key travels in the query string (so it can be opened in a browser), which
means it lands in request logs. Treat it as a debug toggle: set it while iterating on
`bot-schema.ts`, then `wrangler secret delete BOT_TEST_KEY` when done.

## Notes & tuning

- **What it can answer**: anything expressible as SQL over the D1 schema —
  per-bank figures (`bank_audit_*`, quarterly, thousand TL) and sector
  aggregates (`balance_sheet`, `income_statement`, … monthly, million TL), plus
  macro (`evds_series`), BIST prices, ownership, news. The per-bank vs
  sector-aggregate split is the #1 thing the schema prompt drills.
- **Reply format**: **plain prose only.** `finalize()` strips every code fence,
  asterisk and backtick before sending. The generated SQL and the raw result table
  are **never** shown to the user — they're diagnostics, available only via the
  `bot-ask` harness above. A single fact gets one sentence; a ranking gets one
  numbered item per line.
- **Groups**: Telegram bot privacy mode is ON by default, so in a group the bot
  only sees `/commands` and @mentions. Direct messages see all text. Turn
  privacy off via BotFather (`/setprivacy`) if you want it to read all group
  messages.
- **Abuse / cost**: caps live in `bot_usage` (per UTC day). One question costs **up
  to 7 LLM calls** — at most `MAX_STEPS = 6` query/refine rounds plus a forced final
  answer — and each of those may retry the provider chain up to 3 passes. A simple
  question that queries once and answers costs 2. Budget for the ceiling, not the
  floor, and lower the caps if you hit provider rate limits.
- **Improving answers**: edit `AGENT_SYSTEM` / `SCHEMA_PROMPT` in
  `web/app/lib/bot-schema.ts` — add tables, tighten conventions, add hints. Note the
  loop makes the bot robust to gaps in that file: because it verifies labels and
  values against the live DB before answering, `SCHEMA_PROMPT` is orientation and
  known-good hints, not the bot's whole understanding of the data. Validate changes
  with the `bot-ask` harness and read the `trace`.


## Diagnosing a wrong answer

The bot generates SQL per question, so a wrong answer is usually a wrong query,
not a wrong database. Every step is recorded in `bot_queries` — the question,
the SQL actually executed, and the row count:

```sql
-- recent queries that returned nothing
SELECT asked_at, question, sql_text, detail FROM bot_queries
 WHERE outcome != 'rows' OR row_count = 0
 ORDER BY asked_at DESC LIMIT 20;

-- rankings that look suspiciously short
SELECT asked_at, question, row_count, sql_text FROM bot_queries
 WHERE outcome = 'rows' AND sql_text LIKE '%ORDER BY%'
 ORDER BY asked_at DESC LIMIT 20;
```

**The failure mode to watch for is a silently narrowed population.** Two live
examples, both of which produced fluent, confident, wrong answers:

- A net-profit ranking matched `item_name LIKE '%XIX+XXIV%'` and returned **36
  of 38 banks**. AKBNK files a blank `item_name`; HAYATK uses the compressed
  template and labels the same line `(XVII+XXII)`. Fixed by joining
  `bank_audit_pl_roles` on `role='period_net'`, which resolves each bank's own
  ordinal — never match a P&L label.
- A branch-productivity ranking returned **8 banks when 27 had the data**: the
  model wrote its own `IN (…)` list of about ten tickers, then reported the gaps
  *within its own list* as gaps in the dataset. `checkTickerEnumeration` in
  `bot-sql.ts` now rejects SQL that pins `bank_ticker` to two or more literals
  the question never named.

Neither errored. Both looked complete. Row counts are the tell — if a "rank all
banks" query returns fewer rows than there are banks, the query is wrong.

## Why rankings are rendered, not retyped

The provider chain runs **three different models** (Groq `openai/gpt-oss-120b`,
Cerebras `gpt-oss-120b`, then `gemma-4-31b`), and `chatComplete` takes whichever
answers first. So the same question can be answered by a different model each
time — which formatted identical data two different ways even at `temperature: 0`.

Worse than the cosmetics: the model **retyped every figure**. A 38-bank ranking
was 38 chances to drop a digit, checked by nothing.

`substituteDataList` (`bot-sql.ts`) now re-renders any listing from the rows the
query actually returned, keeping the model's caption and caveats around it. The
numbers are the queried ones by construction, and the layout no longer depends on
which model replied. It fires only on a genuine ranking — enough rows, and prose
that is clearly a list — and returns the answer untouched otherwise, so narrative
replies are unaffected.

## bank_type_code overlaps — the sector is not a sum

Asked for the banking sector's total assets, the bot answered **198,874,433
million TL**. The true figure is **51,760,765**. It had summed all ten
`bank_type_code` groups:

```
10001  entire sector          51,760,765
10002+10003+10004             51,760,765   the sector again, by licence
10005+10006+10007             51,760,765   the sector again, by ownership
10008+10009+10010             43,592,138   deposit banks again, by ownership
                             ────────────
                             198,874,433   = 3.84x the sector
```

The arithmetic was correct; the population was wrong. Nothing errored, and
198 trillion TL is not obviously absurd unless you know the real number.

Root cause: the schema prompt listed the partition codes but **omitted 10001**,
so the model had no way to know a ready-made sector total existed and built one
by adding groups. `10001` is now documented first and explicitly, and
`checkSectorAggregation` (`bot-sql.ts`) rejects any SUM/AVG over a sector table
that doesn't pin `bank_type_code` — a single-value filter, an IN list, or a
GROUP BY all pass.

**The rule for any consumer, not just the bot:** `10001` IS the total. The other
codes are three overlapping partitions of that same sector — never add across
them. The same warning is in `docs/API_MANUAL.md` §8 for API callers.

## The audit (2026-07-20)

Four parallel audits ran the schema prompt and the code against live D1. Every
finding below was reproduced against the database before being fixed; the
prompt's own worked examples were executed, not read.

### Wrong numbers, silently

| | |
|---|---|
| `MAX(amount_total) WHERE statement='assets'` | The grand-total row is MISSING for some bank-quarters, so `MAX` returned the largest **sub-line**. ISCTR read 2.72trn instead of 4.94trn — **7th instead of 3rd** in a 38-row ranking that looked complete. Fixed: take `MAX` across `('assets','liabilities')`; a balance sheet balances, and a sub-line can never exceed the total. |
| `currency IN ('TL','YP','TOTAL')` | Fabricated. The real values are `'TL'` and `'USD'`, and USD exists for exactly ONE month (2025-12, at ~42.8). Filtering the documented `'TOTAL'` returns zero rows; forgetting the filter in Dec-2025 sums 2.3% high or reads 43x low. |
| `loans` table 5 | **thousand TL** while tables 3/4/6/7 are million — a 1000x error across the largest block of that table. |
| `is_subtotal` undocumented | These tables interleave leaves, subtotals and grand totals. `SUM` over them is **8.1x** on balance_sheet, 2x on loans. |
| Overlapping `bank_type_code` via `IN` | The first gate accepted any `IN` list. `IN ('10001','10002','10003','10004')` is **exactly 2.00x**. Now rejected: 10001 with anything, or codes from two partitions. |
| Our own `LIMIT 200` | Silently truncated the population and reported the truncated count as the whole. A real "NPL since 2024, all banks" query is 327 rows → 200, dropping Ziraat, VakıfBank, Yapı Kredi, TEB and TSKB. Now over-fetches by one and says so. |
| A `LIMIT` in a **subquery** | Suppressed the outer cap entirely — the test ran against the whole statement. Now top-level only. |

### Missing or unusable answers

- `bank_audit_credit_quality.section` documented the three **rarest** values (0–2 banks) while `loans_by_stage` (38/38) went unmentioned.
- The ticker list held 31 of 38 banks. Enpara, Hayat Finans, Takasbank and four others answered "no data".
- `bank_audit_equity_change` was documented as a line-item table with an `amount` column. It has neither — it is a wide matrix, and it carries `period_type`.
- `ratio_category`: three of four documented values do not exist.
- `financial_ratios` was labelled "sparsely populated". It is 26,600 rows, every month, no NULLs — the best source of sector ratios.
- `other_data` (394k rows, the largest family-B table) had no entry at all.
- The label-matching rule's own example, `LIKE '%TOTAL%ASSET%'`, matches **9 of 38 banks** — and sat 160 lines below a rule banning exactly that.

### Guards that were not guarding

- `inventedNumbers` — a tested, documented check that every figure in an answer appears in the data — **had never once run**. It was never imported. Now wired, with one correction round.
- The hallucination guard only caught 4+ digit runs, so `%16,2`, `NPL is 2.3%`, `ROE was 38,5%` and `750 branches` could all be stated with **no query run**.
- `substituteDataList` re-rendered from the LAST query's rows, not the answer's — a follow-up `SELECT period, COUNT(*)` could replace a bank ranking with a list of periods under the ranking's caption. Now requires label overlap.
- It also picked the first numeric column, printing absolute Stage-3 amounts under "ranked by NPL ratio". Now reads the `ORDER BY` column.
- The out-of-steps path skipped re-rendering entirely — the longest conversations, most likely to carry a ranking.
- `formatTrNumber(0.004)` produced `"0,"`. Stage coverage is stored as a fraction.

### What stops it recurring

`scripts/check_bot_schema.py` verifies the prompt's assertions against live D1 —
ticker completeness, enum values, column existence, the `bank_type_code` overlap
identities, `pl_roles` coverage, and the balance-sheet identity that exposed the
ISCTR defect. It runs daily in `healthcheck.yml`.

**Prose cannot be unit-tested. The facts it asserts can.**
