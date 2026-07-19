/**
 * GET /api/v1/categories — the dimension vocabulary a caller needs to read a
 * series code: what every dataset token and bank-type code means.
 *
 * Counts and date ranges come from the catalog itself rather than a hand-kept
 * list, so this can't drift from what /api/v1/series will actually serve.
 */
import { cachedAll } from "@/app/lib/db";
import { apiDisabled, disabledResponse, jsonResponse } from "../_shared";

export { OPTIONS } from "../_shared";
export const dynamic = "force-dynamic";

interface DatasetRow {
  dataset: string;
  frequency: string;
  table_number: number | null;
  category: string | null;
  unit: string | null;
  series_count: number;
  start_date: string | null;
  end_date: string | null;
}

interface BankTypeRow {
  code: string;
  name_tr: string;
  name_en: string | null;
  category: string | null;
  series_count: number;
}

export async function GET() {
  if (await apiDisabled()) return disabledResponse();

  const [datasets, bankTypes, defs] = await Promise.all([
    cachedAll<DatasetRow>(
      `SELECT dataset, frequency, MAX(table_number) AS table_number,
              MAX(category) AS category, MAX(unit) AS unit,
              COUNT(*) AS series_count,
              MIN(start_date) AS start_date, MAX(end_date) AS end_date
         FROM api_series
        GROUP BY dataset, frequency
        ORDER BY frequency, dataset`,
    ),
    cachedAll<BankTypeRow>(
      `SELECT bt.code, bt.name_tr, bt.name_en, bt.category,
              COUNT(s.series_code) AS series_count
         FROM bank_types bt
         LEFT JOIN api_series s ON s.bank_type_code = bt.code
        GROUP BY bt.code, bt.name_tr, bt.name_en, bt.category
       HAVING series_count > 0
        ORDER BY bt.code`,
    ),
    cachedAll<{ table_number: number; name_en: string | null; name_tr: string }>(
      `SELECT table_number, name_en, name_tr FROM table_definitions
        ORDER BY table_number`,
    ),
  ]);

  const nameByTable = new Map(
    defs.map((d) => [d.table_number, d.name_en || d.name_tr]),
  );

  return jsonResponse({
    meta: {
      source: "BDDK (Banking Regulation and Supervision Agency of Türkiye)",
      publisher: "Carthago — https://carthago.app",
    },
    datasets: datasets.map((d) => ({
      dataset: d.dataset,
      // Monthly datasets carry BDDK's own table name; weekly ones the bulletin
      // section they came from.
      name: d.table_number !== null
        ? nameByTable.get(d.table_number) ?? d.dataset
        : d.category ?? d.dataset,
      frequency: d.frequency,
      bddk_table_number: d.table_number,
      unit: d.unit,
      series_count: d.series_count,
      start_date: d.start_date,
      end_date: d.end_date,
    })),
    bank_types: bankTypes,
  });
}
