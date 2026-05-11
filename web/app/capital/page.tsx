/**
 * Capital tab — CAR, equity level + growth, leverage.
 */
import {
  ratioCar,
  totalEquity,
  equityYoY,
  leverage,
  latestPerBank,
  PRIMARY_BANK_TYPES,
  BANK_TYPES,
  BANK_TYPE_LABELS,
} from "@/app/lib/metrics";
import BarByBank from "@/app/components/BarByBank";
import TrendChart from "@/app/components/TrendChart";

export const dynamic = "force-dynamic";

export default async function CapitalPage() {
  const sector = [BANK_TYPES.SECTOR];
  const groups = PRIMARY_BANK_TYPES.filter((c) => c !== BANK_TYPES.SECTOR);

  const [
    carAll, carByBank, equity, equityYoYSec, lev,
  ] = await Promise.all([
    ratioCar(PRIMARY_BANK_TYPES),
    latestPerBank(ratioCar, groups),
    totalEquity(sector),
    equityYoY(sector),
    leverage(PRIMARY_BANK_TYPES),
  ]);

  return (
    <main className="px-8 py-8 space-y-8">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Capital</h1>
        <p className="text-sm text-neutral-500">
          Capital adequacy + equity + leverage · BDDK · regulatory min CAR = 12%
        </p>
      </header>

      <section className="space-y-4">
        <div className="space-y-0.5">
          <h2 className="text-base font-semibold text-neutral-900">Capital Adequacy</h2>
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div className="lg:col-span-2">
            <TrendChart
              data={carAll}
              seriesLabels={BANK_TYPE_LABELS}
              title="Capital Adequacy Ratio (%) — by group"
              yFormat="pct"
              decimals={1}
            />
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
          <h2 className="text-base font-semibold text-neutral-900">Equity & Leverage</h2>
          <p className="text-xs text-neutral-500">Sector equity level, growth, and gearing.</p>
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <TrendChart
            data={equity}
            seriesLabels={{ [BANK_TYPES.SECTOR]: "Equity" }}
            title="Total Equity — Level (sector)"
            yFormat="trn"
            decimals={2}
          />
          <TrendChart
            data={equityYoYSec}
            seriesLabels={{ [BANK_TYPES.SECTOR]: "Equity YoY" }}
            title="Equity Growth YoY (%)"
            yFormat="pct"
            decimals={1}
            zeroLine
          />
          <TrendChart
            data={lev}
            seriesLabels={BANK_TYPE_LABELS}
            title="Liabilities / Equity (%)"
            yFormat="pct"
            decimals={0}
          />
        </div>
      </section>
    </main>
  );
}
