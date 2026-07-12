/**
 * /banks/[ticker] — per-bank drill-down.
 *
 * Standardized financial statements (Balance Sheet / Income Statement / Cash
 * Flow) in a Yahoo-Finance-style layout: single continuous table, period-end
 * dates as column headers, computed subtotals (Total Assets, Total Liabilities,
 * Total Liabilities + Equity, plus P&L subtotals) shown in bold. Missing values
 * render as "--".
 *
 * Controls (URL params, server-rendered):
 *   ?statement=bs|is|cf — which statement
 *   ?mode=abs           — the filed figure, TL thousands
 *   ?mode=yoy           — nominal YoY % vs the same quarter a year earlier
 *   ?mode=real          — the same YoY DEFLATED by CPI (nominal | CPI | real |
 *                         verdict). Under 30-40% inflation the nominal column
 *                         says almost nothing: `realGrowth` DIVIDES, it does not
 *                         subtract — 40% against 32% CPI is +6.1% real, not +8.
 *   ?mode=size          — common-size: every line as a % of total assets (BS) or
 *                         of interest income (IS), plus — on the balance sheet —
 *                         the SECTOR MEDIAN share and this bank's gap to it.
 *   ?view=annual        — most recent Q4s (comparable year-end data)
 *   ?view=quarterly     — most recent quarters (sequential); adds a leading TTM
 *                         column for the income statement + cash flow
 *   ?kind=consolidated|unconsolidated
 *
 * All three statements map to BRSA hierarchy codes (see
 * web/app/lib/standard_lines.ts) with canonical English labels — the raw
 * `item_name` is never displayed, so banks are comparable line-for-line.
 *
 * Above the table sits the SHAPE layer — the balance sheet as two composition
 * columns (what it owns / what funds it, each line with its share and its REAL
 * growth), the income statement as a waterfall (how the profit is built) or an
 * interest-flow fan (where the money comes from and goes). Derived in
 * `lib/bank-financials.ts` + `lib/pl-shape.ts`; both reconcile to the filing.
 */
import type { Metadata } from "next";
import type { ReactElement } from "react";
import Link from "next/link";
import { PageHeader, Section, Stat } from "@/app/components/ui";
import { Colophon, SecHead, Vital, Vitals, type MoverRow } from "@/app/components/desk";
import { cpiFromIndex, lastVal, monthLabel, signedPp, valAgo } from "@/app/lib/desk";
import {
  PEER_FIELDS,
  bankFlags,
  engineGate,
  peerStat,
  risingStreak,
} from "@/app/lib/bank-brief";
import {
  balanceSheetLead,
  compositionRows,
  cpiForPeriod,
  realRead,
  type CompLine,
  type StatementMode,
} from "@/app/lib/bank-financials";
import {
  Engine,
  Franchise,
  Identity,
  MoversAndFlags,
  WhereItStands,
  type EngineRow,
  type FundingSlice,
} from "./BriefLayer";
import {
  bankPeriods,
  balanceSheetMultiPeriod,
  balanceSheetLineNames,
  profitLossMultiPeriod,
  profitLossRowsMultiPeriod,
  cashFlowMultiPeriod,
  bankProfile,
  bankStagesLatest,
  sectorLineShares,
  validationByPeriod,
  SECTOR_TOTAL_ASSETS_KEY,
  SECTOR_TOTAL_LE_KEY,
  SECTOR_TOTAL_LIABILITIES_KEY,
} from "@/app/lib/audit";
import { ordOf, ttmEndingAt, yoyPct } from "@/app/lib/period-math";
import { newsByTicker, pressNewsByBank } from "@/app/lib/news";
import { earningsByTicker } from "@/app/lib/earnings";
import { bankOwnership } from "@/app/lib/kap";
import { heatmapPanel } from "@/app/lib/heatmap";
import { evdsSeries } from "@/app/lib/metrics";
import { marketSharePanel, bankShareSeries } from "@/app/lib/market-share";
import { bankMarketRiskDetail } from "@/app/lib/market-risk";
import { bistValuation, bistPriceHistory } from "@/app/lib/bist";
import { liveQuotes, applyLivePrice, formatAsOf } from "@/app/lib/bist-live";
import TimeSeriesChart from "@/app/components/TimeSeriesChart";
import { BankTabs, type BankTab } from "./BankTabs";
import { MarginBridgeChart, MarketShareChart } from "./BankCharts";
import MarketRiskSection from "./MarketRiskSection";
import OwnershipSummary from "./OwnershipSummary";
import EarningsDisclosures from "./EarningsDisclosures";
import BankNewsSection from "./BankNewsSection";
import BsShape from "./BsShape";
import IncomeShape from "./IncomeShape";
import CopyTableButton from "@/app/components/CopyTableButton";
import BankLogo from "@/app/components/BankLogo";
import {
  BS_ASSET_LINES,
  BS_ASSET_ROMAN_HIERARCHIES,
  BS_LIAB_LINES,
  BS_LIAB_ROMAN_HIERARCHIES,
  BS_EQUITY_HIERARCHY,
  BS_LIAB_LINES_PARTICIPATION,
  BS_LIAB_ROMAN_HIERARCHIES_PARTICIPATION,
  BS_EQUITY_HIERARCHY_PARTICIPATION,
  PL_LINES,
  CF_LINES,
  CF_ROMAN_HIERARCHIES,
  indentLevel,
  type StandardLine,
} from "@/app/lib/standard_lines";
import { bankDisplayName, BANK_TYPE_BY_TICKER } from "@/app/lib/bank_names";
import { notFound } from "next/navigation";

export const dynamic = "force-dynamic";

interface Props {
  params: Promise<{ ticker: string }>;
  searchParams: Promise<{ view?: string; kind?: string; statement?: string; mode?: string; tab?: string }>;
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { ticker: rawTicker } = await params;
  const ticker = rawTicker.toUpperCase();
  const name = bankDisplayName(ticker);
  const title = `${name} — Financials & Analysis`;
  const description = `Audited BRSA financials for ${name} (${ticker}): balance sheet, income statement, cash flow, capital, asset quality and profitability — quarterly, from official Turkish banking-sector reports.`;
  return {
    title,
    description,
    alternates: { canonical: `/banks/${ticker}` },
    openGraph: { title: `${title} · Carthago`, description, url: `https://carthago.app/banks/${ticker}` },
  };
}

const NF = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
const fmtTl = (v: number | null | undefined) => (v == null ? "--" : NF.format(v));

/** YoY-growth cell: signed percentage, one decimal. "--" when underivable. */
const PF = new Intl.NumberFormat("en-US", { maximumFractionDigits: 1, signDisplay: "exceptZero" });
const fmtPct = (v: number | null | undefined) => (v == null ? "--" : `${PF.format(v)}%`);

/** Common-size cell: an UNSIGNED share (the "+" of a signed formatter would read
 *  as growth). Contra lines still print negative — the sign is the deduction. */
const SF = new Intl.NumberFormat("en-US", { maximumFractionDigits: 1 });
const fmtShare = (v: number | null | undefined) => (v == null ? "--" : `${SF.format(v)}%`);

/** The lens toggle — four readings of the same filed rows, one URL param. */
const LENS_LABEL: Record<StatementMode, string> = {
  abs: "Absolute",
  yoy: "YoY Growth",
  real: "Real YoY",
  size: "Common-size",
};
const LENS_HINT: Record<StatementMode, string> = {
  abs: "The figure as filed, TL thousands",
  yoy: "Nominal % vs the same quarter a year earlier",
  real: "That growth deflated by CPI — (1+nominal)/(1+CPI)−1, not a subtraction",
  size: "Every line as a % of total assets (balance sheet) or interest income (income statement), against the sector median",
};

/** "2025Q4" → "12/31/2025" (Yahoo-style period-end date). */
function periodToDate(period: string): string {
  const m = /^(\d{4})Q([1-4])$/.exec(period);
  if (!m) return period;
  const year = m[1];
  const q = m[2];
  const endDate: Record<string, string> = {
    "1": `3/31/${year}`,
    "2": `6/30/${year}`,
    "3": `9/30/${year}`,
    "4": `12/31/${year}`,
  };
  return endDate[q] ?? period;
}

/** Pick the periods to display based on view mode. */
function pickPeriods(allPeriods: string[], view: "annual" | "quarterly", count = 4): string[] {
  if (view === "annual") {
    return allPeriods.filter((p) => p.endsWith("Q4")).slice(0, count);
  }
  return allPeriods.slice(0, count);
}

/** One rendered table cell. The lens decides both the text AND its tone —
 *  a real-growth verdict is green/red, a common-size gap past ±5pp is amber. */
interface Cell {
  text: string;
  tone?: "pos" | "neg" | "warn" | "muted";
}

const TONE_CLASS: Record<NonNullable<Cell["tone"]>, string> = {
  pos: "text-positive",
  neg: "text-negative",
  warn: "text-warning",
  muted: "text-faint",
};

interface RowProps {
  label: string;
  cells: Cell[];
  /** A COMPUTED subtotal (Net interest income, Total assets, …) — the sums that
   *  carry the argument. Ruled top and bottom. */
  divider?: boolean;
  /** Indent depth 0/1/2 — drives left padding + text muting. */
  depth?: number;
}

/** Tailwind padding by indent depth (0 = top-level, 1 = sub, 2 = sub-sub). */
const INDENT_PL = ["pl-0", "pl-6", "pl-10"];

/**
 * Three tiers, because the statement has three kinds of line — and the old table
 * gave all of them the same weight and the same rule, which is what made it a wall:
 *
 *   SUBTOTAL   the sums (Net interest income, Gross operating profit, Total assets)
 *              — bold ink, ruled above and below. These are the argument.
 *   COMPONENT  a top-level line that feeds a sum (Interest income, Personnel
 *              expenses) — medium weight, one faint hairline.
 *   DETAIL     its breakdown (Interest from loans, Fees paid) — muted, smaller,
 *              indented, and NO rule at all, so the breakdown reads as one cluster
 *              hanging off its parent instead of thirty free-standing rows.
 */
