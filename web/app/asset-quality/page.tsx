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
import { PageHeader, Section, Stat } from "@/app/components/ui";
import BarByBank from "@/app/components/BarByBank";
import TrendChart from "@/app/components/TrendChart";
import StackedArea from "@/app/components/StackedArea";
import Takeaway from "@/app/components/Takeaway";
import { assetQualityInsights } from "@/app/lib/insights";
import { withLlmHeadline } from "@/app/lib/read-headlines";
import {
  sectorStageShares,
  STAGE_SHARE_LABELS,
  nplFormationAnnual,
  NPL_FORMATION_LABELS,
  provisionMigrationScenarios,
} from "@/app/lib/credit-risk";

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
    stageShares, formation, migration,
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
    // Forward-looking layer (audited §7): TFRS-9 staging, NPL roll-forward,
    // and the Stage-2 migration scenario.
    sectorStageShares(),
    nplFormationAnnual(),
    provisionMigrationScenarios(),
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
    stage2: stageShares.filter((r) => r.bank_type_code === "STAGE2"),
  });

  return (
    <main className="mx-auto w-full max-w-[1440px] px-4 py-8 sm:px-6 lg:px-8 space-y-8">
      <PageHeader
        title="Asset Quality"
        description="NPL ratio + coverage · sub-segment NPL ratios · BDDK Tables 4, 5, 15 + weekly bulletin"
        rangeSelector
        dataThrough={latestPeriod(nplAll, coverageAll)}
      />

      <Takeaway data={await withLlmHeadline("asset-quality", read)} />

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

      {(stageShares.length > 0 || formation.length > 0) && (
        <Section
          index="02"
          title="The forward indicators"
          description="Where the NEXT NPLs come from — TFRS-9 Stage-2 migration and the NPL roll-forward, aggregated across reporting banks (audited quarterly, ~98% of sector)."
        >
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {stageShares.length > 0 && (
              <TrendChart
                data={stageShares}
                seriesLabels={STAGE_SHARE_LABELS}
                title="TFRS-9 staging — % of gross loans (audited quarterly)"
                yFormat="pct"
                decimals={1}
              />
            )}
            {formation.length > 0 && (
              <TrendChart
                data={formation}
                seriesLabels={NPL_FORMATION_LABELS}
                title="NPL roll-forward — formation vs exits (annual, ₺bn)"
                yFormat="bn"
                decimals={0}
              />
            )}
          </div>
          {migration.scenarios.length > 0 && (
            <div className="space-y-2">
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                {migration.scenarios.map((s) => (
                  <Stat
                    key={s.migratePct}
                    label={`${s.migratePct}% of Stage-2 migrates`}
                    value={`+₺${s.provisionBn.toFixed(0)}bn provisions`}
                    hint={
                      s.pctOfEclStock != null
                        ? `+${s.pctOfEclStock.toFixed(1)}% of today's ECL stock`
                        : undefined
                    }
                    tone={s.migratePct >= 20 ? "warning" : "neutral"}
                  />
                ))}
              </div>
              <p className="text-xs text-muted-foreground">
                Sizing device, not a forecast: migration provisioned at the current Stage-3
                coverage rate ({migration.cov3 != null ? `${(migration.cov3 * 100).toFixed(0)}%` : "—"})
                vs Stage-2 today ({migration.cov2 != null ? `${(migration.cov2 * 100).toFixed(0)}%` : "—"}),
                Stage-2 book ₺{migration.stage2Bn?.toFixed(0)}bn · {migration.period}.
              </p>
            </div>
          )}
        </Section>
      )}

      <Section index="03" title="Coverage & Stock" description="Provisions over gross NPL + absolute NPL stock.">
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

      <Section index="04" title="Consumer NPL Breakdown" description="Where household-credit deterioration is concentrated — derived from BDDK Table 4 sub-segments, sector only.">
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

      <Section index="05" title="Commercial NPL by Segment" description="SME vs commercial-total vs derived non-SME, weekly BDDK bulletin (sector).">
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
