import { cachedAll } from "./db";
import type { BreakdownRow } from "@/app/components/SectorBreakdown";

export interface BalancePartRow { period: string; item_order: number; amount_total: number | null }
const ASSETS = [
  { key: "loans", label: "Loans, net", items: [[10, 1], [11, 1], [12, -1]] },
  { key: "securities", label: "Securities", items: [[5, 1], [6, 1], [22, 1]] },
  { key: "cash", label: "Cash, CBRT and reserves", items: [[1, 1], [2, 1], [7, 1]] },
  { key: "banks", label: "Banks and money markets", items: [[3, 1], [4, 1], [8, 1], [9, 1]] },
  { key: "other", label: "Other assets", items: [[16, 1], [20, 1], [21, 1], [23, 1], [24, 1], [25, 1]] },
];
const FUNDING = [
  { key: "deposits", label: "Deposits", items: [[27, 1]] },
  { key: "banks", label: "Banks, CBRT and repo", items: [[30, 1], [31, 1], [32, 1], [33, 1], [34, 1]] },
  { key: "issuance", label: "Debt securities and subordinated debt", items: [[36, 1], [41, 1]] },
  { key: "other", label: "Other liabilities", items: [[35, 1], [39, 1], [40, 1], [42, 1], [45, 1], [46, 1]] },
  { key: "equity", label: "Equity", items: [[55, 1]] },
];

/** Components are independent on each side; this does not infer funding flows. */
export function balanceSheetStructure(rows: BalancePartRow[]) {
  const period = rows.reduce((latest, row) => row.period > latest ? row.period : latest, "");
  const snapshot = rows.filter(row => row.period === period);
  const map = new Map(snapshot.map(row => [row.item_order, row.amount_total]));
  const duplicate = map.size !== snapshot.length;
  const side = (spec: typeof ASSETS, totalId: number): BreakdownRow[] => {
    const parts = spec.map(s => {
      const inputs = s.items.map(([id, sign]) => ({ value: map.get(id), sign }));
      const value = inputs.every(v => v.value != null && Number.isFinite(v.value))
        ? inputs.reduce((sum, v) => sum + v.value! * v.sign, 0) : null;
      return { id: s.key, label: s.label, values: { amount: value } };
    });
    const total = map.get(totalId);
    const sum = parts.reduce((value, row) => value + (row.values.amount ?? 0), 0);
    const valid = !duplicate && total != null && total > 0 && parts.every(row => row.values.amount != null && row.values.amount >= 0)
      && Math.abs(sum - total) <= Math.max(10, total * 1e-6);
    return parts.map(row => ({ ...row, values: { amount: valid ? row.values.amount : null } }));
  };
  return { period, total: map.get(26) ?? null, assets: side(ASSETS, 26), funding: side(FUNDING, 56) };
}

export async function sectorBalanceSheetStructure() {
  const rows = await cachedAll<BalancePartRow>(
    `SELECT year || '-' || PRINTF('%02d', month) AS period, item_order, amount_total
     FROM balance_sheet
     WHERE bank_type_code = '10001' AND currency = 'TL'
       AND year * 100 + month = (SELECT MAX(year * 100 + month) FROM balance_sheet
         WHERE bank_type_code = '10001' AND currency = 'TL')
       AND item_order <= 56 ORDER BY item_order`,
  );
  return balanceSheetStructure(rows);
}

export async function sectorOperatingNetwork() {
  const [network, overseas] = await Promise.all([
    cachedAll<{period:string; item_order:number; value:number | null}>(
      `SELECT year || '-' || PRINTF('%02d', month) AS period, item_order, value_numeric AS value
       FROM other_data WHERE table_number = 16 AND currency = 'TL' AND bank_type_code = '10001'
       AND column_name = 'Adet' AND item_order IN (2,5,6)
       AND year >= (SELECT MAX(year) - 5 FROM other_data WHERE table_number=16)
       ORDER BY year, month, item_order`),
    cachedAll<{period:string; bank_type_code:string; item_order:number; value:number|null}>(
      `SELECT year || '-' || PRINTF('%02d', month) AS period, bank_type_code, item_order, ratio_value AS value
       FROM financial_ratios WHERE table_number = 17 AND bank_type_code IN ('10008','10009','10010','10003','10004')
       AND year * 100 + month = (SELECT MAX(year * 100 + month) FROM financial_ratios
         WHERE table_number=17 AND bank_type_code='10001')
       AND item_order IN (1,2,3) ORDER BY bank_type_code,item_order`),
  ]);
  return { network, overseas };
}

export function operatingNetworkViews(input: Awaited<ReturnType<typeof sectorOperatingNetwork>>) {
  const periods = [...new Set(input.network.map(row => row.period))].sort();
  const ids = [2,5,6];
  const basePeriod = periods.find(period => ids.every(id => input.network.some(row =>
    row.period === period && row.item_order === id && row.value != null && row.value > 0)));
  const base = new Map(input.network.filter(row => row.period === basePeriod).map(row => [row.item_order, row.value]));
  const history = input.network.filter(row => basePeriod != null && row.period >= basePeriod).map(row => ({ period: row.period, bank_type_code: String(row.item_order),
    value: row.value != null && base.get(row.item_order) != null && base.get(row.item_order)! > 0
      ? row.value / base.get(row.item_order)! * 100 : null }));
  const labels: Record<string,string> = {"10008":"Domestic private deposit banks", "10009":"State deposit banks",
    "10010":"Foreign deposit banks", "10003":"Participation", "10004":"Dev & Inv"};
  const overseas: BreakdownRow[] = Object.entries(labels).map(([code,label]) => ({id:code,label,
    values: Object.fromEntries([1,2,3].map(id => [String(id), input.overseas.find(row => row.bank_type_code === code && row.item_order === id)?.value ?? null])) }));
  return { basePeriod, history, overseas, overseasPeriod: input.overseas[0]?.period };
}
