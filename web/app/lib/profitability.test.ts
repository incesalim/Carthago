import { describe, expect, it } from "vitest";
import {
  RECONCILE_TOLERANCE,
  avgStock,
  bridge,
  costIncome,
  deCumulate,
  engine,
  type BsRow,
  type PnlRow,
} from "./profitability";

const T = 1e6; // ₺ trn → the ₺-thousand units the tables store

/** Real shape: the statement is CUMULATIVE, and January is the year to date. */
const pnl = (o: Partial<PnlRow> & { year: number; month: number }): PnlRow => ({
  dep_int: null, nii: null, prov: null, fees: null,
  opex: null, other: null, tax: null, net: null,
  ...o,
});

describe("deCumulate", () => {
  it("treats January as the year to date and subtracts thereafter", () => {
    const rows = [
      pnl({ year: 2026, month: 1, net: 0.09 * T }),
      pnl({ year: 2026, month: 2, net: 0.17 * T }),
      pnl({ year: 2026, month: 3, net: 0.29 * T }),
    ];
    expect(deCumulate(rows, "net").map((p) => p.value)).toEqual([
      expect.closeTo(0.09, 6),
      expect.closeTo(0.08, 6),
      expect.closeTo(0.12, 6),
    ]);
  });

  it("resets across the year boundary — December's YTD is not January's base", () => {
    const rows = [
      pnl({ year: 2025, month: 12, net: 0.94 * T }),
      pnl({ year: 2026, month: 1, net: 0.09 * T }),
    ];
    const out = deCumulate(rows, "net");
    // January must be 0.09, NOT 0.09 − 0.94
    expect(out.at(-1)!.value).toBeCloseTo(0.09, 6);
  });

  it("drops a month whose predecessor is missing rather than inventing one", () => {
    const rows = [
      pnl({ year: 2026, month: 1, net: 0.09 * T }),
      pnl({ year: 2026, month: 3, net: 0.29 * T }), // February absent
    ];
    expect(deCumulate(rows, "net").map((p) => p.period)).toEqual(["2026-01"]);
  });
});

describe("bridge", () => {
  const rows = [
    pnl({ year: 2026, month: 4, nii: 0.5 * T, prov: 0.1 * T, fees: 0.3 * T,
          opex: 0.4 * T, other: -0.05 * T, tax: 0.05 * T, net: 0.2 * T }),
    // May, cumulative: the month itself is nii .206, prov .044, fees .177,
    // opex .209, other −.054, tax .017 → net .059
    pnl({ year: 2026, month: 5, nii: 0.706 * T, prov: 0.144 * T, fees: 0.477 * T,
          opex: 0.609 * T, other: -0.104 * T, tax: 0.067 * T, net: 0.259 * T }),
  ];

  it("de-cumulates the month and reconciles to the REPORTED net line", () => {
    const b = bridge(rows)!;
    expect(b.period).toBe("2026-05");
    expect(b.nii).toBeCloseTo(0.206, 6);
    expect(b.opex).toBeCloseTo(-0.209, 6);
    expect(b.other).toBeCloseTo(-0.054, 6);
    expect(b.net).toBeCloseTo(0.059, 6);
    expect(b.gap).toBeCloseTo(0, 6);
    expect(b.reconciles).toBe(true);
  });

  it("FAILS LOUDLY when the parts stop summing to the reported total", () => {
    // BDDK renumbers a line → opex lands somewhere else → the sum drifts
    const broken = rows.map((r) =>
      r.month === 5 ? { ...r, opex: 0.309 * T } : r,
    );
    const b = bridge(broken)!;
    expect(b.reconciles).toBe(false);
    expect(Math.abs(b.gap)).toBeGreaterThan(RECONCILE_TOLERANCE);
  });
});

describe("engine", () => {
  // 36% of the base is demand and pays nothing; the sector pays 33% on the rest.
  const bs: BsRow[] = Array.from({ length: 13 }, (_, i) => ({
    year: 2026, month: i + 1,
    demand: 10 * T, time_dep: 20 * T, total_dep: 30 * T, equity: 4 * T,
  }));
  const p: PnlRow[] = [
    pnl({ year: 2026, month: 12, dep_int: 6.6 * T, net: 1 * T }), // 6.6 ÷ 20 = 33%
  ];

  it("prices the free book at the rate the sector pays everyone else", () => {
    const e = engine(p, bs).at(-1)!;
    expect(e.demandShare).toBeCloseTo(33.33, 1); // 10 of 30
    expect(e.paidOnTime).toBeCloseTo(33, 1);     // 6.6 ÷ 20
    expect(e.blended).toBeCloseTo(22, 1);        // 6.6 ÷ 30
    expect(e.free).toBeCloseTo(11, 1);
    expect(e.worth).toBeCloseTo(3.3, 2);         // 33% × 10trn
    expect(e.ratio).toBeCloseTo(3.3, 1);         // worth ÷ 1trn of profit
  });

  it("expresses the counterfactual as a COST in pp of the published ROE", () => {
    const e = engine(p, bs).at(-1)!;
    // ₺3.3trn against ₺4trn of equity = 82.5pp — applied to whatever ROE the
    // source publishes, never a home-made ROE of our own.
    expect(e.roeCost).toBeCloseTo(82.5, 1);
  });

  it("skips a month it cannot form honestly", () => {
    expect(engine(p, [])).toHaveLength(0);
  });
});

describe("avgStock / costIncome", () => {
  it("averages the trailing window", () => {
    const bs: BsRow[] = [
      { year: 2026, month: 1, demand: null, time_dep: null, total_dep: null, equity: 2 * T },
      { year: 2026, month: 2, demand: null, time_dep: null, total_dep: null, equity: 4 * T },
    ];
    expect(avgStock(bs, "2026-02", "equity")).toBeCloseTo(3, 6);
  });

  it("computes cost ÷ income from the annualized YTD", () => {
    const rows = [pnl({ year: 2026, month: 6, nii: 0.6 * T, fees: 0.4 * T, opex: 0.5 * T })];
    // annualization cancels in the ratio: 0.5 ÷ (0.6 + 0.4) = 50%
    expect(costIncome(rows)[0].value).toBeCloseTo(50, 6);
  });
});
