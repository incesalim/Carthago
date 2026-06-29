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
import Link from "next/link";
import { PageHeader, Section, Stat } from "@/app/components/ui";
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
import { newsByTicker } from "@/app/lib/news";
import { earningsByTicker, kindLabel } from "@/app/lib/earnings";
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
import OwnershipCard from "@/app/components/OwnershipCard";
import OwnershipRadial from "@/app/components/OwnershipRadial";
import PlSankeySection from "./PlSankeySection";
import SubsidiariesCard from "./SubsidiariesCard";
import CopyTableButton from "@/app/components/CopyTableButton";
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

  const [bsPivot, bsNames, plPivot, plRows, cfPivot, kapItems, profile, stages, validation, ownership, valuationBase, priceHistory, liveMap, heatmap, sharePanel, earnings, mrDetail] =
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
  const cells = (series: PeriodSeries): (number | null | undefined)[] => {
    const byOrd = new Map<number, number>();
    for (const [p, v] of series) {
      const o = ordOf(p);
      if (o != null && v != null) byOrd.set(o, v);
    }
    const cell = (p: string): number | null => {
      if (mode === "abs") return series.get(p) ?? null;
      const o = ordOf(p);
      return o == null ? null : yoyPct(byOrd.get(o) ?? null, byOrd.get(o - 4) ?? null);
    };
    const row = periods.map(cell);
    if (!showTtm || latestOrd == null) return row;
    const ttm =
      mode === "abs"
        ? ttmEndingAt(byOrd, latestOrd)
        : yoyPct(ttmEndingAt(byOrd, latestOrd), ttmEndingAt(byOrd, latestOrd - 4));
    return [ttm, ...row];
  };
  const cellsForLine = (
    line: StandardLine,
    pivot: Map<string, PeriodSeries>,
    stmt: string,
  ): (number | null | undefined)[] => cells(lineSeries(pivot, line, stmt));
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
  const navSections = [
    { id: "overview", label: "Overview" },
    ...(hasPerf ? [{ id: "performance", label: "Performance" }] : []),
    ...(hasMarketRisk ? [{ id: "market-risk", label: "Market Risk" }] : []),
    { id: "financials", label: "Financials" },
    ...(hasOwnership ? [{ id: "ownership", label: "Ownership" }] : []),
    ...(earnings.length > 0 ? [{ id: "earnings", label: "Earnings" }] : []),
    { id: "disclosures", label: "Disclosures" },
  ];

  return (
    <main className="mx-auto w-full max-w-5xl px-4 py-8 sm:px-6 lg:px-8">
      {/* Sticky page chrome (lg+): pin the header and the in-page jump-nav as one
          stacked group — header on top, nav directly below — so neither overlaps
          the other. The header opts out of its own sticky (sticky={false}) and is
          pinned by this wrapper instead; on mobile the nav self-sticks at top-14. */}
      <div className="lg:sticky lg:top-0 lg:z-30">
        <PageHeader
          eyebrow={ticker}
          title={bankDisplayName(ticker)}
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

      {/* ── Overview ──────────────────────────────────────────────────────
          At-a-glance profile + (listed banks) BIST market & valuation. */}
      <div id="overview" className="scroll-mt-24 mb-8">
        <Section title="Overview" contentClassName="">
          {/* Bank-card summary: branches, personnel, TFRS 9 stage + coverage */}
          <BankCard
            profile={profile}
            stages={stages}
            latestPeriod={periods[0] ?? null}
          />

          {/* BIST market data + valuation (Yahoo close × audited equity/earnings).
              Only listed banks return a valuation; others render nothing. */}
          {valuation && (
            <Section
              title="Market & Valuation"
              description={
                `BIST: ${ticker} · ` +
                (valuation.isLive && valuation.asOf
                  ? `⏱ ${formatAsOf(valuation.asOf)}`
                  : `close ${valuation.period_date}`) +
                (valuation.fundamentalsPeriod
                  ? ` · P/B & P/E vs ${valuation.fundamentalsPeriod} audited figures`
                  : "")
              }
              className="mb-6"
              contentClassName=""
            >
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
                <Stat
                  label="Price"
                  value={`₺${nfmt(valuation.price, 2)}`}
                  hint={
                    valuation.changePct1y != null
                      ? `${valuation.changePct1y >= 0 ? "+" : ""}${nfmt(valuation.changePct1y, 1)}% · 1y`
                      : undefined
                  }
                  tone={
                    valuation.changePct1y == null
                      ? "neutral"
                      : valuation.changePct1y >= 0
                        ? "positive"
                        : "negative"
                  }
                />
                <Stat
                  label="Market Cap"
                  value={valuation.marketCap != null ? fmtMarketCap(valuation.marketCap) : "—"}
                />
                <Stat label="P/B" value={valuation.pb != null ? `${nfmt(valuation.pb, 2)}×` : "—"} />
                <Stat label="P/E" value={valuation.pe != null ? `${nfmt(valuation.pe, 1)}×` : "—"} />
                <Stat
                  label="Dividend Yield"
                  value={valuation.dividendYield != null ? `${nfmt(valuation.dividendYield * 100, 2)}%` : "—"}
                />
              </div>
              {priceHistory.length > 0 && (
                <div className="mt-4">
                  <TimeSeriesChart
                    series={{ [`${ticker} share price`]: priceHistory }}
                    title="Share price (daily close, ₺)"
                    yFormat="fx"
                    decimals={2}
                    height={280}              />
                </div>
              )}
            </Section>
          )}
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

      {/* ── Financials ────────────────────────────────────────────────────
          The page's core: standardized BS / IS tables + statement controls. */}
      <div id="financials" className="scroll-mt-24 mb-8">
        <Section title="Financials" contentClassName="">
          {/* Statement controls — sit directly above the statement table they drive:
              statement (BS/IS/CF) · view (absolute/YoY) · period (annual/quarterly) · kind */}
          <div className="mb-3 flex flex-wrap gap-3 items-center">
            <div className="flex gap-1 rounded-xl border border-border bg-card p-1">
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
            <div className="flex gap-1 rounded-xl border border-border bg-card p-1">
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
            <div className="flex gap-1 rounded-xl border border-border bg-card p-1">
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
            <div className="flex gap-1 rounded-xl border border-border bg-card p-1">
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
          <section className="group mb-6 rounded-2xl border border-border bg-card overflow-hidden">
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
          <section className="group rounded-2xl border border-border bg-card overflow-hidden">
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
              <section className="rounded-2xl border border-border bg-card px-5 py-4 text-xs text-muted-foreground">
                Cash flow statement not available for these periods.
              </section>
            ) : (
            <section className="group rounded-2xl border border-border bg-card overflow-hidden">
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

      {/* ── Ownership & structure ─────────────────────────────────────────
          KAP Genel Bilgi Formu: ≥5% holders, radial map, §7 subsidiaries. */}
      {hasOwnership && (
        <div id="ownership" className="scroll-mt-24 mb-8">
          <Section title="Ownership" contentClassName="">
            {/* Ownership structure from the KAP Genel Bilgi Formu (weekly refresh) */}
            <OwnershipCard rows={ownership} />

            {/* Interactive radial map: shareholders → bank → subsidiaries */}
            <OwnershipRadial ticker={ticker} rows={ownership} />

            {/* Subsidiaries / financial investments (same form, §7) */}
            <SubsidiariesCard rows={ownership} />
          </Section>
        </div>
      )}

      {/* ── Earnings & presentations ──────────────────────────────────────
          Results-filing dates (KAP) + investor-presentation decks (IR site). */}
      {earnings.length > 0 && (
        <div id="earnings" className="scroll-mt-24 mb-8">
          <Section title="Earnings & Presentations" contentClassName="">
            <div className="rounded-2xl border border-border bg-card p-4">
              <div className="text-sm font-medium text-foreground mb-3 flex items-baseline justify-between">
                <span>Quarterly results filings &amp; presentation decks</span>
                <Link href="/earnings" className="text-xs text-muted-foreground hover:text-foreground">
                  all banks →
                </Link>
              </div>
              <ul className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-x-4 gap-y-2">
                {earnings.map((e) => (
                  <li key={`${e.source}-${e.external_id}`} className="text-xs">
                    <a
                      href={e.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="block hover:bg-accent -mx-1 px-1 py-1 rounded transition"
                    >
                      <div className="text-[10px] uppercase tracking-wide text-muted-foreground tabular-nums flex items-center gap-1.5">
                        <span className={e.kind === "presentation_deck" ? "text-indigo-600 dark:text-indigo-300 font-semibold" : "text-primary font-semibold"}>
                          {kindLabel(e.kind)}
                        </span>
                        {e.period && <span className="text-foreground">{e.period.slice(4)} {e.period.slice(0, 4)}</span>}
                      </div>
                      <div className="text-foreground leading-snug line-clamp-2">
                        {e.title}
                      </div>
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          </Section>
        </div>
      )}

      {/* ── Disclosures ───────────────────────────────────────────────────
          Recent KAP filings (cached); link out to the full disclosures tab. */}
      <div id="disclosures" className="scroll-mt-24 mb-8">
        <Section title="Disclosures" contentClassName="">
          <div className="rounded-2xl border border-border bg-card p-4">
            <div className="text-sm font-medium text-foreground mb-3 flex items-baseline justify-between">
              <span>Recent KAP disclosures</span>
              {kapItems.length > 0 && (
                <Link
                  href={`/disclosures?ticker=${ticker}`}
                  className="text-xs text-muted-foreground hover:text-foreground"
                >
                  all {ticker} →
                </Link>
              )}
            </div>
            {kapItems.length === 0 ? (
              <div className="text-xs text-muted-foreground italic">No disclosures cached.</div>
            ) : (
              <ul className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-x-4 gap-y-2">
                {kapItems.map((it) => (
                  <li key={it.external_id} className="text-xs">
                    <a
                      href={it.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="block hover:bg-accent -mx-1 px-1 py-1 rounded transition"
                    >
                      <div className="text-[10px] uppercase tracking-wide text-muted-foreground tabular-nums">
                        {new Date(it.published_at).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}
                      </div>
                      <div className="text-foreground leading-snug line-clamp-2">
                        {it.title}
                      </div>
                    </a>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </Section>
      </div>
    </main>
  );
}
