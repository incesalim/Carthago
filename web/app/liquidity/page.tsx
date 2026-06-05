/**
 * Liquidity tab — adapts the liquidity section of the BBVA (Garanti BBVA
 * Research) "Türkiye Banking Sector Outlook" into our data.
 *
 * Structure mirrors the report: TL funding, FC & dollarization, CBRT
 * reserves/funding, and the real-appreciation backdrop. Public-vs-private
 * cuts follow BBVA's framing (Public = state banks; Private = private +
 * foreign banks) — see LIQ_OWNERSHIP in lib/metrics.ts.
 *
 * Out of scope (no data source here): investment-fund volumes/flows & fund
 * dollarization (TEFAS), under-the-mattress gold stock and weekly reserve-flow
 * attribution (BBVA-proprietary estimates), the FCI composite (Bloomberg
 * inputs), and net-reserves-excluding-swaps (needs CBRT swap stock).
 */
import {
  weeklyOwnershipRatio,
  weeklyGrowth,
  weeklyGrowthByOwnership,
  weeklyDollarization,
  evdsMulti,
  evdsSeries,
  latestPeriod,
  WEEKLY_BANK_TYPES,
  LIQ_OWNERSHIP_LABELS,
  LIQ_DOLLARIZATION_LABELS,
  type TimeSeriesRow,
  type WeeklyRow,
  type EvdsRow,
} from "@/app/lib/metrics";
import { PageHeader } from "@/app/components/ui";
import TrendChart from "@/app/components/TrendChart";
import TimeSeriesChart from "@/app/components/TimeSeriesChart";

export const dynamic = "force-dynamic";

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

// Long-form rows → TrendChart points (structurally identical; keeps types tidy).
function toTrend(rows: (TimeSeriesRow | WeeklyRow)[]): { period: string; bank_type_code: string; value: number }[] {
  return rows.map((r) => ({ period: r.period, bank_type_code: r.bank_type_code, value: r.value }));
}

// EVDS rows → TimeSeriesChart points, scaling the value (e.g. /1000 → bn).
function toPoints(rows: EvdsRow[], scale = 1): { period_date: string; value: number }[] {
  return rows.map((r) => ({ period_date: r.period_date, value: r.value * scale }));
}

// Sum several EVDS series by date (used for FX cash = USD + EUR-eq deposits).
function sumByDate(sets: EvdsRow[][], scale = 1): { period_date: string; value: number }[] {
  const acc = new Map<string, number>();
  for (const set of sets) {
    for (const r of set) acc.set(r.period_date, (acc.get(r.period_date) ?? 0) + r.value);
  }
  return Array.from(acc.entries())
    .sort((a, b) => a[0].localeCompare(b[0]))
    .map(([period_date, v]) => ({ period_date, value: v * scale }));
}

