/**
 * Free OpenAI-compatible chat client for the Cloudflare Worker (Telegram bot).
 *
 * Mirrors the Python headline generator's provider chain (src/news/free_llm.py):
 *   Cerebras gpt-oss-120b  →  Groq openai/gpt-oss-120b  →  Cerebras gemma-4-31b
 * but generalised to arbitrary chat completions and reading keys from the
 * Cloudflare env (secrets) rather than process.env.
 *
 * Keys (set with `wrangler secret put` — see docs/TELEGRAM_BOT.md):
 *   CEREBRAS_KEY (or CEREBRAS_API_KEY), GROQ_API_KEY (or GROQ_API_TOKEN).
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
}

// Ordered fallback chain. Each is OpenAI-compatible (`/chat/completions`).
const PROVIDERS: Provider[] = [
  {
    name: "cerebras/gpt-oss-120b",
    base: "https://api.cerebras.ai/v1",
    model: "gpt-oss-120b",
    keys: ["CEREBRAS_KEY", "CEREBRAS_API_KEY"],
  },
  {
    name: "groq/openai/gpt-oss-120b",
    base: "https://api.groq.com/openai/v1",
    model: "openai/gpt-oss-120b",
    keys: ["GROQ_API_KEY", "GROQ_API_TOKEN"],
  },
  {
    name: "cerebras/gemma-4-31b",
    base: "https://api.cerebras.ai/v1",
    model: "gemma-4-31b",
    keys: ["CEREBRAS_KEY", "CEREBRAS_API_KEY"],
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

/**
 * Run a chat completion through the provider fallback chain. Returns the first
 * provider that answers with non-empty text. Throws if every configured
 * provider errors (or none is configured).
 */
export async function chatComplete(
  env: StringEnv,
  messages: ChatMessage[],
  opts: ChatOpts = {},
): Promise<ChatResult> {
  const errors: string[] = [];
  for (const p of PROVIDERS) {
    const key = keyFor(env, p);
    if (!key) continue;
    try {
      const text = await callProvider(p, key, messages, opts);
      if (text) return { text, model: p.name };
      errors.push(`${p.name}: empty`);
    } catch (e) {
      errors.push(`${p.name}: ${e instanceof Error ? e.message : String(e)}`);
    }
  }
  throw new Error(
    errors.length ? `all LLM providers failed — ${errors.join("; ")}` : "no LLM provider configured",
  );
}
