/**
 * Funding detail from BDDK's published monthly cross-tabs and weekly stocks.
 * Amounts stay in source units (million TRY, including the TRY value of FX).
 * Prototype identities: private 2026-09-13-bddk-viz views 04/06/07/08/15/22/23/35/36.
 */
import { cachedAll } from "./db";
import type { SectorTrendPoint } from "./sector-trend";

export interface FundingBreakdownRow {
  id: string;
  label: string;
  values: Record<string, number | null>;
  total?: number | null;
}

export interface DepositDetailRow {
  period: string;
  table_number: number;
  item_order: number;
  total_amount: number | null;
  bracket_10k?: number | null;
  bracket_50k?: number | null;
  bracket_250k?: number | null;
  bracket_1m?: number | null;
  bracket_over_1m?: number | null;
  demand?: number | null;
  maturity_1m?: number | null;
  maturity_1_3m?: number | null;
  maturity_3_6m?: number | null;
  maturity_6_12m?: number | null;
  maturity_over_12m?: number | null;
}

export interface FundingCell {
  period: string;
  item_order: number;
  column_name: string;
  value: number | null;
}

export const DEPOSIT_BRACKETS = [
  { key: "bracket_10k", label: "Up to TRY 10 thousand" },
  { key: "bracket_50k", label: "TRY 10–50 thousand" },
  { key: "bracket_250k", label: "TRY 50–250 thousand" },
  { key: "bracket_1m", label: "TRY 250 thousand–1 million" },
  { key: "bracket_over_1m", label: "Over TRY 1 million" },
] as const;

export const DEPOSIT_CURRENCIES = [
  { key: "tl", label: "Turkish lira" },
  { key: "fx", label: "Foreign currency" },
  { key: "metals", label: "Precious metals" },
] as const;

export const DEPOSIT_TERM_BUCKETS = [
  { key: "demand", label: "Demand" },
  { key: "maturity_1m", label: "Up to 1 month" },
  { key: "maturity_1_3m", label: "1–3 months" },
  { key: "maturity_3_6m", label: "3–6 months" },
  { key: "maturity_6_12m", label: "6–12 months" },
  { key: "maturity_over_12m", label: "Over 12 months" },
] as const;

export const DEPOSIT_SHORT_TERM_BUCKETS = [
  { key: "demand", label: "Demand" },
  { key: "short", label: "Term deposits up to 3 months" },
  { key: "long", label: "Term deposits over 3 months" },
] as const;

const CUSTOMERS = [
  { id: "individuals", label: "Individuals", items: [2, 6, 10] },
  { id: "official", label: "Official institutions", items: [3, 7, 11] },
  { id: "business", label: "Businesses and other institutions", items: [4, 8, 12] },
] as const;

/** Missing constituents never become zero or a misleading complete partition. */
export function fundingSum(values: readonly (number | null | undefined)[]): number | null {
  return values.every((value) => value != null && Number.isFinite(value))
    ? values.reduce<number>((sum, value) => sum + (value as number), 0)
    : null;
}

/** Published cells are rounded to millions; allow at most half a unit per term. */
export function fundingReconciles(parts: readonly (number | null | undefined)[], total: number | null | undefined, roundedCells = parts.length + 1): boolean {
  const sum = fundingSum(parts);
  return sum != null && total != null && Number.isFinite(total)
    && Math.abs(sum - total) <= roundedCells * 0.5 + 1e-8;
}

function checkedPartition(values: Record<string, number | null>, total: number | null, roundedCells = Object.keys(values).length + 1) {
  if (fundingReconciles(Object.values(values), total, roundedCells) && Object.values(values).every((v) => v != null && v >= 0)) return values;
  return Object.fromEntries(Object.keys(values).map((key) => [key, null]));
}

function latestRows<T extends { period: string }>(rows: readonly T[]) {
  const period = rows.reduce<string | null>((latest, row) => latest == null || row.period > latest ? row.period : latest, null);
  return { period, rows: rows.filter((row) => row.period === period) };
}

function uniqueRow<T>(rows: readonly T[]): T | undefined {
  return rows.length === 1 ? rows[0] : undefined;
}

