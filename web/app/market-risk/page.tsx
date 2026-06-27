/**
 * Market Risk tab — CAMELS "S" (Sensitivity to market risk). Homes spine S8
 * (the dashboard audit's P0). Per-bank §4 audit data aggregated "of reporting
 * banks": FX net open position and the interest-rate repricing gap.
 *
 * Securities mark-to-market (the third S-signal) is a documented fast-follow —
 * see web/app/lib/market-risk.ts.
 */
import { PageHeader, Section } from "@/app/components/ui";
import { ChartCard } from "@/app/components/ui/chart-card";
import TrendChart from "@/app/components/TrendChart";
import BopFlowChart from "@/app/components/BopFlowChart";
import {
  fxNopToCapital,
  fxByCurrency,
  FX_CURRENCY_BARS,
  repricingGap1y,
  repricingLadder,
  marketRiskLatestPeriod,
} from "@/app/lib/market-risk";

export const dynamic = "force-dynamic";

const SECTOR = { SECTOR: "Sector (reporting banks)" };

export default async function MarketRiskPage() {
  const [nop, byCcy, gap1y, ladder, latest] = await Promise.all([
    fxNopToCapital(),
    fxByCurrency(),
    repricingGap1y(),
    repricingLadder(),
    marketRiskLatestPeriod(),
  ]);

  return (
    <main className="mx-auto w-full max-w-[1440px] px-4 py-8 sm:px-6 lg:px-8 space-y-8">
      <PageHeader
        eyebrow="Banking Sector · CAMELS S"
        title="Market Risk"
        description="FX net open position and interest-rate repricing gap — per-bank BRSA §4 footnotes, aggregated across reporting banks (quarterly). Securities mark-to-market: coming soon."
        dataThrough={latest ?? undefined}
      />

      <Section
        title="FX exposure"
        description="The sector's net foreign-currency position. A small net-open-position / capital ratio means on- and off-balance FX is well-matched; the by-currency split shows where the system is net long (+) or short (−)."
      >
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <TrendChart
            data={nop}
            seriesLabels={SECTOR}
            title="FX net open position / regulatory capital (%)"
            yFormat="pct"
            decimals={1}
            zeroLine
          />
          <ChartCard title="FX net position by currency (₺bn) — net long (+) / short (−)">
            <BopFlowChart data={byCcy} bars={FX_CURRENCY_BARS} unit=" ₺bn" decimals={0} />
          </ChartCard>
        </div>
      </Section>

      <Section
        title="Interest-rate sensitivity"
        description="The repricing/maturity gap — rate-sensitive assets minus liabilities by bucket. A large net gap in the near buckets means net interest income is exposed to a rate move. Participation banks that don't disclose the schedule are excluded."
      >
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <ChartCard title={`Repricing gap by bucket (₺bn)${ladder.period ? ` · ${ladder.period}` : ""}`}>
            <BopFlowChart data={ladder.data} bars={[{ key: "gap", label: "Net repricing gap" }]} unit=" ₺bn" decimals={0} />
          </ChartCard>
          <TrendChart
            data={gap1y}
            seriesLabels={SECTOR}
            title="Cumulative ≤1y repricing gap / total assets (%)"
            yFormat="pct"
            decimals={1}
            zeroLine
          />
        </div>
      </Section>
    </main>
  );
}
