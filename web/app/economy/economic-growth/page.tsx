/**
 * Economic Growth — reproduces the Albaraka "Ekonomik Büyüme" quarterly GDP
 * report from TÜİK national-accounts series in EVDS: headline growth, the
 * expenditure-side growth contributions, sectoral (production-side) growth,
 * and the two y/y detail tables.
 *
 * Data + derivations: app/lib/growth.ts. What EVDS can't supply (the q/q
 * seasonally-adjusted line, the consumption/investment detail of Şekil 4–5,
 * and the calendar-adjusted production variant) is flagged in the page notes
 * — it would need a separate TÜİK Excel scraper.
 */
import Link from "next/link";
import { getGrowthData, type GrowthTable } from "@/app/lib/growth";
import { PageHeader, Section, Stat } from "@/app/components/ui";
import { ChartCard } from "@/app/components/ui/chart-card";
import TimeSeriesChart from "@/app/components/TimeSeriesChart";
import BopFlowChart, { type BarSeries, type OverlayLine } from "@/app/components/BopFlowChart";

export const dynamic = "force-dynamic";

const MAROON = { light: "#9c1f2f", dark: "#d65a5a" };
const AMBER = { light: "#f5c518", dark: "#fbd34d" };
const ORANGE = { light: "#e8833a", dark: "#f0a35e" };
const GREY = { light: "#9ca3af", dark: "#9ca3af" };
const LBLUE = { light: "#6f9fe0", dark: "#93c5fd" };
const DBLUE = { light: "#1f4068", dark: "#3b6ea5" };
const GREEN = { light: "#0f7b6c", dark: "#34c9b0" };
const NAVY = { light: "#1f4068", dark: "#6f9fe0" };
const INK = { light: "#171717", dark: "#ededed" };

const pct1 = (v: number | null) =>
  v == null
    ? "—"
    : `${v > 0 ? "+" : ""}${new Intl.NumberFormat("en-US", {
        minimumFractionDigits: 1,
        maximumFractionDigits: 1,
      }).format(v)}%`;

