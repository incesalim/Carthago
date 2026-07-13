import { describe, expect, it } from "vitest";
import { aggregateCapital, type CapRow } from "./audit-ratios";

/**
 * The bug this pins: a bank missing ONE capital component used to add its RWA to
 * every denominator while adding nothing to that component's numerator, which
 * silently understated the ratio. ISCTR (2025Q4, 2026Q1) reports no CET1 while
 * carrying ~10.6% of sector RWA — that dragged the published sector CET1 from
 * 11.79% down to 10.56%.
 */
const row = (o: Partial<CapRow> & { bank_ticker: string; total_rwa: number }): CapRow => ({
  period: "2026Q1",
  cet1_capital: null,
  additional_tier1_capital: null,
  tier1_capital: null,
  total_capital: null,
  ...o,
});

const at = (out: ReturnType<typeof aggregateCapital>, code: string) =>
  out.find((r) => r.bank_type_code === code)?.value;

describe("aggregateCapital", () => {
  it("sums numerator and denominator over the SAME banks, per component", () => {
    const out = aggregateCapital([
      // a complete bank: CET1 10 / RWA 100 = 10%
      row({ bank_ticker: "A", cet1_capital: 10, tier1_capital: 12, total_capital: 16, total_rwa: 100 }),
      // no CET1 and no Tier-1 at all → must not drag CET1 down with its RWA
      row({ bank_ticker: "B", total_capital: 20, total_rwa: 100 }),
    ]);
    expect(at(out, "CET1")).toBeCloseTo(10, 6); // NOT 5 — B's RWA sits out of CET1
    expect(at(out, "CAR")).toBeCloseTo(18, 6); // both banks report total capital
  });

  it("recovers a missing CET1 from Tier-1 − AT1 (the ISCTR case)", () => {
    const out = aggregateCapital([
      row({
        bank_ticker: "ISCTR",
        cet1_capital: null,
        additional_tier1_capital: 22_061_250,
        tier1_capital: 420_695_564,
        total_capital: 515_125_095,
        total_rwa: 3_396_087_828,
      }),
    ]);
    // reproduces the ratio ISCTR prints in its own filing: 11.74%
    expect(at(out, "CET1")).toBeCloseTo(11.74, 2);
    expect(at(out, "TIER1")).toBeCloseTo(12.39, 2);
    expect(at(out, "CAR")).toBeCloseTo(15.17, 2);
  });

  it("drops a bank with no RWA (no ratio can be formed)", () => {
    const out = aggregateCapital([
      row({ bank_ticker: "A", cet1_capital: 10, total_capital: 16, total_rwa: 100 }),
      row({ bank_ticker: "Z", cet1_capital: 999, total_capital: 999, total_rwa: 0 }),
    ]);
    expect(at(out, "CET1")).toBeCloseTo(10, 6);
  });

  it("keeps each period separate and sorted", () => {
    const out = aggregateCapital([
      row({ bank_ticker: "A", period: "2026Q1", cet1_capital: 12, total_capital: 16, total_rwa: 100 }),
      row({ bank_ticker: "A", period: "2025Q4", cet1_capital: 10, total_capital: 15, total_rwa: 100 }),
    ]);
    const cet1 = out.filter((r) => r.bank_type_code === "CET1");
    expect(cet1.map((r) => r.period)).toEqual(["2025Q4", "2026Q1"]);
    expect(cet1.map((r) => r.value)).toEqual([10, 12]);
  });
});
