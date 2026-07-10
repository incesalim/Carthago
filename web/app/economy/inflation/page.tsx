/**
 * Inflation — reproduces the Albaraka "Enflasyon" monthly report from TÜİK
 * CPI/PPI series in EVDS: headline & core inflation, the CPI special-scope
 * core indices (A/B/C/D), the CPI-group and PPI-sector mix, and the monthly
 * history table.
 *
 * Data + derivations: app/lib/inflation.ts. Şekil 2/3 show m/m % per group
 * (the report's weighted contributions need TÜİK weights not in EVDS); the
 * PPI Main-Industrial-Groupings table is TÜİK-Excel-only and not wired.
 */
import type { Metadata } from "next";
import Link from "next/link";
import { getInflationData, type Table1Row, type CoreRow } from "@/app/lib/inflation";
import {
  PageHeader,
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
import { nf } from "@/app/lib/chart-format";
import { ChartCard } from "@/app/components/ui/chart-card";
import TimeSeriesChart from "@/app/components/TimeSeriesChart";
import BopFlowChart, { type BarSeries } from "@/app/components/BopFlowChart";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Turkey Inflation — CPI & PPI",
  description: "Türkiye inflation — CPI, core inflation and producer prices (Yİ-ÜFE) from TÜİK.",
  alternates: { canonical: "/economy/inflation" },
};

const MAROON = { light: "#9c1f2f", dark: "#d65a5a" };
const GREEN = { light: "#3f7d3f", dark: "#6bbf6b" };

function Grid({ children }: { children: React.ReactNode }) {
  return <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">{children}</div>;
}

const pct = (v: number | null, d = 2) => (v == null ? "—" : `${nf(v, d)}%`);

