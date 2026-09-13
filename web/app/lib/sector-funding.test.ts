import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("./db", () => ({ cachedAll: vi.fn() }));
import { cachedAll } from "./db";
import {
  buildDepositFundingDetail, buildLiquidityMaturity, buildSecuritiesUse,
  fundingReconciles, fundingSum, loadDepositFundingDetail,
  loadLiquidityFundingDetail, type DepositDetailRow, type FundingCell,
} from "./sector-funding";

const period = "2026-08";
const deposit = (item_order: number, table_number = 10, overrides: Partial<DepositDetailRow> = {}): DepositDetailRow => ({
  period, table_number, item_order, total_amount: 100,
  demand: 10, maturity_1m: 20, maturity_1_3m: 30,
  maturity_3_6m: 15, maturity_6_12m: 15, maturity_over_12m: 10,
  bracket_10k: 5, bracket_50k: 10, bracket_250k: 15, bracket_1m: 20, bracket_over_1m: 50,
  ...overrides,
});
const deposits = () => [9, 10].flatMap((table) => Array.from({ length: 13 }, (_, i) => deposit(i + 1, table)));
const cell = (item_order: number, value: number | null, column_name = "BirAy", date = period): FundingCell => ({
  period: date, item_order, column_name, value,
});
const liquidity = () => [
  ...Array.from({ length: 11 }, (_, i) => cell(i + 1, 20)),
  cell(18, 220),
  ...Array.from({ length: 17 }, (_, i) => cell(i + 19, 10)),
  cell(42, 170), cell(43, 50),
  cell(18, 100, "YediGun"), cell(42, 130, "YediGun"), cell(43, -30, "YediGun"),
  cell(18, 250, "UcAy"), cell(42, 250, "UcAy"), cell(43, 0, "UcAy"),
  cell(18, 350, "OnikiAy"), cell(42, 200, "OnikiAy"), cell(43, 150, "OnikiAy"),
];

beforeEach(() => vi.mocked(cachedAll).mockReset());

describe("funding arithmetic", () => {
  it("distinguishes absent, zero and invalid values", () => {
    expect(fundingSum([1, 0, -1])).toBe(0);
    expect(fundingSum([1, null])).toBeNull();
    expect(fundingSum([1, undefined])).toBeNull();
    expect(fundingSum([1, NaN])).toBeNull();
    expect(fundingSum([Infinity])).toBeNull();
  });
  it("allows source rounding but rejects economically different totals", () => {
    expect(fundingReconciles([100, 50], 151)).toBe(true);
    expect(fundingReconciles([100, 50], 153)).toBe(false);
    expect(fundingReconciles([100, null], 100)).toBe(false);
    expect(fundingReconciles([0, 0], 0)).toBe(true);
  });
});

describe("deposit cross-sections", () => {
  it("sums only customer amount rows across currencies, excluding depositor counts and totals", () => {
    const input = deposits();
    input.push(deposit(14, 9, { total_amount: 999_999, bracket_over_1m: 999_999 }));
    const output = buildDepositFundingDetail(input);
    expect(output.concentration).toHaveLength(3);
    expect(output.concentration[0].total).toBe(300);
    expect(output.concentration[0].values).toEqual({ bracket_10k: 15, bracket_50k: 30, bracket_250k: 45, bracket_1m: 60, bracket_over_1m: 150 });
    expect(output.customers[0].values).toEqual({ tl: 100, fx: 100, metals: 100 });
  });
  it("uses independent latest periods for T09 and T10 without carrying old missing rows forward", () => {
    const input = deposits();
    input.push(deposit(1, 10, { period: "2026-09" }));
    const output = buildDepositFundingDetail(input);
    expect(output.concentrationPeriod).toBe(period);
    expect(output.maturityPeriod).toBe("2026-09");
    expect(output.customers[0].total).toBeNull();
    expect(Object.values(output.customers[0].values).every((value) => value === null)).toBe(true);
  });
  it("does not fabricate a full partition when a constituent is missing", () => {
    const input = deposits().map((row) => row.table_number === 9 && row.item_order === 6 ? { ...row, bracket_1m: null } : row);
    expect(Object.values(buildDepositFundingDetail(input).concentration[0].values)).toEqual([null, null, null, null, null]);
  });
  it("rejects a bracket distribution that disagrees with published amounts", () => {
    const input = deposits().map((row) => row.table_number === 9 && row.item_order === 2 ? { ...row, total_amount: 200 } : row);
    expect(buildDepositFundingDetail(input).concentration[0].values.bracket_over_1m).toBeNull();
  });
  it("does not silently choose one of two colliding source rows", () => {
    const input = deposits();
    input.push(deposit(2, 10, { total_amount: 200 }));
    expect(buildDepositFundingDetail(input).customers[0].values.tl).toBeNull();
  });
  it("keeps currency maturity and the nine joint customer/currency classes distinct", () => {
    const output = buildDepositFundingDetail(deposits());
    expect(output.maturity.map((row) => row.id)).toEqual(["tl", "fx", "metals"]);
    expect(output.customerMaturity).toHaveLength(9);
    expect(output.customerMaturity[0].values).toEqual({ demand: 10, short: 50, long: 40 });
    expect(output.customerMaturity[0].total).toBe(100);
  });
  it("preserves disclosed zeros without inventing shares for missing or negative balances", () => {
    const zero = deposit(1, 10, { total_amount: 0, demand: 0, maturity_1m: 0, maturity_1_3m: 0, maturity_3_6m: 0, maturity_6_12m: 0, maturity_over_12m: 0 });
    expect(buildDepositFundingDetail([zero]).maturity[0].values.demand).toBe(0);
    expect(buildDepositFundingDetail([deposit(1, 10, { demand: -10, maturity_1m: 40 })]).maturity[0].values.demand).toBeNull();
  });
  it("does not lose valid rounded values when six published maturity cells become three display groups", () => {
    const row = deposit(2, 10, { total_amount: 103 });
    expect(buildDepositFundingDetail([row]).customerMaturity[0].values).toEqual({ demand: 10, short: 50, long: 40 });
  });
});