export function buildDepositFundingDetail(raw: readonly DepositDetailRow[]) {
  const amounts = latestRows(raw.filter((row) => row.table_number === 9));
  const terms = latestRows(raw.filter((row) => row.table_number === 10));
  const get = (rows: readonly DepositDetailRow[], item: number) => uniqueRow(rows.filter((row) => row.item_order === item));
  const concentration: FundingBreakdownRow[] = CUSTOMERS.map((customer) => {
    const rows = customer.items.map((item) => get(amounts.rows, item));
    const total = fundingSum(rows.map((row) => row?.total_amount));
    const values = Object.fromEntries(DEPOSIT_BRACKETS.map(({ key }) => [key, fundingSum(rows.map((row) => row?.[key]))]));
    return { id: customer.id, label: customer.label, values: checkedPartition(values, total, rows.length * (DEPOSIT_BRACKETS.length + 1)), total };
  });
  const customers: FundingBreakdownRow[] = CUSTOMERS.map((customer) => {
    const values = Object.fromEntries(DEPOSIT_CURRENCIES.map(({ key }, i) => [key, get(terms.rows, customer.items[i])?.total_amount ?? null]));
    const total = fundingSum(Object.values(values));
    return { id: customer.id, label: customer.label, values: checkedPartition(values, total), total };
  });
  const maturity: FundingBreakdownRow[] = DEPOSIT_CURRENCIES.map(({ key, label }, i) => {
    const row = get(terms.rows, [1, 5, 9][i]);
    const total = row?.total_amount ?? null;
    const values = Object.fromEntries(DEPOSIT_TERM_BUCKETS.map(({ key: bucket }) => [bucket, row?.[bucket] ?? null]));
    return { id: key, label, values: checkedPartition(values, total), total };
  });
  const customerMaturity: FundingBreakdownRow[] = CUSTOMERS.flatMap((customer) => DEPOSIT_CURRENCIES.map(({ key, label }, i) => {
    const row = get(terms.rows, customer.items[i]);
    const total = row?.total_amount ?? null;
    const values = {
      demand: row?.demand ?? null,
      short: fundingSum([row?.maturity_1m, row?.maturity_1_3m]),
      long: fundingSum([row?.maturity_3_6m, row?.maturity_6_12m, row?.maturity_over_12m]),
    };
    return { id: `${customer.id}-${key}`, label: `${customer.label} · ${label}`, values: checkedPartition(values, total, DEPOSIT_TERM_BUCKETS.length + 1), total };
  }));
  return { concentrationPeriod: amounts.period, maturityPeriod: terms.period, concentration, customers, maturity, customerMaturity };
}

export async function loadDepositFundingDetail() {
  const rows = await cachedAll<DepositDetailRow>(
    `WITH latest AS (
       SELECT table_number, MAX(year * 12 + month) AS stamp FROM deposits
       WHERE table_number IN (9, 10) AND bank_type_code = '10001' AND currency = 'TL'
       GROUP BY table_number
     )
     SELECT printf('%04d-%02d', d.year, d.month) AS period, d.table_number, d.item_order,
            d.total_amount, d.bracket_10k, d.bracket_50k, d.bracket_250k,
            d.bracket_1m, d.bracket_over_1m, d.demand, d.maturity_1m,
            d.maturity_1_3m, d.maturity_3_6m, d.maturity_6_12m, d.maturity_over_12m
     FROM deposits d JOIN latest l ON d.table_number = l.table_number AND d.year * 12 + d.month = l.stamp
     WHERE d.bank_type_code = '10001' AND d.currency = 'TL' AND d.item_order BETWEEN 1 AND 13
     ORDER BY d.table_number, d.item_order`,
  );
  return buildDepositFundingDetail(rows);
}

const HORIZONS = [
  { key: "YediGun", label: "7 days" },
  { key: "BirAy", label: "1 month" },
  { key: "UcAy", label: "3 months" },
  { key: "OnikiAy", label: "12 months" },
] as const;

export function buildLiquidityMaturity(raw: readonly FundingCell[]) {
  const snapshot = latestRows(raw);
  const value = (item: number, column: string) => uniqueRow(snapshot.rows.filter((row) => row.item_order === item && row.column_name === column))?.value ?? null;
  const horizons: FundingBreakdownRow[] = HORIZONS.map(({ key, label }) => {
    const assets = value(18, key);
    const liabilities = value(42, key);
    const net = value(43, key);
    return { id: key, label, values: { net: fundingReconciles([assets, liabilities == null ? null : -liabilities], net) ? net : null } };
  });
  const v = (item: number) => value(item, "BirAy");
  const neg = (amount: number | null) => amount == null ? null : -amount;
  const parts: FundingBreakdownRow[] = [
    { id: "cash", label: "Cash, CBRT and required reserves", values: { net: fundingSum([v(1), v(6)]) } },
    { id: "securities", label: "Securities receivables", values: { net: fundingSum([v(2), v(9)]) } },
    { id: "loans", label: "Loan and lease receivables", values: { net: fundingSum([v(8), v(10)]) } },
    { id: "banks", label: "Banks, money market and reverse repo", values: { net: fundingSum([v(3), v(4), v(5)]) } },
    { id: "fees", label: "Non-cash loan commissions", values: { net: v(7) } },
    { id: "derivatives", label: "Derivative receivables less payables", values: { net: fundingSum([v(11), neg(v(35))]) } },
    { id: "deposits", label: "Deposit liabilities", values: { net: neg(v(19)) } },
    { id: "repo", label: "Repo liabilities", values: { net: neg(v(26)) } },
    { id: "other", label: "Other liabilities", values: { net: neg(fundingSum(Array.from({ length: 15 }, (_, i) => i + 20).filter((i) => i !== 26).map(v))) } },
  ];
  const assets = Array.from({ length: 11 }, (_, i) => v(i + 1));
  const liabilities = Array.from({ length: 17 }, (_, i) => v(i + 19));
  // Validate leaf identities before presenting an additive net bridge. T11's
  // derivative subtotals (11,35) enter once; their own children never enter.
  const valid = fundingReconciles(assets, v(18)) && fundingReconciles(liabilities, v(42))
    && fundingReconciles([v(18), neg(v(42))], v(43))
    && fundingReconciles([...assets, ...liabilities.map(neg)], v(43));
  return {
    period: snapshot.period,
    horizons,
    components: valid ? parts : parts.map((row) => ({ ...row, values: { net: null } })),
    net: valid ? v(43) : null,
  };
}

