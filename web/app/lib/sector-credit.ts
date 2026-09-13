import { cachedAll } from "./db";

/** All displayed monetary values use millions of TL, as in metrics.ts. */
export interface CreditBreakdownRow {
  id: string;
  label: string;
  values: Record<string, number | null>;
  total?: number | null;
  reconciled?: boolean;
}

export interface CreditSnapshot {
  asOf: string | null;
  data: CreditBreakdownRow[];
  total: number | null;
}

export interface CreditLoanRow {
  table_number: number;
  period: string;
  item_order: number;
  item_name: string;
  short_term_total: number | null;
  medium_long_total: number | null;
  total_tl: number | null;
  total_fx: number | null;
  total_amount: number | null;
  npl_amount: number | null;
}

export interface CreditOtherRow {
  period: string;
  item_order: number;
  column_name: string;
  value_numeric: number | null;
}

export const CREDIT_SECTOR_LABELS: Record<number, string> = {
  1: "Agriculture and forestry", 5: "Fishing", 6: "Mining", 9: "Manufacturing",
  26: "Electricity, gas and water", 27: "Construction", 28: "Wholesale and retail trade",
  32: "Hotels and restaurants", 36: "Transport and communications", 44: "Financial intermediation",
  50: "Real estate and business services", 55: "Public administration and defence", 56: "Education",
  57: "Health and social services", 58: "Other community services", 63: "Private households with employees",
  64: "International organisations",
};

const MATURITY_LABELS: Record<number, string> = {
  1: "Discounted receivables", 2: "Export loans", 3: "Import loans", 4: "Export-guaranteed investment loans",
  5: "Other investment loans", 6: "Working capital loans", 7: "Commercial instalment loans",
  8: "Specialised loans", 9: "Fund-financed loans", 10: "Consumer loans", 11: "Credit cards",
  12: "Securities purchase loans", 13: "Precious metal loans", 14: "Factoring receivables",
  15: "Deferred trade finance", 16: "Partnership finance", 17: "Loans to non-bank financial institutions",
  18: "Loans to non-residents", 19: "Other loans",
};

const SME_LABELS: Record<number, string> = { 2: "Micro", 3: "Small", 4: "Medium" };
const GUARANTEE_LABELS: Record<number, string> = {
  2: "Letters of guarantee", 17: "Acceptance credits", 20: "Letters of credit", 23: "Endorsements",
  24: "Pre-financing without guarantees", 25: "Securities underwriting guarantees", 26: "Other guarantees and sureties",
};
const PURPOSE_LABELS: Record<number, string> = {
  3: "Bid guarantees", 4: "Performance guarantees", 5: "Advance payment guarantees",
  6: "Customs guarantees", 7: "Retention guarantees", 8: "Pre-financing guarantees", 9: "Guarantees for cash loans",
};

const number = (value: number | null | undefined): number | null =>
  typeof value === "number" && Number.isFinite(value) ? value : null;
const ratio = (value: number | null, total: number | null): number | null =>
  value != null && total != null && total > 0 ? value / total * 100 : null;

/** Source rounding permits a few unit differences; missing legs never reconcile. */
export function creditComponentsReconcile(parts: (number | null)[], total: number | null): boolean {
  return total != null && parts.every((value) => value != null) &&
    Math.abs(parts.reduce<number>((sum, value) => sum + (value ?? 0), 0) - total) <= Math.max(5, Math.abs(total) * 0.000001);
}

function latest<T extends { period: string }>(rows: T[]): { asOf: string | null; rows: T[] } {
  const asOf = rows.reduce<string | null>((max, row) => !max || row.period > max ? row.period : max, null);
  return { asOf, rows: rows.filter((row) => row.period === asOf) };
}

