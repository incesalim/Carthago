/**
 * /banks/[ticker] — per-bank drill-down.
 *
 * Latest unconsolidated BS Assets + Liabilities + P&L as tables, plus a
 * Recent KAP disclosures widget. Period / kind selector lets the reader
 * walk back through quarters.
 */
import Link from "next/link";
import {
  bankPeriods,
  balanceSheet,
  profitLoss,
} from "@/app/lib/audit";
import { newsByTicker } from "@/app/lib/news";
import { notFound } from "next/navigation";

export const dynamic = "force-dynamic";

interface Props {
  params: Promise<{ ticker: string }>;
  searchParams: Promise<{ period?: string; kind?: string }>;
}

const fmtTl = (v: number | null) =>
  v == null ? "—" : new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(v);

export default async function BankDetailPage({ params, searchParams }: Props) {
  const { ticker: rawTicker } = await params;
  const sp = await searchParams;
  const ticker = rawTicker.toUpperCase();

  const periods = await bankPeriods(ticker);
  if (periods.length === 0) notFound();

  const period = sp.period ?? periods[0].period;
  const kind = (sp.kind as "consolidated" | "unconsolidated") ?? "unconsolidated";

  const [bs, pl, kapItems] = await Promise.all([
    balanceSheet(ticker, period, kind),
    profitLoss(ticker, period, kind),
    newsByTicker(ticker, 15),
  ]);

  const bsAssets = bs.filter((r) => r.statement === "assets");
  const bsLiab = bs.filter((r) => r.statement === "liabilities");
  const distinctPeriods = Array.from(new Set(periods.map((p) => p.period))).sort().reverse();

  return (
    <main className="px-8 py-8">
      <div className="flex items-baseline justify-between mb-2">
        <h1 className="text-3xl font-bold">{ticker}</h1>
        <Link href="/banks" className="text-sm text-neutral-500 hover:text-neutral-900">
          ← All banks
        </Link>
      </div>
      <p className="text-sm text-neutral-500 mb-6">
        Per-bank quarterly BRSA audit reports · values in TL thousands
      </p>

      {/* Period + kind selector */}
      <div className="mb-6 flex flex-wrap gap-3 items-center">
        <div className="flex flex-wrap gap-1 rounded-lg border bg-neutral-50 p-1">
          {distinctPeriods.slice(0, 8).map((p) => (
            <Link
              key={p}
              href={`/banks/${ticker}?period=${p}&kind=${kind}`}
              className={`px-2 py-1 text-xs rounded-md transition ${
                p === period
                  ? "bg-white shadow-sm font-medium text-neutral-900"
                  : "text-neutral-600 hover:text-neutral-900"
              }`}
            >
              {p}
            </Link>
          ))}
        </div>
        <div className="flex gap-1 rounded-lg border bg-neutral-50 p-1">
          {(["unconsolidated", "consolidated"] as const).map((k) => (
            <Link
              key={k}
              href={`/banks/${ticker}?period=${period}&kind=${k}`}
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
          <ul className="space-y-2 max-h-[280px] overflow-y-auto pr-1 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-x-4">
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

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* BS Assets */}
        <div className="rounded-lg border bg-white p-5 shadow-sm">
          <h2 className="text-sm font-semibold mb-2">
            Assets — {period} · {kind} ({bsAssets.length} rows)
          </h2>
          <div className="overflow-x-auto max-h-[600px]">
            <table className="w-full text-xs">
              <thead className="border-b text-neutral-500 sticky top-0 bg-white">
                <tr>
                  <th className="text-left py-1 pr-2 w-12">#</th>
                  <th className="text-left py-1 pr-2">Item</th>
                  <th className="text-right py-1 pl-2">TL</th>
                  <th className="text-right py-1 pl-2">FC</th>
                  <th className="text-right py-1 pl-2">Total</th>
                </tr>
              </thead>
              <tbody>
                {bsAssets.map((r) => (
                  <tr key={`${r.statement}_${r.item_order}`} className="border-b border-neutral-100">
                    <td className="py-0.5 pr-2 text-neutral-500 tabular-nums">{r.hierarchy}</td>
                    <td className="py-0.5 pr-2">{r.item_name}</td>
                    <td className="py-0.5 pl-2 text-right tabular-nums">{fmtTl(r.amount_tl)}</td>
                    <td className="py-0.5 pl-2 text-right tabular-nums">{fmtTl(r.amount_fc)}</td>
                    <td className="py-0.5 pl-2 text-right tabular-nums font-medium">{fmtTl(r.amount_total)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* P&L */}
        <div className="rounded-lg border bg-white p-5 shadow-sm">
          <h2 className="text-sm font-semibold mb-2">
            Income Statement — {period} · {kind} ({pl.length} rows)
          </h2>
          <div className="overflow-x-auto max-h-[600px]">
            <table className="w-full text-xs">
              <thead className="border-b text-neutral-500 sticky top-0 bg-white">
                <tr>
                  <th className="text-left py-1 pr-2 w-12">#</th>
                  <th className="text-left py-1 pr-2">Item</th>
                  <th className="text-right py-1 pl-2">Amount</th>
                </tr>
              </thead>
              <tbody>
                {pl.map((r) => (
                  <tr key={r.item_order} className="border-b border-neutral-100">
                    <td className="py-0.5 pr-2 text-neutral-500 tabular-nums">{r.hierarchy}</td>
                    <td className="py-0.5 pr-2">{r.item_name}</td>
                    <td className="py-0.5 pl-2 text-right tabular-nums font-medium">{fmtTl(r.amount)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* BS Liab */}
      <div className="mt-6 rounded-lg border bg-white p-5 shadow-sm">
        <h2 className="text-sm font-semibold mb-2">
          Liabilities & Equity — {period} · {kind} ({bsLiab.length} rows)
        </h2>
        <div className="overflow-x-auto max-h-[600px]">
          <table className="w-full text-xs">
            <thead className="border-b text-neutral-500 sticky top-0 bg-white">
              <tr>
                <th className="text-left py-1 pr-2 w-12">#</th>
                <th className="text-left py-1 pr-2">Item</th>
                <th className="text-right py-1 pl-2">TL</th>
                <th className="text-right py-1 pl-2">FC</th>
                <th className="text-right py-1 pl-2">Total</th>
              </tr>
            </thead>
            <tbody>
              {bsLiab.map((r) => (
                <tr key={r.item_order} className="border-b border-neutral-100">
                  <td className="py-0.5 pr-2 text-neutral-500 tabular-nums">{r.hierarchy}</td>
                  <td className="py-0.5 pr-2">{r.item_name}</td>
                  <td className="py-0.5 pl-2 text-right tabular-nums">{fmtTl(r.amount_tl)}</td>
                  <td className="py-0.5 pl-2 text-right tabular-nums">{fmtTl(r.amount_fc)}</td>
                  <td className="py-0.5 pl-2 text-right tabular-nums font-medium">{fmtTl(r.amount_total)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </main>
  );
}
