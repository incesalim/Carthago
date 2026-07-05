/**
 * Telegram bot orchestrator: turn a user's message into a grounded answer by
 * generating read-only SQL, running it against D1, and summarising the rows.
 *
 * Flow: command? → rate-limit → LLM makes SQL (or a plain answer) → sanitize →
 * execute → LLM summarises rows → reply with the answer + the raw data + the SQL.
 *
 * Public bot: every step is defensive. The SQL is gated by bot-sql.ts (writes
 * are impossible), and usage is capped per-chat and globally to protect the
 * free-tier LLM quota.
 */
import type { StringEnv } from "./cf-env";
import { chatComplete, llmConfigured } from "./llm";
import { ANSWER_SYSTEM, SQL_SYSTEM } from "./bot-schema";
import {
  DEFAULT_ROW_CAP,
  extractSql,
  formatTable,
  sanitizeSelect,
} from "./bot-sql";
import { escapeHtml, sendMessage, type TgUpdate } from "./telegram";

const MAX_MSG_LEN = 500;
const ROW_CAP = DEFAULT_ROW_CAP;

/** The bound D1 handle, without needing the workers-types global in app code. */
type Db = CloudflareEnv["DB"];

function intEnv(v: string | undefined, dflt: number): number {
  const n = v ? parseInt(v, 10) : NaN;
  return Number.isFinite(n) && n > 0 ? n : dflt;
}

/**
 * Add Turkish-style thousand separators ('.') to standalone integers of 5+
 * digits (money amounts). Deterministic so the digits are never altered. The
 * lookarounds skip anything adjacent to a digit/dot/comma, so years (2026),
 * periods (2026Q1), decimals (40.75) and ratios are left alone; a leading '-'
 * is preserved.
 */
function groupThousands(s: string): string {
  return s.replace(/(?<![\d.,])\d{5,}(?![\d.,])/g, (m) =>
    m.replace(/\B(?=(\d{3})+(?!\d))/g, "."),
  );
}

const WELCOME = `👋 I'm the Turkish banking-sector bot. Ask about a bank or the sector and I'll query the database and answer.

Try:
• Garanti's total assets latest quarter
• Rank banks by capital adequacy ratio this quarter
• Akbank NPL (stage 3) ratio since 2024
• Yapı Kredi net profit in 2024Q4

Per-bank figures are in thousand TL, sector figures in million TL. Per-bank data is quarterly from BRSA reports (~2022Q1 onward); I also have macro (EVDS), BIST prices, ownership and news.`;

/** Lazy, idempotent create of the usage table (also created by migration 0020). */
let usageReady: Promise<void> | null = null;
function ensureUsageTable(db: Db): Promise<void> {
  if (usageReady) return usageReady;
  const p = db
    .prepare(
      `CREATE TABLE IF NOT EXISTS bot_usage (
         chat_id TEXT NOT NULL, day TEXT NOT NULL, count INTEGER NOT NULL DEFAULT 0,
         PRIMARY KEY (chat_id, day))`,
    )
    .run()
    .then(() => undefined)
    .catch((e: unknown) => {
      usageReady = null; // allow a retry on the next message
      throw e;
    });
  usageReady = p;
  return p;
}

/** Increment `chat_id`'s counter for today and return the new value. */
async function bump(db: Db, chatId: string, day: string): Promise<number> {
  const row = await db
    .prepare(
      `INSERT INTO bot_usage (chat_id, day, count) VALUES (?, ?, 1)
       ON CONFLICT(chat_id, day) DO UPDATE SET count = count + 1
       RETURNING count`,
    )
    .bind(chatId, day)
    .first<{ count: number }>();
  return row?.count ?? 0;
}

/** Charge one unit of quota; returns a human reason if a cap is hit. */
async function rateLimit(
  db: Db,
  env: StringEnv,
  chatId: number,
): Promise<string | null> {
  const perChat = intEnv(env.BOT_PER_CHAT_DAILY, 20);
  const global = intEnv(env.BOT_GLOBAL_DAILY, 300);
  const day = new Date().toISOString().slice(0, 10);
  await ensureUsageTable(db);
  const mine = await bump(db, String(chatId), day);
  if (mine > perChat) {
    return `You've hit today's limit of ${perChat} questions. Try again tomorrow 🙏`;
  }
  const total = await bump(db, "__global__", day);
  if (total > global) {
    return "The bot has hit its shared daily quota. Please try again tomorrow 🙏";
  }
  return null;
}