/** Pure snapshot transform; never combine observations from different months. */
export function creditStructure(loans: CreditLoanRow[], other: CreditOtherRow[]) {
  const sectors = latest(loans.filter((row) => row.table_number === 5));
  const maturity = latest(loans.filter((row) => row.table_number === 3));
  const sme = latest(loans.filter((row) => row.table_number === 6));
  const guarantees = latest(other);
  const sectorMap = new Map(sectors.rows.map((row) => [row.item_order, row]));
  const maturityMap = new Map(maturity.rows.map((row) => [row.item_order, row]));
  const smeMap = new Map(sme.rows.map((row) => [row.item_order, row]));
  const otherMap = new Map<string, number | null>();
  const conflicts = new Set<string>();
  for (const row of guarantees.rows) {
    const key = `${row.item_order}:${row.column_name}`;
    const value = number(row.value_numeric);
    if (otherMap.has(key) && otherMap.get(key) !== value) conflicts.add(key);
    otherMap.set(key, conflicts.has(key) ? null : value);
  }
  const monetary = (value: number | null | undefined, divisor = 1) => {
    const clean = number(value);
    return clean == null ? null : clean / divisor;
  };
  const readOther = (item: number, column = "Toplam") => otherMap.get(`${item}:${column}`) ?? null;

  // T05 is published in thousands of TL; other monthly credit tables in millions.
  const sectorDistribution: CreditSnapshot = {
    asOf: sectors.asOf,
    total: monetary(sectorMap.get(70)?.total_amount, 1000),
    data: Object.entries(CREDIT_SECTOR_LABELS).map(([id, label]) => {
      const row = sectorMap.get(Number(id));
      return { id, label, values: { credit: monetary(row?.total_amount, 1000) } };
    }).sort((a, b) => (b.values.credit ?? -Infinity) - (a.values.credit ?? -Infinity)),
  };
  const maturities: CreditSnapshot = {
    asOf: maturity.asOf,
    total: number(maturityMap.get(20)?.total_amount),
    data: Object.entries(MATURITY_LABELS).map(([id, label]) => {
      const row = maturityMap.get(Number(id));
      const total = number(row?.total_amount);
      const parts = [number(row?.short_term_total), number(row?.medium_long_total)];
      const valid = creditComponentsReconcile(parts, total);
      return { id, label, total, reconciled: valid, values: { short: parts[0], long: parts[1] } };
    }).sort((a, b) => (b.total ?? -Infinity) - (a.total ?? -Infinity)),
  };
  const smeCurrency: CreditSnapshot = {
    asOf: sme.asOf,
    total: number(smeMap.get(1)?.total_amount),
    data: Object.entries(SME_LABELS).map(([id, label]) => {
      const row = smeMap.get(Number(id));
      const total = number(row?.total_amount);
      const parts = [number(row?.total_tl), number(row?.total_fx)];
      const valid = creditComponentsReconcile(parts, total);
      return { id, label, total, reconciled: valid, values: { tl: parts[0], fx: parts[1] } };
    }),
  };
  const smeRecords: CreditSnapshot = {
    asOf: sme.asOf,
    total: number(smeMap.get(5)?.total_amount),
    data: Object.entries(SME_LABELS).map(([id, label]) => ({
      id, label, values: {
        records: ratio(number(smeMap.get(Number(id) + 4)?.total_amount), number(smeMap.get(5)?.total_amount)),
        credit: ratio(number(smeMap.get(Number(id))?.total_amount), number(smeMap.get(1)?.total_amount)),
      },
    })),
  };
  const nonCash: CreditSnapshot = {
    asOf: guarantees.asOf, total: readOther(1),
    data: Object.entries(GUARANTEE_LABELS).map(([id, label]) => {
      const total = readOther(Number(id));
      const parts = [readOther(Number(id), "Tp"), readOther(Number(id), "Yp")];
      const valid = creditComponentsReconcile(parts, total);
      return { id, label, total, reconciled: valid, values: { tl: parts[0], fx: parts[1] } };
    }),
  };
  const guaranteePurpose: CreditSnapshot = {
    asOf: guarantees.asOf, total: readOther(2),
    data: Object.entries(PURPOSE_LABELS).map(([id, label]) => ({
      id, label, values: { amount: readOther(Number(id)) },
    })).sort((a, b) => (b.values.amount ?? -Infinity) - (a.values.amount ?? -Infinity)),
  };
  return { sectorDistribution, maturities, smeCurrency, smeRecords, nonCash, guaranteePurpose };
}

export async function loadCreditStructure() {
  const [loans, other] = await Promise.all([
    cachedAll<CreditLoanRow>(`WITH latest AS (
      SELECT table_number, MAX(year * 100 + month) AS ym FROM loans
      WHERE table_number IN (3, 5, 6) AND bank_type_code = '10001' AND currency = 'TL'
      GROUP BY table_number
    ) SELECT l.table_number, l.year || '-' || PRINTF('%02d', l.month) AS period,
      l.item_order, l.item_name, l.short_term_total, l.medium_long_total,
      l.total_tl, l.total_fx, l.total_amount, l.npl_amount
      FROM loans l JOIN latest ON latest.table_number = l.table_number AND latest.ym = l.year * 100 + l.month
      WHERE l.bank_type_code = '10001' AND l.currency = 'TL' ORDER BY l.table_number, l.item_order`),
    cachedAll<CreditOtherRow>(`SELECT year || '-' || PRINTF('%02d', month) AS period,
      item_order, column_name, value_numeric FROM other_data
      WHERE table_number = 14 AND bank_type_code = '10001' AND currency = 'TL'
      AND item_order BETWEEN 1 AND 26 AND column_name IN ('Tp', 'Yp', 'Toplam')
      AND year * 100 + month = (SELECT MAX(year * 100 + month) FROM other_data
        WHERE table_number = 14 AND bank_type_code = '10001' AND currency = 'TL')
      ORDER BY item_order, column_name`),
  ]);
  return creditStructure(loans, other);
}
