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
 *
 * The SPINE is `bankSummaries()`, not `heatmapPanel()`. The panel deliberately
 * refuses to hold a peer-excluded bank at all — `ensure()` hands those callers a
 * throwaway row, because every rank, colour scale and percentile downstream is
 * computed off that map. Building the index off it dropped Takasbank from the
 * list entirely, so the app couldn't reach a bank the website lists and serves
 * a full page for. Peer exclusion belongs to the RANKING, not to the universe.
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

  // Ratios, keyed by ticker at the common period. Absent for a peer-excluded
  // bank by construction — see the header note.
  const metrics = new Map(
    panel.filter((r) => r.period === period).map((r) => [r.bank_ticker, r]),
  );

  const rows = summaries
    .map((s) => {
      const m = metrics.get(s.bank_ticker);
      const excluded = isPeerExcluded(s.bank_ticker);
      return {
        ticker: s.bank_ticker,
        name: BANK_NAMES[s.bank_ticker] ?? s.bank_ticker,
        type: BANK_TYPE_BY_TICKER[s.bank_ticker] ?? null,
        typeLabel: BANK_TYPE_BADGE_LABELS[BANK_TYPE_BY_TICKER[s.bank_ticker]] ?? null,
        // Takasbank is a CCP, not a lender. It carries real filings and gets its
        // own page, but it is flagged so no client-side league table seats a
        // clearing house's CAR among deposit-funded banks.
        peerExcluded: excluded,
        // Scale comes from bankSummaries, so it is present even for a bank the
        // ratio panel refuses to hold.
        totalAssets: s.total_assets, // thousand TL
        roe: m?.roe ?? null,
        roeAdjusted: m?.roeAdjusted ?? null,
        npl: m?.npl_ratio ?? null,
        car: m?.car ?? null,
        cet1: m?.cet1 ?? null,
        nim: m?.nim ?? null,
        costIncome: m?.cost_income ?? null,
        periodsHeld: s.periods,
        latestPeriodHeld: s.latest_period,
      };
    })
    .sort((a, b) => (b.totalAssets ?? -Infinity) - (a.totalAssets ?? -Infinity));

  return jsonResponse({
    period,
    count: rows.length,
    // The client ranks and colour-scales off `peers`; `count` is the universe.
    peers: rows.filter((r) => !r.peerExcluded).length,
    rows,
  });
}