export function buildSecuritiesUse(raw: readonly FundingCell[]): SectorTrendPoint[] {
  const periods = [...new Set(raw.map((row) => row.period))].sort();
  return periods.flatMap((period) => {
    const value = (item: number) => uniqueRow(raw.filter((row) => row.period === period && row.item_order === item && row.column_name === "Toplam"))?.value ?? null;
    const total = value(29);
    return [{ item: 27, key: "repo" }, { item: 28, key: "pledged" }].map(({ item, key }) => {
      const amount = value(item);
      return { period, bank_type_code: key, value: amount != null && total != null && total > 0 ? amount / total * 100 : null };
    });
  });
}

export const NON_DEPOSIT_FUNDING_LABELS: Record<string, string> = {
  "5.0.10": "Domestic bank funding",
  "5.0.11": "Foreign bank funding",
  "5.0.12": "Securities issued",
  "5.0.16": "Repo funding",
};

export const SYNDICATION_LABELS: Record<string, string> = {
  "1": "Other syndicated loans",
  "2": "Trade finance syndicated loans",
  "3": "Securitization loans",
};

export async function loadLiquidityFundingDetail() {
  const [maturity, securities, syndication, funding] = await Promise.all([
    cachedAll<FundingCell>(
      `SELECT printf('%04d-%02d', year, month) AS period, item_order, column_name, value_numeric AS value
       FROM other_data WHERE table_number = 11 AND bank_type_code = '10001' AND currency = 'TL'
       AND year * 12 + month = (SELECT MAX(year * 12 + month) FROM other_data
         WHERE table_number = 11 AND bank_type_code = '10001' AND currency = 'TL')
       AND column_name IN ('YediGun', 'BirAy', 'UcAy', 'OnikiAy') AND item_order BETWEEN 1 AND 43
       ORDER BY item_order, column_name`,
    ),
    cachedAll<FundingCell>(
      `SELECT printf('%04d-%02d', year, month) AS period, item_order, column_name, value_numeric AS value
       FROM other_data WHERE table_number = 8 AND bank_type_code = '10001' AND currency = 'TL'
       AND column_name = 'Toplam' AND item_order IN (27, 28, 29)
       AND year * 12 + month >= (SELECT MAX(year * 12 + month) - 60 FROM other_data
         WHERE table_number = 8 AND bank_type_code = '10001' AND currency = 'TL')
       ORDER BY year, month, item_order`,
    ),
    cachedAll<SectorTrendPoint>(
      `SELECT printf('%04d-%02d', year, month) AS period, CAST(item_order AS TEXT) AS bank_type_code, total_amount AS value
       FROM loans WHERE table_number = 7 AND bank_type_code = '10001' AND currency = 'TL'
       AND item_order IN (1, 2, 3)
       AND year * 12 + month >= (SELECT MAX(year * 12 + month) - 60 FROM loans
         WHERE table_number = 7 AND bank_type_code = '10001' AND currency = 'TL')
       ORDER BY year, month, item_order`,
    ),
    cachedAll<SectorTrendPoint>(
      `SELECT period_date AS period, item_id AS bank_type_code, value
       FROM weekly_series WHERE category = 'diger_bilanco' AND bank_type_code = '10001' AND currency = 'TOTAL'
       AND item_id IN ('5.0.10', '5.0.11', '5.0.12', '5.0.16')
       AND period_date >= (SELECT date(MAX(period_date), '-3 years') FROM weekly_series
         WHERE category = 'diger_bilanco' AND bank_type_code = '10001' AND currency = 'TOTAL')
       ORDER BY period_date, item_id`,
    ),
  ]);
  return { maturity: buildLiquidityMaturity(maturity), securities: buildSecuritiesUse(securities), syndication, funding };
}
