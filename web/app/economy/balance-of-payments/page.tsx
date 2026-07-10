/**
 * Balance of Payments — reproduces the Albaraka "Ödemeler Dengesi" monthly
 * report (10 figures + summary table) from TCMB EVDS series. Faithful to the
 * source layout: 3 headline balances, the annualised current-account block,
 * the financial-account (capital inflow) detail, and the financing identity.
 *
 * Data + derivations live in app/lib/bop.ts; all values are TCMB BoP, USD bn
 * unless the summary table (USD million). See METRICS.md § External balance.
 */
import type { Metadata } from "next";
import Link from "next/link";
import { getBopData } from "@/app/lib/bop";
import { getPortfolioFlowsData } from "@/app/lib/portfolio-flows";
import { latestPeriod } from "@/app/lib/metrics";
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
import { ChartCard } from "@/app/components/ui/chart-card";
import TimeSeriesChart from "@/app/components/TimeSeriesChart";
import BopFlowChart, { type BarSeries, type OverlayLine } from "@/app/components/BopFlowChart";
import { nf } from "@/app/lib/chart-format";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Turkey Balance of Payments",
  description: "Türkiye's balance of payments — current account and capital and financial flows from CBRT data.",
  alternates: { canonical: "/economy/balance-of-payments" },
};

// Source-report palette (orange / maroon / grey / amber), light & dark.
const ORANGE = { light: "#e8833a", dark: "#f0a35e" };
const MAROON = { light: "#9c1f2f", dark: "#d65a5a" };
const GREY = { light: "#9ca3af", dark: "#9ca3af" };
const AMBER = { light: "#f5c518", dark: "#fbd34d" };
const INK = { light: "#171717", dark: "#ededed" };

function Grid({ children }: { children: React.ReactNode }) {
  return <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">{children}</div>;
}

const nf2 = (v: number | null) => (v == null ? "—" : nf(v, 2));

const nfInt = (v: number | null) => (v == null ? "—" : nf(v, 0));

const tone = (v: number | null) =>
  v == null ? "neutral" : v < 0 ? "negative" : "positive";