/** Entry point — process one Telegram update. Never throws. */
export async function handleUpdate(
  update: TgUpdate,
  env: StringEnv,
  db: Db,
): Promise<void> {
  const msg = update.message;
  const text = msg?.text?.trim();
  if (!msg || !text || msg.from?.is_bot) return;
  const chatId = msg.chat.id;

  try {
    if (/^\/(start|help)\b/i.test(text)) {
      await sendMessage(env, chatId, WELCOME, null);
      return;
    }
    if (text.length > MAX_MSG_LEN) {
      await sendMessage(env, chatId, `Please keep questions under ${MAX_MSG_LEN} characters.`, null);
      return;
    }
    if (!llmConfigured(env)) {
      await sendMessage(env, chatId, "⚙️ The bot isn't configured yet (no LLM key).", null);
      return;
    }

    const capped = await rateLimit(db, env, chatId);
    if (capped) {
      await sendMessage(env, chatId, capped, null);
      return;
    }

    // 1) Natural language → SQL (or a plain-text answer for meta/greetings).
    let gen;
    try {
      gen = await chatComplete(
        env,
        [
          { role: "system", content: SQL_SYSTEM },
          { role: "user", content: text },
        ],
        { temperature: 0, maxTokens: 700 },
      );
    } catch {
      await sendMessage(env, chatId, "⚠️ The model is unavailable right now. Please try again shortly.", null);
      return;
    }

    const sql = extractSql(gen.text);
    if (!sql) {
      // The model chose to answer in prose (greeting / capability / can't-answer).
      await sendMessage(env, chatId, escapeHtml(gen.text.slice(0, 3500)));
      return;
    }

    // 2) Gate the SQL.
    const san = sanitizeSelect(sql, ROW_CAP);
    if (!san.ok) {
      await sendMessage(
        env,
        chatId,
        `I couldn't build a safe query for that (${escapeHtml(san.error)}). Try rephrasing.\n\n<pre>${escapeHtml(sql)}</pre>`,
      );
      return;
    }

    // 3) Execute (read-only).
    let rows: Record<string, unknown>[];
    try {
      const res = await db.prepare(san.sql).all<Record<string, unknown>>();
      rows = (res.results ?? []).slice(0, ROW_CAP);
    } catch (e) {
      await sendMessage(
        env,
        chatId,
        `The query failed: ${escapeHtml(e instanceof Error ? e.message : "error")}.\n\n<pre>${escapeHtml(san.sql)}</pre>`,
      );
      return;
    }

    if (!rows.length) {
      await sendMessage(env, chatId, `No matching data.\n\n<pre>${escapeHtml(san.sql)}</pre>`);
      return;
    }

    // 4) Summarise the rows (grounded); the raw table below is the source of truth.
    let answer = "";
    try {
      const payload = JSON.stringify(rows.slice(0, 50)).slice(0, 8000);
      const summ = await chatComplete(
        env,
        [
          { role: "system", content: ANSWER_SYSTEM },
          { role: "user", content: `Question: ${text}\nSQL: ${san.sql}\nRows (JSON):\n${payload}` },
        ],
        { temperature: 0, maxTokens: 900 },
      );
      answer = summ.text.trim();
    } catch {
      // Summary is optional — fall back to the raw table below.
    }

    // Strip stray markdown the model may add — we render as HTML, not markdown,
    // so **bold** / `code` would show its literal markers.
    const clean = answer.replace(/\*+/g, "").replace(/`/g, "").trim();

    // Reply is plain in-chat text (the model lists rows one per line). Only if
    // the summary failed do we fall back to the raw table so there's an answer.
    const out = clean
      ? escapeHtml(groupThousands(clean))
      : `<pre>${escapeHtml(formatTable(rows))}</pre>`;
    await sendMessage(env, chatId, out);
  } catch (e) {
    console.error(`[bot] unhandled: ${e instanceof Error ? e.stack : e}`);
    await sendMessage(env, chatId, "⚠️ Something went wrong handling that. Please try again.", null);
  }
}
