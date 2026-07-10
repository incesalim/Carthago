import { describe, expect, it } from "vitest";
import { prettyPeriod, seriesFinding } from "./chart-findings";

const mk = (values: (number | null)[], startYear = 2025, startMonth = 4) =>
  values.map((value, i) => {
    const m = startMonth + i;
    const year = startYear + Math.floor((m - 1) / 12);
    const month = ((m - 1) % 12) + 1;
    return { period: `${year}-${String(month).padStart(2, "0")}`, value };
  });

describe("prettyPeriod", () => {
  it("formats monthly and quarterly period keys", () => {
    expect(prettyPeriod("2026-04")).toBe("Apr 2026");
    expect(prettyPeriod("2026-04-01")).toBe("Apr 2026");
    expect(prettyPeriod("2026Q1")).toBe("Q1 2026");
    expect(prettyPeriod("whatever")).toBe("whatever");
  });
});

describe("seriesFinding", () => {
  it("returns null on insufficient data", () => {
    expect(seriesFinding([], { noun: "X" })).toBeNull();
    expect(seriesFinding(mk([16.4]), { noun: "X" })).toBeNull();
    expect(seriesFinding(mk([null, null]), { noun: "X" })).toBeNull();
  });

  it("describes a fall with the change over the window", () => {
    // 13 points, 17.4 → 16.4 over 12 months (Apr 2025 → Apr 2026).
    const s = mk([17.4, 17.5, 18.0, 18.2, 18.3, 18.5, 18.9, 19.2, 19.7, 16.8, 16.8, 16.5, 16.4]);
    expect(seriesFinding(s, { noun: "Capital adequacy" })).toBe(
      "Capital adequacy eased to 16.4% in Apr 2026 (−1.0pp over 12m)",
    );
  });

  it("uses the stronger verb for a sharp move", () => {
    const s = mk([20.0, 19.0, 18.0, 17.0, 16.0, 15.0, 14.5, 14.0, 13.5, 13.0, 12.5, 12.2, 12.0]);
    expect(seriesFinding(s, { noun: "The ratio" })).toContain("fell to 12.0%");
  });

  it("reads flat series as holding, without a delta clause", () => {
    const s = mk([2.6, 2.61, 2.62, 2.63, 2.64, 2.65]);
    // Δ=0.05 < flat band 0.15 → holds, no parenthetical.
    expect(seriesFinding(s, { noun: "NPL" })).toBe("NPL holds at 2.7% in Sep 2025");
  });

  it("describes a rise, skipping the window suffix when history is shorter", () => {
    const s = mk([3.7, 4.0, 4.4, 4.7, 5.0]);
    expect(seriesFinding(s, { noun: "NIM", decimals: 2 })).toBe(
      "NIM climbed to 5.00% in Aug 2025 (+1.30pp)",
    );
  });

  it("skips null gaps when picking level and prior", () => {
    const s = mk([10.0, null, 11.0, null, 12.0]);
    expect(seriesFinding(s, { noun: "X", window: 2 })).toBe(
      "X climbed to 12.0% in Aug 2025 (+2.0pp over 2m)",
    );
  });
});
