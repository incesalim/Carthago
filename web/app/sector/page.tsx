/**
 * Sector — Total Assets time series.
 *
 * Server-rendered chart using D1 directly from a Server Component.
 * No API route needed; the SQL query runs at the edge during render.
 */
import { getDB } from "@/app/lib/db";
import TotalAssetsChart from "./TotalAssetsChart";
import { PageHeader, ChartCard } from "@/app/components/ui";

// Per-request rendering — page reads from D1 each time, no static prerendering.
export const dynamic = "force-dynamic";

interface Row {
  period: string;
  total: number;
}

async function fetchSectorTotalAssets(): Promise<Row[]> {
  const db = await getDB();
  // Sector total assets = bank_type_code 10001 (sektör), currency 'TL'
  // (BDDK reports values in TL million, regardless of TL/FX origin).
  const { results } = await db
    .prepare(
      `SELECT
         year || '-' || PRINTF('%02d', month) AS period,
         amount_total AS total
       FROM balance_sheet
       WHERE bank_type_code = '10001'
         AND currency = 'TL'
         AND item_name = 'TOPLAM AKTİFLER'
       ORDER BY year, month`
    )
    .all<Row>();
  return results;
}

export default async function SectorPage() {
  const data = await fetchSectorTotalAssets();
  const latest = data.at(-1);

  return (
    <main className="mx-auto w-full max-w-[1440px] px-4 py-8 sm:px-6 lg:px-8 space-y-6">
      <PageHeader
        eyebrow="Banking Sector"
        title="Total Assets"
        description={
          <>
            Live D1 query · {data.length} months loaded
            {latest &&
              ` · latest: ${latest.period} = ₺${(latest.total / 1_000_000).toFixed(1)} trn`}
          </>
        }
      />
      <ChartCard title="Total Assets — sector (₺ trn)">
        <TotalAssetsChart data={data} />
      </ChartCard>
    </main>
  );
}
