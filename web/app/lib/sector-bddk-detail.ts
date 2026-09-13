/** BDDK bulletin detail used by the sector reports. All monetary outputs are
 * million TL. T05 is the exception at source (thousand TL), converted here.
 * Snapshots use one published period; incomplete partitions never become zero. */
import { cachedAll } from "./db";
import { BANK_TYPES, BANK_TYPE_LABELS, PRIMARY_BANK_TYPES } from "./metrics";
import type { SectorTrendPoint } from "./sector-trend";
import type { PnlRow } from "./profitability";

export interface BulletinCell {
  period: string;
  bank_type_code: string;
  item_order: number;
  value: number | null;
}
export interface BulletinLoan {
  period: string;
  item_order: number;
  total_amount: number | null;
  npl_amount: number | null;
}
export interface BulletinBreakdownRow {
  id: string;
  label: string;
  values: Record<string, number | null>;
  total?: number | null;
}
export interface BulletinBridgeRow { id: string; label: string; value: number; total?: boolean }
const finite = (v: number | null | undefined): v is number => v != null && Number.isFinite(v);
const sum = (values: (number | null | undefined)[]): number | null =>
  values.every(finite) ? values.reduce<number>((a, b) => a + b, 0) : null;
const pct = (a: number | null, b: number | null) => finite(a) && finite(b) && b > 0 ? a / b * 100 : null;
// Published amounts are rounded to million TL; tolerate that rounding only.
export const reconciles = (a: number | null, b: number | null, tolerance = 5) =>
  finite(a) && finite(b) && Math.abs(a - b) <= tolerance;
const lastPeriod = (rows: { period: string }[]) => rows.reduce((p, r) => r.period > p ? r.period : p, "");
const cells = (rows: BulletinCell[]) => {
  const values = new Map<number, number | null>();
  const conflicts = new Set<number>();
  for (const row of rows) {
    // Conflicting duplicates are unavailable, not arbitrarily selected.
    if (values.has(row.item_order) && values.get(row.item_order) !== row.value) conflicts.add(row.item_order);
    values.set(row.item_order, conflicts.has(row.item_order) ? null : row.value);
  }
  return (order: number) => values.get(order) ?? null;
};

async function otherTable(table: number, orders: number[], groups: readonly string[] = [BANK_TYPES.SECTOR]) {
  return cachedAll<BulletinCell>(
    `SELECT year || '-' || PRINTF('%02d', month) AS period, bank_type_code, item_order,
            value_numeric AS value
       FROM other_data
      WHERE table_number = ? AND currency = 'TL' AND column_name = 'Toplam'
        AND bank_type_code IN (${groups.map(() => "?").join(",")})
        AND item_order IN (${orders.map(() => "?").join(",")})
      ORDER BY year, month, bank_type_code, item_order`, [table, ...groups, ...orders],
  );
}

export function buildCapitalDetail(input: BulletinCell[]) {
  const period = lastPeriod(input.filter(r => r.bank_type_code === BANK_TYPES.SECTOR));
  const current = input.filter(r => r.period === period);
  const value = cells(current.filter(r => r.bank_type_code === BANK_TYPES.SECTOR));
  const tier1 = value(1), cet1 = value(6), tier2 = value(2), deductions = value(4), total = value(5);
  const otherTier1 = finite(tier1) && finite(cet1) ? tier1 - cet1 : null;
  const capitalSum = sum([cet1, otherTier1, tier2, finite(deductions) ? -deductions : null]);
  const capitalValid = reconciles(capitalSum, total);
  const bridge: BulletinBridgeRow[] = capitalValid ? [
    { id: "cet1", label: "Common equity Tier 1", value: cet1! },
    { id: "at1", label: "Other Tier 1 capital", value: otherTier1! },
    { id: "tier2", label: "Tier 2 capital", value: tier2! },
    { id: "deductions", label: "Capital deductions", value: -deductions! },
    { id: "total", label: "Regulatory capital", value: total!, total: true },
  ] : [];
  const riskRows: BulletinBreakdownRow[] = PRIMARY_BANK_TYPES.map(code => {
    const get = cells(current.filter(r => r.bank_type_code === code));
    const credit = get(10), market = get(30), operational = get(31), total = get(7);
    const valid = reconciles(sum([credit, market, operational]), total);
    return { id: code, label: BANK_TYPE_LABELS[code], total,
      values: { credit: valid ? credit : null, market: valid ? market : null, operational: valid ? operational : null } };
  });
  return { period, bridge, capitalValid, riskRows };
}
export async function capitalBulletinDetail() {
  return buildCapitalDetail(await otherTable(12, [1, 2, 4, 5, 6, 7, 10, 30, 31], PRIMARY_BANK_TYPES));
}

