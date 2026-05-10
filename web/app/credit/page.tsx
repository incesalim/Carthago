/**
 * Credit tab — loan growth, currency split, FX share.
 */
import {
  totalLoans,
  tlLoans,
  fxLoans,
  totalLoansYoY,
  totalLoansMoM,
  latestPerBank,
  PRIMARY_BANK_TYPES,
  BANK_TYPES,
  BANK_TYPE_LABELS,
  type TimeSeriesRow,
} from "@/app/lib/metrics";
import BarByBank from "@/app/components/BarByBank";
import TrendChart from "@/app/components/TrendChart";

export const dynamic = "force-dynamic";

/** Compute FX share of loans = fx / (tl + fx) per period, sector only. */
function computeFxShare(tl: TimeSeriesRow[], fx: TimeSeriesRow[]): TimeSeriesRow[] {
  const tlMap = new Map(tl.map((r) => [r.period + "|" + r.bank_type_code, r.value]));
  const out: TimeSeriesRow[] = [];
  for (const r of fx) {
    const key = r.period + "|" + r.bank_type_code;
    const t = tlMap.get(key);
    if (t == null || r.value == null || (t + r.value) === 0) continue;
    out.push({
      period: r.period,
      bank_type_code: r.bank_type_code,
      value: (r.value * 100) / (t + r.value),
    });
  }
  return out;
}

export default async function CreditPage() {
  const sector = [BANK_TYPES.SECTOR];
  const groups = PRIMARY_BANK_TYPES.filter((c) => c !== BANK_TYPES.SECTOR);

  const [
    loansSector, tlSec, fxSec,
    yoyAll, momAll, yoyByBank,
  ] = await Promise.all([
    totalLoans(sector),
    tlLoans(sector),
    fxLoans(sector),
    totalLoansYoY(PRIMARY_BANK_TYPES),
    totalLoansMoM(sector),
    latestPerBank(totalLoansYoY, groups),
  ]);

  const fxShare = computeFxShare(tlSec, fxSec);

  return (
    <main className="p-8 max-w-7xl mx-auto">
      <h1 className="text-3xl font-bold mb-2">Credit</h1>
      <p className="text-sm text-neutral-500 mb-6">
        Loans · sector aggregate + group breakdown · BDDK monthly bulletin
      </p>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">
        <TrendChart
          data={loansSector}
          seriesLabels={{ [BANK_TYPES.SECTOR]: "Sector" }}
          title="Total Loans — Level (sector)"
          yFormat="trn"
          decimals={2}
        />
        <TrendChart
          data={yoyAll}
          seriesLabels={BANK_TYPE_LABELS}
          title="Loan Growth YoY (%) by group"
          yFormat="pct"
          decimals={1}
          zeroLine
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-4">
        <div className="lg:col-span-2">
          <TrendChart
            data={momAll}
            seriesLabels={{ [BANK_TYPES.SECTOR]: "Sector" }}
            title="Loan Growth MoM (%) — sector"
            yFormat="pct"
            decimals={2}
            zeroLine
          />
        </div>
        <BarByBank
          data={yoyByBank}
          labels={BANK_TYPE_LABELS}
          title={`Loan YoY by group · ${yoyByBank[0]?.period ?? ""}`}
          format="pct"
          decimals={1}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <TrendChart
          data={tlSec}
          seriesLabels={{ [BANK_TYPES.SECTOR]: "TL Loans" }}
          title="TL Loans — Level"
          yFormat="trn"
          decimals={2}
        />
        <TrendChart
          data={fxSec}
          seriesLabels={{ [BANK_TYPES.SECTOR]: "FX Loans" }}
          title="FX Loans — Level (TL equivalent)"
          yFormat="trn"
          decimals={2}
        />
        <TrendChart
          data={fxShare}
          seriesLabels={{ [BANK_TYPES.SECTOR]: "FX share" }}
          title="FX Share of Total Loans (%)"
          yFormat="pct"
          decimals={1}
        />
      </div>
    </main>
  );
}
