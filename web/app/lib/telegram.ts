/**
 * Minimal Telegram Bot API helpers for the webhook route.
 *
 * The bot is send-only from our side (we reply to the chat that messaged us);
 * incoming updates arrive via the webhook. Secrets (wrangler secret put):
 *   TELEGRAM_BOT_TOKEN, TELEGRAM_WEBHOOK_SECRET.
 */
import type { StringEnv } from "./cf-env";

export interface TgChat {
  id: number;
  type: string; // 'private' | 'group' | 'supergroup' | 'channel'
}
export interface TgUser {
  id: number;
  is_bot: boolean;
  first_name?: string;
  username?: string;
}
export interface TgMessage {
  message_id: number;
  from?: TgUser;
  chat: TgChat;
  text?: string;
}
export interface TgUpdate {
  update_id: number;
  message?: TgMessage;
  edited_message?: TgMessage;
}

const MAX_TG_LEN = 4096;

/** HTML-escape dynamic text so arbitrary content can't break parse_mode=HTML. */
export function escapeHtml(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

/** Verify the secret Telegram echoes back in a header (set at setWebhook time).
 *  Fails closed: no configured secret → reject. */
export function verifyTelegramSecret(req: Request, env: StringEnv): boolean {
  const expected = env.TELEGRAM_WEBHOOK_SECRET;
  if (!expected) return false;
  const got = req.headers.get("x-telegram-bot-api-secret-token");
  return got === expected;
}

/** Send a message to a chat. Truncates to Telegram's 4096-char limit. Best
 *  effort — logs and returns false on failure, never throws. */
export async function sendMessage(
  env: StringEnv,
  chatId: number | string,
  text: string,
  parseMode: "HTML" | null = "HTML",
): Promise<boolean> {
  const token = env.TELEGRAM_BOT_TOKEN;
  if (!token) {
    console.error("[telegram] TELEGRAM_BOT_TOKEN not set");
    return false;
  }
  const body: Record<string, unknown> = {
    chat_id: chatId,
    text: text.length > MAX_TG_LEN ? text.slice(0, MAX_TG_LEN - 1) + "…" : text,
    disable_web_page_preview: true,
  };
  if (parseMode) body.parse_mode = parseMode;
  try {
    const r = await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!r.ok) {
      console.error(`[telegram] sendMessage HTTP ${r.status}: ${(await r.text()).slice(0, 200)}`);
      return false;
    }
    return true;
  } catch (e) {
    console.error(`[telegram] sendMessage failed: ${e instanceof Error ? e.message : e}`);
    return false;
  }
}
