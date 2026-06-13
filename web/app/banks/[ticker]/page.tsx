/**
 * /banks/[ticker] — per-bank drill-down.
 *
 * Standardized financial tables (Balance Sheet + Income Statement) in a
 * Yahoo-Finance-style layout: single continuous table, period-end dates
 * as column headers, computed subtotals (Total Assets, Total Liabilities,
 * Total Liabilities + Equity, plus P&L subtotals) shown in bold. Missing
 * values render as "--".
 *
 * View modes:
 *   ?view=annual    — most recent Q4s (default, comparable year-end data)
 *   ?view=quarterly — most recent quarters (sequential)
 *
 * Lines map to BRSA hierarchy codes — see web/app/lib/standard_lines.ts.
 * Raw `item_name` from the database is never displayed.
 */
import Link from "next/link";
import { PageHeader, Section, Stat } from "@/app/components/ui";
import {
  bankPeriods,
  balanceSheetMultiPeriod,
  balanceSheetLineNames,
  profitLossMultiPeriod,
  profitLossRowsMultiPeriod,
  bankProfile,
  bankStagesLatest,
  validationByPeriod,
} from "@/app/lib/audit";
import { newsByTicker } from "@/app/lib/news";
import { bankOwnership } from "@/app/lib/kap";
import { bistValuation, bistPriceHistory } from "@/app/lib/bist";
import { liveQuotes, applyLivePrice, formatAsOf } from "@/app/lib/bist-live";
import TimeSeriesChart from "@/app/components/TimeSeriesChart";
import BankCard from "@/app/components/BankCard";
import OwnershipCard from "@/app/components/OwnershipCard";
import OwnershipRadial from "@/app/components/OwnershipRadial";
import PlSankeySection from "@/app/components/PlSankeySection";
import SubsidiariesCard from "@/app/components/SubsidiariesCard";
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
  resolveBsLineLabel,
  PL_LINES,
  indentLevel,
  type StandardLine,
} from "@/app/lib/standard_lines";
import { bankDisplayName, BANK_TYPE_BY_TICKER } from "@/app/lib/bank_names";
import { notFound } from "next/navigation";

export const dynamic = "force-dynamic";

interface Props {
  params: Promise<{ ticker: string }>;
  searchParams: Promise<{ view?: string; kind?: string; statement?: string }>;
}

const NF = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
const fmtTl = (v: number | null | undefined) => (v == null ? "--" : NF.format(v));

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
}

/** Tailwind padding by indent depth (0 = top-level, 1 = sub, 2 = sub-sub). */
const INDENT_PL = ["pl-3", "pl-7", "pl-12"];

function Row({ label, values, bold, divider, depth = 0 }: RowProps) {
  const pl = INDENT_PL[Math.min(depth, INDENT_PL.length - 1)];
  const muted = depth >= 2;
  return (
    <tr
      className={
        (bold ? "bg-muted " : "") +
        (divider ? "border-t border-border " : "border-b border-border")
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
          {fmtTl(v)}
        </td>
      ))}
    </tr>
  );
}

/** Helper to pull a line's value for each period from the pivot map. */
function valuesForLine(
  line: StandardLine,
  pivot: Map<string, Map<string, number | null>>,
  periods: string[],
  statement: string,
): (number | null | undefined)[] {
  const key = statement ? `${statement}::${line.hierarchy}` : line.hierarchy;
  const periodMap = pivot.get(key) ?? new Map();
  return periods.map((p) => periodMap.get(p) ?? null);
}

/** Sum non-null values across a list of BRSA hierarchy codes per period.
 *  Used for synthetic Total Assets / Total Liabilities rows — pass the
 *  Roman-numeral parent codes (BS_ASSET_ROMAN_HIERARCHIES etc.) to avoid
 *  double-counting sub-items that are also displayed individually. */
