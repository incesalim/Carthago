/**
 * Free OpenAI-compatible chat client for the Cloudflare Worker (Telegram bot).
 *
 * Provider chain (see PROVIDERS below):
 *   Groq openai/gpt-oss-120b  →  Cerebras gpt-oss-120b  →  Cerebras gemma-4-31b
 *     →  OpenRouter nvidia/nemotron-3-super-120b-a12b:free
 *
 * ⚠️ NEMOTRON IS LAST ON PURPOSE — 2026-08-02. It was promoted to FIRST on
 * 2026-08-01 and it worked: `llm: answered by openrouter/nemotron-3-super-120b`,
 * no fallback. But the Worker then logged
 *
 *   waitUntil() tasks did not complete within the allowed time and have been
 *   cancelled
 *
 * and the bot stopped replying on Telegram. The webhook ACKs immediately and
 * runs the agent loop inside `ctx.waitUntil`, so exceeding that budget kills the
 * reply AFTER the answer has been generated — the model looks healthy in the log
 * and the user gets silence.
 *
 * The budget is the problem, not the model. `bot.ts` allows MAX_STEPS = 6 rounds,
 * each a `chatComplete`, each with a 45s per-call timeout and up to 3 chain
 * passes. Groq's inference is fast enough that six rounds fit; Nemotron on a free
 * endpoint is slower per call, and the same loop ran past the allowance.
 *
 * So this is NOT "Nemotron doesn't work". Re-promoting it needs the loop bounded
 * first — a shorter per-call timeout and/or fewer steps — verified against
 * `npx wrangler tail` before it goes back to the front.
 *
 * Groq-before-Cerebras INTENTIONALLY diverges from the Python headline lane
 * (src/news/free_llm.py), which is Cerebras-first and falls back to a
 * deterministic template. That lane makes one call per run. Don't "resync" the
 * two chains.
 *
 * Keys (set with `wrangler secret put` — see docs/TELEGRAM_BOT.md):
 *   OPEN_ROUTER_API (or OPENROUTER_API_KEY), GROQ_API_KEY (or GROQ_API_TOKEN),
 *   CEREBRAS_KEY (or CEREBRAS_API_KEY).
 *
 * ⚠️ A GitHub Actions secret is NOT a Worker secret. `OPEN_ROUTER_API` was set on
 * the Worker on 2026-08-01 with `wrangler secret put`; the identically-named
 * Actions secret is a different store and never reached it.
 */
import type { StringEnv } from "./cf-env";

export interface ChatMessage {
  role: "system" | "user" | "assistant";
  content: string;
}

interface Provider {
  name: string;
  base: string;
  model: string;
  keys: string[];
  /** Extra request headers this provider wants (OpenRouter's attribution). */
  headers?: Record<string, string>;
}

// Ordered fallback chain. Each is OpenAI-compatible (`/chat/completions`).
// Groq first: much higher free-tier rate limit than Cerebras (~5 req/min), which
// matters because the agent loop makes several calls per question. Nemotron sits
// LAST until the loop's time budget is fixed — see the header.
const PROVIDERS: Provider[] = [
  {
    name: "groq/openai/gpt-oss-120b",
    base: "https://api.groq.com/openai/v1",
    model: "openai/gpt-oss-120b",
    keys: ["GROQ_API_KEY", "GROQ_API_TOKEN"],
  },
  {
    name: "cerebras/gpt-oss-120b",
    base: "https://api.cerebras.ai/v1",
    model: "gpt-oss-120b",
    keys: ["CEREBRAS_KEY", "CEREBRAS_API_KEY"],
  },
  {
    name: "cerebras/gemma-4-31b",
    base: "https://api.cerebras.ai/v1",
    model: "gemma-4-31b",
    keys: ["CEREBRAS_KEY", "CEREBRAS_API_KEY"],
  },
  {
    name: "openrouter/nemotron-3-super-120b",
    base: "https://openrouter.ai/api/v1",
    // Pinned to the `:free` variant on purpose. The paid twin
    // (nvidia/nemotron-3-super-120b-a12b) is a different id and WOULD BILL;
    // dropping the suffix is the one-character mistake that turns this lane
    // from free to metered without any other visible change.
    model: "nvidia/nemotron-3-super-120b-a12b:free",
    keys: ["OPEN_ROUTER_API", "OPENROUTER_API_KEY"],
    // OpenRouter attributes usage to a referring app. Same pair the Python
    // lanes send (scripts/scratch_test_openrouter.py, summarize_regulations.py).
    headers: { "HTTP-Referer": "https://carthago.app", "X-Title": "carthago" },
  },
];

