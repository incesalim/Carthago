import { describe, expect, it } from "vitest";
import { problemCoverageSeries, type StageAggRow } from "./credit-risk";

/**
 * The bug this pins (2026-07-13 sector-page audit, finding 5): `/asset-quality`'s
 * "Cover on the problem book" vital printed provisions ÷ (Stage 2 + Stage 3) —
 * a coverage ratio in the 70s — over a sparkline of the Stage-2 SHARE of gross
 * loans, around 10%. Headline and mark were different quantities on different
 * axes, so the trend a reader took from the picture was not the trend of the
 * number above it.
 */
const row = (o: Partial<StageAggRow> = {}): StageAggRow => ({
  period: "2026Q1",
  s2: 1000,
  s3: 300,
  total: 10_000,
  ecl2: 100,
  ecl3: 200,
  ecl_total: 350,
  n: 30,
  ...o,
});

describe("problemCoverageSeries", () => {
  it("covers the whole problem book, not one stage", () => {
    // (100 + 200) / (1000 + 300) = 23.08%
    expect(problemCoverageSeries([row()])[0].value).toBeCloseTo(23.077, 3);
  });

  it("is not the Stage-2 share — the series that used to be drawn here", () => {
    const cov = problemCoverageSeries([row()])[0].value;
    const stage2Share = (1000 / 10_000) * 100;
    expect(cov).not.toBeCloseTo(stage2Share, 1);
  });

  it("takes ECL magnitudes — filers store provisions signed either way", () => {
    const signed = problemCoverageSeries([row({ ecl2: -100, ecl3: -200 })])[0].value;
    expect(signed).toBeCloseTo(23.077, 3);
  });

  it("drops a quarter too thin to aggregate, or missing a leg", () => {
    expect(problemCoverageSeries([row({ n: 4 })])).toHaveLength(0);
    expect(problemCoverageSeries([row({ ecl3: null })])).toHaveLength(0);
    expect(problemCoverageSeries([row({ s2: 0, s3: 0 })])).toHaveLength(0);
  });

  it("gates on `total` like stageLadder, so the last point IS the headline", () => {
    // The ratio never divides by `total` — but the vital's printed value comes
    // from stageLadder, which skips a quarter without one. Diverging filters put
    // a different quarter at the end of the sparkline than in the headline.
    expect(problemCoverageSeries([row({ total: null })])).toHaveLength(0);
    expect(problemCoverageSeries([row({ total: 0 })])).toHaveLength(0);
  });

  it("keeps periods in source order, one point each", () => {
    const out = problemCoverageSeries([row({ period: "2025Q4" }), row({ period: "2026Q1" })]);
    expect(out.map((r) => r.period)).toEqual(["2025Q4", "2026Q1"]);
    expect(out.every((r) => r.bank_type_code === "PROBLEM_COV")).toBe(true);
  });
});
