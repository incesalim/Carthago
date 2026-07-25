import { describe, expect, it } from "vitest";
import { realRate, nominalVsReal } from "./real-terms";

/**
 * The bug this pins (2026-07-13 sector-page audit, finding 3): `/` computed
 * "real" by subtracting CPI — the g−π shortcut `series.ts` explicitly forbids —
 * on the two figures the landing page leads with. At a ~32% CPI that is 1.2–1.8pp
 * adrift, and it made `/`'s "credit in real terms" disagree with `/credit`'s own
 * Fisher-deflated line.
 */
describe("realRate", () => {
  it("is Fisher, not the subtraction", () => {
    // the audit's case: credit +37.5% nominal against 32.6% CPI
    expect(realRate(37.5, 32.6)).toBeCloseTo(3.695, 3);
    expect(realRate(37.5, 32.6)).not.toBeCloseTo(37.5 - 32.6, 1);
  });

  it("agrees with the series form on the same inputs", () => {
    const viaSeries = nominalVsReal(
      [{ period: "2026-05", value: 24.7 }],
      new Map([["2026-05", 32.1]]),
    ).find((r) => r.bank_type_code === "REAL")!.value;
    expect(realRate(24.7, 32.1)).toBeCloseTo(viaSeries, 10);
  });

  it("keeps the sign of the real outcome", () => {
    expect(realRate(24.7, 32.1)).toBeLessThan(0); // ROE below the inflation hurdle
    expect(realRate(40, 32.1)).toBeGreaterThan(0);
    expect(realRate(32.1, 32.1)).toBeCloseTo(0, 10);
  });

  it("is always shallower than the shortcut when inflation is positive", () => {
    // why the landing page over-stated both the loss and the gain
    for (const [g, pi] of [[24.7, 32.1], [37.5, 32.6], [10, 5]] as const) {
      expect(Math.abs(realRate(g, pi)!)).toBeLessThan(Math.abs(g - pi));
    }
  });

  it("returns null rather than a fabricated number", () => {
    expect(realRate(null, 32)).toBeNull();
    expect(realRate(24, null)).toBeNull();
    expect(realRate(24, -100)).toBeNull(); // (1+π) = 0
  });
});
