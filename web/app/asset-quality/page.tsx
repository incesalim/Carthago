/**
 * Asset Quality tab — NPL ratio, NPL by bank, coverage, gross NPL level,
 * consumer NPL composition + ratios, commercial NPL ratios.
 */
import type { Metadata } from "next";
import {
  ratioNpl,
  ratioCoverage,
  consumerNplMix,
  consumerNplRatios,
  commercialNplRatios,
  weeklySeries,
  latestPerBank,
  PRIMARY_BANK_TYPES,
  WEEKLY_BANK_TYPES,
  BANK_TYPE_LABELS,
  type TimeSeriesRow,
} from "@/app/lib/metrics";
import Link from "next/link";
import { Section, Stat } from "@/app/components/ui";
import { GlobalRangeSelector } from "@/app/components/range-context";
import {
  ChartRow,
  Colophon,
  Depth,
  DeskHeader,
  SecHead,
  Vital,
  Vitals,
} from "@/app/components/desk";
import { lastVal, monthLabel, streak, valAgo } from "@/app/lib/desk";
import BarByBank from "@/app/components/BarByBank";
import TrendChart from "@/app/components/TrendChart";
import StackedArea from "@/app/components/StackedArea";
import Takeaway from "@/app/components/Takeaway";
import { assetQualityInsights } from "@/app/lib/insights";
import { seriesFinding } from "@/app/lib/chart-findings";
import { withLlmHeadline } from "@/app/lib/read-headlines";
import {
  sectorStageShares,
  STAGE_SHARE_LABELS,
  nplFormationAnnual,
  NPL_FORMATION_LABELS,
  provisionMigrationScenarios,
} from "@/app/lib/credit-risk";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Turkish Banks — Asset Quality & NPLs",
  description: "Non-performing loans, Stage 2 and Stage 3 exposures and coverage ratios across Türkiye's banking sector and by bank.",
  alternates: { canonical: "/asset-quality" },
};

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

  // ---- the brief's computed vitals -----------------------------------------
  const nplSector = nplAll.filter((r) => r.bank_type_code === SECTOR);
  const covSector = coverageAll.filter((r) => r.bank_type_code === SECTOR);
  const stage2 = stageShares.filter((r) => r.bank_type_code === "STAGE2");
  const cardsNpl = consumerTrend.filter((r) => r.bank_type_code === "CARDS");
  const smeNpl = commercialTrend.filter((r) => r.bank_type_code === "SME");

  const nplNow = lastVal(nplSector);
  const nplStreak = streak(nplSector, "up");
  const covNow = lastVal(covSector);
  const covD = covNow != null && covSector.at(-2)?.value != null ? covNow - (covSector.at(-2)!.value as number) : null;
  const s2Now = lastVal(stage2);
  const grossNow = lastVal(gross);
  const grossAgo = valAgo(gross, 52);
  const grossYoY = grossNow != null && grossAgo != null && grossAgo > 0 ? (grossNow / grossAgo - 1) * 100 : null;
  const cardsNow = lastVal(cardsNpl);
  const smeNow = lastVal(smeNpl);

  // "The Read" — deterministic, computed from the same series the charts show.
  const read = assetQualityInsights({
    npl: nplSector,
    coverage: covSector,
    grossNpl: gross,
    cardsNpl,
    smeNpl,
    stage2,
  });

  return (
    <main className="mx-auto w-full max-w-[1440px] px-4 py-7 sm:px-6 lg:px-9">
      <DeskHeader
        title="Asset Quality"
        record={
          <>
            Record <b className="font-normal text-foreground">{monthLabel(nplSector.at(-1)?.period)}</b> · vs{" "}
            {monthLabel(nplSector.at(-2)?.period, false)} · stages: quarterly filings
          </>
        }
        right="every figure computed from source series"
      />

      <SecHead
        title="The vitals"
        meta="level · direction · pipeline · cover"
        className="mb-2.5 mt-6"
      />
      <Vitals>
        <Vital
          label="NPL ratio"
          value={nplNow != null ? nplNow.toFixed(2) : "—"}
          unit="%"
          series={nplSector.slice(-13)}
          note={
            nplStreak >= 3 ? (
              <em className="not-italic font-semibold text-negative">
                {nplStreak} straight rises
              </em>
            ) : (
              "broadly stable"
            )
          }
        />
        <Vital
          label="Stage-2 share"
          value={s2Now != null ? s2Now.toFixed(1) : "—"}
          unit="%"
          series={stage2.slice(-8)}
          decimals={1}
          note="the pre-NPL watchlist — audited quarterly"
        />
        <Vital
          label="NPL coverage"
          value={covNow != null ? covNow.toFixed(1) : "—"}
          unit="%"
          series={covSector.slice(-13)}
          decimals={1}
          note={
            covD != null && covD < -0.3
              ? "thinning as the stock grows"
              : "provisions / gross NPL"
          }
        />
        <Vital
          label="Gross NPL stock, y/y"
          value={grossYoY != null ? `+${grossYoY.toFixed(0)}` : "—"}
          unit="%"
          note={
            nplNow != null && nplNow < 3 ? (
              <>
                fast off a low base — <Link href="/credit" className="font-semibold text-primary">/credit</Link> grows the denominator
              </>
            ) : (
              "stock growth, weekly series"
            )
          }
        />
        <Vital
          label="Card NPL"
          value={cardsNow != null ? cardsNow.toFixed(1) : "—"}
          unit="%"
          series={cardsNpl.slice(-13)}
          decimals={1}
          note="consumer stress leads the cycle"
        />
        <Vital
          label="SME NPL"
          value={smeNow != null ? smeNow.toFixed(1) : "—"}
          unit="%"
          series={smeNpl.slice(-13)}
          decimals={1}
          note={
            smeNow != null && nplNow != null && smeNow > 1.5 * nplNow ? (
              <em className="not-italic font-semibold text-negative">
                {(smeNow / nplNow).toFixed(1)}× the sector ratio
              </em>
            ) : (
              "vs the sector book"
            )
          }
        />
      </Vitals>

      <Depth action={<GlobalRangeSelector />}>
      <Takeaway data={await withLlmHeadline("asset-quality", read)} />

      <Section index="01" title="NPL Ratio">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div className="lg:col-span-2">
            <TrendChart
              data={nplAll}
              seriesLabels={BANK_TYPE_LABELS}
              title={
                seriesFinding(nplAll.filter((r) => r.bank_type_code === SECTOR), { noun: "The NPL ratio", decimals: 2 }) ??
                "NPL Ratio (%) — by group"
              }
              description="Gross NPL / total loans, %, monthly · by ownership group"
              source="Source: BDDK monthly bulletin"
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
        <ChartRow
          data={commercialTrend}
          labels={{ SME: "SME", COMMERCIAL: "Commercial (all)", NONSME: "Non-SME (derived)" }}
          deltaPeriods={52}
          deltaLabel="52w"
        >
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
        </ChartRow>
      </Section>
      </Depth>

      <Colophon />
    </main>
  );
}
