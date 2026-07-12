/**
 * /cross-bank — the "Compare" tab.
 *
 * A matchup sheet: pick up to four banks, state the peer frame they are measured
 * against, and read every metric as a row on a real value axis (CompareBoard).
 * The full banks × metrics grid, the over-time grid and the market-share league
 * carry over underneath, as the evidence layer.
 *
 * This file is now just the data fan-out: one cached heatmapPanel() plus the
 * market-share panel. Every rank, median and axis is derived client-side off the
 * frame the reader chooses — see CompareBoard.
 */
import type { Metadata } from "next";
import {
  heatmapPanel,
  latestCommonPeriod,
  METRIC_DEFS,
  type MetricKey,
} from "@/app/lib/heatmap";
import { marketSharePanel, leagueTable, hhiSeries } from "@/app/lib/market-share";
import { listedBistTickers } from "@/app/lib/bist";
import { liveQuotes } from "@/app/lib/bist-live";
import {
  BANK_NAMES,
  BANK_TYPE_BY_TICKER,
  BANK_TYPE_BADGE_LABELS,
} from "@/app/lib/bank_names";
import { Colophon, DeskHeader } from "@/app/components/desk";
import CompareBoard from "./CompareBoard";
import MarketShareSection from "./MarketShareSection";
import type { BoardBank } from "./picks";
import type { PanelCell } from "./HeatmapOverTime";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Turkish Banks Compared — Cross-Bank League",
  description:
    "Compare Turkish banks head-to-head — market share, margins, cost of risk, capital and returns across the sector on one screen.",
  alternates: { canonical: "/cross-bank" },
};

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

/** '2026Q1' → 'Q1 2026' for the record line. */
function quarterLabel(p: string | null | undefined): string {
  const m = p ? /^(\d{4})Q([1-4])$/.exec(p) : null;
  return m ? `Q${m[2]} ${m[1]}` : p || "—";
}

export default async function CrossBankPage() {
  // Live (delayed) quotes for the listed banks → P/B & P/E reflect the latest
  // price (graceful fallback to the quarter-end close if Yahoo is unreachable).
  const [live, period, sharePanel] = await Promise.all([
    listedBistTickers().then(liveQuotes),
    latestCommonPeriod(),
    marketSharePanel(),
  ]);
  const panel = await heatmapPanel(undefined, live);

  const league = period ? leagueTable(sharePanel, period) : [];
  const hhiAll = hhiSeries(sharePanel);
  const hhiLatest = period ? (hhiAll.find((h) => h.period === period) ?? null) : null;

  // Banks, ordered by group then latest assets — the bench's reading order.
  const periods = [...new Set(panel.map((r) => r.period))].sort();
  const latestAssets = new Map<string, number>();
  const latestPeriodByBank = new Map<string, string>();
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
  const banks: BoardBank[] = [...new Set(panel.map((r) => r.bank_ticker))]
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

  const reporting = period
    ? new Set(panel.filter((r) => r.period === period).map((r) => r.bank_ticker)).size
    : 0;
  const liveNote = live.size
    ? " · P/B & P/E live (~15-min delayed)"
    : " · P/B & P/E at last close";

  return (
    <main className="mx-auto w-full max-w-[1440px] px-4 py-7 sm:px-6 lg:px-9">
      <DeskHeader
        title="Compare"
        record={
          <>
            Record <b className="font-normal text-foreground">{quarterLabel(period)}</b> ·{" "}
            {reporting} of {banks.length} banks reporting{liveNote}
          </>
        }
        right="every figure computed from source series"
      />

      {period ? (
        <CompareBoard
          metrics={METRIC_DEFS}
          banks={banks}
          periods={periods}
          panel={panelCells}
          period={period}
          marketShare={
            <MarketShareSection league={league} hhi={hhiLatest} period={period} />
          }
        />
      ) : (
        <p className="mt-6 text-sm text-muted-foreground">
          No per-bank audit data available yet.
        </p>
      )}

      <Colophon />
    </main>
  );
}
