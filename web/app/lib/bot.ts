/**
 * Telegram bot orchestrator: turn a user's message into a grounded answer by
 * generating read-only SQL, running it against D1, and answering from the rows.
 *
 * Flow: command? → rate-limit → runAgent() — a LOOP (≤ MAX_STEPS rounds) in which
 * the model emits a ```sql block, sees the rows (or the error, or "0 rows"), and
 * self-corrects; when it emits plain text instead, that's the final answer. Reply
 * is prose only — the SQL and raw rows are diagnostics, exposed solely through
 * /api/admin/bot-ask. See docs/TELEGRAM_BOT.md.
 *
 * Public bot: every step is defensive. The SQL is gated by bot-sql.ts (writes are
 * impossible); a figure stated before any query returned rows is treated as a
 * hallucination and never sent (see `gotData`); and usage is capped per-chat and
 * globally to protect the free-tier LLM quota.
 */
import type { StringEnv } from "./cf-env";
import { chatComplete, llmConfigured, type ChatMessage } from "./llm";
import { AGENT_SYSTEM } from "./bot-schema";
import { BANK_NAMES } from "./bank_names";
import {
  DEFAULT_ROW_CAP, checkSectorAggregation, checkTickerEnumeration, formatTable,
  numbersIn, sanitizeSelect, substituteDataList, unsupportedFigures,
} from "./bot-sql";
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
 * Turn a provider-chain failure into something the user can act on.
 *
 * "The model is unavailable" was returned for every cause alike, so a caller
 * could not tell a five-minute free-tier rate limit from a dead key or a real
 * outage — and neither could we, because the reason was discarded.
 */
export function llmFailureMessage(err: string): string {
  const e = err.toLowerCase();
  if (/\b429\b|rate.?limit|too many requests|quota/.test(e)) {
    return "⚠️ The free model quota is exhausted for the moment (all providers " +
           "rate-limited). It usually clears within a few minutes — please try again shortly.";
  }
  if (/no llm provider configured/.test(e)) {
    return "⚠️ No language model is configured, so I can't answer questions right now.";
  }
  if (/\b(401|403)\b|unauthor|invalid.*key/.test(e)) {
    return "⚠️ The language-model credentials are being rejected. This needs an " +
           "operator — it won't fix itself by retrying.";
  }
  if (/abort|timeout|timed out/.test(e)) {
    return "⚠️ The model timed out. Try a narrower question, or retry in a moment.";
  }
  return "⚠️ The model is unavailable right now. Please try again shortly.";
}

/**
 * Short, non-reversible chat identifier — enough to group repeated failures from
 * one conversation, not enough to identify who asked.
 */
function chatHash(chatId?: number): string | null {
  if (chatId === undefined) return null;
  let h = 0;
  for (const ch of String(chatId)) h = (Math.imul(h, 31) + ch.charCodeAt(0)) | 0;
  return (h >>> 0).toString(36);
}

/**
 * Record one query the agent ran. Fire-and-forget: diagnostics must never break
 * an answer, so every failure here is swallowed. Table created lazily so the bot
 * keeps working before migration 0033 is applied.
 */
async function logQuery(
  db: Db,
  row: {
    chatHash: string | null; question: string; step: number; sql: string;
    outcome: "rows" | "rejected" | "error"; rowCount?: number; detail?: string;
  },
): Promise<void> {
  try {
    await db
      .prepare(
        `INSERT INTO bot_queries
           (chat_hash, question, step, sql_text, outcome, row_count, detail)
         VALUES (?, ?, ?, ?, ?, ?, ?)`,
      )
      .bind(row.chatHash, row.question, row.step, row.sql, row.outcome,
            row.rowCount ?? null, row.detail ?? null)
      .run();
  } catch {
    // Table missing (pre-migration) or D1 hiccup — never surface to the user.
  }
}

/**
 * The agent loop: the model runs read-only SQL to explore + verify against the
 * live DB, sees each result (or error / 0 rows) and self-corrects, then answers
 * in prose. Every query is gated by sanitizeSelect (read-only) and row-capped.
 */
