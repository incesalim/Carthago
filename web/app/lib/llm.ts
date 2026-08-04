/**
 * Free OpenAI-compatible chat client for the Cloudflare Worker (Telegram bot).
 *
 * Provider chain (see PROVIDERS below):
 *   OpenRouter nvidia/nemotron-3-super-120b-a12b:free
 *     →  Groq openai/gpt-oss-120b
 *     →  Cerebras gpt-oss-120b
 *     →  Cerebras gemma-4-31b
 *
 * WHY THE FIRST ATTEMPT AT NEMOTRON FAILED, and what fixed it (2026-08-01/02).
 * Promoting it to first worked at the model level — the Worker logged
 * `llm: answered by openrouter/nemotron-3-super-120b`, no fallback — and the bot
 * then went SILENT on Telegram:
 *
 *   waitUntil() tasks did not complete within the allowed time and have been
 *   cancelled
 *
 * The webhook ACKs immediately and runs the agent loop inside `ctx.waitUntil`,
 * so exceeding that allowance kills the reply AFTER the answer exists. Healthy
 * logs, no message. Two causes, both now closed:
 *
 *   1. nemotron-3 is a REASONING model. At OpenRouter's default effort it emits
 *      a long thinking trace before each answer; `stripReasoning()` discards
 *      that text but we still waited for every token. Six of those per question
 *      is what blew the budget. Fixed with `reasoning: { effort: "low" }` on the
 *      provider — see the note there.
 *   2. Nothing bounded the run in TIME. Step count cannot, because the cost of a
 *      step depends on the model. `bot.ts` now runs to a wall-clock budget and
 *      passes a `deadline` down through here, so the chain stops walking
 *      providers and stops sleeping between retries once the caller can no
 *      longer use the result — leaving room to send a degraded answer instead of
 *      being cancelled mid-flight.
 *
 * The second fix is the load-bearing one: it makes ANY slow provider safe here,
 * not just this one.
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
  /** Extra body fields merged into the completion request. */
  params?: Record<string, unknown>;
  /** Not part of the default walk — reachable only when a caller names it in
   *  `providerOrder`. Lets a lane opt into a provider without changing the
   *  bot's tuned chain. */
  optIn?: boolean;
}

// Ordered fallback chain. Each is OpenAI-compatible (`/chat/completions`).
// Groq first: much higher free-tier rate limit than Cerebras (~5 req/min), which
// matters because the agent loop makes several calls per question. Nemotron sits
// LAST until the loop's time budget is fixed — see the header.
const PROVIDERS: Provider[] = [
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
    // ⚠️ THIS LINE IS WHY NEMOTRON IS USABLE HERE. nemotron-3 is a REASONING
    // model (its endpoint advertises reasoning / reasoning_effort /
    // include_reasoning). At OpenRouter's default effort it emits a long
    // thinking trace before every answer — `stripReasoning()` below throws that
    // text away, but we still WAITED for every token of it. Six of those in one
    // agent loop blew the Worker's waitUntil budget and the bot went silent on
    // 2026-08-01: answers were generated and then cancelled before sending.
    // Low effort keeps the reasoning that helps it write SQL and drops the
    // essay. Do not remove this without re-measuring against `wrangler tail`.
    params: { reasoning: { effort: "low" } },
  },
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
  // OPT-IN, analyst deep-dive lane only (user-authorized PAID model,
  // 2026-08-04 — "deepseek flash on openrouter, that's cheap"). There is NO
  // :free variant (measured: HTTP 404). Same configuration wisdom as the
  // briefing lane (kimi.py): upstream pinned to Baidu — unpinned, OpenRouter
  // draws from ~8 providers whose output quality ranged 7–4,436 tokens — and
  // no silent fallback, so an outage fails loudly into the OSS chain below.
  {
    name: "openrouter/deepseek-v4-flash",
    base: "https://openrouter.ai/api/v1",
    model: "deepseek/deepseek-v4-flash",
    keys: ["OPEN_ROUTER_API", "OPENROUTER_API_KEY"],
    headers: { "HTTP-Referer": "https://carthago.app", "X-Title": "carthago" },
    params: { provider: { order: ["Baidu"], allow_fallbacks: false }, seed: 1729 },
    optIn: true,
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
  /** Absolute wall-clock cutoff (Date.now() ms) for this whole call, retries
   *  and fallbacks included. Without it the chain can walk every provider and
   *  every retry pass, which is far longer than any single `timeoutMs` — and
   *  the caller's own budget is what the Worker's waitUntil actually enforces.
   *  Past the cutoff the chain stops trying and throws, so the caller can still
   *  send a degraded reply instead of being cancelled mid-flight. */
  deadline?: number;
  /** Provider names (the `name` field) this CALL should skip. The analyst memo
   *  lane excludes nemotron: on a long instruction-heavy prose prompt the
   *  reasoning model leaks its planning monologue into the CONTENT channel
   *  (measured 2026-08-04 — both calibration memos came back as "We must not
   *  compute…" essays, truncated at max_tokens, with the figure guard
   *  helplessly passing one because every echoed number was in the data).
   *  The bot's short SQL loop keeps nemotron first — the chains differ on
   *  purpose, like the Python headline lane does. */
  excludeProviders?: string[];
  /** Full replacement chain for this CALL: exactly these provider names, in
   *  this order (unknown names are ignored). The only way to reach an
   *  `optIn` provider. Callers that pass nothing get the default walk. */
  providerOrder?: string[];
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
        ...p.params,
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
  const chain = opts.providerOrder
    ? opts.providerOrder
        .map((name) => PROVIDERS.find((p) => p.name === name))
        .filter((p): p is Provider => p != null)
    : PROVIDERS.filter((p) => !p.optIn);
  for (const p of chain) {
    if (opts.deadline != null && Date.now() >= opts.deadline) {
      errors.push("deadline reached before trying remaining providers");
      break;
    }
    if (opts.excludeProviders?.includes(p.name)) {
      continue;
    }
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
      // Don't sleep into a deadline we've already missed — the retry would
      // start work the caller can no longer use, and burn the budget it needs
      // to send a degraded answer.
      if (opts.deadline != null && Date.now() + backoffs[attempt] >= opts.deadline) break;
      await new Promise((r) => setTimeout(r, backoffs[attempt]));
    }
  }
  throw last;
}
