/**
 * Economy tab — adapts the Türkiye macro section of the BBVA (Garanti BBVA
 * Research) "Türkiye Economic Outlook" into our data.
 *
 * Structure mirrors the report: growth & activity, labor market, inflation
 * & monetary policy, lira & external balance, fiscal stance — closed by
 * BBVA's published baseline scenario table for context.
 *
 * Out of scope (no data source here): CDS spreads, OIS pricing and
 * sovereign yield curves (Bloomberg), BIST indices, the GDP nowcast and
 * the FCI composite (BBVA-proprietary), and foreigners' positioning flows.
 */
import Link from "next/link";
import { getEconomyData, BBVA_BASELINE } from "@/app/lib/economy";
import { latestPeriod } from "@/app/lib/metrics";
import { PageHeader } from "@/app/components/ui";
import TimeSeriesChart from "@/app/components/TimeSeriesChart";

export const dynamic = "force-dynamic";

function Section({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
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

export default async function EconomyPage() {
  const d = await getEconomyData();

  const dataThrough = latestPeriod(
    d.gdpGrowth,
    d.cpiYoY,
    d.unemployment,
    d.ca12m,
    d.budgetPctGdp,
    d.usdtry,
  );

  return (
    <main className="mx-auto w-full max-w-[1440px] px-4 py-8 sm:px-6 lg:px-8 space-y-8">
      <PageHeader
        eyebrow="Adapted from BBVA / Garanti BBVA Research"
        title="Economy"
        description="Growth · labor · inflation & policy · external balance · fiscal — TCMB EVDS (TURKSTAT, CBRT, Treasury)"
        dataThrough={dataThrough}
      >
        <Link
          href="/economy/balance-of-payments"
          className="rounded-md border border-border px-2.5 py-1.5 text-sm font-medium text-foreground transition-colors hover:bg-accent"
        >
          Balance of Payments →
        </Link>
      </PageHeader>

      <Section
        title="Growth & Activity"
        subtitle="GDP grew 3.6% in 2025 on domestic demand; industrial momentum stays weak while services hold up (report pp. 29–30)."
      >
        <Grid>
          <TimeSeriesChart
            series={{ "GDP growth (y/y)": d.gdpGrowth }}
            title="GDP Growth (y/y %, chain-linked volume, quarterly)"
            yFormat="pct"
            decimals={1}
          />
          <TimeSeriesChart
            series={{ "Industrial production (y/y)": d.ipGrowth }}
            title="Industrial Production (y/y %, SA, 2021=100)"
            yFormat="pct"
            decimals={1}
          />
        </Grid>
      </Section>

      <Section
        title="Labor Market"
        subtitle="Headline unemployment is historically low, but participation has been sliding — the report flags worsening employment quality (p. 31)."
      >
        <Grid>
          <TimeSeriesChart
            series={{
              "Unemployment rate": d.unemployment,
              "Participation rate": d.participation,
            }}
            title="Unemployment & Labor Force Participation (SA %)"
            yFormat="pct"
            decimals={1}
          />
          <TimeSeriesChart
            series={{ Employed: d.employedMn }}
            title="Employment Level (mn persons, SA)"
            yFormat="raw"
            decimals={1}
          />
        </Grid>
      </Section>

      <Section
        title="Inflation & Monetary Policy"
        subtitle="Disinflation decelerated even before the conflict — monthly CPI persistently above 2% with unanchored expectations (pp. 32–33, 39)."
      >
        <Grid>
          <TimeSeriesChart
            series={{
              "CPI (y/y)": d.cpiYoY,
              "CBRT cost of funding": d.fundingMonthly,
            }}
            title="CPI Inflation vs CBRT Effective Funding Cost (%)"
            yFormat="pct"
            decimals={1}
          />
          <TimeSeriesChart
            series={{ "CPI (m/m)": d.cpiMoM }}
            title="Monthly CPI (m/m %)"
            yFormat="pct"
            decimals={2}
          />
          <TimeSeriesChart
            series={{
              "Current year-end": d.expCurrentYearEnd,
              "Next year-end": d.expNextYearEnd,
              "12 months ahead": d.exp12m,
            }}
            title="Market Participants' CPI Expectations (CBRT survey, %)"
            yFormat="pct"
            decimals={1}
          />
          <TimeSeriesChart
            series={{ "Ex-ante real funding rate": d.realRate }}
            title="Ex-ante Real Policy Rate (funding cost vs 12m-ahead expectation, %)"
            yFormat="pct"
            decimals={1}
          />
        </Grid>
      </Section>

      <Section
        title="Lira & External Balance"
        subtitle="External balance was worsening before the conflict; every 10% rise in energy prices costs ~0.3–0.4% of GDP on the current account (pp. 35, 41)."
      >
        <Grid>
          <TimeSeriesChart
            series={{ "USD/TRY": d.usdtry }}
            title="USD/TRY"
            yFormat="fx"
            decimals={2}
          />
          <TimeSeriesChart
            series={{ "REER (CPI based)": d.reer }}
            title="Real Effective Exchange Rate (2003 = 100)"
            yFormat="rate"
            decimals={1}
          />
          <TimeSeriesChart
            series={{
              "Current account": d.ca12m,
              "ex gold": d.caExGold12m,
              "ex gold & energy": d.caExGoldEnergy12m,
            }}
            title="Current Account Balance (12m rolling, USD bn)"
            yFormat="raw"
            decimals={1}
          />
          <TimeSeriesChart
            series={{ "Net errors & omissions": d.neo12m }}
            title="Net Errors & Omissions (12m rolling, USD bn)"
            yFormat="raw"
            decimals={1}
          />
        </Grid>
      </Section>

      <Section
        title="Fiscal Stance"
        subtitle="Cash primary balance back in surplus gives room for fiscal maneuver against the conflict shock (p. 34). Treasury general budget, 12m rolling."
      >
        <TimeSeriesChart
          series={{
            "Budget balance": d.budgetPctGdp,
            "Primary balance": d.primaryPctGdp,
            "Cash balance": d.cashPctGdp,
          }}
          title="General Budget Balances (12m rolling, % of GDP)"
          yFormat="pct"
          decimals={1}
          height={340}
        />
      </Section>

      <Section
        title="BBVA Baseline Scenario"
        subtitle={`${BBVA_BASELINE.source} (${BBVA_BASELINE.asOf}). Forecasts assume a short-lived conflict; biases are to higher inflation and weaker growth if it lasts.`}
      >
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-accent/40 text-left">
                <th className="px-3 py-2 font-medium text-muted-foreground"></th>
                {BBVA_BASELINE.years.map((y) => (
                  <th key={y} className="px-3 py-2 text-right font-medium text-muted-foreground">
                    {y}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {BBVA_BASELINE.rows.map((r) => (
                <tr key={r.label} className="border-b border-border/60 last:border-0">
                  <td className="px-3 py-1.5 text-foreground">{r.label}</td>
                  {r.values.map((v, i) => (
                    <td
                      key={i}
                      className={`px-3 py-1.5 text-right tabular-nums ${
                        i === r.values.length - 1
                          ? "font-semibold text-foreground"
                          : "text-muted-foreground"
                      }`}
                    >
                      {v}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>
    </main>
  );
}
