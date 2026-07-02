/**
 * Asset Quality tab — NPL ratio, NPL by bank, coverage, gross NPL level,
 * consumer NPL composition + ratios, commercial NPL ratios.
 */
import {
  ratioNpl,
  ratioCoverage,
  consumerNplMix,
  consumerNplRatios,
  commercialNplRatios,
  weeklySeries,
  latestPerBank,
  latestPeriod,
  PRIMARY_BANK_TYPES,
  WEEKLY_BANK_TYPES,
  BANK_TYPE_LABELS,
  type TimeSeriesRow,
} from "@/app/lib/metrics";
import { PageHeader, Section } from "@/app/components/ui";
import BarByBank from "@/app/components/BarByBank";
import TrendChart from "@/app/components/TrendChart";
import StackedArea from "@/app/components/StackedArea";
import Takeaway from "@/app/components/Takeaway";
import { assetQualityInsights } from "@/app/lib/insights";

export const dynamic = "force-dynamic";

// Reshape `consumerNplRatios` rows into long-form TrendChart input keyed by
// a synthetic "bank_type_code" per segment (so we get one line per segment).
function ratiosToTrendRows(
  rows: Array<{ period: string; housing: number | null; auto: number | null; gpl: number | null; cards: number | null }>,
): TimeSeriesRow[] {
  const out: TimeSeriesRow[] = [];
  for (const r of rows) {
    if (r.housing != null) out.push({ period: r.period, bank_type_code: "HOUSING", value: r.housing });
    if (r.auto    != null) out.push({ period: r.period, bank_type_code: "AUTO",    value: r.auto });
    if (r.gpl     != null) out.push({ period: r.period, bank_type_code: "GPL",     value: r.gpl });
    if (r.cards   != null) out.push({ period: r.period, bank_type_code: "CARDS",   value: r.cards });
  }
  return out;
}

function commercialToTrendRows(
  rows: Array<{ period: string; sme: number | null; commercial: number | null; non_sme: number | null }>,
): TimeSeriesRow[] {
  const out: TimeSeriesRow[] = [];
  for (const r of rows) {
    if (r.sme        != null) out.push({ period: r.period, bank_type_code: "SME",        value: r.sme });
    if (r.commercial != null) out.push({ period: r.period, bank_type_code: "COMMERCIAL", value: r.commercial });
    if (r.non_sme    != null) out.push({ period: r.period, bank_type_code: "NONSME",     value: r.non_sme });
  }
  return out;
}

export default async function AssetQualityPage() {
  const sector = [WEEKLY_BANK_TYPES.SECTOR];
  const groups = PRIMARY_BANK_TYPES.filter((c) => c !== "10001");

  const [
    nplAll, nplByBank, coverageAll, gross,
    cMix, cRatios, commRatios,
  ] = await Promise.all([
    ratioNpl(PRIMARY_BANK_TYPES),
    latestPerBank(ratioNpl, groups),
    ratioCoverage(PRIMARY_BANK_TYPES),
    // Real reported NPL stock from the weekly bulletin (2.0.1), in place of the
    // old loans × npl_ratio synthesis.
    weeklySeries("takipteki_alacaklar", "2.0.1", "TOTAL", sector, 156),
    consumerNplMix(),
    consumerNplRatios(),
    commercialNplRatios(),
  ]);

  const SECTOR = "10001";
  const consumerTrend = ratiosToTrendRows(cRatios);
  const commercialTrend = commercialToTrendRows(commRatios);

  // "The Read" — deterministic, computed from the same series the charts show.
  const read = assetQualityInsights({
    npl: nplAll.filter((r) => r.bank_type_code === SECTOR),
    coverage: coverageAll.filter((r) => r.bank_type_code === SECTOR),
    grossNpl: gross,
    cardsNpl: consumerTrend.filter((r) => r.bank_type_code === "CARDS"),
    smeNpl: commercialTrend.filter((r) => r.bank_type_code === "SME"),
  });

  return (
    <main className="mx-auto w-full max-w-[1440px] px-4 py-8 sm:px-6 lg:px-8 space-y-8">
      <PageHeader
        title="Asset Quality"
        description="NPL ratio + coverage · sub-segment NPL ratios · BDDK Tables 4, 5, 15 + weekly bulletin"
        rangeSelector
        dataThrough={latestPeriod(nplAll, coverageAll)}
      />

      <Takeaway data={read} />

      <Section index="01" title="NPL Ratio">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div className="lg:col-span-2">
            <TrendChart
              data={nplAll}
              seriesLabels={BANK_TYPE_LABELS}
              title="NPL Ratio (%) — by group"
              yFormat="pct"
              decimals={2}
            />
          </div>
          <BarByBank
            data={nplByBank}
            labels={BANK_TYPE_LABELS}
            title={`NPL by group · ${nplByBank[0]?.period ?? ""}`}
            format="pct"
            decimals={2}
          />
        </div>
      </Section>

      <Section index="02" title="Coverage & Stock" description="Provisions over gross NPL + absolute NPL stock.">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <TrendChart
            data={coverageAll}
            seriesLabels={BANK_TYPE_LABELS}
            title="Provisions / Gross NPL (%) — by group"
            yFormat="pct"
            decimals={1}
          />
          <TrendChart
            data={gross}
            seriesLabels={{ [WEEKLY_BANK_TYPES.SECTOR]: "Gross NPL" }}
            title="Gross NPL — Level (sector, TL bn · weekly)"
            yFormat="bn"
            decimals={0}
          />
        </div>
      </Section>

      <Section index="03" title="Consumer NPL Breakdown" description="Where household-credit deterioration is concentrated — derived from BDDK Table 4 sub-segments, sector only.">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <StackedArea
            data={cMix.map((r) => ({
              period: r.period,
              Housing: r.housing ?? 0,
              Auto: r.auto ?? 0,
              "Gen. Purpose": r.gpl ?? 0,
              "Retail Cards": r.cards ?? 0,
            }))}
            series={[
              { key: "Housing", label: "Housing" },
              { key: "Auto", label: "Auto" },
              { key: "Gen. Purpose", label: "Gen. Purpose" },
              { key: "Retail Cards", label: "Retail Cards" },
            ]}
            title="Consumer NPL — Composition (sector, TL bn)"
            yFormat="bn"
            decimals={0}
          />
          <TrendChart
            data={consumerTrend}
            seriesLabels={{
              HOUSING: "Housing",
              AUTO: "Auto",
              GPL: "Gen. Purpose",
              CARDS: "Retail Cards",
            }}
            title="Consumer NPL Ratio by Product (%)"
            yFormat="pct"
            decimals={2}
          />
        </div>
      </Section>

      <Section index="04" title="Commercial NPL by Segment" description="SME vs commercial-total vs derived non-SME, weekly BDDK bulletin (sector).">
        <TrendChart
          data={commercialTrend}
          seriesLabels={{
            SME: "SME",
            COMMERCIAL: "Commercial (all)",
            NONSME: "Non-SME (derived)",
          }}
          title="Commercial NPL Ratio (%) — sector"
          yFormat="pct"
          decimals={2}
          height={320}
        />
      </Section>
    </main>
  );
}
