/**
 * Non-Bank Financial Institutions — overview.
 *
 * BDDK-supervised non-bank sectors that compete with bank lending: financial
 * leasing, factoring, and financing companies (the credit-substitution group).
 * Data: app/lib/non-bank.ts (BDDK BultenAylikBdmk monthly bulletin). The
 * "Share of Banking" sub-page quantifies their penetration of bank business.
 */
import Link from "next/link";
import { getNonBankData, type SectorLatest } from "@/app/lib/non-bank";
import { PageHeader, Section, Stat } from "@/app/components/ui";
import StackedArea from "@/app/components/StackedArea";

export const dynamic = "force-dynamic";

const fmtTrn = (v: number | null) =>
  v == null ? "—" : `₺${new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(v / 1_000_000)} trn`;
const fmtBn = (v: number | null) =>
  v == null ? "—" : `₺${new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(v / 1_000)} bn`;
const fmtPct = (v: number | null, d = 1) =>
  v == null ? "—" : `${new Intl.NumberFormat("en-US", { minimumFractionDigits: d, maximumFractionDigits: d }).format(v)}%`;

export default async function NonBankPage() {
  const d = await getNonBankData();

  return (
    <main className="mx-auto w-full max-w-[1440px] px-4 py-8 sm:px-6 lg:px-8 space-y-8">
      <PageHeader
        title="Non-Bank Financial Institutions"
        description="BDDK-supervised non-bank lenders that compete with banks for credit: financial leasing, factoring, and financing companies. Aggregate sector balance sheets from the BDDK monthly bulletin (BultenAylikBdmk), in Million TL."
        dataThrough={d.asOfPeriod || undefined}
      />

      {!d.hasData ? (
        <Section title="No data yet" description="The non-bank sector tables haven't been populated in D1 yet — run the backfill to see the sector here.">
          <div />
        </Section>
      ) : (
        <>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <Stat
              label="Non-bank sector assets"
              value={fmtTrn(d.nbfiAssets)}
              hint={`3 sectors · ${d.asOfLabel}`}
              tone="neutral"
            />
            <Stat
              label="Share of banking assets"
              value={fmtPct(d.assetSharePct, 2)}
              hint="non-bank ÷ (banking + non-bank)"
              tone="neutral"
            />
            <Stat
              label="Lending book"
              value={fmtTrn(d.nbfiCredit)}
              hint={`amortized-cost financing · ${d.asOfLabel}`}
              tone="neutral"
            />
          </div>

          <Section
            title="Sector size over time"
            description="Total assets of each non-bank sector, Million TL, stacked. Monthly, from 2020 (where the banking aggregate begins)."
          >
            <StackedArea
              data={d.sectorAssetsStack}
              series={[
                { key: "leasing", label: "Financial leasing" },
                { key: "factoring", label: "Factoring" },
                { key: "financing", label: "Financing cos." },
              ]}
              title="Non-bank sector assets (₺ bn, stacked)"
              yFormat="bn"
              colorKeys
            />
          </Section>

          <Section
            title="By sector"
            description={`Snapshot at ${d.asOfLabel}. The lending book is the sector's amortized-cost financial assets (factoring receivables / lease receivables / financing loans). YoY is the change in total assets vs. a year earlier.`}
          >
            <div className="overflow-x-auto rounded-lg border border-border">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border bg-accent/40 text-left text-xs text-muted-foreground">
                    <th className="px-3 py-2 font-medium">Sector</th>
                    <th className="px-3 py-2 text-right font-medium">Assets (₺ bn)</th>
                    <th className="px-3 py-2 text-right font-medium">Lending book (₺ bn)</th>
                    <th className="px-3 py-2 text-right font-medium">Equity (₺ bn)</th>
                    <th className="px-3 py-2 text-right font-medium">YoY assets</th>
                  </tr>
                </thead>
                <tbody>
                  {d.sectors.map((s: SectorLatest) => (
                    <tr key={s.code} className="border-b border-border/60 last:border-0">
                      <td className="px-3 py-2 text-foreground">{s.label}</td>
                      <td className="px-3 py-2 text-right tabular-nums text-foreground">{fmtBn(s.assets)}</td>
                      <td className="px-3 py-2 text-right tabular-nums text-foreground">{fmtBn(s.credit)}</td>
                      <td className="px-3 py-2 text-right tabular-nums text-foreground">{fmtBn(s.equity)}</td>
                      <td
                        className={`px-3 py-2 text-right tabular-nums ${
                          s.growthYoY == null
                            ? "text-muted-foreground"
                            : s.growthYoY < 0
                              ? "text-negative"
                              : "text-positive"
                        }`}
                      >
                        {fmtPct(s.growthYoY)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="text-xs text-muted-foreground">
              Want the penetration view?{" "}
              <Link href="/non-bank/share-of-banking" className="text-primary hover:underline">
                Share of Banking →
              </Link>
            </p>
          </Section>

          <p className="text-xs text-muted-foreground">
            Scope: the three credit-substitution sectors. Asset-management (VYŞ) — a complement that
            buys NPLs from banks — and savings-finance are not included here. Source: BDDK monthly
            bulletin (BultenAylikBdmk); reconciles to FKB published sector totals.
          </p>
        </>
      )}
    </main>
  );
}