export default async function LiquidityPage() {
  const LOANS = { category: "krediler", item_id: "1.0.1" };
  const DEPOSITS = { category: "mevduat", item_id: "4.0.1" };
  const sector = [WEEKLY_BANK_TYPES.SECTOR];

  const [
    tlLtd, fcLtd,
    depYoY, dep13w,
    depGrowthPubPriv,
    dollarization,
    evds, reer,
  ] = await Promise.all([
    // Loan-to-deposit ratios, public vs private
    weeklyOwnershipRatio(LOANS.category, LOANS.item_id, DEPOSITS.category, DEPOSITS.item_id, "TL"),
    weeklyOwnershipRatio(LOANS.category, LOANS.item_id, DEPOSITS.category, DEPOSITS.item_id, "FX"),
    // TL deposit growth, sector — YoY (52w) + 13w annualized
    weeklyGrowth(DEPOSITS.category, DEPOSITS.item_id, "TL", 52, sector),
    weeklyGrowth(DEPOSITS.category, DEPOSITS.item_id, "TL", 13, sector),
    // TL deposit growth, public vs private (YoY)
    weeklyGrowthByOwnership(DEPOSITS.category, DEPOSITS.item_id, "TL", 52),
    // Deposit dollarization (sector / public / private)
    weeklyDollarization(),
    // CBRT funding + reserves + residents' FC (EVDS, already in D1)
    evdsMulti(
      ["TP.APIFON3", "TP.AB.TOPLAM", "TP.HPBITABLO4.4", "TP.HPBITABLO4.5", "TP.HPBITABLO4.7"],
      3,
    ),
    // REER over a longer horizon to show the real-appreciation trend
    evdsSeries("TP.RK.T1.Y", 8),
  ]);

  // TL deposit growth, sector — combine the two windows into one chart.
  const tlDepGrowthSector = [
    ...depYoY.map((r) => ({ period: r.period, bank_type_code: "YOY", value: r.value })),
    ...dep13w.map((r) => ({ period: r.period, bank_type_code: "W13", value: r.value })),
  ];

  // EVDS-derived series. APIFON3 is million TL → TrendChart "bn" divides by 1000.
  const netFunding = (evds["TP.APIFON3"] ?? []).map((r) => ({
    period: r.period_date,
    bank_type_code: "NETFUND",
    value: r.value,
  }));

  // Reserves & residents' FC are in USD millions → /1000 for USD bn.
  const grossReserves = {
    "Gross reserves": toPoints(evds["TP.AB.TOPLAM"] ?? [], 1 / 1000),
  };
  const residentsFc = {
    "FX cash (USD + EUR)": sumByDate(
      [evds["TP.HPBITABLO4.4"] ?? [], evds["TP.HPBITABLO4.5"] ?? []],
      1 / 1000,
    ),
    "Precious metals": toPoints(evds["TP.HPBITABLO4.7"] ?? [], 1 / 1000),
  };
  const reerSeries = { "REER (CPI based, 2003=100)": toPoints(reer) };

  return (
    <main className="mx-auto w-full max-w-[1440px] px-4 py-8 sm:px-6 lg:px-8 space-y-8">
      <PageHeader
        eyebrow="Adapted from BBVA / Garanti BBVA Research"
        title="Liquidity"
        description="TL & FC funding · dollarization · CBRT reserves and funding — BDDK weekly bulletin + TCMB EVDS"
        dataThrough={latestPeriod(tlLtd, fcLtd, dollarization, netFunding)}
      />

      <Section
        title="TL Funding"
        subtitle="Loan-to-deposit pressure and deposit momentum on the TL book. Public = state banks; Private = private + foreign banks (BBVA framing)."
      >
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <TrendChart
            data={toTrend(tlLtd)}
            seriesLabels={LIQ_OWNERSHIP_LABELS}
            title="TL Loan / Deposit Ratio (%) — public vs private"
            yFormat="pct"
            decimals={0}
          />
          <TrendChart
            data={tlDepGrowthSector}
            seriesLabels={{ YOY: "YoY", W13: "13-week annualized" }}
            title="TL Deposit Growth — sector (%)"
            yFormat="pct"
            decimals={1}
            zeroLine
          />
        </div>
        <TrendChart
          data={toTrend(depGrowthPubPriv)}
          seriesLabels={LIQ_OWNERSHIP_LABELS}
          title="TL Deposit Growth YoY (%) — public vs private"
          yFormat="pct"
          decimals={1}
          zeroLine
          height={320}
        />
      </Section>

      <Section
        title="FC & Dollarization"
        subtitle="Foreign-currency funding pressure and households' appetite for FC savings vs TL."
      >
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <TrendChart
            data={toTrend(fcLtd)}
            seriesLabels={LIQ_OWNERSHIP_LABELS}
            title="FC Loan / Deposit Ratio (%) — public vs private"
            yFormat="pct"
            decimals={0}
          />
          <TrendChart
            data={toTrend(dollarization)}
            seriesLabels={LIQ_DOLLARIZATION_LABELS}
            title="Deposit Dollarization — FC share of deposits (%)"
            yFormat="pct"
            decimals={1}
          />
        </div>
        <TimeSeriesChart
          series={residentsFc}
          title="Residents' FC Savings — households (USD bn)"
          yFormat="raw"
          decimals={0}
        />
      </Section>

      <Section
        title="CBRT Liquidity & Reserves"
        subtitle="System TL liquidity stance and the central bank's FX reserve buffer."
      >
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <TrendChart
            data={netFunding}
            seriesLabels={{ NETFUND: "Net CBRT funding" }}
            title="Net CBRT Funding (TL bn) — + excess / − lack of TL liquidity"
            yFormat="bn"
            decimals={0}
            zeroLine
          />
          <TimeSeriesChart
            series={grossReserves}
            title="CBRT Gross International Reserves (USD bn)"
            yFormat="raw"
            decimals={0}
          />
        </div>
      </Section>

      <Section
        title="Macro Backdrop"
        subtitle="Real appreciation eases financial conditions and supports the appetite for TL savings."
      >
        <TimeSeriesChart
          series={reerSeries}
          title="Real Effective Exchange Rate (CPI based, 2003 = 100)"
          yFormat="rate"
          decimals={1}
        />
      </Section>
    </main>
  );
}