describe("monthly liquidity table", () => {
  it("retains separate signed published horizons, including an actual zero", () => {
    const output = buildLiquidityMaturity(liquidity());
    expect(output.horizons.map((row) => row.values.net)).toEqual([-30, 50, 0, 150]);
  });
  it("reconciles one-month components without adding derivative sub-items or other horizons", () => {
    const input = liquidity();
    input.push(cell(12, 999_999), cell(36, 999_999));
    const output = buildLiquidityMaturity(input);
    expect(output.components).toHaveLength(9);
    expect(fundingSum(output.components.map((row) => row.values.net))).toBe(50);
    expect(output.net).toBe(50);
    expect(output.components.find((row) => row.id === "derivatives")?.values.net).toBe(10);
    expect(output.components.find((row) => row.id === "other")?.values.net).toBe(-140);
  });
  it("withholds decomposition when a required leaf is absent but retains valid published horizons", () => {
    const output = buildLiquidityMaturity(liquidity().filter((row) => row.item_order !== 7));
    expect(output.components.every((row) => row.values.net === null)).toBe(true);
    expect(output.net).toBeNull();
    expect(output.horizons[1].values.net).toBe(50);
  });
  it("withholds a corrupted published net gap and does not replace it with its own arithmetic", () => {
    const output = buildLiquidityMaturity(liquidity().map((row) => row.item_order === 43 && row.column_name === "BirAy" ? { ...row, value: 500 } : row));
    expect(output.horizons[1].values.net).toBeNull();
    expect(output.net).toBeNull();
  });
  it("does not fill a partial new month with the previous month's liability values", () => {
    const output = buildLiquidityMaturity([...liquidity(), cell(18, 300, "BirAy", "2026-09")]);
    expect(output.period).toBe("2026-09");
    expect(output.horizons.every((row) => row.values.net === null)).toBe(true);
    expect(output.net).toBeNull();
  });
});

describe("securities use", () => {
  it("shows overlapping memorandum shares independently even when their sum exceeds 100%", () => {
    const output = buildSecuritiesUse([cell(27, 70, "Toplam"), cell(28, 60, "Toplam"), cell(29, 100, "Toplam")]);
    expect(output.map((row) => row.value)).toEqual([70, 60]);
  });
  it("uses the same period's denominator and preserves missing/zero denominators", () => {
    const output = buildSecuritiesUse([
      cell(27, 70, "Toplam", "2026-07"), cell(29, 100, "Toplam", "2026-07"),
      cell(27, 80, "Toplam"), cell(29, 0, "Toplam"),
    ]);
    expect(output.map((row) => row.value)).toEqual([70, null, null, null]);
  });
});

describe("narrow live loaders", () => {
  it("loads both monthly deposit cuts from their latest published months in the TL reporting presentation", async () => {
    vi.mocked(cachedAll).mockResolvedValueOnce(deposits());
    const result = await loadDepositFundingDetail();
    expect(result.concentrationPeriod).toBe(period);
    const sql = vi.mocked(cachedAll).mock.calls[0][0];
    expect(sql).toContain("GROUP BY table_number");
    expect(sql).toContain("d.currency = 'TL'");
    expect(sql).toContain("d.item_order BETWEEN 1 AND 13");
  });
  it("reads new funding domains without touching data or including parent weekly bank-debt totals", async () => {
    vi.mocked(cachedAll).mockResolvedValueOnce(liquidity()).mockResolvedValueOnce([]).mockResolvedValueOnce([]).mockResolvedValueOnce([]);
    const result = await loadLiquidityFundingDetail();
    expect(result.maturity.net).toBe(50);
    const sql = vi.mocked(cachedAll).mock.calls.map(([query]) => query);
    expect(sql).toHaveLength(4);
    expect(sql[3]).toContain("category = 'diger_bilanco'");
    expect(sql[3]).toContain("'5.0.10', '5.0.11', '5.0.12', '5.0.16'");
    expect(sql[3]).not.toContain("'5.0.9'");
    expect(sql.every((query) => !/\b(INSERT|UPDATE|DELETE)\b/.test(query))).toBe(true);
  });
});