function YoyTable({ table, note }: { table: GrowthTable; note?: string }) {
  return (
    <div className="space-y-2">
      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border bg-accent/40 text-left">
              <th className="px-3 py-2 font-medium text-muted-foreground">y/y % change</th>
              {table.quarters.map((q) => (
                <th key={q} className="px-3 py-2 text-right font-medium text-muted-foreground">
                  {q}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {table.rows.map((r) => {
              const isGdp = r.label === "GDP";
              return (
                <tr
                  key={r.label}
                  className={`border-b border-border/60 last:border-0 ${isGdp ? "bg-accent/30 font-semibold" : ""}`}
                >
                  <td className={`px-3 py-1.5 text-foreground ${r.indent ? "pl-6 text-muted-foreground" : ""}`}>
                    {r.label}
                  </td>
                  {r.values.map((v, i) => (
                    <td
                      key={i}
                      className={`px-3 py-1.5 text-right tabular-nums ${
                        v == null ? "text-muted-foreground" : v < 0 ? "text-negative" : "text-foreground"
                      }`}
                    >
                      {v == null ? "—" : v.toFixed(1)}
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {note && <p className="text-xs text-muted-foreground">{note}</p>}
    </div>
  );
}

export default async function EconomicGrowthPage() {
  const d = await getGrowthData();

  return (
    <main className="mx-auto w-full max-w-[1440px] px-4 py-8 sm:px-6 lg:px-8 space-y-8">
      <PageHeader
        title="Economic Growth"
        description="TÜİK quarterly national accounts: GDP growth, expenditure-side contributions, and sectoral (production-side) growth. Chain-linked volume indices; y/y from the index level."
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
        <Stat
          label="GDP growth · y/y"
          value={pct1(d.gdpYoY)}
          hint={`${d.asOfLabel} · chain-linked volume`}
          tone={d.gdpYoY != null && d.gdpYoY < 0 ? "negative" : "positive"}
        />
        <Stat
          label="Nominal GDP · quarter"
          value={d.nominalQ == null ? "—" : `₺${d.nominalQ.toFixed(1)} tn`}
          hint={`current prices · ${d.asOfLabel}`}
        />
        <Stat
          label="Nominal GDP · annualized"
          value={d.nominalAnnual == null ? "—" : `₺${d.nominalAnnual.toFixed(1)} tn`}
          hint="current prices · trailing 4 quarters"
        />
      </div>

      <Section
        title="GDP Growth & Contributions"
        description="GDP grew 2.5% y/y in 2026-Q1 (q/q +0.1% on TÜİK's seasonally-adjusted series — not carried in EVDS). Private consumption drove the expansion (+3.4 pp) while the −12.7% export slump subtracted −2.9 pp."
      >
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <TimeSeriesChart
            series={d.s1}
            title="Şekil 1 · GDP Growth (y/y %, chain-linked volume)"
            yFormat="pct"
            xFormat="quarter"
            decimals={1}
          />
          <ChartCard title="Şekil 2 · Contributions to GDP Growth (y/y, pp)">
            <BopFlowChart
              data={d.s2}
              bars={[
                { key: "consumption", label: "Consumption", fill: MAROON },
                { key: "government", label: "Government", fill: AMBER },
                { key: "investment", label: "Investment", fill: ORANGE },
                { key: "inventories", label: "Inventories", fill: GREY },
                { key: "exports", label: "Exports", fill: LBLUE },
                { key: "imports", label: "Imports (−)", fill: DBLUE },
              ] satisfies BarSeries[]}
              line={{ key: "gdp", label: "GDP (y/y)", color: INK } satisfies OverlayLine}
              unit="%"
            />
          </ChartCard>
        </div>
      </Section>

      <Section
        title="Production Side"
        description="Gross value added by activity, y/y %. Construction and services led; industry and agriculture lagged. Figures use the unadjusted chain-volume index (see table note)."
      >
        <ChartCard title="Şekil 3 · Sectoral Growth (y/y %)">
          <BopFlowChart
            data={d.s3}
            grouped
            bars={[
              { key: "agri", label: "Agriculture", fill: GREEN },
              { key: "industry", label: "Industry", fill: NAVY },
              { key: "constr", label: "Construction", fill: ORANGE },
              { key: "services", label: "Services", fill: AMBER },
            ] satisfies BarSeries[]}
            unit="%"
            height={340}
          />
        </ChartCard>
        <YoyTable
          table={d.prodTable}
          note="y/y from the unadjusted chain-volume index. TÜİK headlines a few sub-sectors (industry, manufacturing, services, public admin) on the calendar-adjusted series, which EVDS does not publish — those rows can differ by up to ~1.5 pp; the GDP total matches exactly."
        />
      </Section>

      <Section
        title="Expenditure Side"
        description="Demand components, y/y %. Consumption-by-durability and investment-by-type come from TÜİK's national-accounts detail (not in EVDS); government and the aggregates from EVDS."
      >
        {d.hasTuik && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <ChartCard title="Şekil 5 · Private Consumption by Durability (y/y %)">
              <BopFlowChart
                data={d.s5cons}
                grouped
                bars={[
                  { key: "durable", label: "Durable", fill: MAROON },
                  { key: "semidur", label: "Semi-durable", fill: NAVY },
                  { key: "nondur", label: "Non-durable", fill: ORANGE },
                  { key: "services", label: "Services", fill: GREY },
                ] satisfies BarSeries[]}
                unit="%"
                height={320}
              />
            </ChartCard>
            <ChartCard title="Şekil 4 · Investment by Type (y/y %)">
              <BopFlowChart
                data={d.s4inv}
                grouped
                bars={[
                  { key: "construction", label: "Construction", fill: NAVY },
                  { key: "machinery", label: "Machinery & equipment", fill: ORANGE },
                  { key: "other", label: "Other assets", fill: GREY },
                ] satisfies BarSeries[]}
                unit="%"
                height={320}
              />
            </ChartCard>
          </div>
        )}
        <ChartCard title="Şekil 6 · Government Consumption (y/y %)">
          <BopFlowChart
            data={d.s6}
            grouped
            bars={[{ key: "gov", label: "Government consumption", fill: ORANGE }] satisfies BarSeries[]}
            unit="%"
            height={300}
          />
        </ChartCard>
        <YoyTable
          table={d.expTable}
          note="Top-level expenditure aggregates from EVDS. The durable/semi/non-durable consumption (Şekil 5) and construction/machinery/other investment (Şekil 4) detail above is ingested from TÜİK's national-accounts Excel (chain-volume index, 2009=100; y/y derived)."
        />
      </Section>

      <p className="text-xs text-muted-foreground">
        Source: TÜİK (TurkStat) quarterly national accounts via EVDS.{" "}
        <Link href="/economy/balance-of-payments" className="text-primary hover:underline">
          Balance of Payments →
        </Link>
      </p>
    </main>
  );
}
