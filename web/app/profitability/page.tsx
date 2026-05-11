/**
 * Profitability tab — ROE, ROA, NIM (all annualized).
 */
import {
  ratioRoe,
  ratioRoa,
  ratioNim,
  PRIMARY_BANK_TYPES,
  BANK_TYPE_LABELS,
} from "@/app/lib/metrics";
import TrendChart from "@/app/components/TrendChart";

export const dynamic = "force-dynamic";

export default async function ProfitabilityPage() {
  const [roe, roa, nim] = await Promise.all([
    ratioRoe(PRIMARY_BANK_TYPES),
    ratioRoa(PRIMARY_BANK_TYPES),
    ratioNim(PRIMARY_BANK_TYPES),
  ]);

  return (
    <main className="px-6 py-8 max-w-7xl mx-auto space-y-8">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Profitability</h1>
        <p className="text-sm text-neutral-500">
          ROE / ROA / NIM · annualized (YTD × 12 / month) · BDDK Table 15
        </p>
      </header>

      <section className="space-y-4">
        <div className="space-y-0.5">
          <h2 className="text-base font-semibold text-neutral-900">Returns</h2>
          <p className="text-xs text-neutral-500">Return on equity & assets by bank group.</p>
        </div>
        <TrendChart
          data={roe}
          seriesLabels={BANK_TYPE_LABELS}
          title="ROE — Annualized (%)"
          yFormat="pct"
          decimals={1}
          zeroLine
          height={300}
        />
        <TrendChart
          data={roa}
          seriesLabels={BANK_TYPE_LABELS}
          title="ROA — Annualized (%)"
          yFormat="pct"
          decimals={2}
          zeroLine
          height={300}
        />
      </section>

      <section className="space-y-4">
        <div className="space-y-0.5">
          <h2 className="text-base font-semibold text-neutral-900">Margins</h2>
        </div>
        <TrendChart
          data={nim}
          seriesLabels={BANK_TYPE_LABELS}
          title="Net Interest Margin — Annualized (%)"
          yFormat="pct"
          decimals={2}
        />
      </section>
    </main>
  );
}
