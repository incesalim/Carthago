import { describe, expect, it } from "vitest";
import { bankPeriodWindow } from "./period-window";

describe("Financials and Desk period windows", () => {
  const available = ["2026Q2", "2026Q1", "2025Q4", "2025Q3", "2025Q2", "2025Q1", "2024Q4"];

  it("keeps current-quarter funding available when annual Financials are selected", () => {
    const annual = bankPeriodWindow(available, "annual");
    const quarterly = bankPeriodWindow(available, "quarterly");
    expect(annual.periods).toEqual(["2025Q4", "2024Q4"]);
    expect(annual.queryPeriods).not.toContain("2026Q2");
    // The Desk's deposits/equity/loans must accompany its 2026Q2 assets.
    expect(annual.currentPeriod).toBe("2026Q2");
    expect(annual.currentPeriod).toBe(quarterly.currentPeriod);
    expect(annual.balanceSheetPeriods).toContain("2026Q2");
    expect(annual.balanceSheetPeriods).toContain("2026Q1");
    expect(annual.balanceSheetPeriods).toEqual(quarterly.balanceSheetPeriods);
  });

  it("keeps a new bank's current balance sheet even before its first year end", () => {
    const window = bankPeriodWindow(["2026Q2", "2026Q1"], "annual");
    expect(window.periods).toEqual([]);
    expect(window.queryPeriods).toEqual([]);
    expect(window.currentPeriod).toBe("2026Q2");
    expect(window.balanceSheetPeriods).toEqual(["2026Q2", "2026Q1"]);
  });

  it("does not invent a current period when the selected filing kind is absent", () => {
    expect(bankPeriodWindow([], "annual")).toEqual({ periods: [], currentPeriod: null, queryPeriods: [], balanceSheetPeriods: [] });
  });
});
