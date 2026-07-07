/**
 * Market Risk tab — CAMELS "S" (Sensitivity to market risk). Homes spine S8
 * (the dashboard audit's P0). Per-bank §4 audit data aggregated "of reporting
 * banks": FX net open position and the interest-rate repricing gap.
 *
 * Securities mark-to-market (the third S-signal) is a documented fast-follow —
 * see web/app/lib/market-risk.ts.
 */
import type { Metadata } from "next";
import { PageHeader, Section, Stat } from "@/app/components/ui";
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
  niiSensitivity,
} from "@/app/lib/market-risk";
import Takeaway from "@/app/components/Takeaway";
import { marketRiskInsights } from "@/app/lib/insights";
import { withLlmHeadline } from "@/app/lib/read-headlines";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Turkish Banks — Market Risk (FX & Repricing)",
  description: "Market-risk profile of Türkiye's banks — FX net open position and interest-rate repricing gaps from BRSA disclosures.",
  alternates: { canonical: "/market-risk" },
};

const SECTOR = { SECTOR: "Sector (reporting banks)" };

export default async function MarketRiskPage() {
  const [nop, byCcy, gap1y, ladder, latest, nii] = await Promise.all([
    fxNopToCapital(),
    fxByCurrency(),
    repricingGap1y(),
    repricingLadder(),
    marketRiskLatestPeriod(),
    niiSensitivity(),
  ]);

  // "The Read" — deterministic, computed from the same series the charts show.
  const read = marketRiskInsights({ nop, gap1y });

  return (
    <main className="mx-auto w-full max-w-[1440px] px-4 py-8 sm:px-6 lg:px-8 space-y-8">
      <PageHeader
        eyebrow="Banking Sector · CAMELS S"
        title="Market Risk"
        description="FX net open position and interest-rate repricing gap — per-bank BRSA §4 footnotes, aggregated across reporting banks (quarterly). Securities mark-to-market: coming soon."
        dataThrough={latest ?? undefined}
      />

      <Takeaway data={await withLlmHeadline("market-risk", read)} />

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

      {nii.scenarios.length > 0 && (
        <Section
          title="What a rate move does to NII"
          description={`First-order one-year ΔNII from a parallel shift, off the ${nii.period ?? "latest"} sector repricing ladder (≤1y buckets, bucket midpoints). Assumes no repricing beta or behavioral offsets — a sizing device, not a forecast.`}
        >
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            {nii.scenarios.map((s) => (
              <Stat
                key={s.bps}
                label={`${s.bps > 0 ? "+" : ""}${s.bps} bps`}
                value={`${s.niiBn >= 0 ? "+" : "−"}₺${Math.abs(s.niiBn).toFixed(0)}bn`}
                hint={s.pctRsa != null ? `${s.pctRsa >= 0 ? "+" : ""}${s.pctRsa.toFixed(2)}% of rate-sensitive assets` : undefined}
                tone={s.niiBn >= 0 ? "positive" : "warning"}
              />
            ))}
          </div>
        </Section>
      )}
    </main>
  );
}
