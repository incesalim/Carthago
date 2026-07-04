/**
 * GET /api/admin/telegram-register — make the Worker register (or inspect) its
 * own Telegram webhook, using the TELEGRAM_BOT_TOKEN + TELEGRAM_WEBHOOK_SECRET
 * it already holds. Lets you set the webhook without ever handling the bot token
 * locally: log into /admin, then open this URL.
 *
 *   ?info   → getWebhookInfo (check current registration, don't change anything)
 *   (none)  → setWebhook to {origin}/api/telegram/webhook
 *
 * Admin-gated. See docs/TELEGRAM_BOT.md.
 */
import { getCloudflareContext } from "@opennextjs/cloudflare";
import { requireAdminOr403 } from "@/app/lib/admin-auth";

export const dynamic = "force-dynamic";

export async function GET(req: Request) {
  const gate = await requireAdminOr403();
  if ("response" in gate) return gate.response;

  const { env } = await getCloudflareContext({ async: true });
  const token = env.TELEGRAM_BOT_TOKEN;
  const secret = env.TELEGRAM_WEBHOOK_SECRET;
  if (!token) {
    return Response.json({ error: "TELEGRAM_BOT_TOKEN not set on the Worker" }, { status: 409 });
  }

  const wantsInfo = new URL(req.url).searchParams.has("info");
  if (wantsInfo) {
    const r = await fetch(`https://api.telegram.org/bot${token}/getWebhookInfo`);
    return Response.json({ action: "getWebhookInfo", telegram: await r.json() });
  }

  if (!secret) {
    return Response.json({ error: "TELEGRAM_WEBHOOK_SECRET not set on the Worker" }, { status: 409 });
  }
  const webhookUrl = `${new URL(req.url).origin}/api/telegram/webhook`;
  const r = await fetch(`https://api.telegram.org/bot${token}/setWebhook`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      url: webhookUrl,
      secret_token: secret,
      allowed_updates: ["message"],
      drop_pending_updates: true,
    }),
  });
  return Response.json({ action: "setWebhook", url: webhookUrl, telegram: await r.json() });
}
