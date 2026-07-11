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
 *   ?mode=abs|yoy       — absolute TL, or YoY % vs the same quarter a year earlier
 *   ?view=annual        — most recent Q4s (comparable year-end data)
 *   ?view=quarterly     — most recent quarters (sequential); adds a leading TTM
 *                         column for the income statement + cash flow
 *   ?kind=consolidated|unconsolidated
 *
 * All three statements map to BRSA hierarchy codes (see
 * web/app/lib/standard_lines.ts) with canonical English labels — the raw
 * `item_name` is never displayed, so banks are comparable line-for-line.
 */
import type { Metadata } from "next";
import type { ReactElement } from "react";
import Link from "next/link";
import { Card, PageHeader, Section, Stat } from "@/app/components/ui";
import { Colophon, SecHead, Vital, Vitals } from "@/app/components/desk";
import { lastVal, signedPp, valAgo } from "@/app/lib/desk";
import {
  bankPeriods,
  balanceSheetMultiPeriod,
  balanceSheetLineNames,
  profitLossMultiPeriod,
  profitLossRowsMultiPeriod,
  cashFlowMultiPeriod,
  bankProfile,
  bankStagesLatest,
  validationByPeriod,
} from "@/app/lib/audit";
import { ordOf, ttmEndingAt, yoyPct } from "@/app/lib/period-math";
import { newsByTicker, pressNewsByBank } from "@/app/lib/news";
import { earningsByTicker } from "@/app/lib/earnings";
import { bankOwnership } from "@/app/lib/kap";
import { heatmapPanel } from "@/app/lib/heatmap";
import { marketSharePanel, bankShareSeries } from "@/app/lib/market-share";
import { bankMarketRiskDetail } from "@/app/lib/market-risk";
import { bistValuation, bistPriceHistory } from "@/app/lib/bist";
import { liveQuotes, applyLivePrice, formatAsOf } from "@/app/lib/bist-live";
import TimeSeriesChart from "@/app/components/TimeSeriesChart";
import BankCard from "./BankCard";
import BankSectionNav from "./BankSectionNav";
import ProfitabilitySection from "./ProfitabilitySection";
import MarketRiskSection from "./MarketRiskSection";
import OwnershipSummary from "./OwnershipSummary";
import EarningsDisclosures from "./EarningsDisclosures";
import BankNewsSection from "./BankNewsSection";
import PlSankeySection from "./PlSankeySection";
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
  searchParams: Promise<{ view?: string; kind?: string; statement?: string; mode?: string }>;
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

interface RowProps {
  label: string;
  values: (number | null | undefined)[];
  bold?: boolean;
  /** Optional extra top border (used for subtotal rows). */
  divider?: boolean;
  /** Indent depth 0/1/2 — drives left padding + text muting. */
  depth?: number;
  /** Cell formatter — `fmtTl` (default) for absolute TL, `fmtPct` for YoY %. */
  format?: (v: number | null | undefined) => string;
}

/** Tailwind padding by indent depth (0 = top-level, 1 = sub, 2 = sub-sub). */
const INDENT_PL = ["pl-3", "pl-7", "pl-12"];

