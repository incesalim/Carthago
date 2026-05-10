/**
 * Deposits tab — total, growth, demand share, maturity composition.
 */
import {
  totalDeposits,
  demandDeposits,
  totalDepositsYoY,
  totalDepositsMoM,
  depositMaturityMix,
  latestPerBank,
  PRIMARY_BANK_TYPES,
  BANK_TYPES,
  BANK_TYPE_LABELS,
  type TimeSeriesRow,
} from "@/app/lib/metrics";
import BarByBank from "@/app/components/BarByBank";
import TrendChart from "@/app/components/TrendChart";
import StackedArea from "@/app/components/StackedArea";

export const dynamic = "force-dynamic";

function demandShare(total: TimeSeriesRow[], demand: TimeSeriesRow[]): TimeSeriesRow[] {
  const totalMap = new Map(total.map((r) => [r.period + "|" + r.bank_type_code, r.value]));
  const out: TimeSeriesRow[] = [];
  for (const r of demand) {
    const t = totalMap.get(r.period + "|" + r.bank_type_code);
    if (t == null || r.value == null || t === 0) continue;
    out.push({
      period: r.period,
      bank_type_code: r.bank_type_code,
      value: (r.value * 100) / t,
    });
  }
  return out;
}

export default async function DepositsPage() {
  const sector = [BANK_TYPES.SECTOR];
  const groups = PRIMARY_BANK_TYPES.filter((c) => c !== BANK_TYPES.SECTOR);

  const [
    depSector, demandSec,
    yoyAll, momSec, yoyByBank, mix,
  ] = await Promise.all([
    totalDeposits(sector),
    demandDeposits(sector),
    totalDepositsYoY(PRIMARY_BANK_TYPES),
    totalDepositsMoM(sector),
    latestPerBank(totalDepositsYoY, groups),
    depositMaturityMix(BANK_TYPES.SECTOR),
  ]);

  const dShare = demandShare(depSector, demandSec);

  return (
    <main className="p-8 max-w-7xl mx-auto">
      <h1 className="text-3xl font-bold mb-2">Deposits</h1>
      <p className="text-sm text-neutral-500 mb-6">
        Deposits · sector aggregate + group breakdown · BDDK monthly bulletin
      </p>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">
        <TrendChart
          data={depSector}
          seriesLabels={{ [BANK_TYPES.SECTOR]: "Sector" }}
          title="Total Deposits — Level (sector)"
          yFormat="trn"
          decimals={2}
        />
        <TrendChart
          data={yoyAll}
          seriesLabels={BANK_TYPE_LABELS}
          title="Deposit Growth YoY (%) by group"
          yFormat="pct"
          decimals={1}
          zeroLine
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-4">
        <div className="lg:col-span-2">
          <TrendChart
            data={momSec}
            seriesLabels={{ [BANK_TYPES.SECTOR]: "Sector" }}
            title="Deposit Growth MoM (%) — sector"
            yFormat="pct"
            decimals={2}
            zeroLine
          />
        </div>
        <BarByBank
          data={yoyByBank}
          labels={BANK_TYPE_LABELS}
          title={`Deposit YoY by group · ${yoyByBank[0]?.period ?? ""}`}
          format="pct"
          decimals={1}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <TrendChart
          data={demandSec}
          seriesLabels={{ [BANK_TYPES.SECTOR]: "Demand" }}
          title="Demand Deposits — Level"
          yFormat="trn"
          decimals={2}
        />
        <TrendChart
          data={dShare}
          seriesLabels={{ [BANK_TYPES.SECTOR]: "Demand share" }}
          title="Demand Share of Total Deposits (%)"
          yFormat="pct"
          decimals={1}
        />
        <StackedArea
          data={mix}
          series={[
            { key: "demand", label: "Demand" },
            { key: "maturity_1m", label: "≤1m" },
            { key: "maturity_1_3m", label: "1-3m" },
            { key: "maturity_3_6m", label: "3-6m" },
            { key: "maturity_6_12m", label: "6-12m" },
            { key: "maturity_over_12m", label: ">12m" },
          ]}
          title="Maturity Composition (sector)"
          yFormat="trn"
          decimals={1}
        />
      </div>
    </main>
  );
}
