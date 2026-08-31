/**
 * Non-Bank Financial Institutions — overview.
 *
 * BDDK-supervised non-bank sectors that compete with bank lending: financial
 * leasing, factoring, and financing companies (the credit-substitution group).
 * Data: app/lib/non-bank.ts (BDDK BultenAylikBdmk monthly bulletin). The
 * "Share of Banking" sub-page quantifies their penetration of bank business.
 */
import { localizeMetadata } from "@/i18n/metadata";
import { getText } from "@/i18n/server";
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

const pageMetadata: Metadata = {
  title: "Turkish Non-Bank Financial Sector",
  description: "Türkiye's non-bank financial sector — leasing, factoring and financing companies and their size relative to banks.",
  alternates: { canonical: "/non-bank" },
};

export async function generateMetadata(): Promise<Metadata> {
  return localizeMetadata(pageMetadata);
}

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
  const tx = await getText();
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
        title={tx("Non-Bank Financial Institutions")}
        record={
          d.hasData ? (
            <>{tx("Record ")}<b className="font-normal text-foreground">{tx(monthLabel(d.asOfPeriod))}</b>{tx(" · monthly — leasing · factoring · financing")}</>
          ) : undefined
        }
        right="every figure computed from source series"
      />

      {!d.hasData ? (
        <Section
          className="mt-6"
          title={tx("No data yet")}
          description={tx("The non-bank sector tables haven't been populated in D1 yet — run the backfill to see the sector here.")}
        >
          <div />
        </Section>
      ) : (
        <>
          <SecHead title={tx("The vitals")} meta={tx("level · penetration · mix · momentum")} className="mb-2.5 mt-6" />
          <Vitals cols={5}>
            <Vital
              label={tx("Non-bank assets")}
              value={`₺${nf(d.nbfiAssets / 1_000_000, 2)}`}
              unit="trn"
              series={totalAssets.slice(-13)}
              format="trn"
              decimals={2}
              note={
                assetsYoY != null ? (
                  <>
                    {tx(assetsYoY >= 0 ? "+" : "−")}
                    {tx(Math.abs(assetsYoY).toFixed(1))}{tx("% y/y — leasing + factoring + financing")}</>
                ) : (
                  "leasing + factoring + financing"
                )
              }
            />
            <Vital
              label={tx("Share of banking assets")}
              value={d.assetSharePct != null ? d.assetSharePct.toFixed(2) : "—"}
              unit="%"
              series={assetShareSeries.slice(-13)}
              decimals={2}
              note={
                <>
                  {tx(assetShareD != null ? tx("{0} over 12m — ", {0: signedPp(assetShareD, 2)}) : "")}
                  <Link href="/non-bank/share-of-banking" className="font-semibold text-primary">{tx("/non-bank/share-of-banking")}</Link>
                </>
              }
            />
            <Vital
              label={tx("Share of system credit")}
              value={d.creditSharePct != null ? d.creditSharePct.toFixed(2) : "—"}
              unit="%"
              series={creditShareSeries.slice(-13)}
              decimals={2}
              note={
                <>{tx("book ")}{tx(fmtTrn(d.nbfiCredit))}{tx(" vs bank loans ")}{tx(fmtTrn(d.bankCredit))}
                </>
              }
            />
            <Vital
              label={tx("Largest segment")}
              value={largestShare != null ? largestShare.toFixed(0) : "—"}
              unit="%"
              note={largest ? <>{tx(largest.label)} — {tx(fmtBn(largest.assets))}{tx(" of the sector’s assets")}</> : undefined}
            />
            <Vital
              label={tx("Fastest growth, y/y")}
              value={fastest?.growthYoY != null ? fastest.growthYoY.toFixed(1) : "—"}
              unit="%"
              note={fastest ? <>{tx(fastest.label)}{tx(" — assets vs a year earlier")}</> : undefined}
            />
          </Vitals>

          <Depth action={<GlobalRangeSelector />}>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              <Stat
                label={tx("Non-bank sector assets")}
                value={fmtTrn(d.nbfiAssets)}
                hint={tx("3 sectors · {0}", {0: d.asOfLabel})}
                tone="neutral"
              />
              <Stat
                label={tx("Share of banking assets")}
                value={fmtPct(d.assetSharePct, 2)}
                hint={tx("non-bank ÷ (banking + non-bank)")}
                tone="neutral"
              />
              <Stat
                label={tx("Lending book")}
                value={fmtTrn(d.nbfiCredit)}
                hint={tx("amortized-cost financing · {0}", {0: d.asOfLabel})}
                tone="neutral"
              />
            </div>

            <Section
              index="01"
              title={tx("Sector size over time")}
              description={tx("Total assets of each non-bank sector, Million TL, stacked. Monthly, from 2020 (where the banking aggregate begins).")}
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
                  title={tx("Non-bank sector assets (₺ bn, stacked)")}
                  yFormat="bn"
                  colorKeys
                />
              </ChartRow>
            </Section>

            <Section
              index="02"
              title={tx("By sector")}
              description={tx("Snapshot at {0}. The lending book is the sector's amortized-cost financial assets (factoring receivables / lease receivables / financing loans). YoY is the change in total assets vs. a year earlier.", {0: d.asOfLabel})}
            >
              <Table wrapperClassName="rounded-[10px] border border-border bg-card">
                <TableHeader>
                  <TableRow className="bg-muted/50">
                    <TableHead>{tx("Sector")}</TableHead>
                    <TableHead className="text-right">{tx("Assets (₺ bn)")}</TableHead>
                    <TableHead className="text-right">{tx("Lending book (₺ bn)")}</TableHead>
                    <TableHead className="text-right">{tx("Equity (₺ bn)")}</TableHead>
                    <TableHead className="text-right">{tx("YoY assets")}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {d.sectors.map((s: SectorLatest) => (
                    <TableRow key={s.code}>
                      <TableCell>{tx(s.label)}</TableCell>
                      <TableCellNum>{tx(fmtBn(s.assets))}</TableCellNum>
                      <TableCellNum>{tx(fmtBn(s.credit))}</TableCellNum>
                      <TableCellNum>{tx(fmtBn(s.equity))}</TableCellNum>
                      {/* Growth column: green genuinely means "good" here. */}
                      <TableCellNum
                        tone={
                          s.growthYoY != null && s.growthYoY > 0
                            ? "positive"
                            : toneFor(s.growthYoY)
                        }
                      >
                        {tx(fmtPct(s.growthYoY))}
                      </TableCellNum>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              <p className="text-xs text-muted-foreground">{tx("Want the penetration view?")}{" "}
                <Link href="/non-bank/share-of-banking" className="text-primary hover:underline">{tx("Share of Banking →")}</Link>
              </p>
            </Section>

            <p className="text-xs text-muted-foreground">{tx("Scope: the three credit-substitution sectors. Asset-management (VYŞ) — a complement that buys NPLs from banks — and savings-finance are not included here. Source: BDDK monthly bulletin (BultenAylikBdmk); reconciles to FKB published sector totals.")}</p>
          </Depth>
        </>
      )}

      <Colophon />
    </main>
  );
}
