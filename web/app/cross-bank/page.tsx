/**
 * /cross-bank — cross-bank performance heatmap ("Compare" tab).
 *
 * Puts individual banks side by side across the full performance set (assets,
 * NPL, Stage-2, coverage, provisions, ROE, ROA, NIM, Cost/Income), colored by
 * rank vs peers. Two views (Snapshot at the latest common quarter / Over time
 * for one metric) are toggled client-side. All data + per-column scores are
 * computed server-side here, off the single cached heatmapPanel().
 */
import {
  heatmapPanel,
  latestCommonPeriod,
  METRIC_DEFS,
  type MetricKey,
} from "@/app/lib/heatmap";
import { normalizeColumn } from "@/app/lib/heatmap-normalize";
import { marketSharePanel, leagueTable, hhiSeries } from "@/app/lib/market-share";
import { listedBistTickers } from "@/app/lib/bist";
import { liveQuotes } from "@/app/lib/bist-live";
import {
  BANK_NAMES,
  BANK_TYPE_BY_TICKER,
  BANK_TYPE_BADGE_LABELS,
} from "@/app/lib/bank_names";
import { PageHeader } from "@/app/components/ui";
import HeatmapView from "./HeatmapView";
import MarketShareSection from "./MarketShareSection";
import type { HeatmapBankRow } from "./HeatmapGrid";
import type { HeatmapTimeRow, PanelCell } from "./HeatmapOverTime";

export const dynamic = "force-dynamic";

// Section order, top to bottom — same as /banks. 10006 State · 10005
// Private·Domestic · 10007 Private·Foreign · 10003 Participation · 10004 Dev&Inv.
const GROUP_ORDER = ["10006", "10005", "10007", "10003", "10004"];

const KEYS: MetricKey[] = METRIC_DEFS.map((m) => m.key);

function groupMeta(ticker: string) {
  const code = BANK_TYPE_BY_TICKER[ticker] ?? "other";
  return {
    groupCode: code,
    groupLabel: BANK_TYPE_BADGE_LABELS[code] ?? "Other",
    name: BANK_NAMES[ticker] ?? ticker,
  };
}

export default async function CrossBankPage() {
  // Live (delayed) quotes for the listed banks → P/B & P/E on the snapshot +
  // the last over-time point reflect the latest price (graceful fallback to the
  // quarter-end close if Yahoo is unreachable).
  const [live, period, sharePanel] = await Promise.all([
    listedBistTickers().then(liveQuotes),
    latestCommonPeriod(),
    marketSharePanel(),
  ]);
  const panel = await heatmapPanel(undefined, live);

  // Competitive dynamics: asset-size league table + sector HHI at the snapshot
  // quarter (same period the snapshot heatmap uses).
  const league = period ? leagueTable(sharePanel, period) : [];
  const hhiLatest = period ? hhiSeries(sharePanel).find((h) => h.period === period) ?? null : null;

  // ---- Snapshot: rows at the latest common quarter, scored per column. ------
  const snapRows = period ? panel.filter((r) => r.period === period) : [];
  const snapRaw = snapRows.map((r) => KEYS.map((k) => r[k]));
  const scoreCols = METRIC_DEFS.map((m, ci) =>
    normalizeColumn(snapRaw.map((raw) => raw[ci]), m.direction),
  );
  const snapshotRows: HeatmapBankRow[] = snapRows.map((r, ri) => ({
    ticker: r.bank_ticker,
    ...groupMeta(r.bank_ticker),
    raw: snapRaw[ri],
    scores: METRIC_DEFS.map((_, ci) => scoreCols[ci][ri]),
  }));

  // ---- Over time: full panel, banks ordered by group then latest assets. ----
  const periods = [...new Set(panel.map((r) => r.period))].sort();
  const latestPeriodByBank = new Map<string, string>();
  const latestAssets = new Map<string, number>();
  for (const r of panel) {
    const cur = latestPeriodByBank.get(r.bank_ticker);
    if (!cur || r.period > cur) {
      latestPeriodByBank.set(r.bank_ticker, r.period);
      if (r.total_assets != null) latestAssets.set(r.bank_ticker, r.total_assets);
    }
  }
  const groupRank = (code: string) => {
    const i = GROUP_ORDER.indexOf(code);
    return i === -1 ? GROUP_ORDER.length : i;
  };
  const banks: HeatmapTimeRow[] = [...new Set(panel.map((r) => r.bank_ticker))]
    .map((ticker) => ({ ticker, ...groupMeta(ticker) }))
    .sort((a, b) => {
      const gr = groupRank(a.groupCode) - groupRank(b.groupCode);
      if (gr !== 0) return gr;
      return (latestAssets.get(b.ticker) ?? -1) - (latestAssets.get(a.ticker) ?? -1);
    });
  const panelCells: PanelCell[] = panel.map((r) => ({
    ticker: r.bank_ticker,
    period: r.period,
    raw: KEYS.map((k) => r[k]),
  }));

  // ---- Header copy. Period is YYYYQN — never pass it to dataThrough (expects
  // YYYY-MM); format it inline instead.
  const q = period ? Number(/Q([1-4])$/.exec(period)?.[1]) : null;
  const year = period?.slice(0, 4);
  const liveNote = live.size
    ? " · P/B & P/E live (~15-min delayed)"
    : " · P/B & P/E at last close";
  const description = period
    ? `Individual banks ranked vs peers across the full performance set · Snapshot: Q${q} ${year} · ${snapRows.length} of ${banks.length} banks reporting${liveNote}`
    : "Individual banks ranked vs peers across the full performance set";

  return (
    <main className="mx-auto w-full max-w-[1440px] px-4 py-8 sm:px-6 lg:px-8 space-y-6">
      <PageHeader title="Compare" description={description} />
      {period ? (
        <>
          <HeatmapView
            metrics={METRIC_DEFS}
            snapshot={{ period, rows: snapshotRows }}
            timePanel={{ banks, periods, panel: panelCells }}
          />
          <MarketShareSection league={league} hhi={hhiLatest} period={period} />
        </>
      ) : (
        <p className="text-sm text-muted-foreground">No per-bank audit data available yet.</p>
      )}
    </main>
  );
}
