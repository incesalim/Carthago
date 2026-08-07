/**
 * The economy transforms, and the forecast scorecard.
 *
 * The scorecard is the part worth pinning: it grades a third party's published
 * baseline against our own series, and the failure mode is not an arithmetic bug
 * but a QUIET one — scoring a full-year forecast against four months of data and
 * printing the answer as though the year were over, or subtracting a
 * central-government forecast from a general-budget actual. Both would look
 * entirely plausible on the page. The tests assert the guards, not just the mean.
 */
import { describe, expect, it } from "vitest";
import {
  BBVA_BASELINE,
  exAnteReal,
  monthlyAverage,
  pctChange,
  rollingSum,
  scoreBaseline,
  yearMean,
  type EconomyData,
  type Point,
} from "./economy-calc";

const pts = (...pairs: [string, number][]): Point[] =>
  pairs.map(([period_date, value]) => ({ period_date, value }));

describe("pctChange", () => {
  it("computes growth over the given lag", () => {
    const out = pctChange(pts(["2026-01-01", 100], ["2026-02-01", 110]), 1);
    expect(out).toHaveLength(1);
    expect(out[0].value).toBeCloseTo(10, 6);
  });

  it("skips a base of zero instead of emitting Infinity", () => {
    expect(pctChange(pts(["2026-01-01", 0], ["2026-02-01", 110]), 1)).toEqual([]);
  });
});

describe("rollingSum", () => {
  it("emits nothing until a full window exists", () => {
    const rows = pts(["2026-01-01", 1], ["2026-02-01", 2], ["2026-03-01", 3]);
    expect(rollingSum(rows, 3).map((p) => p.value)).toEqual([6]);
    expect(rollingSum(rows, 4)).toEqual([]);
  });

  it("rolls the window forward and applies the scale", () => {
    const rows = pts(["2026-01-01", 1000], ["2026-02-01", 2000], ["2026-03-01", 3000]);
    expect(rollingSum(rows, 2, 1 / 1000).map((p) => p.value)).toEqual([3, 5]);
  });
});

describe("monthlyAverage", () => {
  it("collapses a daily series to month-start averages", () => {
    const out = monthlyAverage(
      pts(["2026-01-02", 10], ["2026-01-30", 20], ["2026-02-03", 45]),
    );
    expect(out).toEqual([
      { period_date: "2026-01-01", value: 15 },
      { period_date: "2026-02-01", value: 45 },
    ]);
  });
});

describe("exAnteReal", () => {
  it("compounds rather than subtracting", () => {
    // Fisher: (1.50 / 1.30 − 1) = 15.38%, NOT the 20pp a subtraction would give.
    // At Turkish rate levels the two answers differ by several points, and the
    // gap is widest exactly where the SIGN of the real rate is in question.
    const out = exAnteReal(pts(["2026-01-01", 50]), pts(["2026-01-01", 30]));
    expect(out[0].value).toBeCloseTo(15.3846, 3);
  });

  it("drops a month with no matching expectation", () => {
    expect(exAnteReal(pts(["2026-01-01", 50]), pts(["2026-02-01", 30]))).toEqual([]);
  });
});

describe("yearMean", () => {
  it("returns the mean AND the count behind it", () => {
    const m = yearMean(pts(["2026-01-01", 10], ["2026-02-01", 20], ["2025-12-01", 99]), "2026");
    expect(m).toEqual({ mean: 15, n: 2 });
  });

  it("returns null when the year has no observations", () => {
    expect(yearMean(pts(["2025-01-01", 10]), "2026")).toBeNull();
  });
});

/** Minimal EconomyData carrying only the series the scorecard reads. */
const dataWith = (over: Partial<EconomyData>): EconomyData =>
  ({
    gdpGrowth: [],
    unemployment: [],
    cpiYoY: [],
    fundingMonthly: [],
    usdtry: [],
    eurtry: [],
    caPctGdp: [],
    ...over,
  }) as unknown as EconomyData;

describe("scoreBaseline", () => {
  it("scores a mean row against the forecast and prints the observation count", () => {
    const year = BBVA_BASELINE.forecastYear;
    const d = dataWith({
      cpiYoY: pts([`${year}-01-01`, 30], [`${year}-02-01`, 20]),
    });
    const row = scoreBaseline(d).find((r) => r.label === "Inflation (avg)")!;
    expect(row.realized).toBe("25.0%");
    expect(row.n).toBe(2);
    // Forecast column is 28.0% → realized 25.0 is 3.0 below it.
    expect(row.gap).toBeCloseTo(-3, 6);
    expect(row.note).toBeNull();
  });

  it("never scores an end-of-period row from a partial year", () => {
    const year = BBVA_BASELINE.forecastYear;
    const d = dataWith({ cpiYoY: pts([`${year}-01-01`, 30]) });
    for (const row of scoreBaseline(d).filter((r) => r.label.includes("(eop)"))) {
      expect(row.realized).toBeNull();
      expect(row.gap).toBeNull();
      expect(row.note).toContain("December");
    }
  });

  it("refuses the %-of-GDP budget rows outright — the basis differs", () => {
    // BBVA quotes CENTRAL GOVERNMENT; our 12-month ratio is the GENERAL budget.
    // Subtracting one from the other would print a basis gap as a forecast error.
    const rows = scoreBaseline(dataWith({})).filter((r) => r.label.startsWith("CG "));
    expect(rows).toHaveLength(2);
    for (const row of rows) {
      expect(row.realized).toBeNull();
      expect(row.note).toContain("central govt");
    }
  });

  it("says so when the forecast year has no observations yet", () => {
    const row = scoreBaseline(dataWith({ cpiYoY: pts(["1999-01-01", 5]) })).find(
      (r) => r.label === "Inflation (avg)",
    )!;
    expect(row.realized).toBeNull();
    expect(row.note).toContain("no");
  });

  it("keeps every published row, scorable or not", () => {
    expect(scoreBaseline(dataWith({}))).toHaveLength(BBVA_BASELINE.rows.length);
  });
});
