/**
 * GET /api/app/v1/banks/{ticker} — one bank.
 *
 * The scorecard at the latest quarter, the trend behind each headline metric,
 * the franchise profile, the TFRS-9 stage view, and that bank's KAP feed.
 *
 * Metric history comes from the same `heatmapPanel` the cross-bank grid reads,
 * filtered to one ticker — so a bank's ROE on its own screen is arithmetically
 * the same number as its cell in the sector heatmap. Computing it locally "just
 * for this screen" is how two surfaces start disagreeing.
 */
import { bankProfile, bankStagesLatest, bankSummaries } from "@/app/lib/audit";
import {
  BANK_NAMES,
  BANK_TYPE_BADGE_LABELS,
  BANK_TYPE_BY_TICKER,
  isPeerExcluded,
} from "@/app/lib/bank_names";
import { heatmapPanel, METRIC_DEFS } from "@/app/lib/heatmap";
import { newsByTicker } from "@/app/lib/news";
import {
  appApiDisabled,
  disabledResponse,
  errorResponse,
  jsonResponse,
} from "../../_shared";

export { OPTIONS } from "../../_shared";
export const dynamic = "force-dynamic";

/** Headline metrics the phone screen leads with, in reading order. The full
 *  21-metric scorecard belongs on a laptop; this is the subset that answers
 *  "how is this bank doing" without scrolling. */
const HEADLINE = [
  "total_assets", "roe", "roa", "npl_ratio", "npl_coverage",
  "car", "cet1", "nim", "cost_income", "lcr",
] as const;

/** How many quarters of trend to ship per metric. Eight = two years, which is
 *  the span a sparkline can actually resolve on a phone. */
const TREND_QUARTERS = 8;

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ ticker: string }> },
) {
  if (await appApiDisabled()) return disabledResponse();

  const { ticker: raw } = await params;
  const ticker = raw.toUpperCase();

  if (!(ticker in BANK_NAMES)) {
    return errorResponse(`Unknown bank '${ticker}'.`, 404);
  }

  const [panel, profile, stages, summaries, news] = await Promise.all([
    heatmapPanel(),
    bankProfile(ticker).catch(() => null),
    bankStagesLatest(ticker).catch(() => null),
    bankSummaries().catch(() => []),
    newsByTicker(ticker, 15).catch(() => []),
  ]);

  const history = panel
    .filter((r) => r.bank_ticker === ticker)
    .sort((a, b) => a.period.localeCompare(b.period));

  const latest = history.at(-1) ?? null;
  if (!latest) {
    return errorResponse(`No audited filings held for '${ticker}'.`, 404);
  }

  const defs = new Map(METRIC_DEFS.map((d) => [d.key, d]));
  const trend = history.slice(-TREND_QUARTERS);

  const scorecard = HEADLINE.map((key) => {
    const d = defs.get(key);
    return {
      key,
      label: d?.label ?? key,
      short: d?.short ?? key,
      // `unit` distinguishes a FRACTION (0.155) from percentage POINTS (15.5) —
      // the audited §4 ratios arrive already in points. Shipping it means the
      // client never has to guess which scaling a metric needs.
      unit: d?.unit ?? "raw",
      decimals: d?.decimals ?? 2,
      direction: d?.direction ?? "neutral",
      // The rule the number was made by, printed under it (DESIGN.md rule 6).
      rule: d?.rule ?? null,
      value: latest[key] ?? null,
      series: trend.map((r) => ({ t: r.period, v: r[key] ?? null })),
    };
  });

  const summary = summaries.find((s) => s.bank_ticker === ticker) ?? null;

  return jsonResponse({
    ticker,
    name: BANK_NAMES[ticker],
    type: BANK_TYPE_BY_TICKER[ticker] ?? null,
    typeLabel: BANK_TYPE_BADGE_LABELS[BANK_TYPE_BY_TICKER[ticker]] ?? null,
    peerExcluded: isPeerExcluded(ticker),
    period: latest.period,
    coverage: {
      periodsHeld: summary?.periods ?? history.length,
      latestPeriodHeld: summary?.latest_period ?? latest.period,
    },
    scorecard,
    // Reported vs free-provision-adjusted. Where a bank has released a
    // discretionary serbest-karşılık stock, the reported ROE is not the
    // franchise's ROE, and the two must be shown together or not at all.
    earningsQuality: {
      roe: latest.roe,
      roeAdjusted: latest.roeAdjusted,
      freeProvision: latest.freeProvision,
    },
    profile: profile
      ? {
          period: profile.period,
          branchesTotal: profile.branches_total,
          branchesDomestic: profile.branches_domestic,
          branchesForeign: profile.branches_foreign,
          personnel: profile.personnel,
        }
      : null,
    stages: stages
      ? {
          period: stages.period,
          stage1: stages.stage1_amount,
          stage2: stages.stage2_amount,
          stage3: stages.stage3_amount,
          total: stages.total_amount,
          coverage1: stages.stage1_coverage,
          coverage2: stages.stage2_coverage,
          coverage3: stages.stage3_coverage,
        }
      : null,
    news: news.map((n) => ({
      id: `${n.source}:${n.external_id}`,
      publishedAt: n.published_at,
      title: n.title,
      summary: n.summary,
      url: n.url,
      source: n.source,
      category: n.category,
      language: n.language,
    })),
    web: `https://carthago.app/banks/${ticker}`,
  });
}