function Row({ label, cells, divider, depth = 0 }: RowProps) {
  const pl = INDENT_PL[Math.min(depth, INDENT_PL.length - 1)];
  const detail = depth >= 1 && !divider;

  const rowCls = divider
    ? "border-y border-foreground hover:bg-muted"
    : detail
      ? "hover:bg-muted"
      : "border-b border-hair hover:bg-muted";

  const labelCls = divider
    ? "py-2 text-[12.5px] font-bold text-foreground"
    : detail
      ? "py-[3px] text-[11px] text-muted-foreground"
      : "py-[5px] text-[12px] font-medium text-foreground";

  const figCls = divider
    ? "py-2 text-[12.5px] font-semibold text-foreground"
    : detail
      ? "py-[3px] text-[11px] text-muted-foreground"
      : "py-[5px] text-[11.5px] text-foreground";

  return (
    <tr className={rowCls}>
      <td className={`pr-3 ${pl} ${labelCls}`}>{label}</td>
      {cells.map((c, i) => (
        <td
          key={i}
          className={`pl-4 text-right font-mono tabular-nums whitespace-nowrap ${figCls} ${
            c.tone ? `${TONE_CLASS[c.tone]} ${divider ? "font-semibold" : ""}` : ""
          }`}
        >
          {c.text}
        </td>
      ))}
    </tr>
  );
}

/** Mono-caps band that splits the statement into its blocks (Assets · Funding). */
function GroupRow({ label, span }: { label: string; span: number }) {
  return (
    <tr>
      <td
        colSpan={span}
        className="border-b border-border pt-4 pb-1 font-mono text-[8.5px] uppercase tracking-[0.1em] text-faint"
      >
        {label}
      </td>
    </tr>
  );
}

/** A labelled control group — the label states what the control reaches. */
function ControlGroup({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="mb-1 font-mono text-[8px] uppercase tracking-[0.12em] text-faint">{label}</div>
      <div className="flex flex-wrap items-center gap-x-3.5 gap-y-1">{children}</div>
    </div>
  );
}

/** Underlined text toggle — the Desk idiom (no pills, no fills). */
function Toggle({
  href,
  on,
  title,
  children,
}: {
  href: string;
  on: boolean;
  title?: string;
  children: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      scroll={false}
      title={title}
      aria-current={on ? "true" : undefined}
      className={
        on
          ? "border-b-2 border-foreground pb-0.5 text-[12.5px] font-semibold text-foreground"
          : "border-b-2 border-transparent pb-0.5 text-[12.5px] text-muted-foreground transition-colors hover:text-foreground"
      }
    >
      {children}
    </Link>
  );
}

type PeriodSeries = Map<string, number | null>;

/** A line's raw period→value series from the pivot map (over every queried
 *  period — the mode/TTM transform reads prior-year periods from it). */
function lineSeries(
  pivot: Map<string, PeriodSeries>,
  line: StandardLine,
  statement: string,
): PeriodSeries {
  const key = statement ? `${statement}::${line.hierarchy}` : line.hierarchy;
  return pivot.get(key) ?? new Map();
}

/** Sum non-null values across a list of BRSA hierarchy codes, per period.
 *  Used for synthetic Total Assets / Total Liabilities rows — pass the
 *  Roman-numeral parent codes (BS_ASSET_ROMAN_HIERARCHIES etc.) to avoid
 *  double-counting sub-items that are also displayed individually. */
function sumSeries(
  pivot: Map<string, PeriodSeries>,
  hierarchies: string[],
  statement: string,
): PeriodSeries {
  const allPeriods = new Set<string>();
  for (const h of hierarchies) {
    const m = pivot.get(`${statement}::${h}`);
    if (m) for (const p of m.keys()) allPeriods.add(p);
  }
  const out: PeriodSeries = new Map();
  for (const p of allPeriods) {
    let total = 0;
    let any = false;
    for (const h of hierarchies) {
      const v = pivot.get(`${statement}::${h}`)?.get(p);
      if (v != null) {
        total += v;
        any = true;
      }
    }
    out.set(p, any ? total : null);
  }
  return out;
}

const nfmt = (v: number, d = 2) =>
  new Intl.NumberFormat("en-US", { minimumFractionDigits: d, maximumFractionDigits: d }).format(v);

/** Market cap (TL) → "₺570.8B" / "₺1.05T". */
function fmtMarketCap(tl: number): string {
  if (tl >= 1e12) return `₺${nfmt(tl / 1e12, 2)}T`;
  return `₺${nfmt(tl / 1e9, 1)}B`;
}

