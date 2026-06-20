import { describe, expect, it } from "vitest";
import { lowerBound } from "./chart-range";

describe("lowerBound", () => {
  it("shifts the year for trailing windows, keeping the date width", () => {
    expect(lowerBound("2026-06-20", "1Y")).toBe("2025-06-20");
    expect(lowerBound("2026-06-20", "3Y")).toBe("2023-06-20");
    expect(lowerBound("2026-06-20", "5Y")).toBe("2021-06-20");
    expect(lowerBound("2026-06", "1Y")).toBe("2025-06");
  });

  it("YTD is January of the latest data year", () => {
    expect(lowerBound("2026-06-20", "YTD")).toBe("2026-01");
    expect(lowerBound("2026-06", "YTD")).toBe("2026-01");
  });

  it("All (or empty data) has no lower bound", () => {
    expect(lowerBound("2026-06", "All")).toBe("");
    expect(lowerBound("", "1Y")).toBe("");
  });

  it("cuts correctly via lexicographic compare across cadences", () => {
    const lb = lowerBound("2026-06-20", "1Y"); // "2025-06-20"
    expect("2025-06-20" >= lb).toBe(true); // exactly one year ago is included
    expect("2025-06-19" >= lb).toBe(false);
    expect("2026-01-01" >= lb).toBe(true);
    const ytd = lowerBound("2026-06-20", "YTD"); // "2026-01"
    expect("2026-01-15" >= ytd).toBe(true);
    expect("2025-12-31" >= ytd).toBe(false);
  });

  it("falls back to no bound for a non-ISO / unparseable period", () => {
    expect(lowerBound("FY2026", "1Y")).toBe("");
  });
});
