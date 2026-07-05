/**
 * GET /api/admin/bot-ask?key=<BOT_TEST_KEY>&q=<question> — run the Telegram
 * bot's agent loop over one question and return the reply + the query trace,
 * WITHOUT going through Telegram. A test harness for validating the bot.
 *
 * Gated by the BOT_TEST_KEY secret (set via `wrangler secret put`); returns 404
 * when the key is unset so the endpoint is invisible unless deliberately enabled.
 */
import { getCloudflareContext } from "@opennextjs/cloudflare";
import type { StringEnv } from "@/app/lib/cf-env";
import { runAgent } from "@/app/lib/bot";

export const dynamic = "force-dynamic";

export async function GET(req: Request) {
  const { env } = await getCloudflareContext({ async: true });
  const sEnv = env as unknown as StringEnv;
  const key = sEnv.BOT_TEST_KEY;
  const url = new URL(req.url);
  if (!key || url.searchParams.get("key") !== key) {
    return new Response("not found", { status: 404 });
  }
  const q = url.searchParams.get("q");
  if (!q) return Response.json({ error: "missing q" }, { status: 400 });

  const started = Date.now();
  const { reply, trace } = await runAgent(sEnv, env.DB, q);
  // Return the plain reply (strip the HTML entities the Telegram path adds).
  const plain = reply.replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&amp;/g, "&");
  return Response.json({ q, reply: plain, steps: trace.length, trace, ms: Date.now() - started });
}
