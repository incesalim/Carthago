import { describe, expect, it } from "vitest";
import {
  ordOf,
  periodFromOrd,
  singleQuarter,
  ttmEndingAt,
  yoyPct,
} from "./period-math";

describe("ordOf / periodFromOrd", () => {
  it("maps quarters to monotonically increasing ordinals", () => {
    expect(ordOf("2024Q4")!).toBeLessThan(ordOf("2025Q1")!);
    expect(ordOf("2025Q1")! + 1).toBe(ordOf("2025Q2")!);
  });

  it("round-trips through periodFromOrd", () => {
    for (const p of ["2022Q1", "2024Q3", "2025Q4", "2026Q1"]) {
      expect(periodFromOrd(ordOf(p)!)).toBe(p);
    }
  });

  it("returns null for non-quarter strings", () => {
    expect(ordOf("2025")).toBeNull();
    expect(ordOf("2025Q5")).toBeNull();
    expect(ordOf("")).toBeNull();
  });
});

describe("singleQuarter", () => {
  // 2025: Q1 YTD 10, Q2 YTD 25, Q3 YTD 25, Q4 YTD 60.
  const ytd = new Map<number, number>([
    [ordOf("2025Q1")!, 10],
    [ordOf("2025Q2")!, 25],
    [ordOf("2025Q3")!, 25],
    [ordOf("2025Q4")!, 60],
  ]);

  it("treats Q1 YTD as a single quarter", () => {
    expect(singleQuarter(ytd, ordOf("2025Q1")!)).toBe(10);
  });

  it("de-cumulates later quarters by subtracting the prior YTD", () => {
    expect(singleQuarter(ytd, ordOf("2025Q2")!)).toBe(15);
    expect(singleQuarter(ytd, ordOf("2025Q3")!)).toBe(0);
    expect(singleQuarter(ytd, ordOf("2025Q4")!)).toBe(35);
  });

  it("returns null when the current or prior YTD is missing", () => {
    expect(singleQuarter(ytd, ordOf("2026Q1")!)).toBeNull(); // current missing
    const onlyQ2 = new Map<number, number>([[ordOf("2025Q2")!, 25]]);
    expect(singleQuarter(onlyQ2, ordOf("2025Q2")!)).toBeNull(); // prior missing
  });
});

describe("ttmEndingAt", () => {
  it("sums the trailing four single quarters", () => {
    // Two full years: 2024 single Qs 5/5/5/5, 2025 single Qs 10/10/10/10.
    // Build YTD maps from those.
    const ytd = new Map<number, number>();
    let acc24 = 0;
    for (let q = 1; q <= 4; q++) { acc24 += 5; ytd.set(ordOf(`2024Q${q}`)!, acc24); }
    let acc25 = 0;
    for (let q = 1; q <= 4; q++) { acc25 += 10; ytd.set(ordOf(`2025Q${q}`)!, acc25); }
    // TTM ending 2025Q4 = the four 2025 single quarters = 40.
    expect(ttmEndingAt(ytd, ordOf("2025Q4")!)).toBe(40);
    // TTM ending 2025Q2 = 2024Q3+2024Q4+2025Q1+2025Q2 = 5+5+10+10 = 30.
    expect(ttmEndingAt(ytd, ordOf("2025Q2")!)).toBe(30);
  });

  it("returns null when any trailing quarter is underivable", () => {
    const ytd = new Map<number, number>([
      [ordOf("2025Q3")!, 25],
      [ordOf("2025Q4")!, 60],
    ]);
    expect(ttmEndingAt(ytd, ordOf("2025Q4")!)).toBeNull();
  });
});

describe("yoyPct", () => {
  it("computes percentage growth against a positive base", () => {
    expect(yoyPct(120, 100)).toBeCloseTo(20);
    expect(yoyPct(80, 100)).toBeCloseTo(-20);
  });

  it("uses the magnitude of a negative base", () => {
    // loss of 100 → profit of 50: (50 - -100)/100 = +150%
    expect(yoyPct(50, -100)).toBeCloseTo(150);
  });

  it("returns null on a zero base or missing operand", () => {
    expect(yoyPct(50, 0)).toBeNull();
    expect(yoyPct(null, 100)).toBeNull();
    expect(yoyPct(50, null)).toBeNull();
    expect(yoyPct(undefined, undefined)).toBeNull();
  });
});
