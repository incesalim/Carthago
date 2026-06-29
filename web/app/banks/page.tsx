/**
 * /banks — index of all banks with audit-data coverage.
 *
 * Banks are grouped by their BDDK type and, within each group, ordered by
 * latest total assets (largest first). Click a bank to drill into its
 * quarterly BS + P&L. Each per-bank page also surfaces its recent KAP
 * disclosures, and /disclosures (cross-bank) is reachable from the header link.
 */
import Link from "next/link";
import { bankSummaries, type BankSummary } from "@/app/lib/audit";
import { BANK_NAMES, BANK_TYPE_BY_TICKER, BANK_TYPE_BADGE_LABELS } from "@/app/lib/bank_names";
import { PageHeader } from "@/app/components/ui";
import BankTypeBadge from "@/app/components/BankTypeBadge";

export const dynamic = "force-dynamic";

// Section order, top to bottom. Codes: 10006 State · 10005 Private·Domestic ·
// 10007 Private·Foreign · 10003 Participation · 10004 Dev & Inv. Within each
// section, banks sort by latest total assets (desc).
const GROUP_ORDER = ["10006", "10005", "10007", "10003", "10004"];

export default async function BanksPage() {
  const banks = await bankSummaries();
  const through = banks.reduce(
    (m, b) => (b.latest_period > m ? b.latest_period : m),
    "",
  );

  // Bucket by BDDK type, then sort each bucket by total assets (desc, nulls last).
  const byType = new Map<string, BankSummary[]>();
  for (const b of banks) {
    const code = BANK_TYPE_BY_TICKER[b.bank_ticker] ?? "other";
    const bucket = byType.get(code) ?? [];
    bucket.push(b);
    byType.set(code, bucket);
  }
  for (const bucket of byType.values()) {
    bucket.sort((a, b) => (b.total_assets ?? -1) - (a.total_assets ?? -1));
  }
  // Known groups in GROUP_ORDER first; any unmapped ("other") fall to the end.
  const codes = [
    ...GROUP_ORDER.filter((c) => byType.has(c)),
    ...[...byType.keys()].filter((c) => !GROUP_ORDER.includes(c)),
  ];

  return (
    <main className="mx-auto w-full max-w-[1440px] px-4 py-8 sm:px-6 lg:px-8">
      <PageHeader
        title="Banks"
        description={`${banks.length} banks · per-bank quarterly BRSA audit reports`}
        dataThrough={through || undefined}
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

      <div className="space-y-8">
        {codes.map((code) => {
          const group = byType.get(code)!;
          const label = BANK_TYPE_BADGE_LABELS[code] ?? "Other";
          return (
            <section key={code}>
              <div className="mb-3 flex items-baseline gap-2">
                <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  {label}
                </h2>
                <span className="text-xs tabular-nums text-muted-foreground/60">
                  {group.length}
                </span>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {group.map((b) => {
                  const typeCode = BANK_TYPE_BY_TICKER[b.bank_ticker];
                  return (
                    <Link
                      key={b.bank_ticker}
                      href={`/banks/${b.bank_ticker}`}
                      className="block rounded-2xl border border-border bg-card p-4 transition-colors hover:border-primary/40"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex items-center gap-2 min-w-0">
                          <span className="font-semibold truncate">{BANK_NAMES[b.bank_ticker] ?? b.bank_ticker}</span>
                          {typeCode && (
                            <BankTypeBadge code={typeCode} label={BANK_TYPE_BADGE_LABELS[typeCode]} />
                          )}
                        </div>
                        <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[11px] font-semibold tabular-nums text-primary shrink-0">
                          {b.bank_ticker}
                        </span>
                      </div>
                      <div className="text-xs text-muted-foreground mt-1">
                        {b.periods} quarters · latest {b.latest_period}
                      </div>
                    </Link>
                  );
                })}
              </div>
            </section>
          );
        })}
      </div>
    </main>
  );
}