export async function runAgent(
  env: StringEnv, db: Db, question: string, chatId?: number,
): Promise<AgentResult> {
  const messages: ChatMessage[] = [
    { role: "system", content: AGENT_SYSTEM },
    { role: "user", content: question },
  ];
  const trace: { sql: string; result: string }[] = [];
  const ch = chatHash(chatId);
  let gotData = false; // a query has returned ≥1 row this session
  // Rows from the last successful query — the model answers FROM these, so a
  // listing it types out can be re-rendered from them instead of trusted.
  let lastRows: Record<string, unknown>[] = [];
  // The SQL behind lastRows — its ORDER BY tells the renderer which column the
  // answer is actually about.
  let lastSql: string | undefined;
  // One correction round only; a model that cannot ground its figures twice is
  // not going to on the third try, and each attempt costs free-tier quota.
  let retriedForNumbers = false;

  for (let step = 0; step < MAX_STEPS; step++) {
    let gen;
    try {
      gen = await chatComplete(env, messages, { temperature: 0, maxTokens: 1400 });
    } catch (e) {
      // llm.ts builds a per-provider reason ("groq: HTTP 429 …; cerebras: …").
      // A bare `catch {}` discarded it, so an outage and an exhausted free tier
      // were indistinguishable — from the outside AND from the logs.
      const why = e instanceof Error ? e.message : String(e);
      trace.push({ sql: "", result: `llm failed: ${why}` });
      await logQuery(db, { chatHash: ch, question, step, sql: "",
        outcome: "error", detail: why.slice(0, 400) });
      return { reply: llmFailureMessage(why), trace };
    }

    const sql = fencedSql(gen.text);
    if (!sql) {
      // A final answer that states figures / {placeholder}s while NO query has
      // returned data is a hallucination. NEVER show it - push the model back to
      // querying and keep looping. (Strip separators first so a grouped number
      // like 43.520.620 still reads as a 4+ digit figure.)
      // The 4+ digit test alone let every RATIO through: "%16,2", "NPL ratio is
      // 2.3%", "ROE was 38,5%", "750 branches" were all sent with no query run —
      // and those are the most-asked question shapes. Catch a percentage, a
      // decimal, or any bare figure paired with a unit word.
      const digitsOnly = gen.text.replace(/[.,\s]/g, "");
      const statesAFigure =
        /\d{4,}/.test(digitsOnly) ||
        /%\s*\d|\d\s*%/.test(gen.text) ||
        /\d+[.,]\d/.test(gen.text) ||
        /\b\d{2,}\s*(?:şube|branch|adet|personel|employee|bank)/i.test(gen.text);
      const ungrounded = !gotData && (statesAFigure || /\{[a-z_]+\}/i.test(gen.text));
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
      const answer = substituteDataList(gen.text, lastRows, 5, lastSql);

      // Last line of defence: every figure in the answer should be traceable to
      // a figure in the rows. `gotData` only proves SOME query returned SOMETHING
      // — it says nothing about whether THIS sentence's numbers came from it.
      // Give the model one chance to correct itself before giving up.
      const unsupported = lastRows.length
        ? unsupportedFigures(answer, numbersIn(JSON.stringify(lastRows)))
        : [];
      if (unsupported.length && !retriedForNumbers) {
        retriedForNumbers = true;
        await logQuery(db, { chatHash: ch, question, step, sql: lastSql ?? "",
          outcome: "rejected",
          detail: `answer cited figures absent from the data: ${unsupported.slice(0, 5).map(String).join(", ")}` });
        messages.push({ role: "assistant", content: gen.text });
        messages.push({
          role: "user",
          content:
            `These figures are not in any result you retrieved: ${unsupported.slice(0, 8).map(String).join(", ")}. ` +
            "Do NOT state a number you did not query. Either re-query to get it, or " +
            "rewrite the answer using only the values you actually have.",
        });
        continue;
      }
      return { reply: finalize(answer) || "⚠️ I couldn't produce an answer. Please try rephrasing.", trace };
    }

    // The model wants to run a query: record its turn, run it, feed the result back.
    messages.push({ role: "assistant", content: gen.text });
    const san = sanitizeSelect(sql, ROW_CAP);
    if (!san.ok) {
      trace.push({ sql, result: `rejected: ${san.error}` });
      await logQuery(db, { chatHash: ch, question, step, sql,
        outcome: "rejected", detail: san.error });
      messages.push({ role: "user", content: `Query rejected (${san.error}). Fix the SQL and try again.` });
      continue;
    }
    // Gate the model's choice of POPULATION, not just its verbs: a query that
    // picks its own list of banks answers for a subset while sounding complete.
    const agg = checkSectorAggregation(san.sql);
    if (!agg.ok) {
      trace.push({ sql: san.sql, result: `rejected: ${agg.error}` });
      await logQuery(db, { chatHash: ch, question, step, sql: san.sql,
        outcome: "rejected", detail: agg.error });
      messages.push({ role: "user", content: `Query rejected — ${agg.error}. Rewrite it.` });
      continue;
    }
    const pop = checkTickerEnumeration(san.sql, question, BANK_NAMES);
    if (!pop.ok) {
      trace.push({ sql: san.sql, result: `rejected: ${pop.error}` });
      await logQuery(db, { chatHash: ch, question, step, sql: san.sql,
        outcome: "rejected", detail: pop.error });
      messages.push({ role: "user", content: `Query rejected — ${pop.error}. Rewrite it.` });
      continue;
    }

    let feedback: string;
    try {
      const res = await db.prepare(san.sql).all<Record<string, unknown>>();
      const fetched = res.results ?? [];
      // sanitizeSelect asked for ROW_CAP + 1 when it imposed the cap, so an
      // extra row here means the real population is LARGER than what we hold.
      const truncated = san.capImposed === true && fetched.length > ROW_CAP;
      const rows = fetched.slice(0, ROW_CAP);
      // An aggregate over ZERO matching rows still returns ONE row — of NULLs.
      // Counting that as "a query returned data" switched off the hallucination
      // guard below while nothing had actually been retrieved: this really
      // happened on `SELECT SUM(amount_total) … WHERE item_name LIKE '%VARLIK%'`,
      // which matched no labels, returned one NULL, and left the model free to
      // answer from memory. Require at least one non-null value.
      const meaningful = rows.some((r: Record<string, unknown>) =>
        Object.values(r).some((v) => v !== null && v !== undefined),
      );
      if (meaningful) { gotData = true; lastRows = rows; lastSql = san.sql; }
      trace.push({ sql: san.sql, result: `${rows.length} rows` });
      await logQuery(db, { chatHash: ch, question, step, sql: san.sql,
        outcome: "rows", rowCount: rows.length });
      const EMPTY_ADVICE =
        " Inspect why — check the real labels/columns/values (labels vary by " +
        "bank/language and some are blank) — then try a corrected query, or " +
        "confirm the data truly isn't there.";
      if (!rows.length) {
        feedback = "Result: 0 rows." + EMPTY_ADVICE;
      } else if (!meaningful) {
        // Every value NULL. For an aggregate that means the WHERE matched
        // NOTHING — reporting it as "1 row" reads like success and invites an
        // answer built on a null.
        feedback =
          "Result: your filter matched NO rows (the single row returned is all " +
          "NULL — an aggregate over an empty set)." + EMPTY_ADVICE;
      } else {
        // formatTable's own "… (+N more rows)" notice sits at the END, so a hard
        // slice could cut it off and hide the truncation. State the full count
        // up front, and append an explicit marker if the slice bites.
        const table = formatTable(rows, MODEL_ROWS, 80);
        // Cut on a LINE boundary. A raw character slice ends mid-row and even
        // mid-number, so the model reads 10000 for 100000245 and believes it.
        const body = table.length > MODEL_RESULT_CHARS
          ? table.slice(0, MODEL_RESULT_CHARS).replace(/\n[^\n]*$/, "")
          : table;
        const cut = body.length < table.length;
        feedback =
          `Result (${rows.length} row${rows.length === 1 ? "" : "s"}` +
          `${rows.length > MODEL_ROWS ? `, showing the first ${MODEL_ROWS}` : ""}):\n` +
          body +
          // The POPULATION was cut, not just the display: more rows matched than
          // we are allowed to fetch. This is the one that silently dropped
          // Ziraat, VakıfBank and Yapı Kredi from a multi-period ranking.
          (truncated
            ? `\n⚠ MORE THAN ${ROW_CAP} ROWS MATCHED — this is a TRUNCATED ` +
              "POPULATION, not the whole result. Do NOT rank, count, or describe " +
              "it as complete. Re-query with an aggregate (COUNT/SUM/MAX), a " +
              "tighter filter, or one period at a time."
            : "") +
          (cut ? `\n… output shortened — you are seeing part of ${rows.length} rows. ` +
                 "Do not state a count from this; re-query with fewer columns." : "");
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : "query failed";
      trace.push({ sql: san.sql, result: `error: ${msg}` });
      await logQuery(db, { chatHash: ch, question, step, sql: san.sql,
        outcome: "error", detail: msg });
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
    // Re-render here too. This branch used to send the model's hand-typed
    // figures straight through, and it is reached by exactly the longest,
    // most-refined conversations — the ones most likely to carry a ranking.
    const forced = substituteDataList(gen.text, lastRows, 5, lastSql);
    return { reply: finalize(forced) || "⚠️ I couldn't work that out. Please try rephrasing.", trace };
  } catch (e) {
    // Same reasoning as the loop's handler: keep the cause. Failing on the
    // FINAL call after N successful queries is the most frustrating shape, and
    // it looked identical to "I couldn't work it out" — which blames the
    // question rather than the provider.
    const why = e instanceof Error ? e.message : String(e);
    trace.push({ sql: "", result: `llm failed (final answer): ${why}` });
    await logQuery(db, { chatHash: ch, question, step: MAX_STEPS, sql: "",
      outcome: "error", detail: why.slice(0, 400) });
    return { reply: llmFailureMessage(why), trace };
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
    const { reply } = await runAgent(env, db, text, chatId);
    await sendMessage(env, chatId, reply);
  } catch (e) {
    console.error(`[bot] unhandled: ${e instanceof Error ? e.stack : e}`);
    await sendMessage(env, chatId, "⚠️ Something went wrong handling that. Please try again.", null);
  }
}
