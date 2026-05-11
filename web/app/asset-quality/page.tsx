/**
 * Asset Quality tab — NPL ratio, NPL by bank, coverage, gross NPL level.
 */
import {
  ratioNpl,
  ratioCoverage,
  latestPerBank,
  PRIMARY_BANK_TYPES,
  BANK_TYPES,
  BANK_TYPE_LABELS,
  type TimeSeriesRow,
} from "@/app/lib/metrics";
import { getDB } from "@/app/lib/db";
import BarByBank from "@/app/components/BarByBank";
import TrendChart from "@/app/components/TrendChart";

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
      `WITH loans AS (
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
       FROM loans l
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
        <h2 className="text-base font-semibold text-neutral-900">{title}</h2>
        {subtitle && <p className="text-xs text-neutral-500">{subtitle}</p>}
      </div>
      <div className="space-y-4">{children}</div>
    </section>
  );
}

export default async function AssetQualityPage() {
  const sector = [BANK_TYPES.SECTOR];
  const groups = PRIMARY_BANK_TYPES.filter((c) => c !== BANK_TYPES.SECTOR);

  const [
    nplAll, nplByBank, coverageAll, gross,
  ] = await Promise.all([
    ratioNpl(PRIMARY_BANK_TYPES),
    latestPerBank(ratioNpl, groups),
    ratioCoverage(PRIMARY_BANK_TYPES),
    nplAmount(sector),
  ]);

  return (
    <main className="px-8 py-8 space-y-8">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Asset Quality</h1>
        <p className="text-sm text-neutral-500">
          NPL ratio + coverage · BDDK Table 15 · sector + group breakdowns
        </p>
      </header>

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
    </main>
  );
}