export default async function BalanceOfPaymentsPage() {
  const [d, pf] = await Promise.all([getBopData(), getPortfolioFlowsData()]);
  const dataThrough = latestPeriod(
    d.s1["Current account"] ?? [],
    d.s9["Net errors & omissions"] ?? [],
  );

  return (
    <main className="mx-auto w-full max-w-[1440px] px-4 py-8 sm:px-6 lg:px-8 space-y-8">
      <PageHeader
        title="Balance of Payments"
        description="TCMB balance-of-payments statistics: current account, financial-account flows, and the financing of the current-account deficit. Values in USD bn unless noted."
        rangeSelector
        dataThrough={dataThrough}
      />

      {/* Cover KPIs — mirror the report's three headline balances. */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Stat
          label="Current account · monthly"
          value={`${nf2(d.caMonthly)}`}
          hint={`USD bn · ${d.asOfLabel}`}
          tone={tone(d.caMonthly)}
        />
        <Stat
          label="Current account · 12-month"
          value={`${nf2(d.ca12m)}`}
          hint={`USD bn · trailing 12m to ${d.asOfLabel}`}
          tone={tone(d.ca12m)}
        />
        <Stat
          label="Core balance · monthly"
          value={`${nf2(d.coreMonthly)}`}
          hint={`USD bn · ex gold & energy · ${d.asOfLabel}`}
          tone={tone(d.coreMonthly)}
        />
      </div>

      <Section
        title="Current Account"
        description="Annualised (trailing-12-month) balances, USD bn. The core balance strips out the volatile gold and energy bills; net tourism is the main services offset to the goods deficit."
      >
        <Grid>
          <TimeSeriesChart
            series={d.s1}
            title="Şekil 1 · Current Account (12m rolling, USD bn)"
            yFormat="raw"
            decimals={1}          />
          <TimeSeriesChart
            series={d.s2}
            title="Şekil 2 · Goods & Tourism (12m rolling, USD bn)"
            yFormat="raw"
            decimals={1}          />
        </Grid>
      </Section>

      <Section
        title="Capital Inflows & Financial Account"
        description="Monthly financing flows on a net-incurrence-of-liabilities basis (inflows into Türkiye), USD bn. Bars stack above/below zero; Şekil 4 & 5 add the 12-month cumulative on the right axis."
      >
        <Grid>
          <ChartCard title="Şekil 3 · Capital Inflows (monthly, USD bn)">
            <BopFlowChart
              data={d.s3}
              bars={[
                { key: "fdi", label: "Direct investment", fill: ORANGE },
                { key: "portfolio", label: "Portfolio investment", fill: MAROON },
                { key: "loans", label: "Loans", fill: GREY },
                { key: "trade", label: "Trade credits", fill: AMBER },
              ] satisfies BarSeries[]}
              unit=" bn"
            />
          </ChartCard>
          <ChartCard title="Şekil 4 · Direct Investment (monthly, USD bn)">
            <BopFlowChart
              data={d.s4}
              bars={[
                { key: "realEstate", label: "Real estate", fill: ORANGE },
                { key: "other", label: "Other", fill: MAROON },
              ] satisfies BarSeries[]}
              line={{ key: "twelveM", label: "12-month", color: INK, rightAxis: true } satisfies OverlayLine}
              unit=" bn"
            />
          </ChartCard>
          <ChartCard title="Şekil 5 · Portfolio Investment (monthly, USD bn)">
            <BopFlowChart
              data={d.s5}
              bars={[
                { key: "equity", label: "Equity & fund shares", fill: ORANGE },
                { key: "debt", label: "Debt securities", fill: MAROON },
              ] satisfies BarSeries[]}
              line={{ key: "twelveM", label: "12-month", color: INK, rightAxis: true } satisfies OverlayLine}
              unit=" bn"
            />
          </ChartCard>
          <ChartCard title="Şekil 6 · Loans by Borrower (net liab., monthly, USD bn)">
            <BopFlowChart
              data={d.s6}
              bars={[
                { key: "banks", label: "Banks", fill: ORANGE },
                { key: "gov", label: "General government", fill: MAROON },
                { key: "other", label: "Other sectors", fill: GREY },
              ] satisfies BarSeries[]}
              unit=" bn"
            />
          </ChartCard>
        </Grid>
      </Section>

      <Section
        title="Foreign Portfolio Flows — Weekly (TCMB securities statistics)"
        description="Non-residents' weekly net transactions in Borsa İstanbul equities and government domestic debt securities (GDDS / DİBS), net buy +, net sell −, and their total holdings. Week-ending Friday, USD. Source: TCMB «Yurt Dışı Yerleşikler Menkul Kıymet İstatistikleri» — the dataset behind the widely-cited weekly foreign-flows chart, and more timely than the monthly BoP portfolio line (Şekil 5) above."
      >
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <Stat
            label="Net equity flow · last week"
            value={nfInt(pf.netEquityLatest)}
            hint={`USD mn · ${pf.asOfLabel}`}
            tone={tone(pf.netEquityLatest)}
          />
          <Stat
            label="Net bond (GDDS) flow · last week"
            value={nfInt(pf.netGddsLatest)}
            hint={`USD mn · ${pf.asOfLabel}`}
            tone={tone(pf.netGddsLatest)}
          />
          <Stat
            label="Foreign equity holdings"
            value={nf2(pf.equityHoldings)}
            hint={`USD bn · ${pf.asOfLabel}`}
            tone="neutral"
          />
        </div>
        <Grid>
          <ChartCard title="Weekly Net Securities Flows (USD mn)">
            <BopFlowChart
              data={pf.flows}
              bars={[
                { key: "equity", label: "Equity", fill: MAROON },
                { key: "bonds", label: "Govt bonds (DİBS)", fill: ORANGE },
              ] satisfies BarSeries[]}
              unit=" mn"
              decimals={0}
              height={360}
            />
          </ChartCard>
          <TimeSeriesChart
            series={pf.holdings}
            title="Non-resident Holdings (USD bn)"
            yFormat="raw"
            decimals={1}
          />
        </Grid>
      </Section>

      <Section
        title="Trade Credits, Deposits & Errors"
        description="Annualised (trailing-12-month) flows, USD bn. Currency & deposits split into residents' asset acquisition abroad vs. liabilities incurred to non-residents."
      >
        <Grid>
          <TimeSeriesChart
            series={d.s7}
            title="Şekil 7 · Trade Credits (12m rolling, USD bn)"
            yFormat="raw"
            decimals={1}          />
          <TimeSeriesChart
            series={d.s8}
            title="Şekil 8 · Currency & Deposits (12m rolling, USD bn)"
            yFormat="raw"
            decimals={1}          />
          <TimeSeriesChart
            series={d.s9}
            title="Şekil 9 · Net Errors & Omissions (12m rolling, USD bn)"
            yFormat="raw"
            decimals={1}          />
        </Grid>
      </Section>

      <Section
        title="Financing of the Current-Account Deficit"
        description="Şekil 10 · Monthly, USD bn. Identity: current account ≡ net foreign investment + (reserves − net errors). Net foreign investment = FDI + portfolio + other investment (net); the residual is reserve change less net errors."
      >
        <ChartCard title="Şekil 10 · Financing of the Current Account (monthly, USD bn)">
          <BopFlowChart
            data={d.s10}
            grouped
            bars={[
              { key: "nfi", label: "Net foreign investment", fill: ORANGE },
              { key: "need", label: "Financing requirement (current account)", fill: MAROON },
            ] satisfies BarSeries[]}
            line={{ key: "resNeo", label: "Reserves − net errors", color: INK, dotted: true } satisfies OverlayLine}
            unit=" bn"
            height={360}
          />
        </ChartCard>
      </Section>

      <Section
        title="Summary"
        description={`Monthly and trailing-12-month cumulative balances, USD million — ${d.asOfLabel} vs. one year earlier.`}
      >
        <Table wrapperClassName="rounded-[10px] border border-border bg-card">
          <TableHeader>
            <TableRow className="bg-muted/50">
              <TableHead />
              <TableHead className="text-right" colSpan={2}>
                {d.asOfLabel}
              </TableHead>
              <TableHead className="text-right" colSpan={2}>
                year earlier
              </TableHead>
            </TableRow>
            <TableRow>
              <TableHead>USD million</TableHead>
              <TableHead className="text-right">Monthly</TableHead>
              <TableHead className="text-right">12-month</TableHead>
              <TableHead className="text-right">Monthly</TableHead>
              <TableHead className="text-right">12-month</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {d.table.map((r) => (
              <TableRow key={r.label}>
                <TableCell className="py-1.5">{r.label}</TableCell>
                {r.cells.map((v, i) => (
                  <TableCellNum key={i} tone={toneFor(v)} className="py-1.5">
                    {nfInt(v)}
                  </TableCellNum>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
        <p className="text-xs text-muted-foreground">
          Source: TCMB (CBRT) balance-of-payments statistics via EVDS.{" "}
          <Link href="/economy" className="text-primary hover:underline">
            ← Back to Economy
          </Link>
        </p>
      </Section>
    </main>
  );
}
