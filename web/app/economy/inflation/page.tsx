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
import Link from "next/link";
import { getInflationData, type Table1Row, type CoreRow } from "@/app/lib/inflation";
import { PageHeader, Section, Stat } from "@/app/components/ui";
import { ChartCard } from "@/app/components/ui/chart-card";
import TimeSeriesChart from "@/app/components/TimeSeriesChart";
import BopFlowChart, { type BarSeries } from "@/app/components/BopFlowChart";

export const dynamic = "force-dynamic";

const MAROON = { light: "#9c1f2f", dark: "#d65a5a" };
const GREEN = { light: "#3f7d3f", dark: "#6bbf6b" };

function Grid({ children }: { children: React.ReactNode }) {
  return <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">{children}</div>;
}

const pct = (v: number | null, d = 2) =>
  v == null
    ? "—"
    : `${new Intl.NumberFormat("en-US", { minimumFractionDigits: d, maximumFractionDigits: d }).format(v)}%`;

const cell = (v: number | null) =>
  `px-3 py-1.5 text-right tabular-nums ${v == null ? "text-muted-foreground" : v < 0 ? "text-negative" : "text-foreground"}`;

export default async function InflationPage() {
  const d = await getInflationData();

  return (
    <main className="mx-auto w-full max-w-[1440px] px-4 py-8 sm:px-6 lg:px-8 space-y-8">
      <PageHeader
        eyebrow="Adapted from Albaraka — Enflasyon"
        title="Inflation"
        description="TÜİK consumer (TÜFE) and producer (Yİ-ÜFE) prices: headline, core, and the group/sector breakdown. y/y, m/m and core indices derived from the index level."
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
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-accent/40 text-left">
                <th className="px-3 py-2 font-medium text-muted-foreground">Core index</th>
                <th className="px-3 py-2 text-right font-medium text-muted-foreground">Monthly</th>
                <th className="px-3 py-2 text-right font-medium text-muted-foreground">Since Dec</th>
                <th className="px-3 py-2 text-right font-medium text-muted-foreground">Annual</th>
                <th className="px-3 py-2 text-right font-medium text-muted-foreground">12m avg</th>
              </tr>
            </thead>
            <tbody>
              {d.core.map((r: CoreRow) => (
                <tr
                  key={r.label}
                  className={`border-b border-border/60 last:border-0 ${r.label.startsWith("C ") ? "bg-accent/30 font-semibold" : ""}`}
                >
                  <td className="px-3 py-1.5 text-foreground">{r.label}</td>
                  <td className={cell(r.mm)}>{pct(r.mm)}</td>
                  <td className={cell(r.cum)}>{pct(r.cum)}</td>
                  <td className={cell(r.yy)}>{pct(r.yy)}</td>
                  <td className={cell(r.avg12)}>{pct(r.avg12)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
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
            <div className="overflow-x-auto rounded-lg border border-border">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border bg-accent/40 text-left">
                    <th className="px-3 py-2 font-medium text-muted-foreground">Main Industrial Grouping</th>
                    <th className="px-3 py-2 text-right font-medium text-muted-foreground">Monthly</th>
                    <th className="px-3 py-2 text-right font-medium text-muted-foreground">Annual</th>
                  </tr>
                </thead>
                <tbody>
                  {d.mig.map((r) => (
                    <tr key={r.label} className="border-b border-border/60 last:border-0">
                      <td className="px-3 py-1.5 text-foreground">{r.label}</td>
                      <td className={cell(r.mm)}>{pct(r.mm)}</td>
                      <td className={cell(r.yy)}>{pct(r.yy)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
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
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-accent/40 text-left">
                <th className="px-3 py-2 font-medium text-muted-foreground" />
                <th className="px-3 py-2 text-right font-medium text-muted-foreground" colSpan={2}>
                  CPI (TÜFE)
                </th>
                <th className="px-3 py-2 text-right font-medium text-muted-foreground" colSpan={2}>
                  PPI (Yİ-ÜFE)
                </th>
              </tr>
              <tr className="border-b border-border text-left text-xs text-muted-foreground">
                <th className="px-3 py-1.5 font-medium">Month</th>
                <th className="px-3 py-1.5 text-right font-medium">m/m</th>
                <th className="px-3 py-1.5 text-right font-medium">y/y</th>
                <th className="px-3 py-1.5 text-right font-medium">m/m</th>
                <th className="px-3 py-1.5 text-right font-medium">y/y</th>
              </tr>
            </thead>
            <tbody>
              {d.table1.map((r: Table1Row, i) => (
                <tr key={r.month} className={`border-b border-border/60 last:border-0 ${i === 0 ? "bg-accent/30 font-semibold" : ""}`}>
                  <td className="px-3 py-1.5 text-foreground">{r.month}</td>
                  <td className={cell(r.cpiMM)}>{pct(r.cpiMM)}</td>
                  <td className={cell(r.cpiYY)}>{pct(r.cpiYY)}</td>
                  <td className={cell(r.ppiMM)}>{pct(r.ppiMM)}</td>
                  <td className={cell(r.ppiYY)}>{pct(r.ppiYY)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="text-xs text-muted-foreground">
          Source: TÜİK (TurkStat) CPI &amp; domestic PPI via EVDS. Adapted from
          Albaraka Türk «Enflasyon» report. The producer-price Main Industrial
          Groupings breakdown (intermediate / durable / energy / capital goods)
          is published only in TÜİK&apos;s bulletin, not EVDS — not shown here.{" "}
          <Link href="/economy/budget" className="text-primary hover:underline">
            Budget →
          </Link>
        </p>
      </Section>
    </main>
  );
}
