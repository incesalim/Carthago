import { describe, expect, it } from "vitest";
import { evaluateProfitabilitySignals, type ProfitabilitySignalInputs } from "./profitability";
import type { PnlRow } from "../profitability";

const T = 1e6;
const cpi = Array.from({ length: 30 }, (_, i) => ({ period_date: new Date(Date.UTC(2024, i, 1)).toISOString().slice(0, 10), value: 100 * Math.pow(1.2, i / 12) }));
const june: PnlRow = { year: 2026, month: 6, dep_int: T, nii: 3 * T, prov: 0.5 * T, fees: T, opex: 3 * T, other: 0.1 * T, tax: 0.1 * T, net: 0.5 * T };
const may: PnlRow = Object.fromEntries(Object.entries(june).map(([name, value]) => [name, name === "year" ? value : name === "month" ? 5 : value! * 5 / 6])) as unknown as PnlRow;
const input: ProfitabilitySignalInputs = {
  roe: [{ period: "2026-06", value: 10 }], cpi, pnl: [may, june],
  deposits: [{ year: 2026, month: 6, demand: 10 * T, time_dep: 10 * T, total_dep: 20 * T, equity: 5 * T }],
};
const read = (code: string, overrides: Partial<ProfitabilitySignalInputs> = {}) => evaluateProfitabilitySignals({ ...input, ...overrides }).find(row => row.id === `profitability:${code}`)!;

describe("profitability research signals", () => {
  it("preserves five identities and makes completely missing data unavailable", () => {
    const rows = evaluateProfitabilitySignals({ roe: [], cpi: [], pnl: [], deposits: [] });
    expect(rows.map(row => row.id)).toEqual(["profitability:free-funding", "profitability:real-roe", "profitability:cost-income", "profitability:savers-below-cpi", "profitability:pnl-reconcile"]);
    expect(rows.every(row => row.state === "unavailable")).toBe(true);
  });

  it("retains the annualized funding arithmetic and strict profit threshold", () => {
    const signal = read("free-funding");
    expect(signal.state).toBe("active");
    expect(signal.facts.find(f => f.key === "funding-value")?.value).toBeCloseTo(2);
    expect(signal.facts.find(f => f.key === "cost-profit-ratio")?.value).toBeCloseTo(2);
    expect(read("free-funding", { pnl: [may, { ...june, dep_int: 0.5 * T }] }).state).toBe("clear");
    expect(read("free-funding", { pnl: [may, { ...june, dep_int: null }] }).state).toBe("unavailable");
  });

  it("uses same-month CPI for Fisher ROE and preserves separately dated latest readings", () => {
    const inflatedJune = cpi.map((row, i) => i === cpi.length - 1 ? { ...row, value: row.value * 2 } : row);
    const signal = read("real-roe", { roe: [{ period: "2026-04", value: 10 }], cpi: inflatedJune });
    expect(signal.asOf).toBe("2026-04");
    expect(signal.facts.find(f => f.key === "real-roe")?.value).toBeCloseTo((1.1 / 1.2 - 1) * 100);
    expect(signal.facts.find(f => f.key === "average-cpi")?.asOf).toBe("2026-04");
    expect(signal.facts.find(f => f.key === "latest-average-cpi")?.asOf).toBe("2026-06");
    expect(read("real-roe", { roe: [{ period: "2026-06", value: 30 }] }).state).toBe("clear");
  });

  it("does not substitute an older CPI value for a missing comparison-month input", () => {
    const missing = cpi.map(row => row.period_date.startsWith("2026-04") ? { ...row, value: null } : row);
    expect(read("real-roe", { roe: [{ period: "2026-04", value: 10 }], cpi: missing }).state).toBe("unavailable");
    expect(read("savers-below-cpi", { cpi: cpi.slice(0, -2) }).state).toBe("unavailable");
  });

  it("keeps current cost/income separate from missing comparison history", () => {
    expect(read("cost-income").state).toBe("active");
    expect(read("cost-income", { pnl: [may, { ...june, opex: 2 * T }] }).state).toBe("clear");
    expect(read("cost-income", { pnl: [may, { ...june, opex: null }] }).state).toBe("unavailable");
    const history = Array.from({ length: 13 }, (_, i) => {
      const date = new Date(Date.UTC(2025, 5 + i, 1));
      return { ...june, year: date.getUTCFullYear(), month: date.getUTCMonth() + 1, opex: i === 0 ? null : june.opex };
    });
    const signal = read("cost-income", { pnl: history });
    expect(signal.state).toBe("active");
    expect(signal.facts.find(f => f.key === "cost-income-prior")?.value).toBeNull();
  });

  it("separates a nominal funding gap from the real-return rule", () => {
    const signal = read("savers-below-cpi");
    expect(signal.state).toBe("active");
    expect(signal.facts.find(f => f.key === "nominal-gap")?.value).toBeCloseTo(-10);
    expect(read("savers-below-cpi", { pnl: [may, { ...june, dep_int: 3 * T }] }).state).toBe("clear");
  });

  it("keeps the reconciliation tolerance and never zero-fills undisclosed components", () => {
    expect(read("pnl-reconcile").state).toBe("clear");
    const january = { ...june, month: 1, nii: 0.001 * T, prov: 0, fees: 0, opex: 0, other: 0, tax: 0, net: 0 };
    expect(read("pnl-reconcile", { pnl: [january] }).state).toBe("clear");
    expect(read("pnl-reconcile", { pnl: [{ ...january, nii: 0.001001 * T }] }).state).toBe("active");
    expect(read("pnl-reconcile", { pnl: [may, { ...june, prov: null }] }).state).toBe("unavailable");
    expect(read("pnl-reconcile", { pnl: [june] }).state).toBe("unavailable");
  });
});
