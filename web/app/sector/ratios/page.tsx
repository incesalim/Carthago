/**
 * Sector — Key Ratios dashboard.
 *
 * - URL-driven bank-type filter (?type=10003 etc.)
 * - Each KPI card shows a sparkline of the full time-series
 * - All queries fan out in parallel with Promise.all
 */
import {
  ratioLdr,
  ratioNim,
  ratioNpl,
  ratioRoa,
  ratioRoe,
  totalAssets,
  latestPeriod,
  BANK_TYPES,
  BANK_TYPE_LABELS,
  type TimeSeriesRow,
} from "@/app/lib/metrics";
import { PageHeader } from "@/app/components/ui";
import BankTypeFilter from "./BankTypeFilter";
import Sparkline from "./Sparkline";

export const dynamic = "force-dynamic";

interface KpiCardProps {
  label: string;
  value: string;
  period: string;
  hint?: string;
  series: TimeSeriesRow[];
  format?: "pct" | "trn" | "raw";
  decimals?: number;
}

function KpiCard({ label, value, period, hint, series, format, decimals }: KpiCardProps) {
  const sparkData = series.map((r) => ({ period: r.period, value: r.value }));
  return (
    <div className="rounded-lg border bg-card p-5 shadow-sm">
      <div className="text-xs uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
      <div className="mt-2 text-3xl font-semibold tabular-nums">{value}</div>
      <div className="mt-1 text-xs text-muted-foreground">
        {period}
        {hint ? ` · ${hint}` : ""}
      </div>
      <div className="mt-3">
        <Sparkline data={sparkData} format={format} decimals={decimals} />
      </div>
    </div>
  );
}

const fmtPct = (v: number | null | undefined, decimals = 2) =>
  v == null ? "—" : `${v.toFixed(decimals)}%`;

const fmtTrn = (v: number | null | undefined) =>
  v == null ? "—" : `₺${(v / 1_000_000).toFixed(2)} trn`;

const VALID_TYPES: string[] = Object.values(BANK_TYPES);

export default async function RatiosPage({
  searchParams,
}: {
  searchParams: Promise<{ type?: string }>;
}) {
  const params = await searchParams;
  const bankType: string = params.type && VALID_TYPES.includes(params.type)
    ? params.type
    : BANK_TYPES.SECTOR;
  const bt = [bankType];

  const [assets, npl, nim, ldr, roa, roe] = await Promise.all([
    totalAssets(bt),
    ratioNpl(bt),
    ratioNim(bt),
    ratioLdr(bt),
    ratioRoa(bt),
    ratioRoe(bt),
  ]);

  const a = assets.at(-1);
  const n = npl.at(-1);
  const c = nim.at(-1);
  const l = ldr.at(-1);
  const ra = roa.at(-1);
  const re = roe.at(-1);

  return (
    <main className="mx-auto w-full max-w-[1440px] px-4 py-8 sm:px-6 lg:px-8">
      <PageHeader
        eyebrow="Banking Sector"
        title="Key Ratios"
        dataThrough={latestPeriod(assets, npl, nim, ldr, roa, roe)}
        description={
          <>
            BDDK monthly bulletin · {BANK_TYPE_LABELS[bankType]} ({bankType}) · queried live from D1
          </>
        }
        className="mb-4"
      />

      <div className="mb-6">
        <BankTypeFilter active={bankType} />
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
        <KpiCard label="Total Assets" value={fmtTrn(a?.value)} period={a?.period ?? "—"}
                 series={assets} format="trn" decimals={2} />
        <KpiCard label="NPL Ratio" value={fmtPct(n?.value)} period={n?.period ?? "—"}
                 hint="Takipteki / Toplam Krediler" series={npl} format="pct" decimals={2} />
        <KpiCard label="Net Interest Margin" value={fmtPct(c?.value)} period={c?.period ?? "—"}
                 hint="annualized · NII / avg assets" series={nim} format="pct" decimals={2} />
        <KpiCard label="Loan / Deposit" value={fmtPct(l?.value, 1)} period={l?.period ?? "—"}
                 series={ldr} format="pct" decimals={1} />
        <KpiCard label="ROA" value={fmtPct(ra?.value)} period={ra?.period ?? "—"}
                 hint="annualized" series={roa} format="pct" decimals={2} />
        <KpiCard label="ROE" value={fmtPct(re?.value, 1)} period={re?.period ?? "—"}
                 hint="annualized" series={roe} format="pct" decimals={1} />
      </div>

      <div className="mt-10 text-xs text-muted-foreground">
        Each KPI = one D1 query · 6 queries in parallel · sparklines from 60+ months of history · rendered server-side at the edge
      </div>
    </main>
  );
}
