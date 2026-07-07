/**
 * Liquidity tab — adapts the liquidity section of the BBVA (Garanti BBVA
 * Research) "Türkiye Banking Sector Outlook" into our data.
 *
 * Structure mirrors the report: TL funding, FC & dollarization, CBRT
 * reserves/funding, and the real-appreciation backdrop. Public-vs-private
 * cuts follow BBVA's framing (Public = state banks; Private = private +
 * foreign banks) — see LIQ_OWNERSHIP in lib/metrics.ts.
 *
 * TCMB publishes NO net-reserves headline (only gross AB.TOPLAM + the IMF
 * reserve-template components), so NIR is DERIVED from the analytical balance
 * sheet (FX assets TP.BL054 − FX liabilities TP.BL122, converted to USD). The
 * swap SPOT leg sits in BL054 (verified: net moves with it), so it is split
 * into with-/excluding-swaps via the forward/swap short position from the IMF
 * template (TP.DOVVARNC.K15, monthly): net-excluding-swaps = NIR − |K15|.
 *
 * Out of scope (no data source here): investment-fund volumes/flows & fund
 * dollarization (TEFAS lacks an FC-fund category), under-the-mattress gold stock
 * and weekly reserve-flow attribution (BBVA-proprietary estimates), and the FCI
 * composite (Bloomberg inputs).
 */