const THINK_RE = /<think>[\s\S]*?<\/think>/gi;

/** Drop chain-of-thought that some gpt-oss checkpoints emit before the answer. */
function stripReasoning(text: string): string {
  let t = text.replace(THINK_RE, "");
  const idx = t.lastIndexOf("</think>");
  if (idx !== -1) t = t.slice(idx + "</think>".length);
  return t.trim();
}

function keyFor(env: StringEnv, p: Provider): string | undefined {
  for (const k of p.keys) {
    const v = env[k];
    if (v) return v;
  }
  return undefined;
}

/** True if at least one provider has a usable key configured. */
export function llmConfigured(env: StringEnv): boolean {
  return PROVIDERS.some((p) => keyFor(env, p) !== undefined);
}

export interface ChatResult {
  text: string;
  model: string;
}

interface ChatOpts {
  temperature?: number;
  maxTokens?: number;
  timeoutMs?: number;
}

async function callProvider(
  p: Provider,
  key: string,
  messages: ChatMessage[],
  opts: ChatOpts,
): Promise<string> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), opts.timeoutMs ?? 45_000);
  try {
    const r = await fetch(`${p.base}/chat/completions`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${key}`,
        "Content-Type": "application/json",
        ...p.headers,
      },
      body: JSON.stringify({
        model: p.model,
        temperature: opts.temperature ?? 0,
        max_tokens: opts.maxTokens ?? 1024,
        messages,
      }),
      signal: ctrl.signal,
    });
    if (!r.ok) {
      const body = await r.text().catch(() => "");
      throw new Error(`HTTP ${r.status}: ${body.slice(0, 160)}`);
    }
    const data = (await r.json()) as {
      choices?: { message?: { content?: string } }[];
    };
    return stripReasoning(data.choices?.[0]?.message?.content ?? "");
  } finally {
    clearTimeout(timer);
  }
}

/** One pass over the provider fallback chain. */
async function attemptChain(
  env: StringEnv,
  messages: ChatMessage[],
  opts: ChatOpts,
): Promise<ChatResult> {
  const errors: string[] = [];
  const skipped: string[] = [];
  for (const p of PROVIDERS) {
    const key = keyFor(env, p);
    if (!key) {
      skipped.push(p.name);
      continue;
    }
    try {
      const text = await callProvider(p, key, messages, opts);
      if (text) {
        // WHICH provider actually answered. The chain falls back silently by
        // design, so without this a mis-set key or a wrong model id looks
        // exactly like success: the bot replies normally, one model down the
        // list, and nothing anywhere records that it did. `bot_queries` logs the
        // SQL but not the model. Read it with `npx wrangler tail`.
        // Deliberately no question text and no key material — this is a public
        // bot and the query log already hashes the chat id.
        console.log(
          `llm: answered by ${p.name}` +
            (skipped.length ? ` (no key for: ${skipped.join(", ")})` : "") +
            (errors.length ? ` (failed first: ${errors.join("; ")})` : ""),
        );
        return { text, model: p.name };
      }
      errors.push(`${p.name}: empty`);
    } catch (e) {
      errors.push(`${p.name}: ${e instanceof Error ? e.message : String(e)}`);
    }
  }
  throw new Error(
    errors.length ? `all LLM providers failed — ${errors.join("; ")}` : "no LLM provider configured",
  );
}

/**
 * Run a chat completion through the provider fallback chain. Since the agent
 * loop makes several calls per question and the free tiers are rate-limited
 * (Cerebras ~5/min), a whole-chain failure gets ONE retry after a short backoff
 * to ride out transient 429s. Throws only if both passes fail.
 */
export async function chatComplete(
  env: StringEnv,
  messages: ChatMessage[],
  opts: ChatOpts = {},
): Promise<ChatResult> {
  const backoffs = [2000, 4000]; // ms between retries
  let last: unknown;
  for (let attempt = 0; attempt <= backoffs.length; attempt++) {
    try {
      return await attemptChain(env, messages, opts);
    } catch (e) {
      last = e;
      if (!llmConfigured(env) || attempt === backoffs.length) break;
      await new Promise((r) => setTimeout(r, backoffs[attempt]));
    }
  }
  throw last;
}
