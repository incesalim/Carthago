/**
 * MarketRiskSection — CAMELS "S" for one bank on /banks/[ticker]. The §4
 * footnotes turned into the market-risk view a strategist reads: the FX net
 * open position by currency, the regulatory NOP/capital ratio, and the
 * interest-rate repricing-gap ladder. Magnitude ratios are derived in
 * heatmap.ts (identical to Compare); the per-currency / per-bucket detail comes
 * from market-risk.ts. Renders nothing when the bank has no §4 market-risk data
 * (e.g. participation banks that don't disclose the repricing schedule).
 */
import { Section, Stat } from "@/app/components/ui";
import { ChartCard } from "@/app/components/ui/chart-card";
import BopFlowChart from "@/app/components/BopFlowChart";
import type { BankMetricRow } from "@/app/lib/heatmap";
import { FX_CURRENCY_BARS } from "@/app/lib/market-risk";

type FlowRow = Record<string, number | string | null>;
const pctV = (v: number | null | undefined, d = 1): string => (v == null ? "—" : `${v.toFixed(d)}%`);

export default function MarketRiskSection({
  rows,
  fxCcy,
  ladder,
}: {
  /** This bank's heatmap rows, ascending by period (carry fx_nop, repricing_gap_1y). */
  rows: BankMetricRow[];
  /** This bank's FX net position by currency over time (signed, ₺bn). */
  fxCcy: FlowRow[];
  /** This bank's repricing-gap ladder for the latest quarter (₺bn). */
  ladder: { data: FlowRow[]; period: string | null };
}) {
  const latest = rows[rows.length - 1] ?? null;
  const hasStats = latest != null && (latest.fx_nop != null || latest.repricing_gap_1y != null);
  if (!hasStats && fxCcy.length === 0 && ladder.data.length === 0) return null;

  return (
    <Section
      title="Market risk"
      description="FX net open position and interest-rate repricing gap from the bank's §4 footnotes — the magnitude ratios match Compare. A small FX-NOP / capital means on- and off-balance FX are well-matched; the by-currency split shows where the bank is net long (+) / short (−)."
      contentClassName=""
    >
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="FX NOP / capital" value={pctV(latest?.fx_nop)} />
        <Stat label="Repricing gap ≤1y / assets" value={pctV(latest?.repricing_gap_1y)} />
      </div>

      <div className="mt-4 grid grid-cols-1 lg:grid-cols-2 gap-4">
        {fxCcy.length > 0 && (
          <ChartCard title="FX net position by currency (₺bn) — net long (+) / short (−)">
            <BopFlowChart data={fxCcy} bars={FX_CURRENCY_BARS} unit=" ₺bn" decimals={0} />
          </ChartCard>
        )}
        {ladder.data.length > 0 && (
          <ChartCard title={`Repricing gap by bucket (₺bn)${ladder.period ? ` · ${ladder.period}` : ""}`}>
            <BopFlowChart data={ladder.data} bars={[{ key: "gap", label: "Net repricing gap" }]} unit=" ₺bn" decimals={0} />
          </ChartCard>
        )}
      </div>
    </Section>
  );
}