import type { Metadata } from "next";
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
import { sectorLiquidityRatios, AUDIT_LIQUIDITY_LABELS } from "@/app/lib/audit-ratios";
import { PageHeader, Section } from "@/app/components/ui";
import TrendChart from "@/app/components/TrendChart";
import TimeSeriesChart from "@/app/components/TimeSeriesChart";
import Takeaway from "@/app/components/Takeaway";
import { liquidityInsights } from "@/app/lib/insights";
import { withLlmHeadline } from "@/app/lib/read-headlines";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Turkish Banks — Liquidity & Funding",
  description: "Liquidity and funding of Türkiye's banks: loan-to-deposit, LCR, FX liquidity and the deposit base from BDDK and BRSA data.",
  alternates: { canonical: "/liquidity" },
};

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

  const [
    tlLtd, fcLtd,
    tlGrowthYoY, tlGrowth13w, tlGrowthOwn,
    dollarization,
    evds, reer, liqRatios,
  ] = await Promise.all([
    // Loan-to-deposit ratios, public vs private
    weeklyOwnershipRatio(LOANS.category, LOANS.item_id, DEPOSITS.category, DEPOSITS.item_id, "TL"),
    weeklyOwnershipRatio(LOANS.category, LOANS.item_id, DEPOSITS.category, DEPOSITS.item_id, "FX"),
    // TL deposit growth — sector YoY (52w) + 13-week annualized momentum, plus
    // a public-vs-private 13w cut. Mirrors BBVA's two TL-deposit-growth panels.
    weeklyGrowth(DEPOSITS.category, DEPOSITS.item_id, "TL", 52, [WEEKLY_BANK_TYPES.SECTOR]),
    weeklyGrowth(DEPOSITS.category, DEPOSITS.item_id, "TL", 13, [WEEKLY_BANK_TYPES.SECTOR]),
    weeklyGrowthByOwnership(DEPOSITS.category, DEPOSITS.item_id, "TL", 13),
    // Deposit dollarization (sector / public / private)
    weeklyDollarization(),
    // CBRT funding + reserves + residents' FC (EVDS, already in D1). BL054/BL122
    // are the analytical-balance-sheet FX assets/liabilities for derived NIR;
    // DK.USD.A converts them from TL to USD; DOVVARNC.K15 is the forward/swap
    // short position used to split NIR into with-/excluding-swaps.
    evdsMulti(
      ["TP.APIFON3", "TP.AB.TOPLAM", "TP.BL054", "TP.BL122", "TP.DK.USD.A",
       "TP.DOVVARNC.K15",
       "TP.HPBITABLO4.4", "TP.HPBITABLO4.5", "TP.HPBITABLO4.7"],
      3,
    ),
    // REER over a longer horizon to show the real-appreciation trend
    evdsSeries("TP.RK.T1.Y", 8),
    // Audited §4 regulatory-liquidity ratios (LCR/NSFR/leverage), sector view
    sectorLiquidityRatios(),
  ]);

  // EVDS-derived series. APIFON3 is million TL → TrendChart "bn" divides by 1000.
  const netFunding = (evds["TP.APIFON3"] ?? []).map((r) => ({
    period: r.period_date,
    bank_type_code: "NETFUND",
    value: r.value,
  }));

  // TL deposit growth — merge sector YoY + 13w annualized into one chart.
  const tlDepGrowth = [
    ...tlGrowthYoY.map((r) => ({ period: r.period, bank_type_code: "YOY", value: r.value })),
    ...tlGrowth13w.map((r) => ({ period: r.period, bank_type_code: "W13", value: r.value })),
  ];

  // Reserves & residents' FC are in USD millions → /1000 for USD bn.
  // Derived net international reserves: (FX assets − FX liabilities) from the
  // CBRT analytical balance sheet (both TL thousand, weekly), converted to USD
  // bn at the same-date USD/TRY. (BL054−BL122) / USDTRY / 1e6 = USD bn. The
  // swap SPOT leg sits in BL054 (verified: net FX position moves with it), so
  // this net position INCLUDES swap FX.
  const usdMap = new Map((evds["TP.DK.USD.A"] ?? []).map((r) => [r.period_date, r.value]));
  const bl122Map = new Map((evds["TP.BL122"] ?? []).map((r) => [r.period_date, r.value]));
  const nir = (evds["TP.BL054"] ?? [])
    .filter((r) => bl122Map.has(r.period_date) && usdMap.get(r.period_date))
    .map((r) => ({
      period_date: r.period_date,
      value: (r.value - bl122Map.get(r.period_date)!) / usdMap.get(r.period_date)! / 1e6,
    }));
  // Forward/swap short position (IMF reserve template §2.2.1, monthly, USD m,
  // negative) = the off-BS FX owed forward, dominated by swaps. Net-excl-swaps
  // = NIR − |K15|. Stepped onto the weekly NIR dates (nearest-earlier month).
  const fwdRows = evds["TP.DOVVARNC.K15"] ?? [];
  const fwdBnAt = (date: string): number => {
    for (let i = fwdRows.length - 1; i >= 0; i--) {
      if (fwdRows[i].period_date <= date) return Math.abs(fwdRows[i].value) / 1000;
    }
    return 0;
  };
  const nirExSwaps = nir.map((p) => ({
    period_date: p.period_date,
    value: p.value - fwdBnAt(p.period_date),
  }));
  const reserves = {
    "Gross reserves": toPoints(evds["TP.AB.TOPLAM"] ?? [], 1 / 1000),
    "Net int'l reserves": nir,
    "Net excl. swaps": nirExSwaps,
  };
  const residentsFc = {
    "FX cash (USD + EUR)": sumByDate(
      [evds["TP.HPBITABLO4.4"] ?? [], evds["TP.HPBITABLO4.5"] ?? []],
      1 / 1000,
    ),
    "Precious metals": toPoints(evds["TP.HPBITABLO4.7"] ?? [], 1 / 1000),
  };
  const reerSeries = { "REER (CPI based, 2003=100)": toPoints(reer) };

  // "The Read" — deterministic, computed from the same series the charts show.
  const read = liquidityInsights({
    tlLdrPublic: toTrend(tlLtd).filter((r) => r.bank_type_code === "PUBLIC"),
    tlLdrPrivate: toTrend(tlLtd).filter((r) => r.bank_type_code === "PRIVATE"),
    dollarization: toTrend(dollarization).filter((r) => r.bank_type_code === "SECTOR"),
    netCbrtFunding: netFunding,
    lcr: liqRatios.filter((r) => r.bank_type_code === "LCR"),
  });

  return (
    <main className="mx-auto w-full max-w-[1440px] px-4 py-8 sm:px-6 lg:px-8 space-y-8">
      <PageHeader
        title="Liquidity"
        description="TL & FC funding · dollarization · CBRT reserves and funding — BDDK weekly bulletin + TCMB EVDS"
        rangeSelector
        dataThrough={latestPeriod(tlLtd, fcLtd, dollarization, netFunding)}
      />

      <Takeaway data={await withLlmHeadline("liquidity", read)} />

      <Section
        title="TL Funding"
        description="Loan-to-deposit pressure and TL deposit inflows — public vs private. Full maturity/demand breakdown lives on the Deposits tab."
      >
        <TrendChart
          data={toTrend(tlLtd)}
          seriesLabels={LIQ_OWNERSHIP_LABELS}
          title="TL Loan / Deposit Ratio (%) — public vs private"
          yFormat="pct"
          decimals={0}
          height={320}
        />
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <TrendChart
            data={tlDepGrowth}
            seriesLabels={{ YOY: "YoY", W13: "13-week annualized" }}
            title="TL Deposit Growth — sector (YoY & 13w annualized, %)"
            yFormat="pct"
            decimals={0}
            zeroLine
          />
          <TrendChart
            data={toTrend(tlGrowthOwn)}
            seriesLabels={LIQ_OWNERSHIP_LABELS}
            title="TL Deposit Growth — public vs private (13w annualized, %)"
            yFormat="pct"
            decimals={0}
            zeroLine
          />
        </div>
      </Section>

      <Section
        title="FC & Dollarization"
        description="Foreign-currency funding pressure and households' appetite for FC savings vs TL."
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
        description="System TL liquidity stance and the central bank's FX reserve buffer. Net reserves are derived from the analytical balance sheet (FX assets − liabilities); gross − net is required-reserve FX, and net − net-excl-swaps is the CBRT swap stock."
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
            series={reserves}
            title="CBRT International Reserves (USD bn) — gross, net, net excl. swaps"
            yFormat="raw"
            decimals={0}
          />
        </div>
      </Section>

      <Section
        title="Regulatory Liquidity (audited §4)"
        description="LCR, NSFR and leverage from the quarterly BRSA reports — asset-weighted average across reporting banks. These Basel ratios aren't in the monthly bulletin; this is the per-bank §4 lane aggregated to the sector."
      >
        <TrendChart
          data={liqRatios}
          seriesLabels={AUDIT_LIQUIDITY_LABELS}
          title="LCR / NSFR / Leverage (%) — sector, audited quarterly"
          yFormat="pct"
          decimals={0}
          height={320}
        />
      </Section>

      <Section
        title="Macro Backdrop"
        description="Real appreciation eases financial conditions and supports the appetite for TL savings."
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
