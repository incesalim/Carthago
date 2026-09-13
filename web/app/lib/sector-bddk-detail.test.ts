import { describe, expect, it, vi } from "vitest";
vi.mock("./db", () => ({ cachedAll: vi.fn() }));
import {
  buildCapitalDetail, buildFxBridge, manufacturingNplShares, monthlyNetProfit,
  nonDerivativeCommitments, retailRiskShares, securitiesAccountingMix, smeRiskBySize,
  type BulletinCell, type BulletinLoan,
} from "./sector-bddk-detail";

const cell = (item_order: number, value: number | null, period = "2026-04"): BulletinCell =>
  ({ period, bank_type_code: "10001", item_order, value });
const loan = (item_order: number, total_amount: number | null, npl_amount: number | null = null): BulletinLoan =>
  ({ period: "2026-04", item_order, total_amount, npl_amount });

describe("BDDK sector bulletin detail", () => {
  it("capital bridge respects CET1, other Tier 1, Tier 2 and separate deductions", () => {
    const result = buildCapitalDetail([cell(1, 100), cell(6, 80), cell(2, 30), cell(4, 10), cell(5, 120),
      cell(7, 1000), cell(10, 800), cell(30, 50), cell(31, 150)]);
    expect(result.bridge.map(r => r.value)).toEqual([80, 20, 30, -10, 120]);
    expect(result.riskRows[0].values).toEqual({ credit: 800, market: 50, operational: 150 });
    expect(result.riskRows[1].values.credit).toBeNull();
  });
  it("does not draw a fabricated capital bridge or partial RWA composition", () => {
    const result = buildCapitalDetail([cell(1, 100), cell(6, 80), cell(2, null), cell(4, 10), cell(5, 120),
      cell(7, 1000), cell(10, 800), cell(30, 50)]);
    expect(result.bridge).toEqual([]);
    expect(result.riskRows[0].values.credit).toBeNull();
    expect(buildCapitalDetail([cell(1, 100), cell(6, 80), cell(2, 30), cell(4, 10), cell(5, 200)]).capitalValid).toBe(false);
  });
  it("does not silently select a conflicting duplicate published cell", () => {
    expect(buildCapitalDetail([cell(1, 100), cell(6, 80), cell(2, 30), cell(4, 10), cell(5, 120), cell(5, 140), cell(5, 120)]).bridge).toEqual([]);
  });
  it("monthly profit resets in January and never differences across missing months or nulls", () => {
    const result = monthlyNetProfit([
      { year: 2025, month: 12, net: 900 }, { year: 2026, month: 1, net: 100 },
      { year: 2026, month: 2, net: 180 }, { year: 2026, month: 4, net: 400 },
      { year: 2026, month: 5, net: null }, { year: 2026, month: 6, net: 600 },
    ]);
    expect(result.map(r => r.value)).toEqual([null, 100, 80, null, null, null]);
  });
  it("retail loan share and NPL share use their own four-product denominators", () => {
    const result = retailRiskShares([loan(2, 80), loan(14, 20), loan(3, 80), loan(15, 0),
      loan(4, 80), loan(16, 10), loan(9, 80), loan(17, 10)]);
    expect(result.rows[0].values).toEqual({ loans: 100 / 360 * 100, npl: 50 });
    expect(result.rows.reduce((s, r) => s + r.values.loans!, 0)).toBeCloseTo(100);
    expect(retailRiskShares([loan(2, 80), loan(14, 20)]).rows[0].values).toEqual({ loans: null, npl: null });
  });
  it("SME rates include NPLs in the gross denominator without treating zero as missing", () => {
    const result = smeRiskBySize([loan(1, 270, 30), loan(2, 90, 10), loan(3, 90, 0), loan(4, null, 20)]);
    expect(result.rows[0].values).toEqual({ ratio: 10, sector: 10 });
    expect(result.rows[1].values.ratio).toBe(0);
    expect(result.rows[2].values.ratio).toBeNull();
  });
  it("manufacturing adds exactly 14 non-overlapping children and converts T05 thousand TL", () => {
    const rows = [loan(9, 100000, 14000), ...Array.from({ length: 13 }, (_, i) => loan(i + 10, 0, 1000)), loan(25, 0, 1000),
      loan(23, 0, 99999), loan(24, 0, 99999)];
    const result = manufacturingNplShares(rows);
    expect(result.valid).toBe(true);
    expect(result.rows).toHaveLength(14);
    expect(result.rows[0].total).toBe(1);
    expect(result.rows.reduce((s, r) => s + r.values.share!, 0)).toBeCloseTo(100);
    expect(manufacturingNplShares(rows.filter(r => r.item_order !== 25)).rows.every(r => r.values.share === null)).toBe(true);
  });
  it("FX bridge keeps signed on/off positions and gaps unreconciled periods", () => {
    const rows = [cell(2, 100), cell(6, 500), cell(4, 450), cell(8, 30), cell(9, 20)];
    expect(buildFxBridge(rows).bridge.map(r => r.value)).toEqual([-400, 420, 20]);
    expect(buildFxBridge(rows.map(r => r.item_order === 9 ? { ...r, value: 80 } : r)).history.every(r => r.value === null)).toBe(true);
    expect(buildFxBridge(rows.filter(r => r.item_order !== 8)).bridge).toEqual([]);
  });
  it("securities classes reconcile to their published total and retain missing dates", () => {
    const rows = ["3.0.1", "3.0.14", "3.0.17", "3.0.20"].map((item_id, i) => ({ period: "2026-06-05", item_id, value: [1000, 100, 400, 500][i] }));
    expect(securitiesAccountingMix(rows)[0]).toMatchObject({ fvpl: 10, fvoci: 40, amortized: 50 });
    expect(securitiesAccountingMix(rows.slice(0, 3))[0].fvpl).toBeNull();
  });
  it("commitments exclude derivatives and do not drop disclosed zero leaves", () => {
    const result = nonDerivativeCommitments([cell(39, 120), ...Array.from({ length: 12 }, (_, i) => cell(i + 40, i === 0 ? 0 : i === 1 ? 20 : 10)), cell(28, 5000)]);
    expect(result.valid).toBe(true);
    expect(result.rows).toHaveLength(12);
    expect(result.rows.find(r => r.id === "40")?.values.share).toBe(0);
    expect(result.rows.reduce((s, r) => s + r.values.share!, 0)).toBeCloseTo(100);
  });
});
