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

/** Gross NPL level from loans.npl_amount on TOPLAM KREDİLER row. */
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
       WHERE item_name = 'TOPLAM KREDİLER'
         AND currency = 'TL'
         AND bank_type_code IN (${placeholders})
       ORDER BY year, month, bank_type_code`,
    )
    .bind(...bankTypes)
    .all<TimeSeriesRow>();
  return results;
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
    <main className="p-8 max-w-7xl mx-auto">
      <h1 className="text-3xl font-bold mb-2">Asset Quality</h1>
      <p className="text-sm text-neutral-500 mb-6">
        NPL ratio + coverage · BDDK Table 15 · sector + group breakdowns
      </p>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-4">
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
    </main>
  );
}
