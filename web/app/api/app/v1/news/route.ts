/**
 * GET /api/app/v1/news — the merged feed.
 *
 * Query: ?source=press|google_news|all (default all), ?limit=1..100 (default 50).
 *
 * Press releases (TCMB/BDDK/KAP) and Google News are stored in the same table
 * but arrive on different crons at different volumes, so they are fetched
 * separately and merged here rather than in SQL — a single ORDER BY across both
 * lets a burst of aggregator noise bury the regulator announcement that actually
 * moves the sector.
 *
 * `tickers` (the per-bank alias tagging) rides along so the client can offer
 * "news about this bank" without a second round trip.
 */
import {
  latestGoogleNews,
  latestPress,
  latestRegulationBriefing,
  type NewsItem,
} from "@/app/lib/news";
import {
  appApiDisabled,
  disabledResponse,
  errorResponse,
  jsonResponse,
} from "../_shared";

export { OPTIONS } from "../_shared";
export const dynamic = "force-dynamic";

const MAX_LIMIT = 100;
const DEFAULT_LIMIT = 50;

const wire = (n: NewsItem) => ({
  id: `${n.source}:${n.external_id}`,
  publishedAt: n.published_at,
  title: n.title,
  summary: n.summary,
  url: n.url,
  source: n.source,
  category: n.category,
  language: n.language,
  tickers: n.tickers ? n.tickers.split(",").filter(Boolean) : [],
});

export async function GET(req: Request) {
  if (await appApiDisabled()) return disabledResponse();

  const url = new URL(req.url);
  const source = url.searchParams.get("source") ?? "all";
  if (!["all", "press", "google_news"].includes(source)) {
    return errorResponse(`Unknown source '${source}'. Use press, google_news or all.`);
  }

  const rawLimit = Number(url.searchParams.get("limit") ?? DEFAULT_LIMIT);
  if (!Number.isFinite(rawLimit) || rawLimit < 1) {
    return errorResponse("limit must be a positive integer.");
  }
  const limit = Math.min(Math.floor(rawLimit), MAX_LIMIT);

  const [press, google, briefing] = await Promise.all([
    source === "google_news" ? Promise.resolve([]) : latestPress(limit),
    source === "press" ? Promise.resolve([]) : latestGoogleNews(limit),
    // The briefing is an extra; a missing or malformed one must not cost the
    // reader their feed.
    latestRegulationBriefing().catch(() => null),
  ]);

  const items = [...press, ...google]
    .sort((a, b) => b.published_at.localeCompare(a.published_at))
    .slice(0, limit)
    .map(wire);

  return jsonResponse({
    source,
    count: items.length,
    items,
    // Carries its own provenance: which model wrote it, over what window, from
    // how many items. The app prints that under the briefing — an LLM summary
    // is never shown as if it were a filed figure.
    briefing: briefing
      ? {
          generatedAt: briefing.generated_at,
          windowDays: briefing.window_days,
          itemCount: briefing.item_count,
          model: briefing.model,
          categories: briefing.categories,
        }
      : null,
  });
}
