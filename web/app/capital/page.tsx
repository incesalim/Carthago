/**
 * Capital tab — CAR, equity level + growth, leverage.
 */
import {
  ratioCar,
  ratioRwaDensity,
  ratioOffBsDerivatives,
  totalEquity,
  equityYoY,
  leverage,
  latestPerBank,
  latestPeriod,
  PRIMARY_BANK_TYPES,
  BANK_TYPES,
  BANK_TYPE_LABELS,
} from "@/app/lib/metrics";
import { PageHeader } from "@/app/components/ui";
import BarByBank from "@/app/components/BarByBank";
import TrendChart from "@/app/components/TrendChart";

export const dynamic = "force-dynamic";

export default async function CapitalPage() {
  const sector = [BANK_TYPES.SECTOR];
  const groups = PRIMARY_BANK_TYPES.filter((c) => c !== BANK_TYPES.SECTOR);

  const [
    carAll, carByBank, equity, equityYoYSec, lev,
    rwa, offBsDeriv,
  ] = await Promise.all([
    ratioCar(PRIMARY_BANK_TYPES),
    latestPerBank(ratioCar, groups),
    totalEquity(sector),
    equityYoY(sector),
    leverage(PRIMARY_BANK_TYPES),
    ratioRwaDensity(PRIMARY_BANK_TYPES),
    ratioOffBsDerivatives(PRIMARY_BANK_TYPES),
  ]);

  return (
    <main className="mx-auto w-full max-w-[1440px] px-4 py-8 sm:px-6 lg:px-8 space-y-8">
      <PageHeader
        title="Capital"
        description="Capital adequacy + equity + leverage · BDDK · regulatory min CAR = 12%"
        rangeSelector
        dataThrough={latestPeriod(carAll, equity, lev)}
      />

      <section className="space-y-4">
        <div className="space-y-0.5">
          <h2 className="text-base font-semibold text-foreground">Capital Adequacy</h2>
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div className="lg:col-span-2">
            <TrendChart
              data={carAll}
              seriesLabels={BANK_TYPE_LABELS}
              title="Capital Adequacy Ratio (%) — by group"
              yFormat="pct"
              decimals={1}            />
          </div>
          <BarByBank
            data={carByBank}
            labels={BANK_TYPE_LABELS}
            title={`CAR by group · ${carByBank[0]?.period ?? ""}`}
            format="pct"
            decimals={1}
          />
        </div>
      </section>

      <section className="space-y-4">
        <div className="space-y-0.5">
          <h2 className="text-base font-semibold text-foreground">Equity & Leverage</h2>
          <p className="text-xs text-muted-foreground">Sector equity level, growth, and gearing.</p>
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <TrendChart
            data={equity}
            seriesLabels={{ [BANK_TYPES.SECTOR]: "Equity" }}
            title="Total Equity — Level (sector)"
            yFormat="trn"
            decimals={2}          />
          <TrendChart
            data={equityYoYSec}
            seriesLabels={{ [BANK_TYPES.SECTOR]: "Equity YoY" }}
            title="Equity Growth YoY (%)"
            yFormat="pct"
            decimals={1}
            zeroLine          />
          <TrendChart
            data={lev}
            seriesLabels={BANK_TYPE_LABELS}
            title="Liabilities / Equity (%)"
            yFormat="pct"
            decimals={0}          />
        </div>
      </section>

      <section className="space-y-4">
        <div className="space-y-0.5">
          <h2 className="text-base font-semibold text-foreground">Risk Density</h2>
          <p className="text-xs text-muted-foreground">
            How concentrated each group&apos;s balance-sheet risk is — lower RWA-net/gross
            means more low-weight exposure (govt bonds, cash). Off-BS derivatives /
            total assets shows derivative book size relative to balance sheet.
          </p>
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <TrendChart
            data={rwa}
            seriesLabels={BANK_TYPE_LABELS}
            title="RWA Net / Gross (%)"
            yFormat="pct"
            decimals={1}          />
          <TrendChart
            data={offBsDeriv}
            seriesLabels={BANK_TYPE_LABELS}
            title="Off-Balance-Sheet Derivatives / Total Assets (%)"
            yFormat="pct"
            decimals={1}          />
        </div>
      </section>
    </main>
  );
}
