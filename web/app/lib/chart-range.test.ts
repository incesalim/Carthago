import { describe, expect, it } from "vitest";
import { applicableRanges, lowerBound, DEFAULT_RANGES } from "./chart-range";

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
});

describe("applicableRanges", () => {
  it("drops windows longer than the data span", () => {
    // ~2 years of data → 5Y and 3Y are dead, 1Y is useful.
    const r = applicableRanges("2024-06", "2026-06", DEFAULT_RANGES);
    expect(r).toContain("1Y");
    expect(r).toContain("YTD");
    expect(r).toContain("All");
    expect(r).not.toContain("5Y");
    expect(r).not.toContain("3Y");
  });

  it("does not show a trailing window that duplicates All", () => {
    // Exactly ~5 years → '5Y' would equal 'All', so hide it.
    const r = applicableRanges("2021-06-20", "2026-06-20", DEFAULT_RANGES);
    expect(r).not.toContain("5Y");
    expect(r).toContain("3Y");
    expect(r).toContain("1Y");
  });

  it("keeps every trailing window for a long daily series", () => {
    const r = applicableRanges("2018-01-02", "2026-06-20", DEFAULT_RANGES);
    expect(r).toEqual(DEFAULT_RANGES);
  });

  it("returns the offered ranges unchanged when span is unknown", () => {
    expect(applicableRanges("", "", DEFAULT_RANGES)).toEqual(DEFAULT_RANGES);
  });
});
