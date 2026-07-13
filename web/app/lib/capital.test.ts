import { describe, expect, it } from "vitest";
import {
  capitalStack,
  decompose12m,
  detectStep,
  postStepDrift,
  quartersToFloor,
  type Pt,
} from "./capital";

/** The real thing: sector CAR, Jun 2025 → May 2026, with the January step. */
const CAR: Pt[] = [
  { period: "2025-05", value: 17.51 },
  { period: "2025-06", value: 17.6 },
  { period: "2025-07", value: 17.8 },
  { period: "2025-08", value: 18.2 },
  { period: "2025-09", value: 18.55 },
  { period: "2025-10", value: 18.9 },
  { period: "2025-11", value: 19.3 },
  { period: "2025-12", value: 19.69 },
  { period: "2026-01", value: 16.77 }, // ← the step
  { period: "2026-02", value: 16.8 },
  { period: "2026-03", value: 16.52 },
  { period: "2026-04", value: 16.37 },
  { period: "2026-05", value: 16.34 },
];

describe("detectStep", () => {
  it("finds the January break and calls it a break", () => {
    const s = detectStep(CAR)!;
    expect(s.period).toBe("2026-01");
    expect(s.delta).toBeCloseTo(-2.92, 2);
    expect(s.isBreak).toBe(true);
  });

  it("does NOT call a smooth series a break", () => {
    const smooth: Pt[] = Array.from({ length: 13 }, (_, i) => ({
      period: `2026-${String(i + 1).padStart(2, "0")}`,
      value: 16 - i * 0.1,
    }));
    expect(detectStep(smooth)!.isBreak).toBe(false);
  });

  it("ignores nulls and short series", () => {
    expect(detectStep([{ period: "a", value: null }])).toBeNull();
  });
});

describe("decompose12m", () => {
  it("splits the year into the step and everything else", () => {
    const d = decompose12m(CAR, "2026-01")!;
    expect(d.total).toBeCloseTo(-1.17, 2); // 17.51 → 16.34
    expect(d.step).toBeCloseTo(-2.92, 2);
    // the point of the whole exercise: ex-step, the year ADDED capital
    expect(d.rest).toBeCloseTo(1.75, 2);
    expect(d.rest).toBeGreaterThan(0);
  });

  it("counts no step when the break falls outside the window", () => {
    const d = decompose12m(CAR, "2024-03")!;
    expect(d.step).toBe(0);
    expect(d.rest).toBeCloseTo(d.total, 6);
  });
});

describe("postStepDrift", () => {
  it("measures the slope only after the break", () => {
    const p = postStepDrift(CAR, "2026-01")!;
    expect(p.months).toBe(4); // Jan → May
    expect(p.change).toBeCloseTo(-0.43, 2);
    expect(p.perYear).toBeCloseTo(-1.29, 2);
  });
});

describe("quartersToFloor", () => {
  it("sizes the buffer against a slope", () => {
    expect(quartersToFloor(16.34, -1.29)).toBeCloseTo(13.5, 1);
  });
  it("is null when the buffer is not eroding", () => {
    expect(quartersToFloor(16.34, 0.5)).toBeNull();
  });
});

describe("capitalStack", () => {
  it("derives AT1 and Tier-2 as the gaps, summing back to CAR", () => {
    const [s] = capitalStack([
      { period: "2026Q1", bank_type_code: "CET1", value: 11.79 },
      { period: "2026Q1", bank_type_code: "TIER1", value: 13.46 },
      { period: "2026Q1", bank_type_code: "CAR", value: 16.02 },
    ]);
    expect(s.at1).toBeCloseTo(1.67, 2);
    expect(s.t2).toBeCloseTo(2.56, 2);
    expect(s.cet1 + s.at1 + s.t2).toBeCloseTo(s.car, 6);
  });

  it("drops a quarter missing a component rather than inventing one", () => {
    expect(
      capitalStack([{ period: "2026Q1", bank_type_code: "CET1", value: 11.79 }]),
    ).toHaveLength(0);
  });
});
