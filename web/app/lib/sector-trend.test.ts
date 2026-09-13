import { describe, expect, it } from "vitest";
import { pivotSectorTrend, sectorLatestValues, sectorPaletteIndex, sectorSeriesCodes, sectorTrendScale } from "./sector-trend";

describe("sector-chart observation contract", () => {
  it("retains explicit and implicit gaps, disclosed zero and unlabelled source series", () => {
    const rows = [
      { period: "2026-03", bank_type_code: "A", value: 0 },
      { period: "2026-01", bank_type_code: "A", value: 12 },
      { period: "2026-02", bank_type_code: "A", value: null },
      { period: "2026-01", bank_type_code: "B", value: 8 },
    ];
    const codes = sectorSeriesCodes(rows, { A: "Sector" });
    expect(codes).toEqual(["A", "B"]);
    expect(pivotSectorTrend(rows, codes)).toEqual([
      { period: "2026-01", A: 12, B: 8 },
      { period: "2026-02", A: null, B: null },
      { period: "2026-03", A: 0, B: null },
    ]);
    expect(rows[0].period).toBe("2026-03");
  });

  it("uses each series' own observation grid for deltas and labels an earlier last disclosure", () => {
    const rows = [
      { period: "2026-01", bank_type_code: "A", value: 10 },
      { period: "2026-01", bank_type_code: "B", value: 20 },
      { period: "2026-02", bank_type_code: "A", value: null },
      { period: "2026-02", bank_type_code: "B", value: 18 },
      { period: "2026-03", bank_type_code: "A", value: 12 },
      { period: "2026-03", bank_type_code: "B", value: null },
    ];
    expect(sectorLatestValues(rows, ["A", "B", "C"], 1)).toEqual([
      { code: "A", value: 12, period: "2026-03", delta: null },
      { code: "B", value: 18, period: "2026-02", delta: -2 },
      { code: "C", value: null, period: null, delta: null },
    ]);
    expect(sectorLatestValues(rows, ["A"], 2)[0].delta).toBe(2);
    // Retain the legacy ChartRow comparison basis when replacing its table.
    expect(sectorLatestValues(rows, ["A"], 1, "published")[0].delta).toBe(2);
  });

  it("does not turn non-finite readings into observations", () => {
    const rows = [{ period: "2026-01", bank_type_code: "A", value: Infinity }];
    expect(pivotSectorTrend(rows, ["A"])[0].A).toBeNull();
    expect(sectorLatestValues(rows, ["A"])[0].value).toBeNull();
  });
});

describe("sector-chart scales", () => {
  it("uses a useful line-chart range without an unsolicited zero baseline", () => {
    const scale = sectorTrendScale([15.5, 16.6, 21.8, 26.4]);
    expect(scale.domain[0]).toBeGreaterThan(0);
    expect(scale.domain[0]).toBeLessThanOrEqual(15.5);
    expect(scale.domain[1]).toBeGreaterThanOrEqual(26.4);
    expect(scale.ticks.every((tick, i, ticks) => i === 0 || tick - ticks[i - 1] === scale.step)).toBe(true);
    expect(scale.ticks.length).toBeLessThanOrEqual(7);
  });

  it("includes supplied thresholds and preserves zero when requested", () => {
    expect(sectorTrendScale([15.5, 21.8], [{ value: 12, label: "Target" }]).domain[0]).toBeLessThanOrEqual(12);
    const scale = sectorTrendScale([15.5, 21.8], [{ value: 100, label: "Reference" }], true);
    expect(scale.domain[0]).toBe(0);
    expect(scale.domain[1]).toBeGreaterThanOrEqual(100);
    expect(sectorTrendScale([-20, -10], [], true).domain[1]).toBe(0);
  });

  it("handles tiny ratios, constant values, negative series and entirely missing observations", () => {
    for (const values of [[0.001, 0.003], [16, 16], [-3, 2], [0, 0]]) {
      const scale = sectorTrendScale(values);
      expect(scale.domain[0]).toBeLessThanOrEqual(Math.min(...values));
      expect(scale.domain[1]).toBeGreaterThanOrEqual(Math.max(...values));
      expect(scale.domain[1]).toBeGreaterThan(scale.domain[0]);
      expect(scale.ticks.every(Number.isFinite)).toBe(true);
    }
    expect(sectorTrendScale([null, NaN, Infinity]).domain).toEqual([0, 1]);
  });

  it("keeps ownership colours independent of weekly/monthly code reuse", () => {
    expect(sectorPaletteIndex("State", 5)).toBe(1);
    expect(sectorPaletteIndex("Domestic", 5)).toBe(sectorPaletteIndex("Private", 2));
    expect(sectorPaletteIndex("Foreign", 1)).toBe(3);
  });
});
