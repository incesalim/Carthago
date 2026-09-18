import { describe, expect, it } from "vitest";
import { trendDeltas, type TrendPoint } from "./coverage";

const daysAgo = (n: number) => new Date(Date.UTC(2026, 8, 16) - n * 24 * 3600 * 1000).toISOString();

const point = (n: number, error: number, missing: number): TrendPoint => ({
  checked_at: daysAgo(n), ok: 100, manual: 0, error, missing, not_expected: 50, lanes: 20,
});

describe("trendDeltas", () => {
  it("answers nothing without a baseline at least 6 days older", () => {
    expect(trendDeltas([])).toEqual([]);
    expect(trendDeltas([point(0, 5, 2)])).toEqual([]);
    // Two snapshots 7d apart but only 1 day between the pair — no baseline.
    expect(trendDeltas([point(1, 5, 2), point(8, 5, 2)])).not.toEqual([]);
    expect(trendDeltas([point(0, 5, 2), point(3, 9, 4)])).toEqual([]);
  });

  it("picks the OLDEST point at least 6 days back, not the newest one", () => {
    // latest(0) → 6d(9) → 8d(41): the baseline must be the 8d point, so the
    // delta says the fleet improved, not "worsened since last week".
    const deltas = trendDeltas([point(0, 12, 6), point(6, 9, 8), point(8, 41, 12)]);
    expect(deltas).toEqual([
      { metric: "error", from: 41, to: 12, days: 8 },
      { metric: "missing", from: 12, to: 6, days: 8 },
    ]);
  });

  it("keeps direction unsigned — the component tones it", () => {
    const worsening = trendDeltas([point(0, 30, 3), point(9, 10, 9)]);
    expect(worsening).toEqual([
      { metric: "error", from: 10, to: 30, days: 9 },
      { metric: "missing", from: 9, to: 3, days: 9 },
    ]);
  });

  it("ignores unparseable timestamps rather than inventing a baseline", () => {
    expect(trendDeltas([
      { ...point(0, 5, 2) },
      { ...point(9, 5, 2), checked_at: "not-a-date" },
    ])).toEqual([]);
  });
});
