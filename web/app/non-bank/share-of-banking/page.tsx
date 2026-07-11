/**
 * Non-Bank → Share of Banking — how much of "banking business" the non-bank
 * credit sectors do. Three views:
 *   1. Asset share   — non-bank assets ÷ (banking + non-bank), KPI + trend.
 *   2. Credit share  — non-bank lending book ÷ (bank loans + non-bank), trend.
 *   3. Segment view  — each sector's lending book as a share of total bank loans.
 *
 * Same-source comparison (both BDDK bulletins, Million TL). Data: app/lib/non-bank.ts.
 */
import type { Metadata } from "next";
import Link from "next/link";
import { getNonBankData, type Point } from "@/app/lib/non-bank";
import { Section, Stat } from "@/app/components/ui";
import {
  ChartRow,
  Colophon,
  Depth,
  DeskHeader,
  SecHead,
  Vital,
  Vitals,
} from "@/app/components/desk";
import { lastVal, monthLabel, signedPp, valAgo } from "@/app/lib/desk";
import { GlobalRangeSelector } from "@/app/components/range-context";
import TimeSeriesChart from "@/app/components/TimeSeriesChart";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Non-Bank Finance — Share of Banking",
  description: "How large Türkiye's leasing, factoring and financing sector is relative to total bank assets.",
  alternates: { canonical: "/non-bank/share-of-banking" },
};

const fmtTrn = (v: number | null) =>
  v == null ? "—" : `₺${new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(v / 1_000_000)} trn`;
const fmtPct = (v: number | null, d = 2) =>
  v == null ? "—" : `${new Intl.NumberFormat("en-US", { minimumFractionDigits: d, maximumFractionDigits: d }).format(v)}%`;

/** {label → Point[]} trend map → long-form {period, bank_type_code, value} for ChartRow. */
function trendToLong(trend: Record<string, Point[]>): { period: string; bank_type_code: string; value: number | null }[] {
  const out: { period: string; bank_type_code: string; value: number | null }[] = [];
  for (const [label, points] of Object.entries(trend)) {
    for (const p of points) out.push({ period: p.period_date, bank_type_code: label, value: p.value });
  }
  return out.sort((a, b) => a.period.localeCompare(b.period));
}

export default async function ShareOfBankingPage() {
  const d = await getNonBankData();
  const maxSegShare = Math.max(1, ...d.sectors.map((s) => s.shareOfBankLoans ?? 0));

  // ---- the brief's computed vitals -----------------------------------------
  const assetShareSeries = (d.shareTrend["Share of sector assets"] ?? []).map((p) => ({
    period: p.period_date,
    value: p.value,
  }));
  const creditShareSeries = (d.shareTrend["Share of sector credit"] ?? []).map((p) => ({
    period: p.period_date,
    value: p.value,
  }));
  const assetShareNow = lastVal(assetShareSeries);
  const assetShareAgo = valAgo(assetShareSeries, 12);
  const assetShareD = assetShareNow != null && assetShareAgo != null ? assetShareNow - assetShareAgo : null;
  const creditShareNow = lastVal(creditShareSeries);
  const creditShareAgo = valAgo(creditShareSeries, 12);
  const creditShareD = creditShareNow != null && creditShareAgo != null ? creditShareNow - creditShareAgo : null;

  // The bank book expressed as a multiple of the non-bank lending book.
  const bankMultiple = d.nbfiCredit > 0 && d.bankCredit > 0 ? d.bankCredit / d.nbfiCredit : null;

  const topSegment =
    d.sectors
      .filter((s) => s.shareOfBankLoans != null)
      .sort((a, b) => (b.shareOfBankLoans as number) - (a.shareOfBankLoans as number))[0] ?? null;

  const shareLong = trendToLong(d.shareTrend);

  return (
    <main className="mx-auto w-full max-w-[1440px] px-4 py-7 sm:px-6 lg:px-9">
      <DeskHeader
        title="Share of Banking"
        record={
          d.hasData ? (
            <>
              Record <b className="font-normal text-foreground">{monthLabel(d.asOfPeriod)}</b> · monthly — non-bank vs
              banking aggregate, same source
            </>
          ) : undefined
        }
        right="every figure computed from source series"
      />

      {!d.hasData ? (
        <Section
          className="mt-6"
          title="No data yet"
          description="The non-bank sector tables haven't been populated in D1 yet — run the backfill to see the comparison here."
        >
          <div />
        </Section>
      ) : (
        <>
          <SecHead title="The vitals" meta="assets · credit · segments" className="mb-2.5 mt-6" />
          <Vitals cols={4}>
            <Vital
              label="Share of banking assets"
              value={d.assetSharePct != null ? d.assetSharePct.toFixed(2) : "—"}
              unit="%"
              series={assetShareSeries.slice(-13)}
              decimals={2}
              note={
                assetShareD != null
                  ? `${signedPp(assetShareD, 2)} over 12m — non-bank ÷ (banking + non-bank)`
                  : "non-bank ÷ (banking + non-bank)"
              }
            />
            <Vital
              label="Share of system credit"
              value={d.creditSharePct != null ? d.creditSharePct.toFixed(2) : "—"}
              unit="%"
              series={creditShareSeries.slice(-13)}
              decimals={2}
              note={
                creditShareD != null
                  ? `${signedPp(creditShareD, 2)} over 12m — the truer disintermediation measure`
                  : "lending book ÷ (bank loans + non-bank)"
              }
            />
            <Vital
              label="Non-bank lending book"
              value={d.nbfiCredit > 0 ? `₺${(d.nbfiCredit / 1_000_000).toFixed(2)}` : "—"}
              unit="trn"
              note={
                bankMultiple != null
                  ? `bank loans ${fmtTrn(d.bankCredit)} — ${bankMultiple.toFixed(0)}× the non-bank book`
                  : `vs bank loans ${fmtTrn(d.bankCredit)}`
              }
            />
            <Vital
              label="Top segment vs bank loans"
              value={topSegment?.shareOfBankLoans != null ? topSegment.shareOfBankLoans.toFixed(2) : "—"}
              unit="%"
              note={
                topSegment ? (
                  <>
                    {topSegment.label} — largest slice of bank credit substituted{" "}
                    <Link href="/non-bank" className="font-semibold text-primary">
                      /non-bank
                    </Link>
                  </>
                ) : undefined
              }
            />
          </Vitals>

          <Depth action={<GlobalRangeSelector />}>
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
              index="01"
              title="Penetration over time"
              description="Non-bank share of the financial system, monthly. 'Share of sector assets' is non-bank ÷ (banking + non-bank) total assets; 'share of sector credit' compares the non-bank lending book against bank loans + the non-bank book — the truer disintermediation measure."
            >
              <ChartRow
                data={shareLong}
                labels={{
                  "Share of sector assets": "Sector assets",
                  "Share of sector credit": "Sector credit",
                }}
                deltaPeriods={12}
                deltaLabel="12m"
                fmt={(v) => `${v.toFixed(2)}%`}
              >
                <TimeSeriesChart
                  series={d.shareTrend}
                  title="Non-bank share of banking (%)"
                  yFormat="pct"
                  decimals={2}
                  height={360}
                />
              </ChartRow>
            </Section>

            {/* View 3 — segment vs bank lending */}
            <Section
              index="02"
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
          </Depth>
        </>
      )}

      <Colophon />
    </main>
  );
}
