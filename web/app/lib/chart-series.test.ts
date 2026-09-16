import { describe, expect, it } from "vitest";
import { chartSeriesIndex, chartSeriesTone } from "./chart-series";

describe("chart identities across sector pages", () => {
  it("uses the bank label when weekly and monthly bulletins reuse a code", () => {
    const monthly = { State: "10006", Domestic: "10005", Foreign: "10007", Participation: "10003", "Dev & Inv": "10004" };
    const weekly = { State: "10004", Domestic: "10003", Foreign: "10005", Participation: "10006", "Dev & Inv": "10007" };
    for (const name of Object.keys(monthly) as Array<keyof typeof monthly>) {
      expect(chartSeriesIndex(weekly[name], 0, name)).toBe(chartSeriesIndex(monthly[name], 5, name));
    }
    expect(chartSeriesIndex("PUBLIC", 0, "Public")).not.toBe(chartSeriesIndex("PRIVATE", 0, "Private"));
  });

  it("preserves product identity across wide stacks, facets and monthly card series", () => {
    expect(chartSeriesIndex("RETAIL", 0, "Retail Cards")).toBe(chartSeriesIndex("CARDS", 3, "Retail Cards"));
    expect(chartSeriesIndex("Housing", 3)).toBe(chartSeriesIndex("HOUSING", 0));
    expect(chartSeriesIndex("Auto", 1)).toBe(chartSeriesIndex("AUTO", 0));
    expect(chartSeriesIndex("Gen. Purpose", 2)).toBe(chartSeriesIndex("GPL", 0));
  });

  it("preserves maturity and currency colors when a range hides another series", () => {
    expect(chartSeriesIndex("maturity_3_6m", 0, "3–6m")).toBe(chartSeriesIndex("maturity_3_6m", 3, "3–6 months"));
    expect(chartSeriesIndex("fx", 0, "Foreign currency")).toBe(chartSeriesIndex("fx", 1, "Foreign currency"));
  });

  it("keeps valuation bases and FX position components distinguishable", () => {
    expect(new Set(["NOMINAL", "FXADJ", "REALFX"].map(key => chartSeriesIndex(key, 0))).size).toBe(3);
    expect(new Set(["On-balance-sheet FX position", "Off-balance-sheet FX position", "Net FX position"].map(label => chartSeriesIndex(label, 0))).size).toBe(3);
  });

  it("retains group and inflation identity in suffixed comparison labels", () => {
    expect(chartSeriesIndex("State ROE", 2)).toBe(chartSeriesIndex("State", 0));
    expect(chartSeriesIndex("Private ROE", 1)).toBe(chartSeriesIndex("Private", 0));
    expect(chartSeriesIndex("CPI 12m-avg", 2)).toBe(chartSeriesIndex("CPI 12m avg", 3));
  });

  it("keeps nested reserve components and SME reference comparisons distinct", () => {
    const reserves = ["Residents FX + gold", "— of which gold", "CBRT net reserves"];
    expect(new Set(reserves.map((name, i) => chartSeriesIndex(name, i))).size).toBe(3);
    expect(chartSeriesIndex("ratio", 0, "NPL ratio by SME size")).not.toBe(chartSeriesIndex("sector", 1, "Total SME NPL ratio"));
    expect(chartSeriesIndex("10001", 0, "FX share")).toBe(chartSeriesIndex("fx", 1, "Foreign currency"));
  });

  it("uses explicit status colors for watchlist and nonperforming stages", () => {
    expect(chartSeriesTone("STAGE2", "Stage 2 (watchlist)")).toBe("warning");
    expect(chartSeriesTone("STAGE3", "Stage 3 (NPL)")).toBe("negative");
    expect(chartSeriesTone("10001", "Sector")).toBeNull();
  });
});
