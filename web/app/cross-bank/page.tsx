/**
 * /cross-bank — cross-bank performance heatmap ("Compare" tab).
 *
 * Puts individual banks side by side across the full performance set (assets,
 * NPL, Stage-2, coverage, provisions, ROE, ROA, NIM, Cost/Income), colored by
 * rank vs peers. Two views (Snapshot at the latest common quarter / Over time
 * for one metric) are toggled client-side. All data + per-column scores are
 * computed server-side here, off the single cached heatmapPanel().
 */
import type { Metadata } from "next";
import Link from "next/link";
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
import {
  Colophon,
  Depth,
  DeskHeader,
  SecHead,
  Vital,
  Vitals,
} from "@/app/components/desk";
import HeatmapView from "./HeatmapView";
import MarketShareSection from "./MarketShareSection";
import type { HeatmapBankRow } from "./HeatmapGrid";
import type { HeatmapTimeRow, PanelCell } from "./HeatmapOverTime";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Turkish Banks Compared — Cross-Bank League",
  description: "Compare Turkish banks head-to-head — market share, margins, cost of risk, capital and returns across the sector on one screen.",
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

/** '2026Q1' → 'Q1 2026' for the record line and vitals. */
function quarterLabel(p: string | null | undefined): string {
  const m = p ? /^(\d{4})Q([1-4])$/.exec(p) : null;
  return m ? `Q${m[2]} ${m[1]}` : p || "—";
}

/** Median of the non-null values (null when empty). */
function median(xs: number[]): number | null {
  if (!xs.length) return null;
  const s = [...xs].sort((a, b) => a - b);
  const mid = s.length >> 1;
  return s.length % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2;
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
  const hhiAll = hhiSeries(sharePanel);
  const hhiLatest = period ? hhiAll.find((h) => h.period === period) ?? null : null;

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

  // ---- the brief's computed vitals — medians + named extremes of the same
  // snapshot rows the heatmap scores (fractions in the panel → ×100 here). ----
  type VitalKey = "roe" | "npl_ratio" | "nim";
  const snapMedian = (key: VitalKey) =>
    median(snapRows.map((r) => r[key]).filter((v): v is number => v != null));
  const snapHighest = (key: VitalKey) => {
    let top: { ticker: string; value: number } | null = null;
    for (const r of snapRows) {
      const v = r[key];
      if (v != null && (top == null || v > top.value)) top = { ticker: r.bank_ticker, value: v };
    }
    return top;
  };
  // Median across the reporting fleet, per quarter — the vitals sparklines.
  const medianSeries = (key: VitalKey) =>
    periods
      .map((p) => ({
        period: p,
        value: median(
          panel.filter((r) => r.period === p).map((r) => r[key]).filter((v): v is number => v != null),
        ),
      }))
      .filter((pt): pt is { period: string; value: number } => pt.value != null)
      .map((pt) => ({ period: pt.period, value: pt.value * 100 }));

  const roeMed = snapMedian("roe");
  const nplMed = snapMedian("npl_ratio");
  const nimMed = snapMedian("nim");
  const roeTop = snapHighest("roe");
  const nplTop = snapHighest("npl_ratio");
  const nimTop = snapHighest("nim");
  const leader = league[0] ?? null;
  const hhiNow = hhiLatest?.assets_hhi ?? null;
  const hhiSpark = hhiAll
    .filter((h) => h.assets_hhi != null)
    .map((h) => ({ period: h.period, value: h.assets_hhi as number }));

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
            {snapRows.length} of {banks.length} banks reporting{liveNote}
          </>
        }
        right="every figure computed from source series"
      />

      <SecHead
        title="The vitals"
        meta="medians of the reporting banks · extremes named"
        className="mb-2.5 mt-6"
      />
      <Vitals cols={6}>
        <Vital
          label="Banks compared"
          value={period ? String(snapRows.length) : "—"}
          note={
            <>
              of {banks.length} tracked — the directory at{" "}
              <Link href="/banks" className="font-semibold text-primary">
                /banks
              </Link>
            </>
          }
        />
        <Vital
          label="Median ROE (TTM)"
          value={roeMed != null ? (roeMed * 100).toFixed(1) : "—"}
          unit="%"
          series={medianSeries("roe").slice(-13)}
          decimals={1}
          note={
            roeTop ? (
              <>
                highest: {BANK_NAMES[roeTop.ticker] ?? roeTop.ticker} ({(roeTop.value * 100).toFixed(1)}%) ·{" "}
                <Link href="/profitability" className="font-semibold text-primary">
                  /profitability
                </Link>
              </>
            ) : (
              "TTM net income / 5-quarter avg equity"
            )
          }
        />
        <Vital
          label="Median NPL ratio"
          value={nplMed != null ? (nplMed * 100).toFixed(2) : "—"}
          unit="%"
          series={medianSeries("npl_ratio").slice(-13)}
          note={
            nplTop ? (
              <>
                highest: {BANK_NAMES[nplTop.ticker] ?? nplTop.ticker} ({(nplTop.value * 100).toFixed(2)}%) ·{" "}
                <Link href="/asset-quality" className="font-semibold text-primary">
                  /asset-quality
                </Link>
              </>
            ) : (
              "stage-3 / gross loans, audited"
            )
          }
        />
        <Vital
          label="Median NIM (ann.)"
          value={nimMed != null ? (nimMed * 100).toFixed(2) : "—"}
          unit="%"
          series={medianSeries("nim").slice(-13)}
          note={
            nimTop
              ? `widest: ${BANK_NAMES[nimTop.ticker] ?? nimTop.ticker} (${(nimTop.value * 100).toFixed(2)}%)`
              : "net interest income / period-end assets"
          }
        />
        <Vital
          label="Leader asset share"
          value={leader?.assets_share != null ? (leader.assets_share * 100).toFixed(1) : "—"}
          unit="%"
          note={
            leader
              ? `${BANK_NAMES[leader.bank_ticker] ?? leader.bank_ticker} — rank 1 of ${league.length} by assets`
              : "largest bank / reporting-bank total"
          }
        />
        <Vital
          label="Concentration (HHI)"
          value={hhiNow != null ? hhiNow.toFixed(0) : "—"}
          series={hhiSpark.slice(-13)}
          format="raw"
          decimals={0}
          note="Σ share² × 10,000 — below 1,500 reads unconcentrated"
        />
      </Vitals>

      <Depth>
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
      </Depth>

      <Colophon />
    </main>
  );
}
