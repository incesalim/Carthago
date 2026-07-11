/**
 * Non-Bank Financial Institutions — overview.
 *
 * BDDK-supervised non-bank sectors that compete with bank lending: financial
 * leasing, factoring, and financing companies (the credit-substitution group).
 * Data: app/lib/non-bank.ts (BDDK BultenAylikBdmk monthly bulletin). The
 * "Share of Banking" sub-page quantifies their penetration of bank business.
 */
import type { Metadata } from "next";
import Link from "next/link";
import { getNonBankData, SECTORS, type SectorLatest } from "@/app/lib/non-bank";
import {
  Section,
  Stat,
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
  TableCellNum,
  toneFor,
} from "@/app/components/ui";
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
import StackedArea, { type StackPoint } from "@/app/components/StackedArea";
import { nf } from "@/app/lib/chart-format";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Turkish Non-Bank Financial Sector",
  description: "Türkiye's non-bank financial sector — leasing, factoring and financing companies and their size relative to banks.",
  alternates: { canonical: "/non-bank" },
};

const fmtTrn = (v: number | null) => (v == null ? "—" : `₺${nf(v / 1_000_000, 2)} trn`);
const fmtBn = (v: number | null) => (v == null ? "—" : `₺${nf(v / 1_000, 0)} bn`);
const fmtPct = (v: number | null, d = 1) => (v == null ? "—" : `${nf(v, d)}%`);

/** Wide StackedArea rows → long-form {period, bank_type_code, value} for ChartRow. */
function stackToLong(stack: StackPoint[]): { period: string; bank_type_code: string; value: number | null }[] {
  const out: { period: string; bank_type_code: string; value: number | null }[] = [];
  for (const row of stack) {
    for (const s of SECTORS) {
      const v = row[s.code];
      out.push({
        period: String(row.period),
        bank_type_code: s.code,
        value: typeof v === "number" ? v : null,
      });
    }
  }
  return out;
}

