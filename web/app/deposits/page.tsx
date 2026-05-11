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

function Section({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  return (
    <section className="space-y-4">
      <div className="space-y-0.5">
        <h2 className="text-base font-semibold text-neutral-900">{title}</h2>
        {subtitle && <p className="text-xs text-neutral-500">{subtitle}</p>}
      </div>
      <div className="space-y-4">{children}</div>
    </section>
  );
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
    <main className="px-6 py-8 max-w-7xl mx-auto space-y-8">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Deposits</h1>
        <p className="text-sm text-neutral-500">
          Sector aggregate + group breakdown · BDDK monthly bulletin
        </p>
      </header>

      <Section title="Total Deposits Growth">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
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
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
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
      </Section>

      <Section title="Demand vs. Term" subtitle="Demand share of deposits and full maturity ladder.">
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
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
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
            title="Maturity Composition — Share (%)"
            percentStack
          />
          <TrendChart
            data={yoyAll.filter((r: TimeSeriesRow) => r.bank_type_code === BANK_TYPES.SECTOR)}
            seriesLabels={{ [BANK_TYPES.SECTOR]: "Sector deposits" }}
            title="Deposit YoY — sector"
            yFormat="pct"
            decimals={1}
            zeroLine
          />
        </div>
      </Section>
    </main>
  );
}