export default async function BankDetailPage({ params, searchParams }: Props) {
  const { ticker: rawTicker } = await params;
  const sp = await searchParams;
  const ticker = rawTicker.toUpperCase();

  const allPeriodMeta = await bankPeriods(ticker);
  if (allPeriodMeta.length === 0) notFound();

  const kind = (sp.kind as "consolidated" | "unconsolidated") ?? "unconsolidated";
  const view = (sp.view as "annual" | "quarterly") ?? "quarterly";
  const statement = (sp.statement as "bs" | "is" | "cf") ?? "bs";
  // Each tab IS the page: the server renders one view, not all of them stacked.
  // (The old jump-nav anchored into a single 6,700px document that stated most
  // numbers twice — the brief said them, then the legacy cards said them again.)
  const TAB_IDS: BankTab[] = ["desk", "financials", "risk", "ownership", "news"];
  const tab: BankTab = TAB_IDS.includes(sp.tab as BankTab) ? (sp.tab as BankTab) : "desk";

  const rawMode = (sp.mode as StatementMode) ?? "abs";
  // Common-size needs a denominator with meaning: total assets (balance sheet)
  // or interest income (income statement). The cash-flow statement has neither —
  // a % of "net change in cash" is noise, not a lens — so the Size option is not
  // offered there, and a URL that asks for it lands back on the filed figures.
  const mode: StatementMode =
    rawMode === "size" && statement === "cf" ? "abs" : rawMode;
  // Participation banks (BDDK type 10003) file a different BRSA liabilities
  // layout — equity at XIV., not XVI. It decides the label catalog, the roman
  // ranges AND which banks the sector median may be taken over.
  const isParticipation = BANK_TYPE_BY_TICKER[ticker] === "10003";
  // Helper to build URLs that preserve the other params.
  const url = (overrides: Partial<{ view: string; kind: string; statement: string; mode: string }>) => {
    const params = new URLSearchParams({
      // Every statement control lives on the Financials tab — carry the tab, or
      // changing a lens would drop the reader back onto the Desk.
      tab: "financials",
      view: overrides.view ?? view,
      kind: overrides.kind ?? kind,
      statement: overrides.statement ?? statement,
      mode: overrides.mode ?? mode,
    });
    return `/banks/${ticker}?${params.toString()}`;
  };

  const allPeriods = Array.from(
    new Set(allPeriodMeta.filter((p) => p.kind === kind).map((p) => p.period)),
  ).sort().reverse();
  const periods = pickPeriods(allPeriods, view, 4);
  // YoY needs each displayed period's prior-year same quarter; TTM needs the
  // trailing quarters (incl. one before the earliest for de-cumulation), and
  // a YoY-of-TTM needs another year back. Query a generous trailing window —
  // 8 quarters before the oldest displayed period covers all of them — but
  // never ask for a period the bank doesn't have. Display still uses `periods`.
  const dispOrds = periods.map(ordOf).filter((o): o is number => o != null);
  const latestOrd = dispOrds.length ? Math.max(...dispOrds) : null;
  const floorOrd = (dispOrds.length ? Math.min(...dispOrds) : 0) - 8;
  const queryPeriods = allPeriods.filter((p) => {
    const o = ordOf(p);
    return o != null && o >= floorOrd && latestOrd != null && o <= latestOrd;
  });

  const [bsPivot, bsNames, plPivot, plRows, cfPivot, kapItems, profile, stages, validation, ownership, valuationBase, priceHistory, liveMap, heatmap, sharePanel, earnings, mrDetail, bankNews, cpiRaw, sectorShares] =
    await Promise.all([
      balanceSheetMultiPeriod(ticker, kind, queryPeriods),
      balanceSheetLineNames(ticker, kind, periods),
      profitLossMultiPeriod(ticker, kind, queryPeriods),
      statement === "is"
        ? profitLossRowsMultiPeriod(ticker, kind, periods)
        : Promise.resolve({}),
      cashFlowMultiPeriod(ticker, kind, queryPeriods),
      newsByTicker(ticker, 12),
      bankProfile(ticker),
      bankStagesLatest(ticker, kind),
      validationByPeriod(ticker, kind),
      bankOwnership(ticker),
      bistValuation(ticker, kind),
      bistPriceHistory(ticker, 8),
      liveQuotes([ticker]),
      // Fleet-wide derived metrics + market share (both cached); filtered to this
      // ticker below. heatmapPanel carries the margin engine, marketSharePanel the
      // competitive shares — same source of truth as /cross-bank.
      heatmapPanel(kind),
      marketSharePanel(kind),
      earningsByTicker(ticker, 24),
      bankMarketRiskDetail(kind, ticker),
      pressNewsByBank(ticker, 10),
      // The deflator — every "real terms" read on this page (real ROE, and the
      // Financials real-growth lens) comes off this one series.
      evdsSeries("TP.TUKFIY2025.GENEL", 10),
      // The peer column of the common-size lens. ONE cached D1 select per
      // (kind, latest period), shared by every bank page on that quarter — and
      // only issued when the balance sheet is actually being read common-size.
      statement === "bs" && mode === "size" && periods[0]
        ? sectorLineShares(kind, periods[0], isParticipation ? "participation" : "deposit")
        : Promise.resolve(null),
    ]);

  // Profitability & margins section inputs — this bank's rows, oldest→newest.
  const perfRows = heatmap
    .filter((r) => r.bank_ticker === ticker)
    .sort((a, b) => (a.period < b.period ? -1 : 1));
  const shareRows = bankShareSeries(sharePanel, ticker);
  const perfLatest = perfRows[perfRows.length - 1];
  const hasPerf =
    !!perfLatest &&
    [
      perfLatest.roe, perfLatest.nim, perfLatest.loan_yield, perfLatest.deposit_cost,
      perfLatest.spread, perfLatest.cost_of_risk, perfLatest.ppop_ratio, perfLatest.cost_income,
    ].some((v) => v != null);
  // Market-risk (CAMELS S) section inputs.
  const hasMarketRisk =
    (!!perfLatest &&
      (perfLatest.fx_nop != null ||
        perfLatest.repricing_gap_1y != null ||
        perfLatest.lcr != null)) ||
    mrDetail.hasData;

  // Overlay the latest (delayed) Yahoo price on the stored valuation; if the
  // live fetch returned nothing, keep the stored EOD figures untouched.
  const liveQ = liveMap.get(ticker);
  const valuation = valuationBase && liveQ ? applyLivePrice(valuationBase, liveQ) : valuationBase;

  // Rank-in-field (display-study Phase 4): this bank's place among the banks
  // reporting the same quarter, per metric — the "are we winning?" context every
  // number needs. Same panel as /cross-bank, so the ranks reconcile.
  const rankOf = (
    key: "total_assets" | "roe" | "nim" | "car" | "cet1" | "cost_income",
    higherIsBetter = true,
  ): { rank: number; n: number } | null => {
    if (!perfLatest) return null;
    const field = heatmap
      .filter((r) => r.period === perfLatest.period && r[key] != null)
      .sort((a, b) => (higherIsBetter ? (b[key] as number) - (a[key] as number) : (a[key] as number) - (b[key] as number)));
    const i = field.findIndex((r) => r.bank_ticker === ticker);
    return i === -1 ? null : { rank: i + 1, n: field.length };
  };
  const ord = (n: number) => {
    const s = ["th", "st", "nd", "rd"];
    const v = n % 100;
    return `${n}${s[(v - 20) % 10] ?? s[v] ?? s[0]}`;
  };
  // (The old rank chips are gone: the identity strip carries the assets rank and
  // "Where it stands" places every other metric on the field's distribution —
  // which is the same fact, said once, with the distance to the median attached.)
  const carRank = rankOf("car");
  const ciRank = rankOf("cost_income", false);

  // Per-bank Capital section (the audit's add_missing gap) — audited §4 buffers.
  const hasCapital = !!perfLatest && (perfLatest.car != null || perfLatest.cet1 != null);

  // ── The vitals band (DESIGN.md — the page's one signature element) ─────────
  // Type-only cells computed from `perfRows` (the same heatmapPanel rows the
  // Performance / Capital / Market-risk sections already read) — no new query.
  // Units: car / cet1 / lcr arrive in percentage POINTS from the audited §4
  // tables; roe / npl_ratio are FRACTIONS (×100 here); total_assets is in TL
  // thousands. Notes are computed facts only (buffers, q/q deltas, ranks).
  type VPt = { period: string; value: number };
  const perfSeries = (
    key: "total_assets" | "car" | "cet1" | "lcr" | "npl_ratio" | "roe",
    scale = 1,
  ): VPt[] =>
    perfRows
      .filter((r) => r[key] != null)
      .map((r) => ({ period: r.period, value: (r[key] as number) * scale }));
  const qoq = (s: VPt[]): number | null => {
    const cur = lastVal(s);
    const prev = valAgo(s, 1);
    return cur != null && prev != null ? cur - prev : null;
  };

  const taNow = perfLatest?.total_assets ?? null;
  // Big banks read in ₺trn, the long tail in ₺bn — same series, same scale as
  // the headline so the sparkline and the figure agree.
  const taTrn = taNow != null ? taNow / 1e9 : null;
  const taUseTrn = taTrn != null && taTrn >= 1;
  const assetsSeries = perfSeries("total_assets", taUseTrn ? 1 / 1e9 : 1 / 1e6);
  const taAgo = valAgo(assetsSeries, 4);
  const taLast = lastVal(assetsSeries);
  const taYoY = taLast != null && taAgo != null && taAgo > 0 ? (taLast / taAgo - 1) * 100 : null;
  const assetsRank = rankOf("total_assets");

  const carSeries = perfSeries("car");
  const carNow = perfLatest?.car ?? null;
  const carBuffer = carNow != null ? carNow - 12 : null;
  const carQoq = qoq(carSeries);

  const cet1Series = perfSeries("cet1");
  const cet1Now = perfLatest?.cet1 ?? null;
  const at1T2 = carNow != null && cet1Now != null ? carNow - cet1Now : null;

  const nplSeries = perfSeries("npl_ratio", 100);
  const nplNow = perfLatest?.npl_ratio != null ? perfLatest.npl_ratio * 100 : null;
  const nplQoq = qoq(nplSeries);

  const roeSeries = perfSeries("roe", 100);
  const roeNow = perfLatest?.roe != null ? perfLatest.roe * 100 : null;
  const roeRank = rankOf("roe");

  const lcrSeries = perfSeries("lcr");
  const lcrNow = perfLatest?.lcr ?? null;

  const vitalCells: (ReactElement | null)[] = [
    taNow != null ? (
      <Vital
        key="assets"
        label="Total assets"
        value={taUseTrn ? (taTrn as number).toFixed(2) : (taNow / 1e6).toFixed(0)}
        unit={taUseTrn ? "₺trn" : "₺bn"}
        series={assetsSeries.slice(-8)}
        format="raw"
        decimals={taUseTrn ? 2 : 0}
        note={
          <>
            {taYoY != null ? `${taYoY >= 0 ? "+" : "−"}${Math.abs(taYoY).toFixed(0)}% y/y` : "nominal, TL"}
            {assetsRank && ` · ${ord(assetsRank.rank)} of ${assetsRank.n} by assets`}
          </>
        }
      />
    ) : null,
    carNow != null ? (
      <Vital
        key="car"
        label="CAR (§4)"
        value={carNow.toFixed(1)}
        unit="%"
        series={carSeries.slice(-8)}
        decimals={1}
        note={
          carBuffer != null && carBuffer < 2 ? (
            <em className="not-italic font-semibold text-warning">
              only {carBuffer.toFixed(1)}pp over the 12% minimum
            </em>
          ) : (
            <>
              {carBuffer != null && `${carBuffer.toFixed(1)}pp over the 12% minimum`}
              {carQoq != null && ` · ${signedPp(carQoq, 1)} q/q`}
            </>
          )
        }
      />
    ) : null,
    cet1Now != null ? (
      <Vital
        key="cet1"
        label="CET1 (§4)"
        value={cet1Now.toFixed(1)}
        unit="%"
        series={cet1Series.slice(-8)}
        decimals={1}
        note={
          at1T2 != null
            ? `${at1T2.toFixed(1)}pp of the CAR is AT1 / Tier-2`
            : "core equity over risk-weighted assets"
        }
      />
    ) : null,
    nplNow != null ? (
      <Vital
        key="npl"
        label="NPL ratio"
        value={nplNow.toFixed(2)}
        unit="%"
        series={nplSeries.slice(-8)}
        decimals={2}
        note={
          nplQoq != null && nplQoq > 0.05 ? (
            <em className="not-italic font-semibold text-negative">
              {signedPp(nplQoq)} q/q · stage-3 / gross loans
            </em>
          ) : (
            <>
              {nplQoq != null && `${signedPp(nplQoq)} q/q · `}stage-3 / gross loans
            </>
          )
        }
      />
    ) : null,
    roeNow != null ? (
      <Vital
        key="roe"
        label="ROE (TTM)"
        value={roeNow.toFixed(1)}
        unit="%"
        series={roeSeries.slice(-8)}
        decimals={1}
        note={
          <>
            trailing 4 quarters ÷ avg equity
            {roeRank && ` · ${ord(roeRank.rank)} of ${roeRank.n}`}
          </>
        }
      />
    ) : null,
    lcrNow != null ? (
      <Vital
        key="lcr"
        label="LCR (§4)"
        value={lcrNow.toFixed(0)}
        unit="%"
        series={lcrSeries.slice(-8)}
        decimals={0}
        note={
          lcrNow < 100 ? (
            <em className="not-italic font-semibold text-warning">
              {(lcrNow - 100).toFixed(0)}pp under the 100% minimum
            </em>
          ) : (
            `+${(lcrNow - 100).toFixed(0)}pp over the 100% minimum`
          )
        }
      />
    ) : null,
  ];
  const vitals = vitalCells.filter((c): c is ReactElement => c !== null);
  const vitalCols: 3 | 4 | 5 | 6 =
    vitals.length >= 6 ? 6 : vitals.length === 5 ? 5 : vitals.length === 4 ? 4 : 3;

  // ── The brief (lib/bank-brief.ts) ─────────────────────────────────────────
  // All of it computed from `heatmap` (the fleet panel this page already
  // fetches), the balance-sheet pivot, and the CPI deflator. Nothing new is
  // queried; anything that doesn't resolve is simply not rendered.
  const cpi = cpiFromIndex(
    (cpiRaw as { period_date: string; value: number | null }[]).filter(
      (r): r is { period_date: string; value: number } => r.value != null,
    ),
  );
  const cpi12m = lastVal(cpi.avg12);
  const cpiYoY = lastVal(cpi.yoy);
  const realRoe = roeNow != null && cpi12m != null ? roeNow - cpi12m : null;

  /** '2026Q1' → 'Q1 2026'; used for the movers header. */
  const qLabel = (p: string | null): string => {
    const m = p ? /^(\d{4})Q([1-4])$/.exec(p) : null;
    return m ? `Q${m[2]} ${m[1]}` : "—";
  };
  const prevPeriod = perfRows[perfRows.length - 2]?.period ?? null;

  // Where it stands — this bank as a dot on each metric's field distribution.
  const peerStats = perfLatest
    ? PEER_FIELDS.map((spec) => ({ spec, stat: peerStat(heatmap, ticker, perfLatest.period, spec) }))
        .filter((x): x is { spec: (typeof PEER_FIELDS)[number]; stat: NonNullable<ReturnType<typeof peerStat>> } => x.stat != null)
    : [];

  // The engine — TTM margin ladder, or the gate that explains its absence.
  const gate = engineGate(perfRows);
  const pctOf = (v: number | null | undefined) => (v == null ? null : v * 100);
  const engineRows: EngineRow[] = gate.ready
    ? ([
        { label: "Loan yield", note: "interest on loans ÷ avg gross loans", value: pctOf(perfLatest?.loan_yield), unit: "%", kind: "in", scale: 30 },
        { label: "− Deposit cost", note: "interest on deposits ÷ avg deposits", value: pctOf(perfLatest?.deposit_cost), unit: "%", kind: "out", scale: 30 },
        { label: "= Spread", value: pctOf(perfLatest?.spread), unit: "pp", kind: "total", scale: 30 },
        { label: "Net interest margin", note: "on average assets", value: pctOf(perfLatest?.nim), unit: "%", kind: "sub", scale: 30 },
        { label: "Pre-provision profit / assets", value: pctOf(perfLatest?.ppop_ratio), unit: "%", kind: "sub", scale: 30 },
        { label: "− Cost of risk", value: pctOf(perfLatest?.cost_of_risk), unit: "%", kind: "sub", scale: 30 },
        { label: "Cost / income", note: ciRank ? `${ord(ciRank.rank)} of ${ciRank.n}` : undefined, value: pctOf(perfLatest?.cost_income), unit: "%", kind: "sub", scale: 100 },
        { label: "= ROE (TTM)", value: roeNow, unit: "%", kind: "total", scale: 50 },
        { label: "− Inflation", note: "12-month-average CPI", value: cpi12m, unit: "%", kind: "out", scale: 50 },
        { label: "= Real return on equity", value: realRoe, unit: "pp", kind: "total", scale: 50 },
      ].filter((r) => r.value != null) as EngineRow[])
    : [];

  // Flags — the registry; each prints the rule it fired on.
  const nplRises = risingStreak(nplSeries.map((p) => p.value));
  const nplMedian = peerStats.find((p) => p.spec.key === "npl_ratio")?.stat.median ?? null;
  const assetsQoqPct =
    taLast != null && valAgo(assetsSeries, 1) != null && (valAgo(assetsSeries, 1) as number) > 0
      ? (taLast / (valAgo(assetsSeries, 1) as number) - 1) * 100
      : null;
  const stage2Share =
    stages?.stage2_amount != null && stages.total_amount != null && stages.total_amount > 0
      ? (stages.stage2_amount / stages.total_amount) * 100
      : null;

  // Funding mix + productivity, from the balance sheet the Financials section
  // already pivots. Deposits first — the mix bar's hero.
  const latestBsPeriod = periods[0] ?? null;
  const liabAt = (hierarchy: string): number | null =>
    latestBsPeriod ? (bsPivot.get(`liabilities::${hierarchy}`)?.get(latestBsPeriod) ?? null) : null;
  const depositsTl = liabAt(isParticipation ? "I." : "I.");
  const equityTl = liabAt(isParticipation ? BS_EQUITY_HIERARCHY_PARTICIPATION : BS_EQUITY_HIERARCHY);
  const loansTl = latestBsPeriod ? (bsPivot.get("assets::2.1")?.get(latestBsPeriod) ?? null) : null;
  const ldr = depositsTl != null && depositsTl > 0 && loansTl != null ? (loansTl / depositsTl) * 100 : null;

  const fundingSlices: FundingSlice[] = taNow
    ? ([
        { label: "Deposits", value: depositsTl, className: "bg-data" },
        { label: "Money market", value: liabAt("III."), className: "bg-chart-2" },
        { label: "Borrowed", value: liabAt("II."), className: "bg-chart-3" },
        { label: "Issued", value: liabAt("IV."), className: "bg-chart-6" },
        { label: "Equity", value: equityTl, className: "bg-warning" },
      ].filter((s) => s.value != null && s.value > 0) as FundingSlice[])
    : [];
  if (fundingSlices.length > 0 && taNow) {
    const named = fundingSlices.reduce((a, s) => a + s.value, 0);
    if (taNow - named > 0) {
      fundingSlices.push({ label: "Other", value: taNow - named, className: "bg-muted-foreground/30" });
    }
  }

  const franchiseStats: Array<{ k: string; v: string; note?: string }> = [];
  if (ldr != null) {
    franchiseStats.push({ k: "Loan / deposit", v: `${ldr.toFixed(0)}%`, note: ldr < 100 ? "self-funded" : "leans on wholesale" });
  }
  if (profile?.branches_total && taNow) {
    franchiseStats.push({
      k: "Assets per branch",
      v: `₺${(taNow / 1e6 / profile.branches_total).toFixed(1)}bn`,
      note: `${profile.branches_total.toLocaleString()} branches`,
    });
  } else {
    franchiseStats.push({ k: "Assets per branch", v: "—", note: "branch count not filed" });
  }
  if (profile?.personnel && taNow) {
    franchiseStats.push({
      k: "Assets per employee",
      v: `₺${(taNow / 1e3 / profile.personnel).toFixed(0)}mn`,
      note: `${profile.personnel.toLocaleString()} staff`,
    });
  }
  if (taNow && equityTl && equityTl > 0) {
    franchiseStats.push({ k: "Leverage", v: `${(taNow / equityTl).toFixed(1)}×`, note: "assets ÷ equity" });
  }

  const stageSummary =
    stages && stages.total_amount ? (
      <table className="w-full border-collapse">
        <tbody>
          {(
            [
              ["Stage 1 — performing", stages.stage1_amount, stages.stage1_ecl],
              ["Stage 2 — watchlist", stages.stage2_amount, stages.stage2_ecl],
              ["Stage 3 — NPL", stages.stage3_amount, stages.stage3_ecl],
            ] as Array<[string, number | null, number | null]>
          ).map(([label, amt, ecl]) => (
            <tr key={label}>
              <td className="border-b border-hair py-1.5 text-[12px] text-foreground">{label}</td>
              <td className="border-b border-hair py-1.5 text-right font-mono text-[12px] font-semibold tabular-nums text-foreground">
                {amt != null ? `₺${(amt / 1e6).toFixed(amt / 1e6 >= 100 ? 0 : 1)}bn` : "—"}
              </td>
              <td className="border-b border-hair py-1.5 pl-3 text-right font-mono text-[10.5px] text-faint">
                {amt != null && stages.total_amount
                  ? `${((amt / stages.total_amount) * 100).toFixed(1)}%`
                  : "—"}
                {ecl != null && amt != null && amt > 0 ? ` · ${((ecl / amt) * 100).toFixed(1)}% cover` : ""}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    ) : undefined;

  const flags = bankFlags({
    car: carNow,
    carQoq,
    carRank,
    assetsQoqPct,
    roe: roeNow,
    cpi12m,
    npl: nplNow,
    nplRises,
    nplMedian,
    stage2Share,
    costIncome: pctOf(perfLatest?.cost_income),
    filings: gate.filings,
    lcr: lcrNow,
    ldr,
  });

  const spreadNow = pctOf(perfLatest?.spread);
  const spreadPrev = pctOf(perfRows[perfRows.length - 2]?.spread);
  const moverRows: MoverRow[] = (
    [
      carNow != null && carQoq != null
        ? {
            label: "Capital adequacy",
            note: assetsQoqPct != null ? `while assets grew ${assetsQoqPct.toFixed(1)}% q/q` : undefined,
            prev: carNow - carQoq,
            curr: carNow,
            fmt: (v: number) => `${v.toFixed(1)}%`,
            deltaDecimals: 2,
            good: "up" as const,
          }
        : null,
      spreadNow != null && spreadPrev != null
        ? { label: "Loan–deposit spread", prev: spreadPrev, curr: spreadNow, good: "up" as const }
        : null,
      nplNow != null && nplQoq != null
        ? {
            label: "NPL ratio",
            note: nplRises >= 2 ? `${nplRises} consecutive rises` : undefined,
            prev: nplNow - nplQoq,
            curr: nplNow,
            good: "down" as const,
          }
        : null,
      roeNow != null && pctOf(perfRows[perfRows.length - 2]?.roe) != null
        ? {
            label: "ROE (TTM)",
            prev: pctOf(perfRows[perfRows.length - 2]?.roe) as number,
            curr: roeNow,
            fmt: (v: number) => `${v.toFixed(1)}%`,
            deltaDecimals: 1,
            good: "up" as const,
          }
        : null,
    ].filter(Boolean) as MoverRow[]
  ).slice(0, 5);

  const identityItems: Array<{ k: string; v: ReactElement | string }> = [];
  if (assetsRank) identityItems.push({ k: "Rank", v: `#${assetsRank.rank} of ${assetsRank.n} by assets` });
  if (profile?.branches_total) identityItems.push({ k: "Branches", v: profile.branches_total.toLocaleString() });
  if (profile?.personnel) identityItems.push({ k: "Staff", v: profile.personnel.toLocaleString() });
  // Largest disclosed shareholder — the same rows the Ownership section reads
  // (item = "shareholder", minus the "Toplam" total line).
  const topHolder = ownership
    .filter((r) => r.item === "shareholder" && !/^toplam$/i.test((r.holder ?? "").trim()))
    .sort((a, b) => (b.ratio_pct ?? 0) - (a.ratio_pct ?? 0))[0];
  identityItems.push({
    k: "Owner",
    v: topHolder?.holder
      ? `${topHolder.holder}${topHolder.ratio_pct != null ? ` ${topHolder.ratio_pct.toFixed(1)}%` : ""}`
      : "— not filed to KAP",
  });
  if (valuation?.pb != null) identityItems.push({ k: "Market", v: `BIST ${ticker} · P/B ${valuation.pb.toFixed(2)}×` });
  void cpiYoY;

  // ⚠ on a period column = that quarter's extraction failed one or more
  // internal-sum identity checks (TL+FC=Total, parent=Σchildren, TOTAL=Σromans,
  // assets=liabilities+equity) — treat its figures with care. Scoped to the
  // statement(s) the DISPLAYED table shows: a footnote failure (stages, equity,
  // cash-flow) must not flag the Balance Sheet if its own figures are clean.
  const WARN_STATEMENTS: Record<string, string[]> = {
    bs: ["assets", "liabilities", "cross"],
    is: ["profit_loss"],
    cf: ["cash_flow"],
  };
  const STATEMENT_LABEL: Record<string, string> = {
    bs: "balance sheet",
    is: "income statement",
    cf: "cash flow statement",
  };
  const periodWarning = (p: string): string | null => {
    const byStmt = validation.get(p);
    if (!byStmt) return null;
    let failed = 0;
    let passed = 0;
    for (const s of WARN_STATEMENTS[statement] ?? []) {
      const c = byStmt.get(s);
      if (c) {
        failed += c.checks_failed;
        passed += c.checks_passed;
      }
    }
    if (failed === 0) return null;
    const label = STATEMENT_LABEL[statement] ?? statement;
    return `${failed} of ${failed + passed} internal-sum checks failed for this quarter's ${label} extraction — figures may be incomplete or misread.`;
  };
  const anyWarning = periods.some((p) => periodWarning(p) !== null);

  // ── The lens ──────────────────────────────────────────────────────────────
  // Four readings of the same filed rows, all off the same URL param so every one
  // of them is server-rendered and shareable:
  //   abs  — the filed figure (TL thousands)
  //   yoy  — nominal % vs the same quarter a year earlier
  //   real — that nominal y/y DEFLATED by CPI, plus a verdict word
  //   size — common-size: % of total assets (BS) / of interest income (IS), and
  //          on the balance sheet the SECTOR MEDIAN share and the gap to it
  //
  // A leading TTM column (trailing-twelve-month) is shown for the income statement
  // + cash flow in quarterly view only (at Q4 annual view, TTM equals the Q4 YTD
  // column). P&L and cash flow are YTD-cumulative within the year, so TTM
  // de-cumulates; the balance sheet is point-in-time (no TTM).
  const isReal = mode === "real";
  const isSize = mode === "size";
  const showTtm = statement !== "bs" && view === "quarterly" && !isReal;
  const showPeers = isSize && statement === "bs" && sectorShares != null;
  const latestPeriod = periods[0] ?? null;

  // The deflator, matched to the quarter the table is read at.
  const cpiPick = cpiForPeriod(cpi.yoy, latestPeriod);

  // Common-size denominators, one per rendered column: total assets for the
  // balance sheet, interest income for the income statement. Same roman-total
  // arithmetic as the synthetic "Total Assets" row, so a share and the row it
  // divides agree by construction.
  const denomSeries: PeriodSeries =
    statement === "bs"
      ? sumSeries(bsPivot, BS_ASSET_ROMAN_HIERARCHIES, "assets")
      : (plPivot.get("I.") ?? new Map());

  const byOrdOf = (series: PeriodSeries): Map<number, number> => {
    const byOrd = new Map<number, number>();
    for (const [p, v] of series) {
      const o = ordOf(p);
      if (o != null && v != null) byOrd.set(o, v);
    }
    return byOrd;
  };
  // Absolute value per rendered column (TTM first when applicable). Deduction
  // lines are carried as positive magnitudes upstream — the accounting sign is
  // applied HERE, on the displayed figure, never to a growth rate.
  const colsAbs = (series: PeriodSeries, contra: boolean): (number | null)[] => {
    const byOrd = byOrdOf(series);
    const signed = (v: number | null): number | null => (v == null ? null : contra ? -v : v);
    const row = periods.map((p) => signed(series.get(p) ?? null));
    if (!showTtm || latestOrd == null) return row;
    return [signed(ttmEndingAt(byOrd, latestOrd)), ...row];
  };
  // Nominal y/y per rendered column — computed on the MAGNITUDE, so a rising
  // expense reads +%.
  const colsYoy = (series: PeriodSeries): (number | null)[] => {
    const byOrd = byOrdOf(series);
    const row = periods.map((p) => {
      const o = ordOf(p);
      return o == null ? null : yoyPct(byOrd.get(o) ?? null, byOrd.get(o - 4) ?? null);
    });
    if (!showTtm || latestOrd == null) return row;
    return [yoyPct(ttmEndingAt(byOrd, latestOrd), ttmEndingAt(byOrd, latestOrd - 4)), ...row];
  };
  const denomCols = colsAbs(denomSeries, false);
  const colsSize = (series: PeriodSeries, contra: boolean): (number | null)[] =>
    colsAbs(series, contra).map((v, i) => {
      const d = denomCols[i];
      return v == null || d == null || d === 0 ? null : (v / d) * 100;
    });

  const numCells = (
    vals: (number | null)[],
    fmt: (v: number | null | undefined) => string,
  ): Cell[] => vals.map((v) => ({ text: fmt(v) }));

  /** The sector-median + gap pair, in the SAME display sign as the bank's own
   *  share (the peer map carries contra lines as magnitudes, as the pivot does).
   *  "--" whenever the peer set doesn't hold the line — never a fabricated 0. */
  const peerCells = (key: string | null, own: number | null, contra: boolean): Cell[] => {
    if (!showPeers) return [];
    const raw = key == null ? undefined : sectorShares!.shares.get(key);
    if (raw == null) return [{ text: "--", tone: "muted" }, { text: "--", tone: "muted" }];
    const med = contra ? -raw : raw;
    if (own == null) return [{ text: `${med.toFixed(1)}%` }, { text: "--", tone: "muted" }];
    const gap = own - med;
    return [
      { text: `${med.toFixed(1)}%` },
      {
        text: `${gap >= 0 ? "+" : "−"}${Math.abs(gap).toFixed(1)}`,
        tone: Math.abs(gap) >= 5 ? "warn" : undefined,
      },
    ];
  };

  /** The real lens: one row = nominal y/y | CPI y/y | real y/y | verdict, all at
   *  the latest displayed period. `realGrowth` DIVIDES — (1+n)/(1+cpi)−1. */
  const realCells = (series: PeriodSeries): Cell[] => {
    const r = realRead(series, latestPeriod, cpiPick?.value ?? null);
    const tone = r.real == null ? undefined : r.real > 3 ? "pos" : r.real < -3 ? "neg" : "warn";
    return [
      { text: fmtPct(r.nominal) },
      { text: r.cpi == null ? "--" : `${PF.format(r.cpi)}%`, tone: "muted" },
      { text: fmtPct(r.real), tone },
      { text: r.verdict ?? "--", tone },
    ];
  };

  /** Every lens, for one catalog line. Pass `peerKey: null` to withhold the peer
   *  median — used for the two lines whose BRSA code is genuinely ambiguous
   *  fleet-wide (asset 2.3 is Factoring for some banks, Securities at Amortized
   *  Cost for others, and the banks that file it with a blank item_name can't be
   *  told apart), so a median across them would compare unlike lines. */
  const cellsForLine = (
    line: StandardLine,
    pivot: Map<string, PeriodSeries>,
    stmt: string,
    peerKey?: string | null,
  ): Cell[] => {
    const raw = lineSeries(pivot, line, stmt);
    // Fold contra lines to magnitude first — BRSA banks file them with either
    // sign — so the display sign is uniform fleet-wide.
    const series: PeriodSeries = line.contra
      ? new Map([...raw].map(([p, v]) => [p, v == null ? null : Math.abs(v)] as [string, number | null]))
      : raw;
    if (isReal) return realCells(series);
    if (isSize) {
      const shares = colsSize(series, !!line.contra);
      const key = peerKey === undefined ? `${stmt}::${line.hierarchy}` : peerKey;
      return [...numCells(shares, fmtShare), ...peerCells(key, shares[0] ?? null, !!line.contra)];
    }
    if (mode === "yoy") return numCells(colsYoy(series), fmtPct);
    return numCells(colsAbs(series, !!line.contra), fmtTl);
  };
  /** The lines whose peer median is withheld (see `cellsForLine`). */
  const AMBIGUOUS_PEER_LINES = new Set(["factoring_recv", "securities_amc"]);

  /** A synthetic subtotal row (Total Assets / Total Liabilities / Total L&E). */
  const cellsForTotal = (series: PeriodSeries, peerKey: string): Cell[] => {
    if (isReal) return realCells(series);
    if (isSize) {
      const shares = colsSize(series, false);
      return [...numCells(shares, fmtShare), ...peerCells(peerKey, shares[0] ?? null, false)];
    }
    if (mode === "yoy") return numCells(colsYoy(series), fmtPct);
    return numCells(colsAbs(series, false), fmtTl);
  };

  const colCount = isReal
    ? 4
    : periods.length + (showTtm ? 1 : 0) + (showPeers ? 2 : 0);
  const blankCells = (): Cell[] => Array(colCount).fill({ text: "--" });
  const unitLabel =
    mode === "yoy"
      ? "Year-over-year % change"
      : isReal
        ? "Year-over-year %, nominal and deflated"
        : isSize
          ? statement === "bs"
            ? "% of total assets"
            : "% of interest income"
          : "All numbers in TL thousands";

  // Shared table header row. The lens decides the columns: period-end dates
  // (abs / yoy / size), plus the peer pair on a common-size balance sheet, or the
  // nominal→CPI→real→verdict quartet for one quarter on the real lens.
  const TH = "py-2 pl-4 text-right font-mono text-[8.5px] font-normal uppercase tracking-[0.07em] text-faint whitespace-nowrap";
  const periodHeaderRow = (
    <tr className="border-b border-foreground">
      <th className={`${TH} pl-0 text-left`}>Breakdown</th>
      {isReal ? (
        <>
          <th className={TH}>Nominal y/y</th>
          <th className={TH}>CPI y/y</th>
          <th className={`${TH} text-foreground`}>Real y/y</th>
          <th className={TH}>Verdict</th>
        </>
      ) : (
        <>
          {showTtm && (
            <th className={TH}>TTM</th>
          )}
          {periods.map((p) => (
            <th key={p} className={TH}>
              {periodToDate(p)}
              {periodWarning(p) && (
                <span title={periodWarning(p)!} className="ml-1 cursor-help text-amber-600">⚠</span>
              )}
            </th>
          ))}
          {showPeers && (
            <>
              <th className={TH}>Sector median</th>
              <th className={TH}>Gap (pp)</th>
            </>
          )}
        </>
      )}
    </tr>
  );
  // Cash flow renders from the CF_LINES catalog (codes are consistent across
  // banks). True only if some displayed period actually has CF data — else the
  // CF branch shows a "not available" note instead of an all-"--" table.
  const hasCfData = periods.some((p) => {
    for (const m of cfPivot.values()) if (m.get(p) != null) return true;
    return false;
  });

  // Participation banks (BDDK type 10003) file a different BRSA liabilities
  // layout — equity at XIV., not XVI., with fewer roman items — so they need a
  // separate label catalog + roman ranges. Assets and the income statement
  // share the deposit-bank hierarchy, so only liabilities switch.
  const liabLines = isParticipation ? BS_LIAB_LINES_PARTICIPATION : BS_LIAB_LINES;
  const liabRomans = isParticipation
    ? BS_LIAB_ROMAN_HIERARCHIES_PARTICIPATION
    : BS_LIAB_ROMAN_HIERARCHIES;
  const equityHierarchy = isParticipation
    ? BS_EQUITY_HIERARCHY_PARTICIPATION
    : BS_EQUITY_HIERARCHY;
  // The equity roman + its dotted sub-items, used to split the catalog.
  const equityRomanPrefix = isParticipation ? "XIV" : "XVI";
  const equityDotPrefix = isParticipation ? "14." : "16.";

  // Computed totals. Sum BRSA Roman-numeral parents — never sub-items
  // (e.g. "2.1 Loans" is inside "II. Amortized Cost"; including both would
  // double-count). Equity is summed separately; Total L&E folds it back in.
  const totalAssetsSeries = sumSeries(bsPivot, BS_ASSET_ROMAN_HIERARCHIES, "assets");
  const totalLiabSeries = sumSeries(bsPivot, liabRomans, "liabilities");
  const totalLeSeries = sumSeries(bsPivot, [...liabRomans, equityHierarchy], "liabilities");
  const totalAssets = cellsForTotal(totalAssetsSeries, SECTOR_TOTAL_ASSETS_KEY);
  const totalLiab = cellsForTotal(totalLiabSeries, SECTOR_TOTAL_LIABILITIES_KEY);
  const totalLE = cellsForTotal(totalLeSeries, SECTOR_TOTAL_LE_KEY);

  // Split the liability catalog at the equity boundary so the synthetic
  // "Total Liabilities" subtotal slots in *before* the equity block.
  const liabPreEquity = liabLines.filter(
    (l) => !l.hierarchy.startsWith(equityRomanPrefix) && !l.hierarchy.startsWith(equityDotPrefix),
  );
  const equityBlock = liabLines.filter(
    (l) => l.hierarchy.startsWith(equityRomanPrefix) || l.hierarchy.startsWith(equityDotPrefix),
  );

  // ── The shape (balance sheet) ─────────────────────────────────────────────
  // What this bank OWNS and what FUNDS it, as two composition columns — the read
  // the table can't give: each roman parent's share of total assets and its REAL
  // growth. The roman parents partition the balance sheet exactly, so the columns
  // close to 100% (anything unaccounted lands in an explicit "Other" row); "of
  // which Loans" is nested inside the amortized-cost parent and NOT re-counted.
  const taLatest = latestPeriod ? (totalAssetsSeries.get(latestPeriod) ?? null) : null;
  const assetLabelOf = (h: string) =>
    BS_ASSET_LINES.find((l) => l.hierarchy === h)?.label ?? h;
  const liabLabelOf = (h: string) => liabLines.find((l) => l.hierarchy === h)?.label ?? h;
  const assetCompLines: CompLine[] = [
    ...BS_ASSET_ROMAN_HIERARCHIES.map((h) => ({ hierarchy: h, label: assetLabelOf(h) })),
    { hierarchy: "2.1", label: "Loans", sub: true },
  ];
  const fundingCompLines: CompLine[] = [
    ...liabRomans.map((h) => ({ hierarchy: h, label: liabLabelOf(h) })),
    { hierarchy: equityHierarchy, label: "Shareholders' Equity" },
  ];
  const shapeCpi = cpiPick?.value ?? null;
  const assetComp =
    latestPeriod && taLatest
      ? compositionRows(bsPivot, "assets", assetCompLines, latestPeriod, taLatest, shapeCpi)
      : [];
  const fundingComp =
    latestPeriod && taLatest
      ? compositionRows(bsPivot, "liabilities", fundingCompLines, latestPeriod, taLatest, shapeCpi)
      : [];
  const shapeLead = balanceSheetLead(
    realRead(totalAssetsSeries, latestPeriod, shapeCpi),
    realRead(bsPivot.get("assets::2.1") ?? new Map(), latestPeriod, shapeCpi),
    realRead(bsPivot.get("liabilities::I.") ?? new Map(), latestPeriod, shapeCpi),
  );
  const cpiNote = cpiPick
    ? cpiPick.matched
      ? `CPI y/y read at the quarter end (${monthLabel(cpiPick.month)}): ${cpiPick.value.toFixed(1)}% · real = (1+nominal)/(1+CPI)−1, a deflation, not a subtraction`
      : `CPI y/y taken from the latest print (${monthLabel(cpiPick.month)}): ${cpiPick.value.toFixed(1)}% — the series does not yet reach ${latestPeriod ?? "this quarter"} · real = (1+nominal)/(1+CPI)−1`
    : "CPI is not available for this quarter — real growth is left blank rather than guessed";

  // In-page jump-nav: only list groups that actually render (the ownership
  // group is conditional on having a KAP form), so every anchor resolves.
  const hasOwnership = ownership.length > 0;
  const hasBankNews = bankNews.length > 0;
  // Tabs with nothing to say for this bank are not offered at all.
  const hiddenTabs: BankTab[] = [
    ...(hasMarketRisk || hasCapital ? [] : (["risk"] as BankTab[])),
    ...(hasOwnership ? [] : (["ownership"] as BankTab[])),
    ...(hasBankNews || earnings.length > 0 || kapItems.length > 0 ? [] : (["news"] as BankTab[])),
  ];
  // What each tab holds — printed on the Desk as the way in, so nothing the old
  // one-page layout carried is now hidden behind an unlabelled tab.
  const tabIndex: Array<{ id: BankTab; h: string; p: string; go: string }> = [
    {
      id: "financials",
      h: "Financials",
      p: "Balance sheet · income statement · cash flow — as filed, y/y, real (CPI-deflated) or common-size against the sector. Plus the shape: composition, the profit waterfall and the interest flow.",
      go: "3 statements · 4 lenses",
    },
    ...(hasMarketRisk || hasCapital
      ? [{
          id: "risk" as BankTab,
          h: "Risk & Capital",
          p: `FX net open position and the ≤1y repricing gap from the §4 footnotes${hasCapital ? ", with the audited capital stack and its buffer over the 12% minimum" : ""}.`,
          go: "§4 footnotes",
        }]
      : []),
    ...(hasOwnership
      ? [{ id: "ownership" as BankTab, h: "Ownership", p: "Shareholders ≥5% and the §7 subsidiary grid, from the KAP Genel Bilgi Formu — re-scraped weekly.", go: "KAP" }]
      : []),
    ...(hasBankNews || earnings.length > 0 || kapItems.length > 0
      ? [{
          id: "news" as BankTab,
          h: "News & Filings",
          p: `Press coverage tagged to this bank, quarterly results decks and recent KAP disclosures.`,
          go: `${bankNews.length + earnings.length + kapItems.length} items`,
        }]
      : []),
  ];
  const finQuery = `statement=${statement}&mode=${mode}&view=${view}&kind=${kind}`;

  return (
    <main className="mx-auto w-full max-w-[1200px] px-4 py-8 sm:px-6 lg:px-8">
      {/* Sticky page chrome (lg+): pin the header and the in-page jump-nav as one
          stacked group — header on top, nav directly below — so neither overlaps
          the other. The header opts out of its own sticky (sticky={false}) and is
          pinned by this wrapper instead; on mobile the nav self-sticks at top-14. */}
      <div className="lg:sticky lg:top-0 lg:z-30">
        <PageHeader
          eyebrow={ticker}
          title={
            <span className="inline-flex items-center gap-3">
              <BankLogo ticker={ticker} name={bankDisplayName(ticker)} height={30} />
              {bankDisplayName(ticker)}
            </span>
          }
          description="Standardized per-bank financials from quarterly BRSA reports"
          rangeSelector
          dataThrough={allPeriods[0]}
          sticky={false}
        >
          <Link href="/banks" className="text-sm text-muted-foreground hover:text-foreground">
            ← All banks
          </Link>
        </PageHeader>

        <BankTabs ticker={ticker} active={tab} hide={hiddenTabs} query={finQuery} />
      </div>

      {/* ══ THE DESK ═══════════════════════════════════════════════════════
          The brief: who this bank is, where it stands in the field, what moved,
          what the rules say, what the balance sheet earns and what it is made
          of. It REPLACES the old Overview / Performance / Capital cards — those
          stated the same numbers a second time, which is what made this page
          seven screens long. */}
      {tab === "desk" && (
      <>
      {identityItems.length > 0 && <Identity items={identityItems} />}

      {vitals.length >= 3 && (
        <>
          <SecHead
            title="The vitals"
            meta="audited quarterly · this bank"
            className="mb-2.5 mt-6"
          />
          <Vitals cols={vitalCols}>{vitals}</Vitals>
        </>
      )}

      {/* ── The brief ─────────────────────────────────────────────────────
          Where this bank sits in the field, what moved, what the rules say,
          what the balance sheet earns and what it is made of. Every sentence
          is computed in lib/bank-brief.ts; a section whose inputs don't
          resolve is omitted, and the engine states why. */}
      <WhereItStands stats={peerStats} ctx={{ buffer: carBuffer, realRoe }} />

      <MoversAndFlags
        from={qLabel(prevPeriod)}
        to={qLabel(perfLatest?.period ?? null)}
        movers={moverRows}
        flags={flags}
      />

      {(gate.ready || gate.reason) && (
        <Engine
          gate={gate}
          rows={engineRows}
          chart={hasPerf ? <MarginBridgeChart rows={perfRows} /> : undefined}
        />
      )}

      {fundingSlices.length > 0 && taNow != null && (
        <Franchise
          assets={taNow}
          funding={fundingSlices}
          stats={franchiseStats}
          stages={stageSummary}
          chart={shareRows.length > 1 ? <MarketShareChart rows={shareRows} /> : undefined}
        />
      )}

      {/* Market & valuation — the 11 listed banks only. The rest of the old
          Overview card (branches, staff, stages, rank chips) is now stated once:
          in the identity strip, the vitals and the franchise. */}
      {valuation && (
        <section className="mt-8">
          <SecHead
            title="What the market pays"
            meta={`BIST ${ticker} · ${valuation.isLive && valuation.asOf ? formatAsOf(valuation.asOf) : `close ${valuation.period_date}`}`}
            className="mb-2.5"
          />
          <div className="border-t-2 border-foreground">
            <div className="grid gap-6 py-3 lg:grid-cols-[5fr_7fr]">
              <div>
                <div className="flex flex-wrap items-baseline gap-x-3">
                  <span className="font-mono text-3xl font-semibold tracking-tight text-foreground">
                    ₺{nfmt(valuation.price, 2)}
                  </span>
                  {valuation.changePct1y != null && (
                    <span
                      className={`font-mono text-sm font-semibold ${
                        valuation.changePct1y >= 0 ? "text-positive" : "text-negative"
                      }`}
                    >
                      {valuation.changePct1y >= 0 ? "+" : ""}
                      {nfmt(valuation.changePct1y, 1)}% · 1y
                    </span>
                  )}
                </div>
                <div className="mt-3 grid grid-cols-4 gap-3 border-t border-hair pt-3">
                  {(
                    [
                      ["Mkt cap", valuation.marketCap != null ? fmtMarketCap(valuation.marketCap) : "—"],
                      ["P/B", valuation.pb != null ? `${nfmt(valuation.pb, 2)}×` : "—"],
                      ["P/E", valuation.pe != null ? `${nfmt(valuation.pe, 1)}×` : "—"],
                      ["Div yield", valuation.dividendYield != null ? `${nfmt(valuation.dividendYield * 100, 2)}%` : "—"],
                    ] as const
                  ).map(([label, value]) => (
                    <div key={label}>
                      <div className="text-[10.5px] text-muted-foreground">{label}</div>
                      <div className="font-mono text-sm font-semibold tabular-nums text-foreground">{value}</div>
                    </div>
                  ))}
                </div>
                {valuation.fundamentalsPeriod && (
                  <p className="mt-2 font-mono text-[9px] uppercase tracking-[0.05em] text-faint">
                    P/B &amp; P/E vs {valuation.fundamentalsPeriod} audited figures · daily close
                  </p>
                )}
              </div>
              {priceHistory.length > 0 && (
                <TimeSeriesChart
                  bare
                  series={{ [`${ticker} share price`]: priceHistory }}
                  yFormat="fx"
                  decimals={2}
                  height={170}
                />
              )}
            </div>
          </div>
        </section>
      )}

      {/* The way in to the other tabs — named with what they hold, so nothing the
          old one-page layout carried is now hidden behind an unlabelled tab. */}
      <section className="mt-9 border-t-2 border-foreground pt-2">
        <div className="flex items-baseline gap-2.5">
          <h2 className="text-[14.5px] font-bold text-foreground">In depth</h2>
          <span className="ml-auto font-mono text-[8.5px] uppercase tracking-[0.07em] text-faint">
            {tabIndex.length} more {tabIndex.length === 1 ? "view" : "views"} — same data, one click
          </span>
        </div>
        {tabIndex.map((d) => (
          <Link
            key={d.id}
            href={d.id === "financials" ? `/banks/${ticker}?tab=financials&${finQuery}` : `/banks/${ticker}?tab=${d.id}`}
            className="grid items-baseline gap-4 border-b border-hair py-2.5 lg:grid-cols-[minmax(110px,2fr)_minmax(200px,7fr)_auto]"
          >
            <h4 className="text-[12.5px] font-semibold text-primary">{d.h}</h4>
            <p className="text-[11.5px] leading-snug text-muted-foreground">{d.p}</p>
            <span className="whitespace-nowrap font-mono text-[9.5px] text-faint">{d.go}</span>
          </Link>
        ))}
      </section>
      </>
      )}

      {/* ── Market risk (CAMELS S) ────────────────────────────────────────
          FX net open position + interest-rate repricing gap from §4 footnotes. */}
      {tab === "risk" && hasMarketRisk && (
        <div className="mb-8 mt-6">
          <MarketRiskSection rows={perfRows} detail={mrDetail} />
        </div>
      )}

      {/* ── Capital (audited §4) ──────────────────────────────────────────
          Per-bank solvency buffers — the audit's add_missing gap. LCR lives in
          the Market Risk tiles above; this block is the capital side. */}
      {tab === "risk" && hasCapital && perfLatest && (
        <div className="mb-8">
          <Section
            title="Capital"
            description={`Audited §4 capital ratios · ${perfLatest.period} · buffer vs the 12% regulatory minimum (incl. buffers). Ranks are among banks reporting the quarter.`}
            contentClassName=""
          >
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              <Stat
                label="CAR"
                value={perfLatest.car != null ? `${perfLatest.car.toFixed(1)}%` : "—"}
                hint={rankOf("car") ? `${ord(rankOf("car")!.rank)} of ${rankOf("car")!.n}` : undefined}
                tone={
                  perfLatest.car == null
                    ? "neutral"
                    : perfLatest.car - 12 < 2
                      ? "warning"
                      : perfLatest.car - 12 >= 4
                        ? "positive"
                        : "neutral"
                }
              />
              <Stat
                label="Buffer over minimum"
                value={perfLatest.car != null ? `${(perfLatest.car - 12).toFixed(1)}pp` : "—"}
                hint="CAR − 12%"
              />
              <Stat
                label="CET1"
                value={perfLatest.cet1 != null ? `${perfLatest.cet1.toFixed(1)}%` : "—"}
                hint={rankOf("cet1") ? `${ord(rankOf("cet1")!.rank)} of ${rankOf("cet1")!.n}` : undefined}
              />
              <Stat
                label="AT1 / Tier-2 reliance"
                value={
                  perfLatest.car != null && perfLatest.cet1 != null
                    ? `${(perfLatest.car - perfLatest.cet1).toFixed(1)}pp`
                    : "—"
                }
                hint="CAR − CET1"
              />
            </div>
          </Section>
        </div>
      )}

      {/* ── Financials ────────────────────────────────────────────────────
          The page's core: the SHAPE layer (composition / waterfall / flow) above
          the standardized BS / IS / CF tables, with the lens + statement controls. */}
      {tab === "financials" && (
      <div className="mb-8 mt-6">
        <Section title="Financials" contentClassName="">
          {/* The controls, ABOVE the shape they drive — and grouped by scope, because
              they do not all reach the same distance. Statement, basis and periods
              re-read the filings, so they change the shape AND the table. The lens
              is a way of *reading* the same rows: it now drives the composition's
              trailing column too, so no control is inert on what sits above it. */}
          <div className="mb-4 flex flex-wrap items-end gap-x-6 gap-y-3 border-b border-border pb-3">
            <ControlGroup label="Statement">
              {(["bs", "is", "cf"] as const).map((s2) => (
                <Toggle key={s2} href={url({ statement: s2 })} on={s2 === statement}>
                  {s2 === "bs" ? "Balance sheet" : s2 === "is" ? "Income statement" : "Cash flow"}
                </Toggle>
              ))}
            </ControlGroup>

            <ControlGroup label="Lens">
              {(statement === "cf"
                ? (["abs", "yoy", "real"] as const)
                : (["abs", "yoy", "real", "size"] as const)
              ).map((m) => (
                <Toggle key={m} href={url({ mode: m })} on={m === mode} title={LENS_HINT[m]}>
                  {LENS_LABEL[m]}
                </Toggle>
              ))}
            </ControlGroup>

            <ControlGroup label="Periods">
              {(["quarterly", "annual"] as const).map((v) => (
                <Toggle key={v} href={url({ view: v })} on={v === view}>
                  {v === "annual" ? "Annual" : "Quarterly"}
                </Toggle>
              ))}
            </ControlGroup>

            <ControlGroup label="Basis">
              {(["unconsolidated", "consolidated"] as const).map((k) => (
                <Toggle key={k} href={url({ kind: k })} on={k === kind}>
                  {k === "unconsolidated" ? "Bank-only" : "Consolidated"}
                </Toggle>
              ))}
            </ControlGroup>
          </div>

          {/* The shape — what the statement IS, before what it says. Balance sheet:
              two composition columns. Income statement: the waterfall, or the
              interest flow. Cash flow has no shape layer — just the table. */}
          {statement === "bs" && (
            <BsShape
              assets={assetComp}
              funding={fundingComp}
              lens={mode}
              lead={shapeLead}
              meta={`${latestPeriod ?? "—"} · share of total assets · real y/y`}
              footnote={cpiNote}
            />
          )}
          {statement === "is" && (
            <>
              <IncomeShape rowsByPeriod={plRows} periods={periods} />
              {mode !== "abs" && (
                <p className="mt-1 font-mono text-[8.5px] uppercase tracking-[0.05em] text-faint">
                  The bridge above reads the filed quarter in ₺ — the {LENS_LABEL[mode].toLowerCase()} lens applies to the statement below.
                </p>
              )}
            </>
          )}

          {/* Balance Sheet — single table, assets and liabilities together */}
          {statement === "bs" && (
          <section className="group mb-6">
            <div className="flex items-baseline justify-between gap-3 pb-2">
              <h2 className="text-[13.5px] font-bold text-foreground">Balance Sheet</h2>
              <div className="flex items-center gap-2">
                <span className="font-mono text-[8.5px] uppercase tracking-[0.07em] text-faint">{unitLabel}</span>
                <CopyTableButton />
              </div>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full border-collapse">
                <thead className="text-muted-foreground">{periodHeaderRow}</thead>
                <tbody>
                  <GroupRow label="Assets — what it owns" span={colCount + 1} />
                  {(() => {
                    // Standard, uniform layout for every bank. Asset code 2.3 holds
                    // Factoring (deposit layout) OR Securities at Amortized Cost
                    // (participation / Garanti); 2.4 holds Other OR the ECL (which
                    // audit.ts remaps to 2.ecl). Keep BOTH the Factoring and Securities
                    // rows always present — the one that doesn't apply to this bank
                    // renders blank rather than being relabelled or dropped (which had
                    // caused inconsistent labels + a duplicate ECL row).
                    const n23 = bsNames.get("assets::2.3") ?? "";
                    const n24 = bsNames.get("assets::2.4") ?? "";
                    const layoutB = /beklenen\s*zarar|expected\s*credit/i.test(n24)
                      || (!/fakto?ring/i.test(n23) && /menkul|securit|amorti[sz]|maliyet|itfa/i.test(n23));
                    return BS_ASSET_LINES.map((line) => {
                      const blank = (line.id === "factoring_recv" && layoutB)
                                 || (line.id === "securities_amc" && !layoutB);
                      return (
                        <Row
                          key={line.id}
                          label={line.label}
                          cells={
                            blank
                              ? blankCells()
                              : cellsForLine(
                                  line,
                                  bsPivot,
                                  "assets",
                                  AMBIGUOUS_PEER_LINES.has(line.id) ? null : undefined,
                                )
                          }
                          depth={indentLevel(line.hierarchy)}
                        />
                      );
                    });
                  })()}
                  <Row label="Total Assets" cells={totalAssets} divider />
                  <GroupRow label="Liabilities & equity — what pays for it" span={colCount + 1} />
                  {liabPreEquity.map((line) => (
                    <Row
                      key={line.id}
                      label={line.label}
                      cells={cellsForLine(line, bsPivot, "liabilities")}
                      depth={indentLevel(line.hierarchy)}
                    />
                  ))}
                  <Row label="Total Liabilities" cells={totalLiab} divider />
                  {equityBlock.map((line) => (
                    <Row
                      key={line.id}
                      label={line.label}
                      cells={cellsForLine(line, bsPivot, "liabilities")}
                      depth={indentLevel(line.hierarchy)}
                    />
                  ))}
                  <Row label="Total Liabilities & Equity" cells={totalLE} divider />
                </tbody>
              </table>
            </div>
          </section>
          )}

          {/* Income Statement — standardized table. The flow diagram no longer sits
              below it: the waterfall + interest fan are the SHAPE layer above. */}
          {statement === "is" && (
          <section className="group">
            <div className="flex items-baseline justify-between gap-3 pb-2">
              <h2 className="text-[13.5px] font-bold text-foreground">Income Statement</h2>
              <div className="flex items-center gap-2">
                <span className="font-mono text-[8.5px] uppercase tracking-[0.07em] text-faint">{unitLabel}</span>
                <CopyTableButton />
              </div>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full border-collapse">
                <thead className="text-muted-foreground">{periodHeaderRow}</thead>
                <tbody>
                  {/* Only the six sums that close a block are subtotals; the rest are
                      components with their breakdown nested under them. Passing
                      `divider={line.bold}` (as this did) ruled EVERY top-level line —
                      thirty identical bands, no hierarchy. */}
                  {PL_LINES.map((line) => (
                    <Row
                      key={line.id}
                      label={line.label}
                      cells={cellsForLine(line, plPivot, "")}
                      divider={line.subtotal}
                      depth={indentLevel(line.hierarchy)}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          </section>
          )}

          {/* Cash Flow — standardized via the CF_LINES catalog (BRSA hierarchy
              codes are consistent across banks). Empty → "not available" note. */}
          {statement === "cf" && (
            !hasCfData ? (
              <section className="rounded-[10px] border border-border bg-card px-5 py-4 text-xs text-muted-foreground">
                Cash flow statement not available for these periods.
              </section>
            ) : (
            <section className="group">
              <div className="flex items-baseline justify-between gap-3 pb-2">
                <h2 className="text-[13.5px] font-bold text-foreground">Cash Flow</h2>
                <div className="flex items-center gap-2">
                  <span className="font-mono text-[8.5px] uppercase tracking-[0.07em] text-faint">{unitLabel}</span>
                  <CopyTableButton />
                </div>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full border-collapse">
                  <thead className="text-muted-foreground">{periodHeaderRow}</thead>
                  <tbody>
                    {CF_LINES.map((line) =>
                      line.header ? (
                        <tr key={line.id}>
                          <td
                            colSpan={colCount + 1}
                            className="border-b border-border pb-1 pt-4 font-mono text-[8.5px] uppercase tracking-[0.1em] text-faint"
                          >
                            {line.label}
                          </td>
                        </tr>
                      ) : (
                        <Row
                          key={line.id}
                          label={line.label}
                          cells={cellsForLine(line, cfPivot, "")}
                          divider={CF_ROMAN_HIERARCHIES.includes(line.hierarchy)}
                          depth={indentLevel(line.hierarchy)}
                        />
                      ),
                    )}
                  </tbody>
                </table>
              </div>
            </section>
            )
          )}

          <p className="text-[11px] text-muted-foreground mt-3">
            Lines aligned by BRSA hierarchy code. &quot;--&quot; indicates the line was not
            reported for that period or did not extract.
            {statement === "bs" && (
              <> &quot;Total Assets&quot;, &quot;Total Liabilities&quot;, and
              &quot;Total Liabilities &amp; Equity&quot; are computed as sums of the
              Roman-numeral rows. Lines labelled &quot;(-)&quot; are deductions shown as
              magnitudes.</>
            )}
            {statement === "cf" && (
              <> Section totals (Roman numerals) follow the BRSA chain
              V&nbsp;=&nbsp;I+II+III+IV and VII&nbsp;=&nbsp;V+VI; amounts are
              cumulative year-to-date.</>
            )}
            {mode === "yoy" && (
              <> Cells show year-over-year % change vs the same quarter one year
              earlier; &quot;--&quot; where the prior-year period is unavailable.</>
            )}
            {isReal && (
              <>
                {" "}Real growth deflates the nominal rate:
                {" "}(1&nbsp;+&nbsp;nominal)&nbsp;/&nbsp;(1&nbsp;+&nbsp;CPI)&nbsp;−&nbsp;1 —
                a division, not a subtraction. Columns are the latest displayed
                quarter ({latestPeriod ?? "—"}) against the same quarter a year
                earlier. {cpiNote}. The verdict band is real&nbsp;&gt;&nbsp;+3%
                growing, −3%&nbsp;to&nbsp;+3% standing still,
                &lt;&nbsp;−3% shrinking.
              </>
            )}
            {isSize && statement === "bs" && (
              <>
                {" "}Every line is shown as a % of total assets (the sum of the
                Roman-numeral rows).{" "}
                {showPeers && sectorShares
                  ? `"Sector median" is the median share across the ${sectorShares.n} ${
                      isParticipation ? "participation" : "deposit / development"
                    } banks that filed ${latestPeriod} on the same BRSA template — the two templates put different line-items on the same Roman numeral, so a median across both would compare unlike lines. A peer that filed the quarter but not the line counts as zero. "Gap" is this bank's share minus that median, in percentage points; ±5pp or wider is marked amber. The median is withheld ("--") for Factoring Receivables and Securities at Amortized Cost: both are filed under code 2.3, and banks that leave the line unnamed cannot be told apart — so no peer set can be formed for them without guessing.`
                  : "The sector median is unavailable for this quarter."}
              </>
            )}
            {isSize && statement === "is" && (
              <> Every line is shown as a % of interest / profit-share income
              (BRSA line I.) — the denominator that makes two banks of different
              size comparable line-for-line.</>
            )}
            {showTtm && (
              <> &quot;TTM&quot; is the trailing twelve months ending the latest quarter
              (de-cumulated from the year-to-date figures).</>
            )}
            {anyWarning && (
              <> <span className="text-amber-600">⚠</span> marks a period whose
              extraction failed internal-sum validation (TL+FC=Total,
              subtotal=Σcomponents) — treat those figures with care.</>
            )}
          </p>
        </Section>
      </div>
      )}

      {/* ── Ownership ─────────────────────────────────────────────────────
          Simplified KAP view (design mock): ≥5% shareholder bars + §7
          subsidiary chips. */}
      {tab === "ownership" && hasOwnership && (
        <div className="mb-8 mt-6">
          <Section title="Ownership" contentClassName="">
            <OwnershipSummary rows={ownership} />
          </Section>
        </div>
      )}

      {/* ── In the News ───────────────────────────────────────────────────
          Press + Google News items tagged with this bank (news_item_banks,
          deterministic name→ticker matcher). Only renders when tagged items
          exist, so quiet banks don't get an empty section. */}
      {tab === "news" && hasBankNews && (
        <div className="mb-8 mt-6">
          <Section title="In the News" contentClassName="">
            <BankNewsSection items={bankNews} />
          </Section>
        </div>
      )}

      {/* ── Earnings & Disclosures ────────────────────────────────────────
          Compact results/presentation list + recent KAP filings, side by side. */}
      {tab === "news" && (
        <div className="mb-8">
          <Section title="Earnings & Disclosures" contentClassName="">
            <EarningsDisclosures earnings={earnings} disclosures={kapItems} ticker={ticker} />
          </Section>
        </div>
      )}

      <Colophon />
    </main>
  );
}
