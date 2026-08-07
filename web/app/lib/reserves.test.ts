/**
 * The reserve buffer is derived, not published, and TWO pages print it
 * (/liquidity's decomposition chart and /economy's vitals cell). That is exactly
 * the shape of thing that drifts silently, so the arithmetic is pinned here.
 *
 * The case that matters most is the LAST one: before this module existed, a week
 * with no reserve-template row was scored as though the CBRT owed nothing
 * forward, which reported its own FX as larger than it was by the whole swap
 * book. "Missing" and "zero" are different facts and the test says so.
 */
import { describe, expect, it } from "vitest";
import { importCoverMonths, reserveBuffer } from "./reserves";
import { type EvdsRow } from "./metrics";

const rows = (...pairs: [string, number][]): EvdsRow[] =>
  pairs.map(([period_date, value]) => ({ period_date, value }));

/**
 * One clean week. BL054/BL122 are TL thousand; at USD/TRY 40 the net position is
 * (4.4e9 − 0.4e9) / 40 / 1e6 = $100bn. Gross is USD m → $150bn. K15 is published
 * negative in USD m, so |−30,000| / 1000 = $30bn of swaps → own = $70bn.
 */
const base = {
  "TP.BL054": rows(["2026-01-09", 4.4e9]),
  "TP.BL122": rows(["2026-01-09", 0.4e9]),
  "TP.AB.TOPLAM": rows(["2026-01-09", 150_000]),
  "TP.DK.USD.A": rows(["2026-01-09", 40]),
  "TP.DOVVARNC.K15": rows(["2026-01-01", -30_000]),
};

describe("reserveBuffer", () => {
  it("derives gross, net and net-excluding-swaps in USD bn", () => {
    const b = reserveBuffer(base);
    expect(b.points).toHaveLength(1);
    expect(b.latest?.gross).toBeCloseTo(150, 6);
    expect(b.latest?.net).toBeCloseTo(100, 6);
    expect(b.latest?.own).toBeCloseTo(70, 6);
    expect(b.swapStock).toBeCloseTo(30, 6);
    expect(b.banksFx).toBeCloseTo(50, 6);
  });

  it("takes the swap position from the nearest EARLIER month, not the nearest", () => {
    // A February template row must not price a January week: the reserve
    // template is a month-end stock, so stepping forward would apply a figure
    // that did not exist yet.
    const b = reserveBuffer({
      ...base,
      "TP.DOVVARNC.K15": rows(["2026-01-01", -30_000], ["2026-02-01", -90_000]),
    });
    expect(b.latest?.own).toBeCloseTo(70, 6);
  });

  it("uses the deeper override when the short window starts before the template", () => {
    const short = { ...base, "TP.DOVVARNC.K15": rows(["2026-02-01", -90_000]) };
    // Without the override the week is unscorable and drops out entirely.
    expect(reserveBuffer(short).points).toHaveLength(0);
    // With it, the earlier monthly row resolves the step and the week survives.
    const deep = reserveBuffer(short, rows(["2025-12-01", -30_000], ["2026-02-01", -90_000]));
    expect(deep.points).toHaveLength(1);
    expect(deep.latest?.own).toBeCloseTo(70, 6);
  });

  it("counts the weeks the CBRT's own FX sat below zero", () => {
    const b = reserveBuffer({
      "TP.BL054": rows(["2026-01-09", 4.4e9], ["2026-01-16", 4.4e9]),
      "TP.BL122": rows(["2026-01-09", 0.4e9], ["2026-01-16", 0.4e9]),
      "TP.AB.TOPLAM": rows(["2026-01-09", 150_000], ["2026-01-16", 150_000]),
      "TP.DK.USD.A": rows(["2026-01-09", 40], ["2026-01-16", 40]),
      // $120bn of swaps against $100bn net → own = −$20bn.
      "TP.DOVVARNC.K15": rows(["2026-01-01", -30_000], ["2026-01-15", -120_000]),
    });
    expect(b.points.map((p) => Math.round(p.own))).toEqual([70, -20]);
    expect(b.weeksOwnNegative).toBe(1);
  });

  it("DROPS a week with no template row rather than scoring it as zero swaps", () => {
    // The regression this module was extracted to stop: treating a missing K15
    // as "no swaps" reported own = net = $100bn, overstating the CBRT's own FX
    // by the entire swap book. Absent is not zero.
    const b = reserveBuffer({ ...base, "TP.DOVVARNC.K15": [] });
    expect(b.points).toHaveLength(0);
    expect(b.latest).toBeNull();
    expect(b.swapStock).toBeNull();
  });

  it("drops a week missing any leg instead of carrying a partial figure", () => {
    for (const missing of ["TP.BL122", "TP.AB.TOPLAM", "TP.DK.USD.A"]) {
      expect(reserveBuffer({ ...base, [missing]: [] }).points).toHaveLength(0);
    }
  });
});

describe("importCoverMonths", () => {
  it("expresses gross reserves as months of the goods import bill", () => {
    // $150bn against a $360bn annual bill = $30bn a month = 5 months.
    expect(importCoverMonths(150, 360)).toBeCloseTo(5, 6);
  });

  it("returns null rather than a ratio against a missing or empty bill", () => {
    expect(importCoverMonths(150, null)).toBeNull();
    expect(importCoverMonths(null, 360)).toBeNull();
    expect(importCoverMonths(150, 0)).toBeNull();
  });
});
