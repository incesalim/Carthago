import { describe, expect, it, vi } from "vitest";
vi.mock("./db", () => ({ cachedAll: vi.fn() }));
import { creditComponentsReconcile, creditStructure, type CreditLoanRow, type CreditOtherRow } from "./sector-credit";

const loan = (table: number, item: number, overrides: Partial<CreditLoanRow> = {}): CreditLoanRow => ({
  table_number: table, period: "2026-07", item_order: item, item_name: `Item ${item}`,
  short_term_total: null, medium_long_total: null, total_tl: null, total_fx: null,
  total_amount: null, npl_amount: null, ...overrides,
});
const other = (item: number, column: string, value: number | null, period = "2026-07"): CreditOtherRow => ({
  period, item_order: item, column_name: column, value_numeric: value,
});

describe("sector credit snapshots", () => {
  it("converts only T05 thousands of TL into the shared millions-of-TL unit", () => {
    const data = creditStructure([
      loan(5, 1, { total_amount: 3_000_000 }), loan(5, 70, { total_amount: 10_000_000 }),
      loan(3, 1, { total_amount: 3000, short_term_total: 1000, medium_long_total: 2000 }),
      loan(6, 2, { total_amount: 3000, total_tl: 2500, total_fx: 500 }),
    ], [other(2, "Tp", 1000), other(2, "Yp", 2000), other(2, "Toplam", 3000)]);
    expect(data.sectorDistribution.data[0].values.credit).toBe(3000);
    expect(data.sectorDistribution.total).toBe(10000);
    expect(data.maturities.data[0].values).toEqual({ short: 1000, long: 2000 });
    expect(data.smeCurrency.data[0].values).toEqual({ tl: 2500, fx: 500 });
    expect(data.nonCash.data[0].values).toEqual({ tl: 1000, fx: 2000 });
  });

  it("never backfills a missing newest-month component from an older month", () => {
    const data = creditStructure([
      loan(6, 2, { period: "2026-06", total_amount: 100, total_tl: 80, total_fx: 20 }),
      loan(6, 2, { total_amount: 100, total_tl: 100, total_fx: null }),
      loan(3, 20, { period: "2026-06", total_amount: 500 }),
    ], [other(2, "Tp", 80, "2026-06"), other(2, "Yp", 20), other(2, "Toplam", 100)]);
    expect(data.smeCurrency.asOf).toBe("2026-07");
    expect(data.maturities.asOf).toBe("2026-06");
    expect(data.smeCurrency.data[0].values).toEqual({ tl: 100, fx: null });
    expect(data.smeCurrency.data[0].reconciled).toBe(false);
    expect(data.nonCash.data[0].values).toEqual({ tl: null, fx: 20 });
    expect(data.nonCash.data[0].reconciled).toBe(false);
  });

  it("preserves disclosed zero and refuses unreconciled or non-finite compositions", () => {
    expect(creditComponentsReconcile([0, 100], 100)).toBe(true);
    expect(creditComponentsReconcile([0, 0], 0)).toBe(true);
    expect(creditComponentsReconcile([null, 100], 100)).toBe(false);
    expect(creditComponentsReconcile([70, 20], 100)).toBe(false);
    const data = creditStructure([
      loan(3, 1, { total_amount: 100, short_term_total: 0, medium_long_total: 100 }),
      loan(3, 2, { total_amount: 100, short_term_total: 70, medium_long_total: 20 }),
      loan(6, 2, { total_amount: Infinity, total_tl: 100, total_fx: 0 }),
    ], [other(24, "Tp", 0), other(24, "Yp", 0), other(24, "Toplam", 0)]);
    expect(data.maturities.data.find(row => row.id === "1")?.values.short).toBe(0);
    expect(data.maturities.data.find(row => row.id === "2")?.values).toEqual({ short: 70, long: 20 });
    expect(data.maturities.data.find(row => row.id === "2")?.reconciled).toBe(false);
    expect(data.smeCurrency.data[0].total).toBeNull();
    expect(data.nonCash.data.find(row => row.id === "24")?.values).toEqual({ tl: 0, fx: 0 });
  });

  it("uses cash-customer records and loan balances with their separate denominators", () => {
    const data = creditStructure([
      loan(6, 1, { total_amount: 1000 }), loan(6, 2, { total_amount: 100 }),
      loan(6, 5, { total_amount: 100 }), loan(6, 6, { total_amount: 70 }),
    ], []);
    expect(data.smeRecords.data[0].values).toEqual({ records: 70, credit: 10 });
    expect(data.smeRecords.data[1].values).toEqual({ records: null, credit: null });
    expect(creditStructure([loan(6, 5, { total_amount: 0 }), loan(6, 6, { total_amount: 0 })], []).smeRecords.data[0].values.records).toBeNull();
  });

  it("excludes nested sectors and collateral rows from mutually exclusive distributions", () => {
    const data = creditStructure([
      loan(5, 9, { total_amount: 1_000_000 }), loan(5, 11, { total_amount: 200_000 }),
      loan(5, 65, { total_amount: 300_000 }),
    ], [other(3, "Toplam", 25), other(10, "Toplam", 100), other(11, "Toplam", 50)]);
    expect(data.sectorDistribution.data.find(row => row.id === "9")?.values.credit).toBe(1000);
    expect(data.sectorDistribution.data.some(row => ["11", "65"].includes(row.id))).toBe(false);
    expect(data.guaranteePurpose.data[0].values.amount).toBe(25);
    expect(data.guaranteePurpose.data.some(row => ["10", "11"].includes(row.id))).toBe(false);
  });

  it("does not select an arbitrary value from conflicting dynamic-table cells", () => {
    const data = creditStructure([], [
      other(3, "Toplam", 25), other(3, "Toplam", 40), other(3, "Toplam", 25),
      other(4, "Toplam", 0), other(4, "Toplam", 0),
    ]);
    expect(data.guaranteePurpose.data.find(row => row.id === "3")?.values.amount).toBeNull();
    expect(data.guaranteePurpose.data.find(row => row.id === "4")?.values.amount).toBe(0);
  });
});
