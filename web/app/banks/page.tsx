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
import { PageHeader } from "@/app/components/ui";

export const dynamic = "force-dynamic";

export default async function BanksPage() {
  const banks = await bankSummaries();

  return (
    <main className="mx-auto w-full max-w-[1440px] px-4 py-8 sm:px-6 lg:px-8">
      <PageHeader
        title="Banks"
        description={`${banks.length} banks · per-bank quarterly BRSA audit reports`}
        className="mb-3"
      />
      <div className="flex flex-wrap gap-4 text-xs text-muted-foreground mb-6">
        <Link
          href="/disclosures"
          className="text-muted-foreground underline hover:text-foreground"
        >
          Recent KAP disclosures (all banks) →
        </Link>
        <Link
          href="/regulation"
          className="text-muted-foreground underline hover:text-foreground"
        >
          TCMB &amp; BDDK regulation →
        </Link>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {banks.map((b) => (
          <Link
            key={b.bank_ticker}
            href={`/banks/${b.bank_ticker}`}
            className="block rounded-lg border bg-card p-4 hover:bg-accent transition"
          >
            <div className="flex items-baseline justify-between">
              <div className="font-medium">{BANK_NAMES[b.bank_ticker] ?? b.bank_ticker}</div>
              <div className="text-xs text-muted-foreground tabular-nums">{b.bank_ticker}</div>
            </div>
            <div className="text-xs text-muted-foreground mt-1">
              {b.periods} quarters · latest {b.latest_period}
            </div>
          </Link>
        ))}
      </div>
    </main>
  );
}
