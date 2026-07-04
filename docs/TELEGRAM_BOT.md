# Telegram Q&A bot

A public Telegram bot that answers natural-language questions about the Turkish
banking sector by generating **read-only SQL** against the live D1 database and
summarising the results. It runs entirely inside the existing Cloudflare Worker
(the Next.js dashboard) — no separate server.

> The bot only ever **reads**. Every query is gated by a sanitizer
> (`web/app/lib/bot-sql.ts`) that rejects anything that isn't a single
> `SELECT`/`WITH` statement, so a prompt-injected or hallucinated write is
> impossible. The whole dataset is already public via the dashboard.

## Flow

```
Telegram → POST /api/telegram/webhook (verify secret header, ACK 200)
        → ctx.waitUntil:
            rate-limit (bot_usage table, per-chat + global daily caps)
            LLM #1  question → ```sql``` (or a plain-text reply for greetings)
            sanitizeSelect()  read-only gate + row cap
            D1 execute
            LLM #2  rows → short grounded answer
            reply: answer + raw data table + the SQL
```

Files:

| Piece | File |
|---|---|
| Webhook route | `web/app/api/telegram/webhook/route.ts` |
| Orchestrator | `web/app/lib/bot.ts` |
| SQL gate + helpers | `web/app/lib/bot-sql.ts` (+ `bot-sql.test.ts`) |
| Schema prompt (text-to-SQL) | `web/app/lib/bot-schema.ts` |
| LLM client (Cerebras→Groq) | `web/app/lib/llm.ts` |
| Telegram API helpers | `web/app/lib/telegram.ts` |
| Rate-limit table | `web/migrations/0020_bot_usage.sql` |
| Webhook setup CLI | `scripts/setup_telegram_webhook.py` |

The LLM is the same free provider chain the "The Read" headline lane uses
(Cerebras `gpt-oss-120b` → Groq → Cerebras `gemma`) — no paid API.

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
   wrangler secret put CEREBRAS_KEY              # reuse the reads-lane key
   wrangler secret put GROQ_API_KEY              # optional fallback
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
   e.g. in CI):

   ```bash
   python scripts/setup_telegram_webhook.py set
   python scripts/setup_telegram_webhook.py info   # verify url + pending_update_count
   ```

Message the bot `/start` — it should reply with examples.

## Notes & tuning

- **What it can answer**: anything expressible as SQL over the D1 schema —
  per-bank figures (`bank_audit_*`, quarterly, thousand TL) and sector
  aggregates (`balance_sheet`, `income_statement`, … monthly, million TL), plus
  macro (`evds_series`), BIST prices, ownership, news. The per-bank vs
  sector-aggregate split is the #1 thing the schema prompt drills.
- **Accuracy**: the reply always shows the **raw result rows and the SQL**, so a
  rounded/loose summary sentence is checkable against ground truth. Numbers in
  the summary that don't appear in the rows get an "approximate" flag.
- **Groups**: Telegram bot privacy mode is ON by default, so in a group the bot
  only sees `/commands` and @mentions. Direct messages see all text. Turn
  privacy off via BotFather (`/setprivacy`) if you want it to read all group
  messages.
- **Abuse / cost**: caps live in `bot_usage` (per UTC day). Every question costs
  ~2 free-tier LLM calls. Lower the caps if you hit provider rate limits.
- **Improving answers**: edit `web/app/lib/bot-schema.ts` — add tables, tighten
  conventions, or add few-shot `Q → SQL` examples. That file is the bot's whole
  understanding of the data.