export async function feeOperatingCostCoverage(): Promise<SectorTrendPoint[]> {
  return cachedAll<SectorTrendPoint>(
    `SELECT year || '-' || PRINTF('%02d', month) AS period, bank_type_code, ratio_value AS value
       FROM financial_ratios WHERE table_number = 15 AND item_name = ?
         AND bank_type_code IN (${PRIMARY_BANK_TYPES.map(() => "?").join(",")})
       ORDER BY year, month, bank_type_code`,
    ["Ücret, Komisyon ve Bankacılık Hizmetleri Gelirleri / İşletme Giderleri (%)", ...PRIMARY_BANK_TYPES],
  );
}
/** Calendar-month de-cumulation, in source million TL. Missing prior month or
 * missing published net profit leaves a gap; January resets to the YTD value. */
export function monthlyNetProfit(rows: Pick<PnlRow, "year" | "month" | "net">[]): SectorTrendPoint[] {
  const key = (year: number, month: number) => `${year}-${String(month).padStart(2, "0")}`;
  const by = new Map(rows.map(r => [key(r.year, r.month), r.net]));
  return rows.map(r => {
    const prior = r.month === 1 ? 0 : by.get(key(r.year, r.month - 1));
    return { period: key(r.year, r.month), bank_type_code: BANK_TYPES.SECTOR,
      value: finite(r.net) && finite(prior) ? r.net - prior : null };
  }).sort((a, b) => a.period.localeCompare(b.period));
}

async function latestLoans(table: number, orders: number[]): Promise<BulletinLoan[]> {
  return cachedAll<BulletinLoan>(
    `SELECT year || '-' || PRINTF('%02d', month) AS period, item_order, total_amount, npl_amount
       FROM loans
      WHERE table_number = ? AND currency = 'TL' AND bank_type_code = '10001'
        AND year * 100 + month = (SELECT MAX(year * 100 + month) FROM loans
          WHERE table_number = ? AND currency = 'TL' AND bank_type_code = '10001')
        AND item_order IN (${orders.map(() => "?").join(",")})
      ORDER BY item_order`, [table, table, ...orders],
  );
}
export function retailRiskShares(input: BulletinLoan[]) {
  const period = lastPeriod(input);
  const by = new Map(input.filter(r => r.period === period).map(r => [r.item_order, r]));
  const products = [
    [2, 14, "Housing"], [3, 15, "Auto"], [4, 16, "General purpose loans"], [9, 17, "Retail Cards"],
  ] as const;
  const parts = products.map(([loan, npl, label]) => ({ id: String(loan), label,
    gross: sum([by.get(loan)?.total_amount, by.get(npl)?.total_amount]), npl: by.get(npl)?.total_amount ?? null }));
  const gross = sum(parts.map(r => r.gross)), npl = sum(parts.map(r => r.npl));
  return { period, rows: parts.map(r => ({ id: r.id, label: r.label, total: r.gross,
    values: { loans: pct(r.gross, gross), npl: pct(r.npl, npl) } })) };
}
export function smeRiskBySize(input: BulletinLoan[]) {
  const period = lastPeriod(input);
  const by = new Map(input.filter(r => r.period === period).map(r => [r.item_order, r]));
  const all = by.get(1);
  const reference = pct(all?.npl_amount ?? null, sum([all?.total_amount, all?.npl_amount]));
  return { period, rows: ([[2, "Micro enterprises"], [3, "Small enterprises"], [4, "Medium-sized enterprises"]] as const).map(([id, label]) => {
    const row = by.get(id), total = sum([row?.total_amount, row?.npl_amount]);
    return { id: String(id), label, total, values: { ratio: pct(row?.npl_amount ?? null, total), sector: reference } };
  }) };
}
const MANUFACTURING_LABELS: Record<number, string> = {
  10: "Food, beverages and tobacco", 11: "Textiles", 12: "Leather", 13: "Wood products",
  14: "Paper products", 15: "Refining, coke and nuclear fuel", 16: "Chemicals", 17: "Rubber and plastics",
  18: "Other non-metallic minerals", 19: "Basic and fabricated metals", 20: "Machinery and equipment",
  21: "Electrical and optical equipment", 22: "Transport equipment", 25: "Other manufacturing",
};
export function manufacturingNplShares(input: BulletinLoan[]) {
  const period = lastPeriod(input);
  const by = new Map(input.filter(r => r.period === period).map(r => [r.item_order, r]));
  const orders = Object.keys(MANUFACTURING_LABELS).map(Number);
  const parent = by.get(9)?.npl_amount ?? null;
  const valid = reconciles(sum(orders.map(id => by.get(id)?.npl_amount)), parent);
  return { period, valid, rows: orders.map(id => {
    const npl = by.get(id)?.npl_amount ?? null;
    return { id: String(id), label: MANUFACTURING_LABELS[id], total: finite(npl) ? npl / 1000 : null,
      values: { share: valid ? pct(npl, parent) : null } };
  }).sort((a, b) => (b.values.share ?? -Infinity) - (a.values.share ?? -Infinity)) };
}
export async function assetQualityBulletinDetail() {
  const [retail, sme, manufacturing] = await Promise.all([
    latestLoans(4, [2, 3, 4, 9, 14, 15, 16, 17]), latestLoans(6, [1, 2, 3, 4]),
    latestLoans(5, [9, ...Object.keys(MANUFACTURING_LABELS).map(Number)]),
  ]);
  return { retail: retailRiskShares(retail), sme: smeRiskBySize(sme), manufacturing: manufacturingNplShares(manufacturing) };
}