function Row({ label, values, bold, divider, depth = 0, format = fmtTl }: RowProps) {
  const pl = INDENT_PL[Math.min(depth, INDENT_PL.length - 1)];
  const muted = depth >= 2;
  return (
    <tr
      className={
        // Flat look (per the design handoff): only computed subtotal/total rows
        // (`divider`) get the muted band + top border. Top-level lines stay bold
        // on white — distinguished by weight + indent, not a shaded stripe.
        divider
          ? "bg-muted border-t border-border "
          : "border-b border-border"
      }
    >
      <td
        className={`py-1.5 pr-3 ${pl} text-xs ${
          bold ? "font-semibold text-foreground" : muted ? "text-muted-foreground" : "text-foreground"
        }`}
      >
        {label}
      </td>
      {values.map((v, i) => (
        <td
          key={i}
          className={`py-1.5 pl-2 pr-3 text-right text-xs tabular-nums ${
            bold ? "font-semibold text-foreground" : muted ? "text-muted-foreground" : "text-foreground"
          }`}
        >
          {format(v)}
        </td>
      ))}
    </tr>
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
  const mode = (sp.mode as "abs" | "yoy") ?? "abs";
  // Helper to build URLs that preserve the other params.
  const url = (overrides: Partial<{ view: string; kind: string; statement: string; mode: string }>) => {
    const params = new URLSearchParams({
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

  const [bsPivot, bsNames, plPivot, plRows, cfPivot, kapItems, profile, stages, validation, ownership, valuationBase, priceHistory, liveMap, heatmap, sharePanel, earnings, mrDetail, bankNews] =
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
  const rankChips = [
    { label: "by assets", r: rankOf("total_assets") },
    { label: "by ROE", r: rankOf("roe") },
    { label: "by NIM", r: rankOf("nim") },
    { label: "by cost / income", r: rankOf("cost_income", false) },
  ].filter((c) => c.r != null) as Array<{ label: string; r: { rank: number; n: number } }>;

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

  // ── Column derivation ─────────────────────────────────────────────────────
  // Display mode: absolute TL (stored value) or YoY % growth vs the same quarter
  // a year earlier. A leading TTM column (trailing-twelve-month) is shown for the
  // income statement + cash flow in quarterly view only (at Q4 annual view, TTM
  // equals the Q4 YTD column). P&L and cash flow are YTD-cumulative within the
  // year, so TTM de-cumulates; the balance sheet is point-in-time (no TTM).
  const showTtm = statement !== "bs" && view === "quarterly";
  const colCount = periods.length + (showTtm ? 1 : 0);
  const formatCell = mode === "yoy" ? fmtPct : fmtTl;
  // Turn a raw period→value series into the cells the table renders.
  const cells = (series: PeriodSeries, contra = false): (number | null | undefined)[] => {
    const byOrd = new Map<number, number>();
    for (const [p, v] of series) {
      const o = ordOf(p);
      if (o != null && v != null) byOrd.set(o, v);
    }
    // Deduction lines are carried as positive magnitudes (so YoY growth reads
    // naturally — a rising expense is +%); the accounting sign is applied only
    // to the absolute-TL display, never to the YoY %.
    const signed = (v: number | null): number | null =>
      v == null ? null : contra ? -v : v;
    const cell = (p: string): number | null => {
      if (mode === "abs") return signed(series.get(p) ?? null);
      const o = ordOf(p);
      return o == null ? null : yoyPct(byOrd.get(o) ?? null, byOrd.get(o - 4) ?? null);
    };
    const row = periods.map(cell);
    if (!showTtm || latestOrd == null) return row;
    const ttm =
      mode === "abs"
        ? signed(ttmEndingAt(byOrd, latestOrd))
        : yoyPct(ttmEndingAt(byOrd, latestOrd), ttmEndingAt(byOrd, latestOrd - 4));
    return [ttm, ...row];
  };
  const cellsForLine = (
    line: StandardLine,
    pivot: Map<string, PeriodSeries>,
    stmt: string,
  ): (number | null | undefined)[] => {
    const raw = lineSeries(pivot, line, stmt);
    // Fold contra lines to magnitude first — BRSA banks file them with either
    // sign — so the display sign (applied in `cells`) is uniform fleet-wide.
    const series: PeriodSeries = line.contra
      ? new Map([...raw].map(([p, v]) => [p, v == null ? null : Math.abs(v)] as [string, number | null]))
      : raw;
    return cells(series, line.contra);
  };
  const blankCells = (): (number | null | undefined)[] => Array(colCount).fill(null);
  const unitLabel = mode === "yoy" ? "Year-over-year % change" : "All numbers in TL thousands";
  // Shared table header row — a leading "TTM" column when applicable, then the
  // period-end dates. Reused across the BS / IS / CF tables.
  const periodHeaderRow = (
    <tr className="border-b">
      <th className="text-left py-2 pl-3 pr-3 font-medium">Breakdown</th>
      {showTtm && (
        <th className="text-right py-2 pl-2 pr-3 font-medium tabular-nums">TTM</th>
      )}
      {periods.map((p) => (
        <th key={p} className="text-right py-2 pl-2 pr-3 font-medium tabular-nums">
          {periodToDate(p)}
          {periodWarning(p) && (
            <span title={periodWarning(p)!} className="ml-1 cursor-help text-amber-600">⚠</span>
          )}
        </th>
      ))}
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
  const isParticipation = BANK_TYPE_BY_TICKER[ticker] === "10003";
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
  const totalAssets = cells(sumSeries(bsPivot, BS_ASSET_ROMAN_HIERARCHIES, "assets"));
  const totalLiab = cells(sumSeries(bsPivot, liabRomans, "liabilities"));
  const totalLE = cells(sumSeries(bsPivot, [...liabRomans, equityHierarchy], "liabilities"));

  // Split the liability catalog at the equity boundary so the synthetic
  // "Total Liabilities" subtotal slots in *before* the equity block.
  const liabPreEquity = liabLines.filter(
    (l) => !l.hierarchy.startsWith(equityRomanPrefix) && !l.hierarchy.startsWith(equityDotPrefix),
  );
  const equityBlock = liabLines.filter(
    (l) => l.hierarchy.startsWith(equityRomanPrefix) || l.hierarchy.startsWith(equityDotPrefix),
  );

  // In-page jump-nav: only list groups that actually render (the ownership
  // group is conditional on having a KAP form), so every anchor resolves.
  const hasOwnership = ownership.length > 0;
  const hasBankNews = bankNews.length > 0;
  const navSections = [
    { id: "overview", label: "Overview" },
    ...(hasPerf ? [{ id: "performance", label: "Performance" }] : []),
    ...(hasMarketRisk ? [{ id: "market-risk", label: "Market Risk" }] : []),
    ...(hasCapital ? [{ id: "capital", label: "Capital" }] : []),
    { id: "financials", label: "Financials" },
    ...(hasOwnership ? [{ id: "ownership", label: "Ownership" }] : []),
    ...(hasBankNews ? [{ id: "news", label: "News" }] : []),
    { id: "disclosures", label: "Disclosures" },
  ];

  return (
    <main className="mx-auto w-full max-w-[1440px] px-4 py-8 sm:px-6 lg:px-8">
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

        {/* In-page jump-nav: Overview · Performance · Financials · Ownership · Disclosures */}
        <BankSectionNav sections={navSections} />
      </div>

      {/* ── The vitals ────────────────────────────────────────────────────
          The page's signature band (DESIGN.md): the six figures that decide
          how this bank is read, computed from the audited quarterly panel the
          sections below already use — level, sparkline, and one computed note. */}
      {vitals.length >= 3 && (
        <>
          <SecHead
            title="The vitals"
            meta="audited quarterly · this bank"
            className="mb-2.5 mt-6"
          />
          <Vitals cols={vitalCols} className="mb-8">
            {vitals}
          </Vitals>
        </>
      )}

      {/* ── Overview ──────────────────────────────────────────────────────
          At-a-glance profile + (listed banks) BIST market & valuation. */}
      <div id="overview" className="scroll-mt-24 mb-8">
        <Section title="Overview" contentClassName="">
          {/* Composed hero band: profile (left) + market snapshot (right) —
              one screenful instead of three stacked full-width strips. */}
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-5">
            <div className={valuation ? "lg:col-span-3" : "lg:col-span-5"}>
              {/* Bank-card summary: branches, personnel, TFRS 9 stage +
                  coverage. The rank-in-field chips (same panel as /cross-bank,
                  so the ranks reconcile) fill the card's footer band. */}
              <BankCard
                profile={profile}
                stages={stages}
                latestPeriod={periods[0] ?? null}
                footer={
                  rankChips.length > 0 ? (
                    <div className="flex flex-wrap items-center gap-2">
                      {rankChips.map((c) => (
                        <span
                          key={c.label}
                          className="inline-flex items-baseline gap-1.5 rounded-md border border-border bg-background/60 px-2.5 py-1"
                        >
                          <span className="font-mono text-sm font-semibold text-foreground">
                            {ord(c.r.rank)}
                          </span>
                          <span className="text-[11px] text-muted-foreground">
                            of {c.r.n} {c.label}
                          </span>
                        </span>
                      ))}
                      <span className="text-[11px] text-faint">
                        · among banks reporting {perfLatest?.period}
                      </span>
                    </div>
                  ) : undefined
                }
              />
            </div>

            {/* BIST market data + valuation (Yahoo close × audited equity/
                earnings) as ONE composed card: price hero, compact multiples
                strip, price history. Only listed banks get a valuation. */}
            {valuation && (
              <Card className="flex h-full flex-col overflow-hidden lg:col-span-2">
                <div className="flex items-baseline justify-between border-b bg-muted px-5 py-3">
                  <h3 className="text-sm font-semibold text-foreground">Market &amp; valuation</h3>
                  <span className="text-[11px] text-muted-foreground tabular-nums">
                    BIST: {ticker} ·{" "}
                    {valuation.isLive && valuation.asOf
                      ? `⏱ ${formatAsOf(valuation.asOf)}`
                      : `close ${valuation.period_date}`}
                  </span>
                </div>
                <div className="flex flex-1 flex-col px-5 py-4">
                  <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                    <span className="font-mono text-3xl font-medium tracking-tight text-foreground">
                      ₺{nfmt(valuation.price, 2)}
                    </span>
                    {valuation.changePct1y != null && (
                      <span
                        className={`font-mono text-sm font-medium ${
                          valuation.changePct1y >= 0 ? "text-positive" : "text-negative"
                        }`}
                      >
                        {valuation.changePct1y >= 0 ? "+" : ""}
                        {nfmt(valuation.changePct1y, 1)}% · 1y
                      </span>
                    )}
                  </div>
                  <div className="mt-3 grid grid-cols-4 gap-2 border-t border-border pt-3">
                    {(
                      [
                        ["Mkt cap", valuation.marketCap != null ? fmtMarketCap(valuation.marketCap) : "—"],
                        ["P/B", valuation.pb != null ? `${nfmt(valuation.pb, 2)}×` : "—"],
                        ["P/E", valuation.pe != null ? `${nfmt(valuation.pe, 1)}×` : "—"],
                        ["Div yield", valuation.dividendYield != null ? `${nfmt(valuation.dividendYield * 100, 2)}%` : "—"],
                      ] as const
                    ).map(([label, value]) => (
                      <div key={label}>
                        <div className="text-[11px] text-muted-foreground">{label}</div>
                        <div className="font-mono text-sm font-semibold tabular-nums text-foreground">
                          {value}
                        </div>
                      </div>
                    ))}
                  </div>
                  {priceHistory.length > 0 && (
                    <div className="mt-3 border-t border-border pt-2">
                      <TimeSeriesChart
                        bare
                        series={{ [`${ticker} share price`]: priceHistory }}
                        yFormat="fx"
                        decimals={2}
                        height={172}
                      />
                    </div>
                  )}
                  {valuation.fundamentalsPeriod && (
                    <p className="mt-auto pt-2 font-mono text-[9.5px] text-faint">
                      P/B &amp; P/E vs {valuation.fundamentalsPeriod} audited figures · daily close, ₺
                    </p>
                  )}
                </div>
              </Card>
            )}
          </div>
        </Section>
      </div>

      {/* ── Performance ───────────────────────────────────────────────────
          Derived analytics: margin bridge (yield − cost = spread), cost of
          risk, PPOP, and competitive market share. The "drivers behind" the
          levels in the statements below. */}
      {hasPerf && (
        <div id="performance" className="scroll-mt-24 mb-8">
          <ProfitabilitySection rows={perfRows} shareRows={shareRows} />
        </div>
      )}

      {/* ── Market risk (CAMELS S) ────────────────────────────────────────
          FX net open position + interest-rate repricing gap from §4 footnotes. */}
      {hasMarketRisk && (
        <div id="market-risk" className="scroll-mt-24 mb-8">
          <MarketRiskSection rows={perfRows} detail={mrDetail} />
        </div>
      )}

      {/* ── Capital (audited §4) ──────────────────────────────────────────
          Per-bank solvency buffers — the audit's add_missing gap. LCR lives in
          the Market Risk tiles above; this block is the capital side. */}
      {hasCapital && perfLatest && (
        <div id="capital" className="scroll-mt-24 mb-8">
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
          The page's core: standardized BS / IS tables + statement controls. */}
      <div id="financials" className="scroll-mt-24 mb-8">
        <Section title="Financials" contentClassName="">
          {/* Statement controls — sit directly above the statement table they drive:
              statement (BS/IS/CF) · view (absolute/YoY) · period (annual/quarterly) · kind */}
          <div className="mb-3 flex flex-wrap gap-3 items-center">
            <div className="flex gap-1 rounded-[9px] border border-border bg-card p-[3px]">
              {(["bs", "is", "cf"] as const).map((s) => (
                <Link
                  key={s}
                  href={url({ statement: s })}
                  scroll={false}
                  className={`px-3 py-1 text-xs rounded-lg transition ${
                    s === statement
                      ? "bg-primary/10 font-semibold text-primary"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {s === "bs" ? "Balance Sheet" : s === "is" ? "Income Statement" : "Cash Flow"}
                </Link>
              ))}
            </div>
            <div className="flex gap-1 rounded-[9px] border border-border bg-card p-[3px]">
              {(["abs", "yoy"] as const).map((m) => (
                <Link
                  key={m}
                  href={url({ mode: m })}
                  scroll={false}
                  className={`px-3 py-1 text-xs rounded-lg transition ${
                    m === mode
                      ? "bg-primary/10 font-semibold text-primary"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {m === "abs" ? "Absolute" : "YoY Growth"}
                </Link>
              ))}
            </div>
            <div className="flex gap-1 rounded-[9px] border border-border bg-card p-[3px]">
              {(["annual", "quarterly"] as const).map((v) => (
                <Link
                  key={v}
                  href={url({ view: v })}
                  scroll={false}
                  className={`px-3 py-1 text-xs rounded-lg transition ${
                    v === view
                      ? "bg-primary/10 font-semibold text-primary"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {v === "annual" ? "Annual" : "Quarterly"}
                </Link>
              ))}
            </div>
            <div className="flex gap-1 rounded-[9px] border border-border bg-card p-[3px]">
              {(["unconsolidated", "consolidated"] as const).map((k) => (
                <Link
                  key={k}
                  href={url({ kind: k })}
                  scroll={false}
                  className={`px-3 py-1 text-xs rounded-lg transition ${
                    k === kind
                      ? "bg-primary/10 font-semibold text-primary"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {k === "consolidated" ? "Consolidated" : "Bank-only"}
                </Link>
              ))}
            </div>
          </div>

          {/* Balance Sheet — single table, assets and liabilities together */}
          {statement === "bs" && (
          <section className="group mb-6 rounded-[10px] border border-border bg-card overflow-hidden">
            <div className="px-5 py-3 border-b bg-muted flex items-center justify-between">
              <h2 className="text-sm font-semibold text-foreground">Balance Sheet</h2>
              <div className="flex items-center gap-2">
                <span className="text-[11px] text-muted-foreground">{unitLabel}</span>
                <CopyTableButton />
              </div>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead className="text-muted-foreground">{periodHeaderRow}</thead>
                <tbody>
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
                          values={blank ? blankCells() : cellsForLine(line, bsPivot, "assets")}
                          bold={line.bold || indentLevel(line.hierarchy) === 0}
                          depth={indentLevel(line.hierarchy)}
                          format={formatCell}
                        />
                      );
                    });
                  })()}
                  <Row label="Total Assets" values={totalAssets} bold divider format={formatCell} />
                  {liabPreEquity.map((line) => (
                    <Row
                      key={line.id}
                      label={line.label}
                      values={cellsForLine(line, bsPivot, "liabilities")}
                      bold={line.bold || indentLevel(line.hierarchy) === 0}
                      depth={indentLevel(line.hierarchy)}
                      format={formatCell}
                    />
                  ))}
                  <Row label="Total Liabilities" values={totalLiab} bold divider format={formatCell} />
                  {equityBlock.map((line) => (
                    <Row
                      key={line.id}
                      label={line.label}
                      values={cellsForLine(line, bsPivot, "liabilities")}
                      bold={line.bold || indentLevel(line.hierarchy) === 0}
                      depth={indentLevel(line.hierarchy)}
                      format={formatCell}
                    />
                  ))}
                  <Row label="Total Liabilities & Equity" values={totalLE} bold divider format={formatCell} />
                </tbody>
              </table>
            </div>
          </section>
          )}

          {/* Income Statement — standardized table, with the P&L flow Sankey below it */}
          {statement === "is" && (
          <section className="group rounded-[10px] border border-border bg-card overflow-hidden">
            <div className="px-5 py-3 border-b bg-muted flex items-center justify-between">
              <h2 className="text-sm font-semibold text-foreground">Income Statement</h2>
              <div className="flex items-center gap-2">
                <span className="text-[11px] text-muted-foreground">{unitLabel}</span>
                <CopyTableButton />
              </div>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead className="text-muted-foreground">{periodHeaderRow}</thead>
                <tbody>
                  {PL_LINES.map((line) => (
                    <Row
                      key={line.id}
                      label={line.label}
                      values={cellsForLine(line, plPivot, "")}
                      bold={line.bold}
                      divider={line.bold}
                      format={formatCell}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          </section>
          )}
          {statement === "is" && (
            <div className="mt-6">
              <PlSankeySection rowsByPeriod={plRows} periods={periods} />
            </div>
          )}

          {/* Cash Flow — standardized via the CF_LINES catalog (BRSA hierarchy
              codes are consistent across banks). Empty → "not available" note. */}
          {statement === "cf" && (
            !hasCfData ? (
              <section className="rounded-[10px] border border-border bg-card px-5 py-4 text-xs text-muted-foreground">
                Cash flow statement not available for these periods.
              </section>
            ) : (
            <section className="group rounded-[10px] border border-border bg-card overflow-hidden">
              <div className="px-5 py-3 border-b bg-muted flex items-center justify-between">
                <h2 className="text-sm font-semibold text-foreground">Cash Flow</h2>
                <div className="flex items-center gap-2">
                  <span className="text-[11px] text-muted-foreground">{unitLabel}</span>
                  <CopyTableButton />
                </div>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead className="text-muted-foreground">{periodHeaderRow}</thead>
                  <tbody>
                    {CF_LINES.map((line) =>
                      line.header ? (
                        <tr key={line.id} className="border-t border-border bg-muted">
                          <td
                            colSpan={colCount + 1}
                            className="py-1.5 pl-3 pr-3 text-xs font-semibold text-foreground"
                          >
                            {line.label}
                          </td>
                        </tr>
                      ) : (
                        <Row
                          key={line.id}
                          label={line.label}
                          values={cellsForLine(line, cfPivot, "")}
                          bold={line.bold}
                          divider={CF_ROMAN_HIERARCHIES.includes(line.hierarchy)}
                          depth={indentLevel(line.hierarchy)}
                          format={formatCell}
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

      {/* ── Ownership ─────────────────────────────────────────────────────
          Simplified KAP view (design mock): ≥5% shareholder bars + §7
          subsidiary chips. */}
      {hasOwnership && (
        <div id="ownership" className="scroll-mt-24 mb-8">
          <Section title="Ownership" contentClassName="">
            <OwnershipSummary rows={ownership} />
          </Section>
        </div>
      )}

      {/* ── In the News ───────────────────────────────────────────────────
          Press + Google News items tagged with this bank (news_item_banks,
          deterministic name→ticker matcher). Only renders when tagged items
          exist, so quiet banks don't get an empty section. */}
      {hasBankNews && (
        <div id="news" className="scroll-mt-24 mb-8">
          <Section title="In the News" contentClassName="">
            <BankNewsSection items={bankNews} />
          </Section>
        </div>
      )}

      {/* ── Earnings & Disclosures ────────────────────────────────────────
          Compact results/presentation list + recent KAP filings, side by side. */}
      <div id="disclosures" className="scroll-mt-24 mb-8">
        <Section title="Earnings & Disclosures" contentClassName="">
          <EarningsDisclosures earnings={earnings} disclosures={kapItems} ticker={ticker} />
        </Section>
      </div>

      <Colophon />
    </main>
  );
}
