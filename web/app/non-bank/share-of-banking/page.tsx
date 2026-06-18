/**
 * Non-Bank → Share of Banking — how much of "banking business" the non-bank
 * credit sectors do. Three views:
 *   1. Asset share   — non-bank assets ÷ (banking + non-bank), KPI + trend.
 *   2. Credit share  — non-bank lending book ÷ (bank loans + non-bank), trend.
 *   3. Segment view  — each sector's lending book as a share of total bank loans.
 *
 * Same-source comparison (both BDDK bulletins, Million TL). Data: app/lib/non-bank.ts.
 */
import Link from "next/link";
import { getNonBankData } from "@/app/lib/non-bank";
import { PageHeader, Section, Stat } from "@/app/components/ui";
import TimeSeriesChart from "@/app/components/TimeSeriesChart";

export const dynamic = "force-dynamic";

const fmtTrn = (v: number | null) =>
  v == null ? "—" : `₺${new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(v / 1_000_000)} trn`;
const fmtPct = (v: number | null, d = 2) =>
  v == null ? "—" : `${new Intl.NumberFormat("en-US", { minimumFractionDigits: d, maximumFractionDigits: d }).format(v)}%`;

export default async function ShareOfBankingPage() {
  const d = await getNonBankData();
  const maxSegShare = Math.max(1, ...d.sectors.map((s) => s.shareOfBankLoans ?? 0));

  return (
    <main className="mx-auto w-full max-w-[1440px] px-4 py-8 sm:px-6 lg:px-8 space-y-8">
      <PageHeader
        title="Share of Banking"
        description="How much of banking business is done by non-bank lenders. Non-bank sectors (leasing, factoring, financing) measured against the BDDK banking-sector aggregate — both from BDDK, both Million TL, so the comparison is same-source and apples-to-apples."
        dataThrough={d.asOfPeriod || undefined}
      />

      {!d.hasData ? (
        <Section title="No data yet" description="The non-bank sector tables haven't been populated in D1 yet — run the backfill to see the comparison here.">
          <div />
        </Section>
      ) : (
        <>
          {/* View 1 — headline shares */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <Stat
              label="Share of banking assets"
              value={fmtPct(d.assetSharePct)}
              hint={`non-bank ÷ (banking + non-bank) · ${d.asOfLabel}`}
              tone="neutral"
            />
            <Stat
              label="Share of system credit"
              value={fmtPct(d.creditSharePct)}
              hint={`lending book ÷ (bank loans + non-bank) · ${d.asOfLabel}`}
              tone="neutral"
            />
            <Stat
              label="Non-bank lending book"
              value={fmtTrn(d.nbfiCredit)}
              hint={`vs. bank loans ${fmtTrn(d.bankCredit)}`}
              tone="neutral"
            />
          </div>

          {/* Views 1 & 2 — share trends */}
          <Section
            title="Penetration over time"
            description="Non-bank share of the financial system, monthly. 'Share of sector assets' is non-bank ÷ (banking + non-bank) total assets; 'share of sector credit' compares the non-bank lending book against bank loans + the non-bank book — the truer disintermediation measure."
          >
            <TimeSeriesChart
              series={d.shareTrend}
              title="Non-bank share of banking (%)"
              yFormat="pct"
              decimals={2}
              height={360}
            />
          </Section>

          {/* View 3 — segment vs bank lending */}
          <Section
            title="By segment"
            description={`Each non-bank sector's lending book as a share of total bank loans (${d.asOfLabel}). Each segment substitutes a different slice of bank credit: leasing ↔ equipment/capex loans, factoring ↔ working-capital, financing companies ↔ auto & consumer.`}
          >
            <div className="space-y-3">
              {d.sectors.map((s) => {
                const share = s.shareOfBankLoans ?? 0;
                return (
                  <div key={s.code} className="flex items-center gap-3">
                    <div className="w-36 shrink-0 text-sm text-foreground">{s.label}</div>
                    <div className="relative h-6 flex-1 overflow-hidden rounded bg-accent/40">
                      <div
                        className="absolute inset-y-0 left-0 rounded bg-primary/70"
                        style={{ width: `${(share / maxSegShare) * 100}%` }}
                      />
                    </div>
                    <div className="w-20 shrink-0 text-right text-sm tabular-nums text-foreground">
                      {fmtPct(share)}
                    </div>
                  </div>
                );
              })}
            </div>
            <p className="text-xs text-muted-foreground">
              Share of total bank loans ({fmtTrn(d.bankCredit)}). Bars scaled to the largest segment.
            </p>
          </Section>

          <p className="text-xs text-muted-foreground">
            Scope: the three credit-substitution sectors. Asset-management (VYŞ) is excluded — it&apos;s a{" "}
            <em>complement</em> to banking (it buys NPLs from banks, it doesn&apos;t substitute lending) —
            and savings-finance isn&apos;t carried in this BDDK bulletin. Including both would add ≈0.8pp.{" "}
            <Link href="/non-bank" className="text-primary hover:underline">
              ← Non-Bank overview
            </Link>
          </p>
        </>
      )}
    </main>
  );
}