export default async function NonBankPage() {
  const d = await getNonBankData();

  // ---- the brief's computed vitals -----------------------------------------
  // Total non-bank assets per period = sum of the three sectors (Million TL).
  const totalAssets = d.sectorAssetsStack.map((r) => ({
    period: String(r.period),
    value: SECTORS.reduce((sum, s) => {
      const v = r[s.code];
      return sum + (typeof v === "number" ? v : 0);
    }, 0),
  }));
  const assetsNow = lastVal(totalAssets);
  const assetsAgo = valAgo(totalAssets, 12);
  const assetsYoY = assetsNow != null && assetsAgo != null && assetsAgo > 0 ? (assetsNow / assetsAgo - 1) * 100 : null;

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

  const largest = d.sectors.length > 0 ? d.sectors.reduce((a, b) => (b.assets > a.assets ? b : a)) : null;
  const largestShare = largest && d.nbfiAssets > 0 ? (100 * largest.assets) / d.nbfiAssets : null;
  const fastest =
    d.sectors
      .filter((s) => s.growthYoY != null)
      .sort((a, b) => (b.growthYoY as number) - (a.growthYoY as number))[0] ?? null;

  const stackLong = stackToLong(d.sectorAssetsStack);

  return (
    <main className="mx-auto w-full max-w-[1440px] px-4 py-7 sm:px-6 lg:px-9">
      <DeskHeader
        title="Non-Bank Financial Institutions"
        record={
          d.hasData ? (
            <>
              Record <b className="font-normal text-foreground">{monthLabel(d.asOfPeriod)}</b> · monthly — leasing ·
              factoring · financing
            </>
          ) : undefined
        }
        right="every figure computed from source series"
      />

      {!d.hasData ? (
        <Section
          className="mt-6"
          title="No data yet"
          description="The non-bank sector tables haven't been populated in D1 yet — run the backfill to see the sector here."
        >
          <div />
        </Section>
      ) : (
        <>
          <SecHead title="The vitals" meta="level · penetration · mix · momentum" className="mb-2.5 mt-6" />
          <Vitals cols={5}>
            <Vital
              label="Non-bank assets"
              value={`₺${nf(d.nbfiAssets / 1_000_000, 2)}`}
              unit="trn"
              series={totalAssets.slice(-13)}
              format="trn"
              decimals={2}
              note={
                assetsYoY != null ? (
                  <>
                    {assetsYoY >= 0 ? "+" : "−"}
                    {Math.abs(assetsYoY).toFixed(1)}% y/y — leasing + factoring + financing
                  </>
                ) : (
                  "leasing + factoring + financing"
                )
              }
            />
            <Vital
              label="Share of banking assets"
              value={d.assetSharePct != null ? d.assetSharePct.toFixed(2) : "—"}
              unit="%"
              series={assetShareSeries.slice(-13)}
              decimals={2}
              note={
                <>
                  {assetShareD != null ? `${signedPp(assetShareD, 2)} over 12m — ` : ""}
                  <Link href="/non-bank/share-of-banking" className="font-semibold text-primary">
                    /non-bank/share-of-banking
                  </Link>
                </>
              }
            />
            <Vital
              label="Share of system credit"
              value={d.creditSharePct != null ? d.creditSharePct.toFixed(2) : "—"}
              unit="%"
              series={creditShareSeries.slice(-13)}
              decimals={2}
              note={
                <>
                  book {fmtTrn(d.nbfiCredit)} vs bank loans {fmtTrn(d.bankCredit)}
                </>
              }
            />
            <Vital
              label="Largest segment"
              value={largestShare != null ? largestShare.toFixed(0) : "—"}
              unit="%"
              note={largest ? <>{largest.label} — {fmtBn(largest.assets)} of the sector&rsquo;s assets</> : undefined}
            />
            <Vital
              label="Fastest growth, y/y"
              value={fastest?.growthYoY != null ? fastest.growthYoY.toFixed(1) : "—"}
              unit="%"
              note={fastest ? <>{fastest.label} — assets vs a year earlier</> : undefined}
            />
          </Vitals>

          <Depth action={<GlobalRangeSelector />}>
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
              index="01"
              title="Sector size over time"
              description="Total assets of each non-bank sector, Million TL, stacked. Monthly, from 2020 (where the banking aggregate begins)."
            >
              <ChartRow
                data={stackLong}
                labels={Object.fromEntries(SECTORS.map((s) => [s.code, s.label]))}
                deltaPeriods={12}
                deltaLabel="12m"
                fmt={(v) => `₺${nf(v / 1_000, 0)} bn`}
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
              </ChartRow>
            </Section>

            <Section
              index="02"
              title="By sector"
              description={`Snapshot at ${d.asOfLabel}. The lending book is the sector's amortized-cost financial assets (factoring receivables / lease receivables / financing loans). YoY is the change in total assets vs. a year earlier.`}
            >
              <Table wrapperClassName="rounded-[10px] border border-border bg-card">
                <TableHeader>
                  <TableRow className="bg-muted/50">
                    <TableHead>Sector</TableHead>
                    <TableHead className="text-right">Assets (₺ bn)</TableHead>
                    <TableHead className="text-right">Lending book (₺ bn)</TableHead>
                    <TableHead className="text-right">Equity (₺ bn)</TableHead>
                    <TableHead className="text-right">YoY assets</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {d.sectors.map((s: SectorLatest) => (
                    <TableRow key={s.code}>
                      <TableCell>{s.label}</TableCell>
                      <TableCellNum>{fmtBn(s.assets)}</TableCellNum>
                      <TableCellNum>{fmtBn(s.credit)}</TableCellNum>
                      <TableCellNum>{fmtBn(s.equity)}</TableCellNum>
                      {/* Growth column: green genuinely means "good" here. */}
                      <TableCellNum
                        tone={
                          s.growthYoY != null && s.growthYoY > 0
                            ? "positive"
                            : toneFor(s.growthYoY)
                        }
                      >
                        {fmtPct(s.growthYoY)}
                      </TableCellNum>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
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
          </Depth>
        </>
      )}

      <Colophon />
    </main>
  );
}
