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
  latestPerBank,
  PRIMARY_BANK_TYPES,
  BANK_TYPES,
  BANK_TYPE_LABELS,
  type TimeSeriesRow,
} from "@/app/lib/metrics";
import { PageHeader } from "@/app/components/ui";
import { getDB } from "@/app/lib/db";
import BarByBank from "@/app/components/BarByBank";
import TrendChart from "@/app/components/TrendChart";
import StackedArea from "@/app/components/StackedArea";

export const dynamic = "force-dynamic";

/** Gross NPL level — derived as total_loans × (npl_ratio / 100).
 * The "Toplam Krediler" row's npl_amount column is NULL in this dataset
 * (only sub-segments carry the absolute value), so we synthesize the
 * stock from the ratio × total. Result is in million TL. */
async function nplAmount(bankTypes: string[]): Promise<TimeSeriesRow[]> {
  const db = await getDB();
  const placeholders = bankTypes.map(() => "?").join(",");
  const { results } = await db
    .prepare(
      // CTE must NOT be named `loans` — D1's SQLite resolves a self-named CTE's
      // inner `FROM loans` to the CTE itself and rejects it as a circular
      // reference. Use a neutral name (`loan_totals`).
      `WITH loan_totals AS (
         SELECT year, month, bank_type_code, total_amount
         FROM loans
         WHERE item_name = 'Toplam Krediler' AND currency = 'TL'
           AND bank_type_code IN (${placeholders})
       ), ratio AS (
         SELECT year, month, bank_type_code, ratio_value
         FROM financial_ratios
         WHERE table_number = 15
           AND item_name = 'Takipteki Alacaklar (Brüt) / Toplam Nakdi Krediler (%)'
           AND bank_type_code IN (${placeholders})
       )
       SELECT
         l.year || '-' || PRINTF('%02d', l.month) AS period,
         l.bank_type_code,
         l.total_amount * r.ratio_value / 100.0 AS value
       FROM loan_totals l
       JOIN ratio r ON r.year = l.year AND r.month = l.month AND r.bank_type_code = l.bank_type_code
       ORDER BY l.year, l.month, l.bank_type_code`,
    )
    .bind(...bankTypes, ...bankTypes)
    .all<TimeSeriesRow>();
  return results;
}

function Section({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  return (
    <section className="space-y-4">
      <div className="space-y-0.5">
        <h2 className="text-base font-semibold text-foreground">{title}</h2>
        {subtitle && <p className="text-xs text-muted-foreground">{subtitle}</p>}
      </div>
      <div className="space-y-4">{children}</div>
    </section>
  );
}

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
  const sector = [BANK_TYPES.SECTOR];
  const groups = PRIMARY_BANK_TYPES.filter((c) => c !== BANK_TYPES.SECTOR);

  const [
    nplAll, nplByBank, coverageAll, gross,
    cMix, cRatios, commRatios,
  ] = await Promise.all([
    ratioNpl(PRIMARY_BANK_TYPES),
    latestPerBank(ratioNpl, groups),
    ratioCoverage(PRIMARY_BANK_TYPES),
    nplAmount(sector),
    consumerNplMix(),
    consumerNplRatios(),
    commercialNplRatios(),
  ]);

  return (
    <main className="mx-auto w-full max-w-[1440px] px-4 py-8 sm:px-6 lg:px-8 space-y-8">
      <PageHeader title="Asset Quality" description="NPL ratio + coverage · sub-segment NPL ratios · BDDK Tables 4, 5, 15 + weekly bulletin" />

      <Section title="NPL Ratio">
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

      <Section title="Coverage & Stock" subtitle="Provisions over gross NPL + absolute NPL stock.">
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
            seriesLabels={{ [BANK_TYPES.SECTOR]: "Gross NPL" }}
            title="Gross NPL — Level (sector, TL bn)"
            yFormat="bn"
            decimals={0}
          />
        </div>
      </Section>

      <Section title="Consumer NPL Breakdown" subtitle="Where household-credit deterioration is concentrated — derived from BDDK Table 4 sub-segments, sector only.">
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
            data={ratiosToTrendRows(cRatios)}
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

      <Section title="Commercial NPL by Segment" subtitle="SME vs commercial-total vs derived non-SME, weekly BDDK bulletin (sector).">
        <TrendChart
          data={commercialToTrendRows(commRatios)}
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
