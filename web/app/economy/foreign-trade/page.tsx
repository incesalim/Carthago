/**
 * Foreign Trade — reproduces the Albaraka "Dış Ticaret Dengesi" report from
 * TÜİK customs-trade series in EVDS: the trade balance, exports & imports
 * (level + growth), the coverage ratio, terms of trade, trade by BEC product
 * group, and the energy deficit vs Brent.
 *
 * Data + derivations: app/lib/foreign-trade.ts. The report's "core balance"
 * line (Albaraka-internal) and the HS-chapter ("Fasıl") tables (TÜİK dynamic
 * DB only) are flagged below rather than approximated.
 */
import Link from "next/link";
import { getForeignTradeData } from "@/app/lib/foreign-trade";
import { PageHeader, Stat } from "@/app/components/ui";
import { ChartCard } from "@/app/components/ui/chart-card";
import TimeSeriesChart from "@/app/components/TimeSeriesChart";
import BopFlowChart, { type BarSeries, type OverlayLine } from "@/app/components/BopFlowChart";

export const dynamic = "force-dynamic";

const MAROON = { light: "#9c1f2f", dark: "#d65a5a" };
const INK = { light: "#171717", dark: "#ededed" };

function Section({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  return (
    <section className="space-y-4">
      <div className="space-y-0.5">
        <h2 className="text-base font-semibold text-foreground">{title}</h2>
        {subtitle && <p className="text-xs text-muted-foreground">{subtitle}</p>}
      </div>
      <div className="space-y-4">{children}</div>
    </section>
  );
}

function Grid({ children }: { children: React.ReactNode }) {
  return <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">{children}</div>;
}

const nf1 = (v: number | null) =>
  v == null ? "—" : new Intl.NumberFormat("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 }).format(v);

export default async function ForeignTradePage() {
  const d = await getForeignTradeData();

  return (
    <main className="mx-auto w-full max-w-[1440px] px-4 py-8 sm:px-6 lg:px-8 space-y-8">
      <PageHeader
        eyebrow="Adapted from Albaraka — Dış Ticaret Dengesi"
        title="Foreign Trade"
        description="TÜİK customs-trade statistics: the trade balance, exports & imports, coverage ratio, terms of trade, trade by product group, and the energy deficit. Values in USD bn unless noted."
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
        <Stat label="Exports · last 3 months" value={`$${nf1(d.expQ)} bn`} hint={`customs · to ${d.asOfLabel}`} tone="positive" />
        <Stat label="Imports · last 3 months" value={`$${nf1(d.impQ)} bn`} hint={`customs · to ${d.asOfLabel}`} tone="neutral" />
        <Stat label="Trade deficit · last 3 months" value={`$${nf1(d.deficitQ)} bn`} hint={`imports − exports · to ${d.asOfLabel}`} tone="negative" />
      </div>

      <Section
        title="Trade Balance"
        subtitle="Annualised (trailing-12-month) customs trade balance, USD bn. The ex-energy line strips out the energy bill — the dominant swing factor."
      >
        <Grid>
          <TimeSeriesChart series={d.s1} title="Şekil 1 · Trade Balance (12m rolling, USD bn)" yFormat="raw" decimals={1} />
          <TimeSeriesChart series={d.coverage} title="Şekil 4 · Export/Import Coverage Ratio (12m, %)" yFormat="pct" decimals={1} />
        </Grid>
      </Section>

      <Section
        title="Exports & Imports"
        subtitle="Annualised level (USD bn) and annual growth. Imports run well above exports — the structural trade gap."
      >
        <Grid>
          <TimeSeriesChart series={d.levels} title="Şekil 2–3 · Exports & Imports (12m rolling, USD bn)" yFormat="raw" decimals={0} />
          <TimeSeriesChart series={d.growth} title="Export & Import Growth (y/y %)" yFormat="pct" decimals={0} />
        </Grid>
      </Section>

      <Section
        title="By Product Group (BEC)"
        subtitle="Broad Economic Categories, annualised USD bn. Intermediate goods (mostly energy & inputs) dominate imports; consumption goods lead exports."
      >
        <Grid>
          <TimeSeriesChart series={d.becExp} title="Şekil 6 · Exports by BEC Group (12m, USD bn)" yFormat="raw" decimals={0} />
          <TimeSeriesChart series={d.becImp} title="Şekil 7 · Imports by BEC Group (12m, USD bn)" yFormat="raw" decimals={0} />
        </Grid>
      </Section>

      <Section
        title="Terms of Trade & Energy"
        subtitle="Terms of trade = export unit-value ÷ import unit-value (2015=100). The energy deficit tracks Brent — the report's clearest single driver of the trade gap."
      >
        <Grid>
          <TimeSeriesChart series={d.terms} title="Şekil 5 · Terms of Trade (%)" yFormat="rate" decimals={1} />
          <ChartCard title="Şekil 8 · Energy Deficit (12m, USD bn) & Brent ($/bbl)">
            <BopFlowChart
              data={d.energy}
              bars={[{ key: "deficit", label: "Energy deficit (12m)", fill: MAROON }] satisfies BarSeries[]}
              line={{ key: "brent", label: "Brent ($/bbl, right)", color: INK, rightAxis: true } satisfies OverlayLine}
              decimals={1}
            />
          </ChartCard>
        </Grid>
      </Section>

      <p className="text-xs text-muted-foreground">
        Source: TÜİK (TurkStat) foreign-trade statistics + Brent via TCMB EVDS.
        Adapted from Albaraka Türk «Dış Ticaret Dengesi» report. Two report
        elements are not reproduced: the «Çekirdek Denge» (core balance) line, an
        Albaraka-internal construction that doesn&apos;t reconcile from EVDS
        primitives; and the HS-chapter («Fasıl») trade tables (Şekil 9), which
        live only in TÜİK&apos;s dynamic foreign-trade database, not EVDS.{" "}
        <Link href="/economy/balance-of-payments" className="text-primary hover:underline">
          Balance of Payments →
        </Link>
      </p>
    </main>
  );
}
