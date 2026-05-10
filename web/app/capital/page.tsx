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
    <main className="p-8 max-w-7xl mx-auto">
      <h1 className="text-3xl font-bold mb-2">Capital</h1>
      <p className="text-sm text-neutral-500 mb-6">
        Capital adequacy + equity + leverage · BDDK · regulatory min CAR = 12%
      </p>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-4">
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
    </main>
  );
}
