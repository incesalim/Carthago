import { describe, expect, it } from "vitest";
import { evaluateCapitalSignals, type CapitalSignalInputs } from "./capital";

const empty: CapitalSignalInputs = { car: [], capitalRatios: [], banks: { period: null, rows: [] }, equityGrowth: [], assetGrowth: [] };
const read = (code: string, input: Partial<CapitalSignalInputs> = {}) => evaluateCapitalSignals({ ...empty, ...input }).find(row => row.id === `capital:${code}`)!;
const ratio = (cet1: number | null) => ({ bank_ticker: "BANK", car: 16, tier1: 14, cet1 });
const audited = (cet1: number, tier1: number, car: number) => [
  { period: "2026Q1", bank_type_code: "CET1", value: cet1 },
  { period: "2026Q1", bank_type_code: "TIER1", value: tier1 },
  { period: "2026Q1", bank_type_code: "CAR", value: car },
];

describe("capital research signals", () => {
  it("preserves all five identities and marks absent inputs unavailable", () => {
    const rows = evaluateCapitalSignals(empty);
    expect(rows.map(row => row.id)).toEqual(["capital:structural-break", "capital:hybrid-buffer", "capital:thin-cet1", "capital:generation-gap", "capital:thin-buffer"]);
    expect(rows.every(row => row.state === "unavailable")).toBe(true);
  });

  it("detects a signed level shift and rejects an omitted calendar month", () => {
    const car = Array.from({ length: 13 }, (_, i) => ({ period: new Date(Date.UTC(2025, i, 1)).toISOString().slice(0, 7), value: 18 + i * 0.1 - (i >= 8 ? 3 : 0) }));
    const signal = read("structural-break", { car });
    expect(signal.state).toBe("active");
    expect(signal.facts.find(f => f.key === "largest-move")?.value).toBeCloseTo(-2.9);
    const gap = read("structural-break", { car: car.filter((_, i) => i !== 7) });
    expect(gap.state).toBe("unavailable");
    expect(gap.facts.find(f => f.key === "largest-move")?.value).toBeNull();
    expect(read("structural-break", { car: car.map((row, i) => ({ ...row, value: 18 + i * 0.1 })) }).state).toBe("clear");
  });

  it("compares hybrid instruments with the audited buffer, including strict equality", () => {
    expect(read("hybrid-buffer", { capitalRatios: audited(10, 12, 15) }).state).toBe("active");
    expect(read("hybrid-buffer", { capitalRatios: audited(12, 14, 17) }).state).toBe("clear");
    const partial = [...audited(10, 12, 15), { period: "2026Q2", bank_type_code: "CET1", value: null }];
    expect(read("hybrid-buffer", { capitalRatios: partial }).state).toBe("unavailable");
  });

  it("does not infer a clear bank register from missing CET1", () => {
    expect(read("thin-cet1", { banks: { period: "2026Q1", rows: [ratio(7)] } }).state).toBe("clear");
    expect(read("thin-cet1", { banks: { period: "2026Q1", rows: [ratio(7), ratio(null)] } }).state).toBe("unavailable");
    const observed = read("thin-cet1", { banks: { period: "2026Q1", rows: [ratio(6.9), ratio(null)] } });
    expect(observed.state).toBe("active");
    expect(observed.facts.find(f => f.key === "below-cet1-target")?.value).toBe(1);
    expect(observed.facts.find(f => f.key === "banks")?.value).toBe(2);
    expect(observed.facts.find(f => f.key === "cet1-minimum")?.value).toBe(4.5);
  });

  it("keeps generation-gap dates and requires matched growth observations", () => {
    const equityGrowth = [{ period: "2026-06", value: 20 }];
    const assetGrowth = [{ period: "2026-06", value: 25 }];
    const signal = read("generation-gap", { equityGrowth, assetGrowth });
    expect(signal.state).toBe("active");
    expect(signal.facts.find(f => f.key === "growth-gap")?.value).toBe(-5);
    expect(read("generation-gap", { equityGrowth, assetGrowth: [{ period: "2026-05", value: 25 }] }).state).toBe("unavailable");
    expect(read("generation-gap", { equityGrowth, assetGrowth: equityGrowth }).state).toBe("clear");
  });

  it("uses the 12% target and a strict two-point buffer threshold", () => {
    expect(read("thin-buffer", { car: [{ period: "2026-06", value: 13.99 }] }).state).toBe("active");
    const atThreshold = read("thin-buffer", { car: [{ period: "2026-06", value: 14 }] });
    expect(atThreshold.state).toBe("clear");
    expect(atThreshold.facts.find(f => f.key === "buffer")?.value).toBe(2);
    expect(read("thin-buffer", { car: [{ period: "2026-06", value: null }] }).state).toBe("unavailable");
  });
});