function sumHierarchies(
  hierarchies: string[],
  pivot: Map<string, Map<string, number | null>>,
  periods: string[],
  statement: string,
): (number | null)[] {
  return periods.map((p) => {
    let total = 0;
    let any = false;
    for (const h of hierarchies) {
      const key = `${statement}::${h}`;
      const v = pivot.get(key)?.get(p);
      if (v != null) {
        total += v;
        any = true;
      }
    }
    return any ? total : null;
  });
}

const nfmt = (v: number, d = 2) =>
  new Intl.NumberFormat("en-US", { minimumFractionDigits: d, maximumFractionDigits: d }).format(v);

/** Market cap (TL) → "₺570.8B" / "₺1.05T". */
function fmtMarketCap(tl: number): string {
  if (tl >= 1e12) return `₺${nfmt(tl / 1e12, 2)}T`;
  return `₺${nfmt(tl / 1e9, 1)}B`;
}

/** Element-wise add of two parallel arrays of (number | null). */
function addArrays(a: (number | null)[], b: (number | null)[]): (number | null)[] {
  return a.map((av, i) => {
    const bv = b[i];
    if (av == null && bv == null) return null;
    return (av ?? 0) + (bv ?? 0);
  });
}

export default async function BankDetailPage({ params, searchParams }: Props) {
  const { ticker: rawTicker } = await params;
  const sp = await searchParams;
  const ticker = rawTicker.toUpperCase();

  const allPeriodMeta = await bankPeriods(ticker);
  if (allPeriodMeta.length === 0) notFound();

  const kind = (sp.kind as "consolidated" | "unconsolidated") ?? "unconsolidated";
  const view = (sp.view as "annual" | "quarterly") ?? "annual";
  const statement = (sp.statement as "bs" | "is") ?? "bs";
  // Helper to build URLs that preserve the other two params.
  const url = (overrides: Partial<{ view: string; kind: string; statement: string }>) => {
    const params = new URLSearchParams({
      view: overrides.view ?? view,
      kind: overrides.kind ?? kind,
      statement: overrides.statement ?? statement,
    });
    return `/banks/${ticker}?${params.toString()}`;
  };

  const allPeriods = Array.from(
    new Set(allPeriodMeta.filter((p) => p.kind === kind).map((p) => p.period)),
  ).sort().reverse();
  const periods = pickPeriods(allPeriods, view, 4);

  const [bsPivot, bsNames, plPivot, plRows, kapItems, profile, stages, validation, ownership, valuationBase, priceHistory, liveMap] =
    await Promise.all([
      balanceSheetMultiPeriod(ticker, kind, periods),
      balanceSheetLineNames(ticker, kind, periods),
      profitLossMultiPeriod(ticker, kind, periods),
      statement === "is"
        ? profitLossRowsMultiPeriod(ticker, kind, periods)
        : Promise.resolve({}),
      newsByTicker(ticker, 12),
      bankProfile(ticker),
      bankStagesLatest(ticker, kind),
      validationByPeriod(ticker, kind),
      bankOwnership(ticker),
      bistValuation(ticker, kind),
      bistPriceHistory(ticker, 8),
      liveQuotes([ticker]),
    ]);

  // Overlay the latest (delayed) Yahoo price on the stored valuation; if the
  // live fetch returned nothing, keep the stored EOD figures untouched.
  const liveQ = liveMap.get(ticker);
  const valuation = valuationBase && liveQ ? applyLivePrice(valuationBase, liveQ) : valuationBase;

  // ⚠ on a period column = that quarter's extraction failed one or more
  // internal-sum identity checks (TL+FC=Total, parent=Σchildren, TOTAL=Σromans,
  // assets=liabilities+equity) — treat its figures with care.
  const periodWarning = (p: string): string | null => {
    const v = validation.get(p);
    if (!v || v.checks_failed === 0) return null;
    return `${v.checks_failed} of ${v.checks_failed + v.checks_passed} internal-sum checks failed for this quarter's extraction — figures may be incomplete or misread.`;
  };
  const anyWarning = periods.some((p) => periodWarning(p) !== null);

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
  // double-count). Equity is summed separately.
  const totalAssets = sumHierarchies(BS_ASSET_ROMAN_HIERARCHIES, bsPivot, periods, "assets");
  const totalLiab = sumHierarchies(liabRomans, bsPivot, periods, "liabilities");
  const equityValues = sumHierarchies([equityHierarchy], bsPivot, periods, "liabilities");
  const totalLE = addArrays(totalLiab, equityValues);

  // Split the liability catalog at the equity boundary so the synthetic
  // "Total Liabilities" subtotal slots in *before* the equity block.
  const liabPreEquity = liabLines.filter(
    (l) => !l.hierarchy.startsWith(equityRomanPrefix) && !l.hierarchy.startsWith(equityDotPrefix),
  );
  const equityBlock = liabLines.filter(
    (l) => l.hierarchy.startsWith(equityRomanPrefix) || l.hierarchy.startsWith(equityDotPrefix),
  );

  return (
    <main className="mx-auto w-full max-w-5xl px-4 py-8 sm:px-6 lg:px-8">
      <PageHeader
        eyebrow={ticker}
        title={bankDisplayName(ticker)}
        description="Standardized per-bank financials from quarterly BRSA reports"
        dataThrough={allPeriods[0]}
        className="mb-6"
      >
        <Link href="/banks" className="text-sm text-muted-foreground hover:text-foreground">
          ← All banks
        </Link>
      </PageHeader>

      {/* Three toggle groups: statement / period view / consolidation kind */}
      <div className="mb-6 flex flex-wrap gap-3 items-center">
        <div className="flex gap-1 rounded-lg border bg-muted p-1">
          {(["bs", "is"] as const).map((s) => (
            <Link
              key={s}
              href={url({ statement: s })}
              className={`px-3 py-1 text-xs rounded-md transition ${
                s === statement
                  ? "bg-card shadow-sm font-medium text-foreground"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              {s === "bs" ? "Balance Sheet" : "Income Statement"}
            </Link>
          ))}
        </div>
        <div className="flex gap-1 rounded-lg border bg-muted p-1">
          {(["annual", "quarterly"] as const).map((v) => (
            <Link
              key={v}
              href={url({ view: v })}
              className={`px-3 py-1 text-xs rounded-md transition ${
                v === view
                  ? "bg-card shadow-sm font-medium text-foreground"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              {v === "annual" ? "Annual" : "Quarterly"}
            </Link>
          ))}
        </div>
        <div className="flex gap-1 rounded-lg border bg-muted p-1">
          {(["unconsolidated", "consolidated"] as const).map((k) => (
            <Link
              key={k}
              href={url({ kind: k })}
              className={`px-3 py-1 text-xs rounded-md transition ${
                k === kind
                  ? "bg-card shadow-sm font-medium text-foreground"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              {k === "consolidated" ? "Consolidated" : "Bank-only"}
            </Link>
          ))}
        </div>
      </div>

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
                height={280}
              />
            </div>
          )}
        </Section>
      )}

      {/* Ownership structure from the KAP Genel Bilgi Formu (weekly refresh) */}
      <OwnershipCard rows={ownership} />

      {/* Interactive radial map: shareholders → bank → subsidiaries */}
      <OwnershipRadial ticker={ticker} rows={ownership} />

      {/* Subsidiaries / financial investments (same form, §7) */}
      <SubsidiariesCard rows={ownership} />

      {/* Recent KAP disclosures */}
      <div className="mb-6 rounded-xl border border-border bg-card p-4 shadow-sm">
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

      {/* Balance Sheet — single table, assets and liabilities together */}
      {statement === "bs" && (
      <section className="group mb-6 rounded-lg border bg-card shadow-sm overflow-hidden">
        <div className="px-5 py-3 border-b bg-muted flex items-center justify-between">
          <h2 className="text-sm font-semibold text-foreground">Balance Sheet</h2>
          <div className="flex items-center gap-2">
            <span className="text-[11px] text-muted-foreground">All numbers in TL thousands</span>
            <CopyTableButton />
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="text-muted-foreground">
              <tr className="border-b">
                <th className="text-left py-2 pl-3 pr-3 font-medium">Breakdown</th>
                {periods.map((p) => (
                  <th key={p} className="text-right py-2 pl-2 pr-3 font-medium tabular-nums">
                    {periodToDate(p)}
                    {periodWarning(p) && (
                      <span title={periodWarning(p)!} className="ml-1 cursor-help text-amber-600">⚠</span>
                    )}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {BS_ASSET_LINES.map((line) => (
                <Row
                  key={line.id}
                  label={resolveBsLineLabel("assets", line.hierarchy, bsNames, line.label)}
                  values={valuesForLine(line, bsPivot, periods, "assets")}
                  bold={line.bold}
                  depth={indentLevel(line.hierarchy)}
                />
              ))}
              <Row label="Total Assets" values={totalAssets} bold divider />
              {liabPreEquity.map((line) => (
                <Row
                  key={line.id}
                  label={line.label}
                  values={valuesForLine(line, bsPivot, periods, "liabilities")}
                  bold={line.bold}
                  depth={indentLevel(line.hierarchy)}
                />
              ))}
              <Row label="Total Liabilities" values={totalLiab} bold divider />
              {equityBlock.map((line) => (
                <Row
                  key={line.id}
                  label={line.label}
                  values={valuesForLine(line, bsPivot, periods, "liabilities")}
                  bold={line.bold}
                  depth={indentLevel(line.hierarchy)}
                />
              ))}
              <Row label="Total Liabilities & Equity" values={totalLE} bold divider />
            </tbody>
          </table>
        </div>
      </section>
      )}

      {/* Income Statement — flow Sankey above the standardized table */}
      {statement === "is" && (
        <PlSankeySection rowsByPeriod={plRows} periods={periods} />
      )}
      {statement === "is" && (
      <section className="group rounded-lg border bg-card shadow-sm overflow-hidden">
        <div className="px-5 py-3 border-b bg-muted flex items-center justify-between">
          <h2 className="text-sm font-semibold text-foreground">Income Statement</h2>
          <div className="flex items-center gap-2">
            <span className="text-[11px] text-muted-foreground">All numbers in TL thousands</span>
            <CopyTableButton />
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="text-muted-foreground">
              <tr className="border-b">
                <th className="text-left py-2 pl-3 pr-3 font-medium">Breakdown</th>
                {periods.map((p) => (
                  <th key={p} className="text-right py-2 pl-2 pr-3 font-medium tabular-nums">
                    {periodToDate(p)}
                    {periodWarning(p) && (
                      <span title={periodWarning(p)!} className="ml-1 cursor-help text-amber-600">⚠</span>
                    )}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {PL_LINES.map((line) => (
                <Row
                  key={line.id}
                  label={line.label}
                  values={valuesForLine(line, plPivot, periods, "")}
                  bold={line.bold}
                  divider={line.bold}
                />
              ))}
            </tbody>
          </table>
        </div>
      </section>
      )}

      <p className="text-[11px] text-muted-foreground mt-3">
        Lines aligned by BRSA hierarchy code. &quot;--&quot; indicates the line was not
        reported for that period or did not extract. &quot;Total Assets&quot;,
        &quot;Total Liabilities&quot;, and &quot;Total Liabilities &amp; Equity&quot;
        are computed as sums of the Roman-numeral rows. Lines labelled
        &quot;(-)&quot; are deductions shown as magnitudes.
        {anyWarning && (
          <> <span className="text-amber-600">⚠</span> marks a period whose
          extraction failed internal-sum validation (TL+FC=Total,
          subtotal=Σcomponents) — treat those figures with care.</>
        )}
      </p>
    </main>
  );
}
