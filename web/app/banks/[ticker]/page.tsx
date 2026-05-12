/**
 * /banks/[ticker] — per-bank drill-down.
 *
 * Standardized financial tables (Balance Sheet + Income Statement) with
 * up to four periods side-by-side. View modes:
 *   ?view=annual    → most recent Q4s (default; comparable year-end data)
 *   ?view=quarterly → most recent quarters (sequential)
 *
 * Line items are pulled by BRSA hierarchy code (I, II, III, …) and
 * rendered with our canonical English labels — see
 * web/app/lib/standard_lines.ts. Raw `item_name` from the database is
 * never displayed (it's noisy: mixes TR / EN, has extraction artefacts,
 * uses different terms for participation banks).
 */
import Link from "next/link";
import {
  bankPeriods,
  balanceSheetMultiPeriod,
  profitLossMultiPeriod,
} from "@/app/lib/audit";
import { newsByTicker } from "@/app/lib/news";
import {
  BS_ASSET_LINES,
  BS_LIAB_LINES,
  PL_LINES,
  type StandardLine,
} from "@/app/lib/standard_lines";
import { notFound } from "next/navigation";

export const dynamic = "force-dynamic";

interface Props {
  params: Promise<{ ticker: string }>;
  searchParams: Promise<{ view?: string; kind?: string }>;
}

const fmtTl = (v: number | null | undefined) =>
  v == null
    ? "—"
    : new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(v);

/** Pick the periods to display based on view mode. */
function pickPeriods(allPeriods: string[], view: "annual" | "quarterly", count = 4): string[] {
  if (view === "annual") {
    // Only Q4 of each year, most recent first
    const q4 = allPeriods.filter((p) => p.endsWith("Q4"));
    return q4.slice(0, count);
  }
  return allPeriods.slice(0, count);
}

/** Render a multi-period row for a single StandardLine. */
function FinRow({
  line,
  pivot,
  periods,
  statement,
}: {
  line: StandardLine;
  pivot: Map<string, Map<string, number | null>>;
  periods: string[];
  /** Only used for BS rows — "assets" | "liabilities". P&L pass empty string. */
  statement: string;
}) {
  const key = statement ? `${statement}::${line.hierarchy}` : line.hierarchy;
  const periodMap = pivot.get(key) ?? new Map();
  return (
    <tr className={line.isTotal ? "border-y border-neutral-300 bg-neutral-50" : "border-b border-neutral-100"}>
      <td className={`py-1.5 pr-3 text-xs ${line.isTotal ? "font-semibold text-neutral-900" : "text-neutral-700"}`}>
        {line.label}
      </td>
      {periods.map((p) => (
        <td
          key={p}
          className={`py-1.5 pl-2 text-right text-xs tabular-nums ${
            line.isTotal ? "font-semibold text-neutral-900" : "text-neutral-800"
          }`}
        >
          {fmtTl(periodMap.get(p))}
        </td>
      ))}
    </tr>
  );
}

/** Section sub-header inside the BS table (Assets / Liabilities & Equity). */
function SectionHeader({ label, span }: { label: string; span: number }) {
  return (
    <tr className="bg-neutral-100">
      <td
        colSpan={span}
        className="py-2 px-3 text-[11px] font-semibold uppercase tracking-wide text-neutral-600"
      >
        {label}
      </td>
    </tr>
  );
}

export default async function BankDetailPage({ params, searchParams }: Props) {
  const { ticker: rawTicker } = await params;
  const sp = await searchParams;
  const ticker = rawTicker.toUpperCase();

  const allPeriodMeta = await bankPeriods(ticker);
  if (allPeriodMeta.length === 0) notFound();

  const kind = (sp.kind as "consolidated" | "unconsolidated") ?? "unconsolidated";
  const view = (sp.view as "annual" | "quarterly") ?? "annual";

  // Distinct periods available for this (ticker, kind), most recent first
  const allPeriods = Array.from(
    new Set(allPeriodMeta.filter((p) => p.kind === kind).map((p) => p.period)),
  ).sort().reverse();

  const periods = pickPeriods(allPeriods, view, 4);

  const [bsPivot, plPivot, kapItems] = await Promise.all([
    balanceSheetMultiPeriod(ticker, kind, periods),
    profitLossMultiPeriod(ticker, kind, periods),
    newsByTicker(ticker, 12),
  ]);

  const periodColSpan = periods.length + 1;

  return (
    <main className="px-8 py-8 max-w-6xl">
      {/* Header */}
      <div className="flex items-baseline justify-between mb-2">
        <h1 className="text-3xl font-bold">{ticker}</h1>
        <Link href="/banks" className="text-sm text-neutral-500 hover:text-neutral-900">
          ← All banks
        </Link>
      </div>
      <p className="text-sm text-neutral-500 mb-6">
        Standardized per-bank financials from quarterly BRSA reports · values in TL thousands
      </p>

      {/* View toggles: annual / quarterly + kind */}
      <div className="mb-6 flex flex-wrap gap-3 items-center">
        <div className="flex gap-1 rounded-lg border bg-neutral-50 p-1">
          {(["annual", "quarterly"] as const).map((v) => (
            <Link
              key={v}
              href={`/banks/${ticker}?view=${v}&kind=${kind}`}
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
              href={`/banks/${ticker}?view=${view}&kind=${k}`}
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

      {/* Balance Sheet (Assets + Liabilities + Equity in one table) */}
      <section className="mb-6 rounded-lg border bg-white shadow-sm overflow-hidden">
        <div className="px-5 py-3 border-b bg-neutral-50">
          <h2 className="text-sm font-semibold text-neutral-900">Balance Sheet</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="border-b text-neutral-500">
              <tr>
                <th className="text-left py-2 px-3 font-medium">Line</th>
                {periods.map((p) => (
                  <th key={p} className="text-right py-2 pl-2 pr-3 font-medium tabular-nums">
                    {p}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              <SectionHeader label="Assets" span={periodColSpan} />
              {BS_ASSET_LINES.map((line) => (
                <FinRow
                  key={line.id}
                  line={line}
                  pivot={bsPivot}
                  periods={periods}
                  statement="assets"
                />
              ))}
              <SectionHeader label="Liabilities & Equity" span={periodColSpan} />
              {BS_LIAB_LINES.map((line) => (
                <FinRow
                  key={line.id}
                  line={line}
                  pivot={bsPivot}
                  periods={periods}
                  statement="liabilities"
                />
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Income Statement */}
      <section className="rounded-lg border bg-white shadow-sm overflow-hidden">
        <div className="px-5 py-3 border-b bg-neutral-50">
          <h2 className="text-sm font-semibold text-neutral-900">Income Statement</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="border-b text-neutral-500">
              <tr>
                <th className="text-left py-2 px-3 font-medium">Line</th>
                {periods.map((p) => (
                  <th key={p} className="text-right py-2 pl-2 pr-3 font-medium tabular-nums">
                    {p}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {PL_LINES.map((line) => (
                <FinRow
                  key={line.id}
                  line={line}
                  pivot={plPivot}
                  periods={periods}
                  statement=""
                />
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Coverage note */}
      <p className="text-[11px] text-neutral-500 mt-3">
        Lines aligned by BRSA hierarchy code (Roman numeral). &quot;—&quot; means the
        line was not reported for that period or did not extract cleanly. Items shown in bold
        are subtotals / totals from the BRSA template.
      </p>
    </main>
  );
}
