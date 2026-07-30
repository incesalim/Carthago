/**
 * GET /api/app/v1/banks — the bank index.
 *
 * One row per bank at the latest COMMON quarter, size-ranked. The client renders
 * this as a searchable list, so it carries just enough per row to sort, filter
 * and show a two-line summary; the full scorecard lives behind
 * /api/app/v1/banks/{ticker}.
 *
 * `latestCommonPeriod()` rather than each bank's own latest: a list that mixes
 * quarters silently ranks a late filer's stale CAR against everyone else's fresh
 * one. One period for the whole list, printed at the top, is the honest read.
 */
import { bankSummaries } from "@/app/lib/audit";
import {
  BANK_NAMES,
  BANK_TYPE_BADGE_LABELS,
  BANK_TYPE_BY_TICKER,
  isPeerExcluded,
} from "@/app/lib/bank_names";
import { heatmapPanel, latestCommonPeriod } from "@/app/lib/heatmap";
import { appApiDisabled, disabledResponse, jsonResponse } from "../_shared";

export { OPTIONS } from "../_shared";
export const dynamic = "force-dynamic";

export async function GET() {
  if (await appApiDisabled()) return disabledResponse();

  const [period, panel, summaries] = await Promise.all([
    latestCommonPeriod(),
    heatmapPanel(),
    bankSummaries(),
  ]);

  // Coverage (how many quarters we hold) is per-bank and independent of the
  // common period — it's what the client shows when a metric cell is empty, so
  // "we hold no filing" reads differently from "the filing has no such line".
  const coverage = new Map(summaries.map((s) => [s.bank_ticker, s]));

  const rows = panel
    .filter((r) => r.period === period)
    .map((r) => {
      const s = coverage.get(r.bank_ticker);
      return {
        ticker: r.bank_ticker,
        name: BANK_NAMES[r.bank_ticker] ?? r.bank_ticker,
        type: BANK_TYPE_BY_TICKER[r.bank_ticker] ?? null,
        typeLabel: BANK_TYPE_BADGE_LABELS[BANK_TYPE_BY_TICKER[r.bank_ticker]] ?? null,
        // Takasbank is a CCP, not a lender. It carries real filings and gets its
        // own page, but it is flagged so no client-side league table seats a
        // clearing house's CAR among deposit-funded banks.
        peerExcluded: isPeerExcluded(r.bank_ticker),
        totalAssets: r.total_assets, // thousand TL
        roe: r.roe,
        roeAdjusted: r.roeAdjusted,
        npl: r.npl_ratio,
        car: r.car,
        cet1: r.cet1,
        nim: r.nim,
        costIncome: r.cost_income,
        periodsHeld: s?.periods ?? 0,
        latestPeriodHeld: s?.latest_period ?? null,
      };
    })
    .sort((a, b) => (b.totalAssets ?? -Infinity) - (a.totalAssets ?? -Infinity));

  return jsonResponse({ period, count: rows.length, rows });
}
