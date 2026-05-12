/**
 * /banks — index of all banks with audit-data coverage.
 *
 * Click a bank to drill into its quarterly BS + P&L. Each per-bank
 * page also surfaces its recent KAP disclosures, and /disclosures
 * (cross-bank) is reachable from the header link.
 */
import Link from "next/link";
import { bankSummaries } from "@/app/lib/audit";
import { BANK_NAMES } from "@/app/lib/bank_names";

export const dynamic = "force-dynamic";

export default async function BanksPage() {
  const banks = await bankSummaries();

  return (
    <main className="px-8 py-8">
      <h1 className="text-2xl font-semibold tracking-tight mb-1">Banks</h1>
      <p className="text-sm text-neutral-500 mb-2">
        {banks.length} banks · per-bank quarterly BRSA audit reports
      </p>
      <div className="flex flex-wrap gap-4 text-xs text-neutral-500 mb-6">
        <Link
          href="/disclosures"
          className="text-neutral-600 underline hover:text-neutral-900"
        >
          Recent KAP disclosures (all banks) →
        </Link>
        <Link
          href="/regulation"
          className="text-neutral-600 underline hover:text-neutral-900"
        >
          TCMB &amp; BDDK regulation →
        </Link>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {banks.map((b) => (
          <Link
            key={b.bank_ticker}
            href={`/banks/${b.bank_ticker}`}
            className="block rounded-lg border bg-white p-4 hover:bg-neutral-50 transition"
          >
            <div className="flex items-baseline justify-between">
              <div className="font-medium">{BANK_NAMES[b.bank_ticker] ?? b.bank_ticker}</div>
              <div className="text-xs text-neutral-400 tabular-nums">{b.bank_ticker}</div>
            </div>
            <div className="text-xs text-neutral-500 mt-1">
              {b.periods} quarters · latest {b.latest_period}
            </div>
          </Link>
        ))}
      </div>
    </main>
  );
}