export function buildFxBridge(input: BulletinCell[]) {
  const periods = [...new Set(input.map(r => r.period))].sort();
  const history: SectorTrendPoint[] = [];
  let bridge: BulletinBridgeRow[] = [];
  for (const period of periods) {
    const get = cells(input.filter(r => r.period === period));
    const inside = finite(get(2)) && finite(get(6)) ? get(2)! - get(6)! : null;
    const outside = finite(get(4)) && finite(get(8)) ? get(4)! - get(8)! : null;
    const net = get(9), valid = reconciles(sum([inside, outside]), net);
    history.push(...[["INSIDE", inside], ["OUTSIDE", outside], ["NET", net]].map(([code, value]) => ({
      period, bank_type_code: String(code), value: valid ? value as number : null,
    })));
    if (period === periods.at(-1) && valid) bridge = [
      { id: "inside", label: "On-balance-sheet FX position", value: inside! },
      { id: "outside", label: "Off-balance-sheet FX position", value: outside! },
      { id: "net", label: "Net FX position", value: net!, total: true },
    ];
  }
  return { period: periods.at(-1) ?? "", bridge, history };
}
export interface WeeklySecurity { period: string; item_id: string; value: number | null }
export function securitiesAccountingMix(input: WeeklySecurity[]) {
  const periods = [...new Set(input.map(r => r.period))].sort();
  return periods.map(period => {
    const by = new Map(input.filter(r => r.period === period).map(r => [r.item_id, r.value]));
    const fvpl = by.get("3.0.14") ?? null, fvoci = by.get("3.0.17") ?? null, amortized = by.get("3.0.20") ?? null;
    const total = by.get("3.0.1") ?? null;
    const valid = reconciles(sum([fvpl, fvoci, amortized]), total, 0.05);
    return { period, fvpl: valid ? pct(fvpl, total) : null, fvoci: valid ? pct(fvoci, total) : null,
      amortized: valid ? pct(amortized, total) : null, total };
  });
}
const COMMITMENT_LABELS: Record<number, string> = {
  40: "Note issuance facility commitments", 41: "Equity participation commitments", 42: "Guaranteed credit commitments",
  43: "Cheque payment commitments", 44: "Credit card spending limits", 45: "Forward asset purchases",
  46: "Forward asset sales", 47: "Forward deposit commitments", 48: "Reserve requirement payment commitments",
  49: "Other irrevocable commitments", 50: "Revocable credit commitments", 51: "Other revocable commitments",
};
export function nonDerivativeCommitments(input: BulletinCell[]) {
  const period = lastPeriod(input), get = cells(input.filter(r => r.period === period));
  const orders = Object.keys(COMMITMENT_LABELS).map(Number), total = get(39);
  const valid = reconciles(sum(orders.map(get)), total);
  return { period, valid, rows: orders.map(id => ({ id: String(id), label: COMMITMENT_LABELS[id],
    total: get(id), values: { share: valid ? pct(get(id), total) : null } }))
    .sort((a, b) => (b.values.share ?? -Infinity) - (a.values.share ?? -Infinity)) };
}
export async function marketRiskBulletinDetail() {
  const [fx, securities, commitments] = await Promise.all([
    otherTable(13, [2, 4, 6, 8, 9]),
    cachedAll<WeeklySecurity>(`SELECT period_date AS period, item_id, value FROM weekly_series
      WHERE bank_type_code = '10001' AND currency = 'TOTAL' AND item_id IN ('3.0.1', '3.0.14', '3.0.17', '3.0.20')
      ORDER BY period_date, item_id`),
    otherTable(14, [39, ...Object.keys(COMMITMENT_LABELS).map(Number)]),
  ]);
  return { fx: buildFxBridge(fx), securities: securitiesAccountingMix(securities), commitments: nonDerivativeCommitments(commitments) };
}
