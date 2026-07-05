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
import { chatComplete, llmConfigured, type ChatMessage } from "./llm";
import { AGENT_SYSTEM } from "./bot-schema";
import { DEFAULT_ROW_CAP, formatTable, sanitizeSelect } from "./bot-sql";
import { escapeHtml, sendMessage, type TgUpdate } from "./telegram";

const MAX_MSG_LEN = 500;
const ROW_CAP = DEFAULT_ROW_CAP;
const MAX_STEPS = 6; // max query/refine rounds the agent may take per question
const MODEL_ROWS = 60; // rows fed back to the model after each query
const MODEL_RESULT_CHARS = 6000; // cap on the result text handed back to the model

/** The bound D1 handle, without needing the workers-types global in app code. */
type Db = CloudflareEnv["DB"];

function intEnv(v: string | undefined, dflt: number): number {
  const n = v ? parseInt(v, 10) : NaN;
  return Number.isFinite(n) && n > 0 ? n : dflt;
}

/**
 * Normalise money amounts to Turkish-style dot separators, deterministically so
 * the digits are never altered. Step 1 collapses any separators the model added
 * (space / comma / non-breaking space between digit-triples) to bare digits;
 * step 2 dot-groups bare integers of 5+ digits. The lookarounds skip anything
 * adjacent to a digit/dot/comma, so years (2026), periods (2026Q1), decimals
 * (8.06) and Turkish decimal commas (40,75) are left alone; a leading '-' is kept.
 */
function groupThousands(s: string): string {
  // Any thousands separator the model might use: ASCII space, comma, or a
  // Unicode space (non-breaking, narrow no-break, thin, figure, punctuation).
  return s
    .replace(/(?<![\d.,])(\d{1,3}(?:[ ,     ]\d{3})+)(?![\d])/g, (m) =>
      m.replace(/[ ,     ]/g, ""),
    )
    .replace(/(?<![\d.,])\d{5,}(?![\d.,])/g, (m) => m.replace(/\B(?=(\d{3})+(?!\d))/g, "."));
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

/** A ```sql fenced block (only) — the loop's signal that the model wants to run
 *  a query, as opposed to giving its final plain-text answer. */
function fencedSql(text: string): string | null {
  const m = text.match(/```(?:sql)?\s*([\s\S]*?)```/i);
  return m && m[1].trim() ? m[1].trim() : null;
}

/** Turn the model's final prose into an HTML-safe, thousand-separated reply. */
function finalize(text: string): string {
  const clean = text
    .replace(/```[\s\S]*?```/g, "") // drop any stray code fence
    .replace(/\*+/g, "")
    .replace(/`/g, "")
    .trim();
  return clean ? escapeHtml(groupThousands(clean)) : "";
}

export interface AgentResult {
  reply: string; // HTML reply for Telegram
  trace: { sql: string; result: string }[]; // queries the model ran (for testing)
}

/**
 * The agent loop: the model runs read-only SQL to explore + verify against the
 * live DB, sees each result (or error / 0 rows) and self-corrects, then answers
 * in prose. Every query is gated by sanitizeSelect (read-only) and row-capped.
 */
export async function runAgent(env: StringEnv, db: Db, question: string): Promise<AgentResult> {
  const messages: ChatMessage[] = [
    { role: "system", content: AGENT_SYSTEM },
    { role: "user", content: question },
  ];
  const trace: { sql: string; result: string }[] = [];
  let gotData = false; // a query has returned ≥1 row this session

  for (let step = 0; step < MAX_STEPS; step++) {
    let gen;
    try {
      gen = await chatComplete(env, messages, { temperature: 0, maxTokens: 1400 });
    } catch {
      return { reply: "⚠️ The model is unavailable right now. Please try again shortly.", trace };
    }

    const sql = fencedSql(gen.text);
    if (!sql) {
      // A final answer that states figures / {placeholder}s while NO query has
      // returned data is a hallucination. NEVER show it - push the model back to
      // querying and keep looping. (Strip separators first so a grouped number
      // like 43.520.620 still reads as a 4+ digit figure.)
      const digitsOnly = gen.text.replace(/[.,\s]/g, "");
      const ungrounded = !gotData && (/\d{4,}/.test(digitsOnly) || /\{[a-z_]+\}/i.test(gen.text));
      if (ungrounded) {
        messages.push({ role: "assistant", content: gen.text });
        messages.push({
          role: "user",
          content:
            "STOP - you have run no query, so those figures are invented and must NOT be shown. " +
            "Reply with ONLY a ```sql block (a SELECT) that fetches the real data. Do not write " +
            "any answer or {placeholder} until a query has returned results.",
        });
        continue;
      }
      // No query needed → this is the final answer to the user.
      return { reply: finalize(gen.text) || "⚠️ I couldn't produce an answer. Please try rephrasing.", trace };
    }

    // The model wants to run a query: record its turn, run it, feed the result back.
    messages.push({ role: "assistant", content: gen.text });
    const san = sanitizeSelect(sql, ROW_CAP);
    if (!san.ok) {
      trace.push({ sql, result: `rejected: ${san.error}` });
      messages.push({ role: "user", content: `Query rejected (${san.error}). Fix the SQL and try again.` });
      continue;
    }

    let feedback: string;
    try {
      const res = await db.prepare(san.sql).all<Record<string, unknown>>();
      const rows = (res.results ?? []).slice(0, ROW_CAP);
      if (rows.length) gotData = true;
      trace.push({ sql: san.sql, result: `${rows.length} rows` });
      feedback = rows.length
        ? `Result (${rows.length} row${rows.length === 1 ? "" : "s"}):\n` +
          formatTable(rows, MODEL_ROWS, 80).slice(0, MODEL_RESULT_CHARS)
        : "Result: 0 rows. Inspect why — check the real labels/columns/values (labels " +
          "vary by bank/language and some are blank) — then try a corrected query, or " +
          "confirm the data truly isn't there.";
    } catch (e) {
      const msg = e instanceof Error ? e.message : "query failed";
      trace.push({ sql: san.sql, result: `error: ${msg}` });
      feedback = `Error: ${msg}. Fix the SQL and try again.`;
    }
    messages.push({ role: "user", content: feedback });
  }

  if (!gotData) {
    return { reply: "⚠️ I couldn't retrieve that reliably. Please try rephrasing.", trace };
  }

  // Out of steps — force a final answer from what was gathered (no more queries).
  messages.push({
    role: "user",
    content: "Stop querying. Give your final plain-text answer now, based on the results so far. No sql block.",
  });
  try {
    const gen = await chatComplete(env, messages, { temperature: 0, maxTokens: 1400 });
    return { reply: finalize(gen.text) || "⚠️ I couldn't work that out. Please try rephrasing.", trace };
  } catch {
    return { reply: "⚠️ I couldn't work that out. Please try rephrasing.", trace };
  }
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

    // The agent loop: the model explores the DB read-only, self-corrects, answers.
    const { reply } = await runAgent(env, db, text);
    await sendMessage(env, chatId, reply);
  } catch (e) {
    console.error(`[bot] unhandled: ${e instanceof Error ? e.stack : e}`);
    await sendMessage(env, chatId, "⚠️ Something went wrong handling that. Please try again.", null);
  }
}
