import { describe, expect, it } from "vitest";
import { alignLatest, mixedCadence, slowestCadence } from "./cadence";

describe("cadence contract", () => {
  it("distinguishes observation cadence from a shared calculation window", () => {
    expect(mixedCadence([{ cadence: "weekly" }, { cadence: "weekly" }])).toBe(false);
    expect(mixedCadence([{ cadence: "weekly" }, { cadence: "monthly" }])).toBe(true);
    expect(slowestCadence([{ cadence: "daily" }, { cadence: "quarterly" }, { cadence: "weekly" }]))
      .toBe("quarterly");
  });

  it("aligns unlike-frequency series to the latest common cutoff", () => {
    const aligned = alignLatest([
      [
        { period: "2026-05-29", value: 10 },
        { period: "2026-06-05", value: 11 },
        { period: "2026-06-12", value: 12 },
      ],
      [
        { period: "2026-04-30", value: 20 },
        { period: "2026-05-31", value: 21 },
      ],
    ]);

    expect(aligned?.asOf).toBe("2026-05-31");
    expect(aligned?.values.map((row) => row?.value)).toEqual([10, 21]);
  });

  it("preserves missingness instead of inventing a comparable value", () => {
    expect(alignLatest([[{ period: "2026-05", value: null }], [{ period: "2026-05", value: 2 }]]))
      .toBeNull();
    expect(alignLatest([])).toBeNull();
  });
});
