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
