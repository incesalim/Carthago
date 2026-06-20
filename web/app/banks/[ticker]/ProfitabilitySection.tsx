/**
 * ProfitabilitySection — the "drivers behind the outcomes" block on
 * /banks/[ticker]. The standardized statements show levels; this section turns
 * them into the ratios a strategist reads: the margin bridge (loan yield −
 * deposit cost = spread), cost of risk, pre-provision earning power, and the
 * bank's competitive share of the reporting universe.
 *
 * All figures are derived in heatmap.ts (margins, TTM basis) and market-share.ts
 * (shares of reporting banks) for the whole fleet, then filtered to this ticker —
 * one source of truth, identical numbers to /cross-bank.
 *
 * Server component; embeds the client TimeSeriesChart for the trends.
 */
import { Section, Stat } from "@/app/components/ui";
import TimeSeriesChart from "@/app/components/TimeSeriesChart";
import type { BankMetricRow } from "@/app/lib/heatmap";
import type { ShareRow } from "@/app/lib/market-share";

/** "2025Q3" → "2025-07-01" (quarter start) so TimeSeriesChart's quarter x-axis
 *  formatter (which parses a real date) renders "2025-Q3". */
function quarterToDate(period: string): string | null {
  const m = /^(\d{4})Q([1-4])$/.exec(period);
  if (!m) return null;
  const month = String((Number(m[2]) - 1) * 3 + 1).padStart(2, "0");
  return `${m[1]}-${month}-01`;
}

const pct = (v: number | null | undefined, d = 2): string =>
  v == null ? "—" : `${(v * 100).toFixed(d)}%`;

export default function ProfitabilitySection({
  rows,
  shareRows,
}: {
  /** This bank's heatmap rows, ascending by period. */
  rows: BankMetricRow[];
  /** This bank's market-share rows, ascending by period. */
  shareRows: ShareRow[];
}) {
  const latest = rows[rows.length - 1] ?? null;
  const latestShare = shareRows[shareRows.length - 1] ?? null;
  if (!latest) return null;

  // Margin-bridge trend: loan yield vs deposit cost (percent points).
  const yieldSeries: { period_date: string; value: number }[] = [];
  const costSeries: { period_date: string; value: number }[] = [];
  for (const r of rows) {
    const d = quarterToDate(r.period);
    if (!d) continue;
    if (r.loan_yield != null) yieldSeries.push({ period_date: d, value: r.loan_yield * 100 });
    if (r.deposit_cost != null) costSeries.push({ period_date: d, value: r.deposit_cost * 100 });
  }
  const hasMarginTrend = yieldSeries.length > 1 || costSeries.length > 1;

  // Market-share trend: assets / loans / deposits share (percent points).
  const aShare: { period_date: string; value: number }[] = [];
  const lShare: { period_date: string; value: number }[] = [];
  const dShare: { period_date: string; value: number }[] = [];
  for (const r of shareRows) {
    const d = quarterToDate(r.period);
    if (!d) continue;
    if (r.assets_share != null) aShare.push({ period_date: d, value: r.assets_share * 100 });
    if (r.loans_share != null) lShare.push({ period_date: d, value: r.loans_share * 100 });
    if (r.deposits_share != null) dShare.push({ period_date: d, value: r.deposits_share * 100 });
  }
  const hasShareTrend = aShare.length > 1 || lShare.length > 1 || dShare.length > 1;

  return (
    <Section
      title="Profitability & margins"
      description="Derived from the audited statements on a trailing-twelve-month basis — same figures as Compare. Market share is of the banks reporting each quarter (~98% of sector)."
      contentClassName=""
    >
      {/* Margin bridge + earnings-quality stats (latest quarter). */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
        <Stat label="ROE (TTM)" value={pct(latest.roe, 1)} />
        <Stat label="NIM (annualized)" value={pct(latest.nim)} />
        <Stat label="Loan yield (TTM)" value={pct(latest.loan_yield, 1)} />
        <Stat label="Deposit cost (TTM)" value={pct(latest.deposit_cost, 1)} />
        <Stat
          label="Loan–deposit spread"
          value={pct(latest.spread, 1)}
          tone={latest.spread == null ? "neutral" : latest.spread >= 0 ? "positive" : "negative"}
        />
        <Stat label="Cost of risk (TTM)" value={pct(latest.cost_of_risk)} />
        <Stat label="PPOP / assets (TTM)" value={pct(latest.ppop_ratio)} />
        <Stat label="Cost / income" value={pct(latest.cost_income, 1)} />
      </div>

      {hasMarginTrend && (
        <div className="mt-4">
          <TimeSeriesChart
            series={{ "Loan yield": yieldSeries, "Deposit cost": costSeries }}
            title="Margin bridge — loan yield vs deposit cost (TTM, %)"
            yFormat="pct"
            xFormat="quarter"
            decimals={1}
            height={280}
          />
        </div>
      )}

      {/* Competitive position. */}
      {latestShare && (
        <div className="mt-6">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Stat
              label="Assets share"
              value={pct(latestShare.assets_share)}
              hint={latestShare.assets_rank != null ? `#${latestShare.assets_rank} by assets` : undefined}
            />
            <Stat label="Loans share" value={pct(latestShare.loans_share)} />
            <Stat label="Deposits share" value={pct(latestShare.deposits_share)} />
          </div>
          {hasShareTrend && (
            <div className="mt-4">
              <TimeSeriesChart
                series={{ Assets: aShare, Loans: lShare, Deposits: dShare }}
                title="Market share of reporting banks (%)"
                yFormat="pct"
                xFormat="quarter"
                decimals={2}
                height={280}
              />
            </div>
          )}
        </div>
      )}
    </Section>
  );
}
