/**
 * Home / Overview tab.
 *
 * 6 sector-level KPI cards + bar chart of loan growth by bank type +
 * trend chart of NPL across groups.
 */
import {
  ratioCar,
  ratioLdr,
  ratioNpl,
  ratioRoe,
  totalAssets,
  totalLoansYoY,
  latestPerBank,
  PRIMARY_BANK_TYPES,
  BANK_TYPES,
  BANK_TYPE_LABELS,
} from "@/app/lib/metrics";
import BarByBank from "@/app/components/BarByBank";
import TrendChart from "@/app/components/TrendChart";
import Sparkline from "@/app/sector/ratios/Sparkline";
import type { TimeSeriesRow } from "@/app/lib/metrics";

export const dynamic = "force-dynamic";

interface KpiCardProps {
  label: string;
  value: string;
  period: string;
  hint?: string;
  series?: TimeSeriesRow[];
  format?: "pct" | "trn" | "raw";
  decimals?: number;
}

function KpiCard({ label, value, period, hint, series, format, decimals }: KpiCardProps) {
  return (
    <div className="rounded-lg border bg-white p-5 shadow-sm">
      <div className="text-xs uppercase tracking-wide text-neutral-500">{label}</div>
      <div className="mt-2 text-3xl font-semibold tabular-nums">{value}</div>
      <div className="mt-1 text-xs text-neutral-500">
        {period}{hint ? ` · ${hint}` : ""}
      </div>
      {series && series.length > 0 && (
        <div className="mt-3">
          <Sparkline
            data={series.map((r) => ({ period: r.period, value: r.value ?? 0 }))}
            format={format}
            decimals={decimals}
          />
        </div>
      )}
    </div>
  );
}

const fmtPct = (v: number | null | undefined, d = 2) =>
  v == null ? "—" : `${v.toFixed(d)}%`;
const fmtTrn = (v: number | null | undefined) =>
  v == null ? "—" : `₺${(v / 1_000_000).toFixed(2)} trn`;

export default async function OverviewPage() {
  const sector = [BANK_TYPES.SECTOR];
  const groupsExSector = PRIMARY_BANK_TYPES.filter((c) => c !== BANK_TYPES.SECTOR);

  const [
    assets, loansYoY, npl, car, ldr, roe,
    loanYoYByBank, nplAllGroups,
  ] = await Promise.all([
    totalAssets(sector),
    totalLoansYoY(sector),
    ratioNpl(sector),
    ratioCar(sector),
    ratioLdr(sector),
    ratioRoe(sector),
    latestPerBank(totalLoansYoY, groupsExSector),
    ratioNpl(PRIMARY_BANK_TYPES),
  ]);

  const a = assets.at(-1);
  const ly = loansYoY.at(-1);
  const n = npl.at(-1);
  const c = car.at(-1);
  const l = ldr.at(-1);
  const r = roe.at(-1);

  return (
    <main className="p-8 max-w-7xl mx-auto">
      <h1 className="text-3xl font-bold mb-2">Banking Sector — Overview</h1>
      <p className="text-sm text-neutral-500 mb-8">
        BDDK monthly bulletin · sector aggregate · live D1 query
      </p>

      <div className="grid grid-cols-2 lg:grid-cols-3 gap-4 mb-8">
        <KpiCard label="Total Assets" value={fmtTrn(a?.value)} period={a?.period ?? "—"}
                 series={assets} format="trn" decimals={2} />
        <KpiCard label="Loan Growth YoY" value={fmtPct(ly?.value, 1)} period={ly?.period ?? "—"}
                 series={loansYoY} format="pct" decimals={1} />
        <KpiCard label="NPL Ratio" value={fmtPct(n?.value)} period={n?.period ?? "—"}
                 series={npl} format="pct" decimals={2} />
        <KpiCard label="Capital Adequacy" value={fmtPct(c?.value, 1)} period={c?.period ?? "—"}
                 hint="SYR · regulatory min 12%" series={car} format="pct" decimals={1} />
        <KpiCard label="Loan / Deposit" value={fmtPct(l?.value, 1)} period={l?.period ?? "—"}
                 series={ldr} format="pct" decimals={1} />
        <KpiCard label="ROE (annualized)" value={fmtPct(r?.value, 1)} period={r?.period ?? "—"}
                 series={roe} format="pct" decimals={1} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <BarByBank
          data={loanYoYByBank}
          labels={BANK_TYPE_LABELS}
          title={`Loan Growth YoY by bank group · ${ly?.period ?? ""}`}
          format="pct"
          decimals={1}
        />
        <TrendChart
          data={nplAllGroups}
          seriesLabels={BANK_TYPE_LABELS}
          title="NPL Ratio — by bank group"
          yFormat="pct"
          decimals={2}
        />
      </div>
    </main>
  );
}
