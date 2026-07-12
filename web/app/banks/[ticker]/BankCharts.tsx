/**
 * The two per-bank trend charts, standalone.
 *
 * They used to live inside `ProfitabilitySection` next to a grid of stat tiles.
 * The Desk brief now states those same eight metrics as the engine ladder, so the
 * tiles are gone and the charts moved to where they explain something: the margin
 * bridge beside the ladder, the share trend beside the loan book.
 */
import TimeSeriesChart from "@/app/components/TimeSeriesChart";
import type { BankMetricRow } from "@/app/lib/heatmap";
import type { ShareRow } from "@/app/lib/market-share";

/** "2025Q3" → "2025-07-01" (quarter start), the x-axis TimeSeriesChart expects. */
function qStart(period: string): string {
  const m = /^(\d{4})Q([1-4])$/.exec(period);
  if (!m) return period;
  const month = (Number(m[2]) - 1) * 3 + 1;
  return `${m[1]}-${String(month).padStart(2, "0")}-01`;
}

const pts = (rows: BankMetricRow[], key: "loan_yield" | "deposit_cost") =>
  rows
    .filter((r) => r[key] != null)
    .map((r) => ({ period_date: qStart(r.period), value: (r[key] as number) * 100 }));

export function MarginBridgeChart({ rows, height = 250 }: { rows: BankMetricRow[]; height?: number }) {
  const yieldSeries = pts(rows, "loan_yield");
  const costSeries = pts(rows, "deposit_cost");
  if (yieldSeries.length < 2 && costSeries.length < 2) return null;
  return (
    <TimeSeriesChart
      series={{ "Loan yield": yieldSeries, "Deposit cost": costSeries }}
      title="Margin bridge — loan yield vs deposit cost (TTM, %)"
      description="What the book earns against what the funding costs — the spread is the gap."
      source="Source: audited P&L ÷ average balances, trailing twelve months"
      yFormat="pct"
      xFormat="quarter"
      decimals={1}
      height={height}
    />
  );
}

export function MarketShareChart({ rows, height = 230 }: { rows: ShareRow[]; height?: number }) {
  const s = (key: "assets_share" | "loans_share" | "deposits_share") =>
    rows.filter((r) => r[key] != null).map((r) => ({ period_date: qStart(r.period), value: (r[key] as number) * 100 }));
  const assets = s("assets_share");
  if (assets.length < 2) return null;
  return (
    <TimeSeriesChart
      series={{ Assets: assets, Loans: s("loans_share"), Deposits: s("deposits_share") }}
      title="Share of the system (%)"
      description="Share of the banks reporting each quarter (~98% of sector assets)."
      yFormat="pct"
      xFormat="quarter"
      decimals={2}
      height={height}
    />
  );
}
