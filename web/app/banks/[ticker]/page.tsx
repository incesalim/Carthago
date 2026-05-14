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
import {
  bankPeriods,
  balanceSheetMultiPeriod,
  profitLossMultiPeriod,
  bankProfile,
  bankStagesLatest,
} from "@/app/lib/audit";
import { newsByTicker } from "@/app/lib/news";
import BankCard from "@/app/components/BankCard";
import {
  BS_ASSET_LINES,
  BS_ASSET_ROMAN_HIERARCHIES,
  BS_LIAB_LINES,
  BS_LIAB_ROMAN_HIERARCHIES,
  BS_EQUITY_HIERARCHY,
  PL_LINES,
  indentLevel,
  type StandardLine,
} from "@/app/lib/standard_lines";
import { bankDisplayName } from "@/app/lib/bank_names";
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
        (bold ? "bg-neutral-50 " : "") +
        (divider ? "border-t border-neutral-300 " : "border-b border-neutral-100")
      }
    >
      <td
        className={`py-1.5 pr-3 ${pl} text-xs ${
          bold ? "font-semibold text-neutral-900" : muted ? "text-neutral-500" : "text-neutral-700"
        }`}
      >
        {label}
      </td>
      {values.map((v, i) => (
        <td
          key={i}
          className={`py-1.5 pl-2 pr-3 text-right text-xs tabular-nums ${
            bold ? "font-semibold text-neutral-900" : muted ? "text-neutral-500" : "text-neutral-800"
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

  const [bsPivot, plPivot, kapItems, profile, stages] = await Promise.all([
    balanceSheetMultiPeriod(ticker, kind, periods),
    profitLossMultiPeriod(ticker, kind, periods),
    newsByTicker(ticker, 12),
    bankProfile(ticker),
    bankStagesLatest(ticker, kind),
  ]);

  // Computed totals. Sum BRSA Roman-numeral parents — never sub-items
  // (e.g. "2.1 Loans" is inside "II. Amortized Cost"; including both would
  // double-count). Equity is summed separately.
  const totalAssets = sumHierarchies(BS_ASSET_ROMAN_HIERARCHIES, bsPivot, periods, "assets");
  const totalLiab = sumHierarchies(BS_LIAB_ROMAN_HIERARCHIES, bsPivot, periods, "liabilities");
  const equityValues = sumHierarchies([BS_EQUITY_HIERARCHY], bsPivot, periods, "liabilities");
  const totalLE = addArrays(totalLiab, equityValues);

  // Split the liability catalog at the equity boundary so the synthetic
  // "Total Liabilities" subtotal slots in *before* the equity block.
  const liabPreEquity = BS_LIAB_LINES.filter(
    (l) => !l.hierarchy.startsWith("XVI") && !l.hierarchy.startsWith("16."),
  );
  const equityBlock = BS_LIAB_LINES.filter(
    (l) => l.hierarchy.startsWith("XVI") || l.hierarchy.startsWith("16."),
  );

  return (
    <main className="px-8 py-8 max-w-5xl">
      {/* Header */}
      <div className="flex items-baseline justify-between mb-2 gap-4 flex-wrap">
        <div>
          <h1 className="text-3xl font-bold">{bankDisplayName(ticker)}</h1>
          <p className="text-xs text-neutral-500 tabular-nums mt-0.5">{ticker}</p>
        </div>
        <Link href="/banks" className="text-sm text-neutral-500 hover:text-neutral-900">
          ← All banks
        </Link>
      </div>
      <p className="text-sm text-neutral-500 mb-6">
        Standardized per-bank financials from quarterly BRSA reports
      </p>

      {/* Three toggle groups: statement / period view / consolidation kind */}
      <div className="mb-6 flex flex-wrap gap-3 items-center">
        <div className="flex gap-1 rounded-lg border bg-neutral-50 p-1">
          {(["bs", "is"] as const).map((s) => (
            <Link
              key={s}
              href={url({ statement: s })}
              className={`px-3 py-1 text-xs rounded-md transition ${
                s === statement
                  ? "bg-white shadow-sm font-medium text-neutral-900"
                  : "text-neutral-600 hover:text-neutral-900"
              }`}
            >
              {s === "bs" ? "Balance Sheet" : "Income Statement"}
            </Link>
          ))}
        </div>
        <div className="flex gap-1 rounded-lg border bg-neutral-50 p-1">
          {(["annual", "quarterly"] as const).map((v) => (
            <Link
              key={v}
              href={url({ view: v })}
              className={`px-3 py-1 text-xs rounded-md transition ${
                v === view
                  ? "bg-white shadow-sm font-medium text-neutral-900"
                  : "text-neutral-600 hover:text-neutral-900"
              }`}
            >
              {v === "annual" ? "Annual" : "Quarterly"}
            </Link>
          ))}
        </div>
        <div className="flex gap-1 rounded-lg border bg-neutral-50 p-1">
          {(["unconsolidated", "consolidated"] as const).map((k) => (
            <Link
              key={k}
              href={url({ kind: k })}
              className={`px-3 py-1 text-xs rounded-md transition ${
                k === kind
                  ? "bg-white shadow-sm font-medium text-neutral-900"
                  : "text-neutral-600 hover:text-neutral-900"
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

      {/* Recent KAP disclosures */}
      <div className="mb-6 rounded-xl border border-neutral-200 bg-white p-4 shadow-sm">
        <div className="text-sm font-medium text-neutral-800 mb-3 flex items-baseline justify-between">
          <span>Recent KAP disclosures</span>
          {kapItems.length > 0 && (
            <Link
              href={`/disclosures?ticker=${ticker}`}
              className="text-xs text-neutral-500 hover:text-neutral-900"
            >
              all {ticker} →
            </Link>
          )}
        </div>
        {kapItems.length === 0 ? (
          <div className="text-xs text-neutral-500 italic">No disclosures cached.</div>
        ) : (
          <ul className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-x-4 gap-y-2">
            {kapItems.map((it) => (
              <li key={it.external_id} className="text-xs">
                <a
                  href={it.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="block hover:bg-neutral-50 -mx-1 px-1 py-1 rounded transition"
                >
                  <div className="text-[10px] uppercase tracking-wide text-neutral-500 tabular-nums">
                    {new Date(it.published_at).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}
                  </div>
                  <div className="text-neutral-900 leading-snug line-clamp-2">
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
      <section className="mb-6 rounded-lg border bg-white shadow-sm overflow-hidden">
        <div className="px-5 py-3 border-b bg-neutral-50 flex items-baseline justify-between">
          <h2 className="text-sm font-semibold text-neutral-900">Balance Sheet</h2>
          <span className="text-[11px] text-neutral-500">All numbers in TL thousands</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="text-neutral-500">
              <tr className="border-b">
                <th className="text-left py-2 pl-3 pr-3 font-medium">Breakdown</th>
                {periods.map((p) => (
                  <th key={p} className="text-right py-2 pl-2 pr-3 font-medium tabular-nums">
                    {periodToDate(p)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {BS_ASSET_LINES.map((line) => (
                <Row
                  key={line.id}
                  label={line.label}
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

      {/* Income Statement */}
      {statement === "is" && (
      <section className="rounded-lg border bg-white shadow-sm overflow-hidden">
        <div className="px-5 py-3 border-b bg-neutral-50 flex items-baseline justify-between">
          <h2 className="text-sm font-semibold text-neutral-900">Income Statement</h2>
          <span className="text-[11px] text-neutral-500">All numbers in TL thousands</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="text-neutral-500">
              <tr className="border-b">
                <th className="text-left py-2 pl-3 pr-3 font-medium">Breakdown</th>
                {periods.map((p) => (
                  <th key={p} className="text-right py-2 pl-2 pr-3 font-medium tabular-nums">
                    {periodToDate(p)}
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

      <p className="text-[11px] text-neutral-500 mt-3">
        Lines aligned by BRSA hierarchy code. &quot;--&quot; indicates the line was not
        reported for that period or did not extract. &quot;Total Assets&quot;,
        &quot;Total Liabilities&quot;, and &quot;Total Liabilities &amp; Equity&quot;
        are computed as sums of the Roman-numeral rows.
      </p>
    </main>
  );
}