export default async function InflationPage() {
  const d = await getInflationData();

  return (
    <main className="mx-auto w-full max-w-[1440px] px-4 py-8 sm:px-6 lg:px-8 space-y-8">
      <PageHeader
        title="Inflation"
        description="TÜİK consumer (TÜFE) and producer (Yİ-ÜFE) prices: headline, core, and the group/sector breakdown. y/y, m/m and core indices derived from the index level."
        rangeSelector
        dataThrough={d.latestPeriod}
      >
        <Link
          href="/economy"
          className="rounded-md border border-border px-2.5 py-1.5 text-sm font-medium text-foreground transition-colors hover:bg-accent"
        >
          ← Economy
        </Link>
      </PageHeader>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Stat label="CPI · y/y" value={pct(d.cpiYoY)} hint={`TÜFE · ${d.asOfLabel}`} tone="warning" />
        <Stat label="PPI · y/y" value={pct(d.ppiYoY)} hint={`Yİ-ÜFE · ${d.asOfLabel}`} tone="warning" />
        <Stat label="Core CPI · y/y" value={pct(d.coreYoY)} hint={`C index · ${d.asOfLabel}`} tone="warning" />
      </div>

      <Section
        title="Headline & Core Inflation"
        description="Annual CPI, core-C and producer-price inflation. Core C strips out energy, food, alcohol-tobacco and gold — the cleanest read on underlying trend."
      >
        <Grid>
          <TimeSeriesChart
            series={d.s1}
            title="Şekil 1 · Inflation Indicators (y/y %)"
            yFormat="pct"
            decimals={1}
          />
          <TimeSeriesChart
            series={d.s6}
            title="Şekil 6 · Core Inflation — C Index (% change)"
            yFormat="pct"
            decimals={1}
          />
        </Grid>
        <Table wrapperClassName="rounded-[10px] border border-border bg-card">
          <TableHeader>
            <TableRow className="bg-muted/50">
              <TableHead>Core index</TableHead>
              <TableHead className="text-right">Monthly</TableHead>
              <TableHead className="text-right">Since Dec</TableHead>
              <TableHead className="text-right">Annual</TableHead>
              <TableHead className="text-right">12m avg</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {d.core.map((r: CoreRow) => (
              <TableRow
                key={r.label}
                className={r.label.startsWith("C ") ? "bg-accent/30 font-semibold" : undefined}
              >
                <TableCell className="py-1.5">{r.label}</TableCell>
                <TableCellNum tone={toneFor(r.mm)} className="py-1.5">{pct(r.mm)}</TableCellNum>
                <TableCellNum tone={toneFor(r.cum)} className="py-1.5">{pct(r.cum)}</TableCellNum>
                <TableCellNum tone={toneFor(r.yy)} className="py-1.5">{pct(r.yy)}</TableCellNum>
                <TableCellNum tone={toneFor(r.avg12)} className="py-1.5">{pct(r.avg12)}</TableCellNum>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Section>

      <Section
        title="Consumer Prices by Group"
        description={`Monthly % change by COICOP main group, ${d.asOfLabel}. The report plots weighted contributions to monthly inflation; shown here as each group's m/m change (TÜİK group weights aren't published in EVDS) — leaders & signs match, magnitudes scale by weight.`}
      >
        <Grid>
          <ChartCard title="Şekil 2 · CPI Groups (monthly % change)">
            <BopFlowChart
              data={d.s2}
              grouped
              bars={[{ key: "mm", label: "Monthly % change", fill: MAROON }] satisfies BarSeries[]}
              unit="%"
              height={340}
            />
          </ChartCard>
          <TimeSeriesChart
            series={d.s4}
            title="Şekil 4 · Clothing & Footwear (monthly %)"
            yFormat="pct"
            decimals={1}
          />
        </Grid>
      </Section>

      <Section
        title="Producer Prices (Yİ-ÜFE)"
        description={`Domestic PPI by NACE sub-sector, monthly % change, ${d.asOfLabel}. Energy and refining swings dominate producer-cost pressure.`}
      >
        <Grid>
          <ChartCard title="Şekil 3 · PPI Sub-sectors (monthly % change)">
            <BopFlowChart
              data={d.s3}
              grouped
              bars={[{ key: "mm", label: "Monthly % change", fill: GREEN }] satisfies BarSeries[]}
              unit="%"
              height={340}
            />
          </ChartCard>
          <TimeSeriesChart
            series={d.s5}
            title="Şekil 5 · Electricity & Gas Production (monthly %)"
            yFormat="pct"
            decimals={1}
          />
        </Grid>
        {d.hasMig && (
          <div className="space-y-2">
            <Table wrapperClassName="rounded-[10px] border border-border bg-card">
              <TableHeader>
                <TableRow className="bg-muted/50">
                  <TableHead>Main Industrial Grouping</TableHead>
                  <TableHead className="text-right">Monthly</TableHead>
                  <TableHead className="text-right">Annual</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {d.mig.map((r) => (
                  <TableRow key={r.label}>
                    <TableCell className="py-1.5">{r.label}</TableCell>
                    <TableCellNum tone={toneFor(r.mm)} className="py-1.5">{pct(r.mm)}</TableCellNum>
                    <TableCellNum tone={toneFor(r.yy)} className="py-1.5">{pct(r.yy)}</TableCellNum>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <p className="text-xs text-muted-foreground">
              Producer prices by Main Industrial Grouping — ingested from TÜİK&apos;s
              bulletin (Domestic PPI MIG, 2003=100; m/m and y/y derived). Not in EVDS.
            </p>
          </div>
        )}
      </Section>

      <Section
        title="Monthly History"
        description="CPI (TÜFE) and PPI (Yİ-ÜFE), monthly and annual % change."
      >
        <Table wrapperClassName="rounded-[10px] border border-border bg-card">
          <TableHeader>
            <TableRow className="bg-muted/50">
              <TableHead />
              <TableHead className="text-right" colSpan={2}>
                CPI (TÜFE)
              </TableHead>
              <TableHead className="text-right" colSpan={2}>
                PPI (Yİ-ÜFE)
              </TableHead>
            </TableRow>
            <TableRow>
              <TableHead>Month</TableHead>
              <TableHead className="text-right">m/m</TableHead>
              <TableHead className="text-right">y/y</TableHead>
              <TableHead className="text-right">m/m</TableHead>
              <TableHead className="text-right">y/y</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {d.table1.map((r: Table1Row, i) => (
              <TableRow key={r.month} className={i === 0 ? "bg-accent/30 font-semibold" : undefined}>
                <TableCell className="py-1.5">{r.month}</TableCell>
                <TableCellNum tone={toneFor(r.cpiMM)} className="py-1.5">{pct(r.cpiMM)}</TableCellNum>
                <TableCellNum tone={toneFor(r.cpiYY)} className="py-1.5">{pct(r.cpiYY)}</TableCellNum>
                <TableCellNum tone={toneFor(r.ppiMM)} className="py-1.5">{pct(r.ppiMM)}</TableCellNum>
                <TableCellNum tone={toneFor(r.ppiYY)} className="py-1.5">{pct(r.ppiYY)}</TableCellNum>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        <p className="text-xs text-muted-foreground">
          Source: TÜİK (TurkStat) CPI &amp; domestic PPI via EVDS. The
          producer-price Main Industrial Groupings breakdown (intermediate /
          durable / energy / capital goods) is published only in TÜİK&apos;s
          bulletin, not EVDS — not shown here.{" "}
          <Link href="/economy/budget" className="text-primary hover:underline">
            Budget →
          </Link>
        </p>
      </Section>
    </main>
  );
}
