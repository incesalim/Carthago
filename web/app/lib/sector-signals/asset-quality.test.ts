import { describe, expect, it } from "vitest";
import { evaluateAssetQualitySignals, type AssetQualitySignalInputs } from "./asset-quality";
import type { RollForwardYear, StageLadder } from "../credit-risk";

const ladder: StageLadder = { period: "2026Q1", n: 10, total: 1000, stage1Share: 70, stage2Share: 20, stage3Share: 10, stage2Bn: 200, stage3Bn: 100, ecl2Bn: 1.8, ecl3Bn: 5, cov2: 0.9, cov3: 5, problemShare: 30, problemBn: 300, provisionsBn: 6.8, problemCov: 6.8 / 3, multipleOfPrinted: 3 };
const annual = (year: string, additions: number, exits = 80): RollForwardYear => ({ year, n: 10, additions, collections: exits * 0.8, writeOffs: exits * 0.15, sold: exits * 0.05, exits, net: additions - exits, collectionShare: 80, disposalShare: 20 });
const npl = Array.from({ length: 7 }, (_, i) => ({ period: `2026-${String(i + 1).padStart(2, "0")}`, value: 2 + i * 0.1 }));
const input: AssetQualitySignalInputs = {
  npl, ladder, roll: [annual("2024", 100), annual("2025", 150)],
  grossNpl: [{ period: "2025-06-02", value: 100 }, { period: "2026-06-01", value: 131 }],
  loans: [{ period: "2025-06-02", value: 1000 }, { period: "2026-06-01", value: 1100 }],
  cpiYoY: new Map([["2026-06", 30]]),
};
const read = (code: string, override: Partial<AssetQualitySignalInputs> = {}) => evaluateAssetQualitySignals({ ...input, ...override }).find(row => row.id === `asset-quality:${code}`)!;

describe("asset-quality research signals", () => {
  it("preserves all four legacy codes and treats missing data as unavailable", () => {
    const rows = evaluateAssetQualitySignals({ npl: [], ladder: null, roll: [], grossNpl: [], loans: [], cpiYoY: new Map() });
    expect(rows.map(row => row.id)).toEqual(["asset-quality:watchlist_thinly_covered", "asset-quality:formation_doubling", "asset-quality:stock_compounding", "asset-quality:npl_ratio_streak"]);
    expect(rows.every(row => row.state === "unavailable")).toBe(true);
  });

  it("requires both stage-size and coverage conditions with their exact boundaries", () => {
    expect(read("watchlist_thinly_covered").state).toBe("active");
    expect(read("watchlist_thinly_covered", { ladder: { ...ladder, cov2: 1 } }).state).toBe("clear");
    expect(read("watchlist_thinly_covered", { ladder: { ...ladder, stage2Share: 19.99 } }).state).toBe("clear");
    expect(read("watchlist_thinly_covered", { ladder: { ...ladder, stage3Share: 0 } }).state).toBe("unavailable");
    expect(read("watchlist_thinly_covered").facts.find(f => f.key === "stage2-balance")?.value).toBe(200);
  });

  it("requires 1.5 times annual additions and positive net formation, not doubling", () => {
    const signal = read("formation_doubling");
    expect(signal.state).toBe("active");
    expect(signal.asOf).toBe("2025Q4");
    expect(signal.facts.find(f => f.key === "formation-multiple")?.value).toBe(1.5);
    expect(signal.facts.find(f => f.key === "collection-share")?.value).toBe(80);
    expect(read("formation_doubling", { roll: [annual("2024", 100), annual("2025", 149.9)] }).state).toBe("clear");
    expect(read("formation_doubling", { roll: [annual("2024", 100), annual("2025", 150, 150)] }).state).toBe("clear");
    expect(read("formation_doubling", { roll: [annual("2024", 0), annual("2025", 150)] }).state).toBe("unavailable");
    expect(read("formation_doubling", { roll: [annual("2023", 100), annual("2025", 150)] }).state).toBe("unavailable");
  });

  it("preserves the real-loan-growth floor and published-CPI requirement", () => {
    const signal = read("stock_compounding");
    expect(signal.state).toBe("active");
    expect(signal.facts.find(f => f.key === "real-loan-growth")?.value).toBeLessThan(0);
    expect(signal.facts.find(f => f.key === "comparison-threshold")?.value).toBeCloseTo(0.3);
    expect(signal.facts.find(f => f.key === "real-npl-growth")?.asOf).toBe("2026-06-01");
    expect(read("stock_compounding", { grossNpl: [{ period: "2025-06-02", value: 100 }, { period: "2026-06-01", value: 130 }] }).state).toBe("clear");
    expect(read("stock_compounding", { cpiYoY: new Map() }).state).toBe("unavailable");
  });

  it("counts six strict monthly rises and never clears an incomplete window", () => {
    expect(read("npl_ratio_streak").state).toBe("active");
    expect(read("npl_ratio_streak").facts.find(f => f.key === "rising-months")?.value).toBe(6);
    expect(read("npl_ratio_streak", { npl: npl.slice(1) }).state).toBe("unavailable");
    expect(read("npl_ratio_streak", { npl: npl.map((row, i) => i === 6 ? { ...row, value: npl[5].value } : row) }).state).toBe("clear");
    expect(read("npl_ratio_streak", { npl: npl.filter((_, i) => i !== 3) }).facts.find(f => f.key === "rising-months")?.value).toBeNull();
  });

  it("does not extend a valid current streak through an older missing month", () => {
    const rows = [
      { period: "2025-12", value: 1.9 },
      // January 2026 is absent; February–August has six consecutive changes.
      ...Array.from({ length: 7 }, (_, i) => ({ period: `2026-${String(i + 2).padStart(2, "0")}`, value: 2 + i * 0.1 })),
    ];
    const signal = read("npl_ratio_streak", { npl: rows });
    expect(signal.state).toBe("active");
    expect(signal.facts.find(f => f.key === "rising-months")?.value).toBe(6);
    expect(signal.facts.find(f => f.key === "start-ratio")?.asOf).toBe("2026-02");
  });
});
