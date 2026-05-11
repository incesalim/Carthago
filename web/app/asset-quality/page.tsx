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

/** Gross NPL level from loans.npl_amount on "Toplam Krediler" row. */
async function nplAmount(bankTypes: string[]): Promise<TimeSeriesRow[]> {
  const db = await getDB();
  const placeholders = bankTypes.map(() => "?").join(",");
  const { results } = await db
    .prepare(
      `SELECT
         year || '-' || PRINTF('%02d', month) AS period,
         bank_type_code,
         npl_amount AS value
       FROM loans
       WHERE item_name = 'Toplam Krediler'
         AND currency = 'TL'
         AND bank_type_code IN (${placeholders})
       ORDER BY year, month, bank_type_code`,
    )
    .bind(...bankTypes)
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
    <main className="px-6 py-8 max-w-7xl mx-auto space-y-8">
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
