/**
 * GET /api/app/v1 — handshake.
 *
 * The client calls this once on launch, before any screen renders. It is the
 * only endpoint whose shape can never change, because a build from a year ago
 * must still be able to parse it well enough to learn that it is too old.
 *
 * Keep it cheap: no D1 reads on the launch path. Everything here is a constant
 * or a coverage figure the screens fetch anyway.
 */
import {
  APP_API_VERSION,
  MIN_SUPPORTED_CLIENT,
  appApiDisabled,
  disabledResponse,
  jsonResponse,
} from "./_shared";

export { OPTIONS } from "./_shared";
export const dynamic = "force-dynamic";

export async function GET() {
  if (await appApiDisabled()) return disabledResponse();

  return jsonResponse({
    name: "Carthago Mobile API",
    version: APP_API_VERSION,
    minSupportedClient: MIN_SUPPORTED_CLIENT,
    // Where the app sends anyone who needs the full surface: the phone carries
    // the brief, the website carries the evidence.
    web: "https://carthago.app",
    screens: {
      overview: "/api/app/v1/overview",
      banks: "/api/app/v1/banks",
      bank: "/api/app/v1/banks/{ticker}",
      economy: "/api/app/v1/economy",
      news: "/api/app/v1/news",
    },
  });
}
