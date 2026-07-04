/**
 * POST /api/telegram/webhook — Telegram pushes each incoming message here.
 *
 * Security: Telegram echoes the secret we registered with setWebhook in the
 * `X-Telegram-Bot-Api-Secret-Token` header; we reject anything that doesn't
 * match (fails closed if the secret isn't configured). We ACK with 200
 * immediately and do the (slow) LLM + SQL work in ctx.waitUntil so Telegram
 * doesn't time out and re-deliver the update. See docs/TELEGRAM_BOT.md.
 */
import { getCloudflareContext } from "@opennextjs/cloudflare";
import type { StringEnv } from "@/app/lib/cf-env";
import { handleUpdate } from "@/app/lib/bot";
import { verifyTelegramSecret, type TgUpdate } from "@/app/lib/telegram";

export const dynamic = "force-dynamic";

export async function POST(req: Request) {
  const { env, ctx } = await getCloudflareContext({ async: true });
  const sEnv = env as unknown as StringEnv;

  if (!verifyTelegramSecret(req, sEnv)) {
    return new Response("forbidden", { status: 401 });
  }

  let update: TgUpdate;
  try {
    update = (await req.json()) as TgUpdate;
  } catch {
    return new Response("ok"); // ignore malformed bodies (don't trigger retries)
  }

  const work = handleUpdate(update, sEnv, env.DB);
  if (ctx?.waitUntil) ctx.waitUntil(work);
  else await work; // fallback if no execution context is available

  return new Response("ok");
}
