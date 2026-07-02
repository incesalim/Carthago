import { describe, expect, it } from "vitest";
import { computeWeeklyGrowth, type WeeklyGrowthInput } from "./weekly-growth";

/** Build a weekly series of consecutive Fridays starting at `start`. */
function fridays(start: string, n: number): string[] {
  const out: string[] = [];
  const d = new Date(start + "T00:00:00Z");
  for (let i = 0; i < n; i++) {
    out.push(d.toISOString().slice(0, 10));
    d.setUTCDate(d.getUTCDate() + 7);
  }
  return out;
}

function rowsFor(
  bank: string,
  dates: string[],
  valueAt: (i: number) => number | null,
): WeeklyGrowthInput[] {
  return dates.map((period, i) => ({
    period,
    bank_type_code: bank,
    value: valueAt(i),
  }));
}

describe("computeWeeklyGrowth", () => {
  it("computes plain YoY on a complete 52-week series", () => {
    // 1% weekly compounding → 52w growth = 1.01^52 - 1
    const dates = fridays("2024-01-05", 105);
    const rows = rowsFor("10001", dates, (i) => 100 * Math.pow(1.01, i));
    const out = computeWeeklyGrowth(rows, 52, dates[52]);
    expect(out).toHaveLength(53);
    for (const p of out) {
      expect(p.value).toBeCloseTo((Math.pow(1.01, 52) - 1) * 100, 6);
    }
  });

  it("does not stretch the window across a gap in one group (SME regression)", () => {
    // Reproduce the private-bank SME shape: 13 consecutive weeks missing.
    // With row-offset LAG the first post-gap point compared against a value
    // 65 weeks old; date-aware pairing must still find the exact 52w base
    // (the gap is shorter than the window) and report true YoY.
    const dates = fridays("2024-01-05", 105);
    const gapStart = 60;
    const rows = rowsFor("10003", dates, (i) =>
      i >= gapStart && i < gapStart + 13 ? null : 100 * Math.pow(1.01, i),
    );
    const out = computeWeeklyGrowth(rows, 52, dates[52]);
    const byPeriod = new Map(out.map((p) => [p.period, p.value]));
    // In-gap weeks emit nothing.
    for (let i = gapStart; i < gapStart + 13; i++) {
      expect(byPeriod.has(dates[i])).toBe(false);
    }
    // First post-gap week: exact 52w base exists → true YoY, not 65w growth.
    const firstAfter = dates[gapStart + 13];
    expect(byPeriod.get(firstAfter)).toBeCloseTo((Math.pow(1.01, 52) - 1) * 100, 6);
  });

  it("tolerates a single skipped holiday week via ±1w and re-annualizes", () => {
    const dates = fridays("2024-01-05", 105);
    const holiday = 10; // year-ago base for dates[62] is missing
    const rows = rowsFor("10001", dates, (i) =>
      i === holiday ? null : 100 * Math.pow(1.01, i),
    );
    const out = computeWeeklyGrowth(rows, 52, dates[52]);
    const byPeriod = new Map(out.map((p) => [p.period, p.value]));
    // Falls back to the 53w-old base, annualized by 364/371.
    const expected = (Math.pow(Math.pow(1.01, 53), 364 / 371) - 1) * 100;
    expect(byPeriod.get(dates[holiday + 52])).toBeCloseTo(expected, 6);
  });

  it("emits nothing before the cutoff and skips non-positive bases", () => {
    const dates = fridays("2024-01-05", 60);
    const rows = rowsFor("10001", dates, (i) => (i === 0 ? 0 : 100 + i));
    const out = computeWeeklyGrowth(rows, 4, dates[55]);
    expect(out.every((p) => p.period >= dates[55])).toBe(true);
    // A zero base 4 weeks earlier must be skipped, not divided by.
    const zeroBased = computeWeeklyGrowth(rows, 4, dates[0]);
    expect(zeroBased.find((p) => p.period === dates[4])).toBeUndefined();
  });
});
