import { describe, expect, it } from "vitest";
import {
  costOfEquity,
  sustainableGrowth,
  justifiedPB,
  fadedRoe,
  projectPath,
  runValuation,
  regressPbOnRoe,
  mean,
  variance,
  covariance,
  linregBeta,
  type Assumptions,
} from "./valuation";

// A clean, hand-computable base scenario. Individual tests override fields.
function scenario(over: Partial<Assumptions> = {}): Assumptions {
  return {
    b0: 1000,
    roe0: 0.3,
    shares: 1_000_000,
    coe: { rf: 0.2, erp: 0, beta: 0 }, // → COE = 0.20 exactly
    payout: 0.5,
    horizon: 2,
    roeFadeTo: 0.22,
    terminalGrowth: 0.1,
    persistence: 0,
    ddmStage1Years: 3,
    ddmStage1Growth: 0.1,
    ...over,
  };
}

describe("cost of equity (CAPM, nominal TRY)", () => {
  it("builds up rf + β·ERP", () => {
    expect(costOfEquity({ rf: 0.38, erp: 0.055, beta: 1.0 })).toBeCloseTo(0.435, 6);
  });
  it("adds the country risk premium", () => {
    expect(costOfEquity({ rf: 0.38, erp: 0.055, beta: 1.0, crp: 0.02 })).toBeCloseTo(0.455, 6);
  });
});

describe("sustainable growth & justified P/B", () => {
  it("g = ROE × (1 − payout)", () => {
    expect(sustainableGrowth(0.28, 0.35)).toBeCloseTo(0.182, 6);
  });
  it("justified P/B = (ROE − g)/(COE − g)", () => {
    expect(justifiedPB(0.28, 0.182, 0.32)).toBeCloseTo(0.7101449, 5);
  });
  it("returns null when COE ≤ g (unbounded perpetuity)", () => {
    expect(justifiedPB(0.28, 0.182, 0.1)).toBeNull();
    expect(justifiedPB(0.28, 0.182, 0.182)).toBeNull();
  });
});

describe("ROE fade", () => {
  it("glides linearly from roe0 to roeFadeTo over the horizon", () => {
    expect(fadedRoe(0.3, 0.2, 1, 4)).toBeCloseTo(0.275, 6);
    expect(fadedRoe(0.3, 0.2, 4, 4)).toBeCloseTo(0.2, 6);
  });
});

describe("residual-income roll-forward", () => {
  const path = projectPath(scenario(), 0.2);

  it("rolls book forward under clean surplus", () => {
    // Y1: ROE 0.26, NI 260, div 130, endBook 1130; Y2: ROE 0.22 on 1130
    expect(path[0]).toMatchObject({ year: 1, beginBook: 1000 });
    expect(path[0].roe).toBeCloseTo(0.26, 6);
    expect(path[0].netIncome).toBeCloseTo(260, 6);
    expect(path[0].endBook).toBeCloseTo(1130, 6);
    expect(path[1].beginBook).toBeCloseTo(1130, 6);
    expect(path[1].roe).toBeCloseTo(0.22, 6);
    expect(path[1].endBook).toBeCloseTo(1254.3, 6);
  });

  it("discounts residual income at the cost of equity", () => {
    // RI1 = (0.26−0.20)·1000 = 60, DF 1/1.2 → PV 50
    expect(path[0].residualIncome).toBeCloseTo(60, 6);
    expect(path[0].pvResidualIncome).toBeCloseTo(50, 6);
    // RI2 = (0.22−0.20)·1130 = 22.6, DF 1/1.44 → PV 15.694444
    expect(path[1].residualIncome).toBeCloseTo(22.6, 6);
    expect(path[1].pvResidualIncome).toBeCloseTo(15.694444, 5);
  });
});

describe("runValuation — residual income terminal modes", () => {
  it("ω=0 uses a Gordon growing perpetuity (hand-computed)", () => {
    const r = runValuation(scenario());
    expect(r.coe).toBeCloseTo(0.2, 6);
    expect(r.sumPvExplicit).toBeCloseTo(65.694444, 4);
    // riTerminal = (0.22−0.20)·1254.3 = 25.086; TV = /0.10 = 250.86; PV ×1/1.44
    expect(r.terminalValueRI).toBeCloseTo(250.86, 4);
    expect(r.pvTerminalRI).toBeCloseTo(174.208333, 3);
    expect(r.fairValueRI).toBeCloseTo(1239.902778, 3);
    expect(r.impliedPB).toBeCloseTo(1.239903, 4);
    expect(r.warnings).toHaveLength(0);
  });

  it("ω>0 decays abnormal earnings (Ohlson AR(1))", () => {
    const r = runValuation(scenario({ persistence: 0.6 }));
    // TV = 25.086 / (1 + 0.20 − 0.6) = 41.81; PV ×1/1.44 = 29.034722
    expect(r.terminalValueRI).toBeCloseTo(41.81, 4);
    expect(r.pvTerminalRI).toBeCloseTo(29.034722, 3);
    expect(r.fairValueRI).toBeCloseTo(1094.729167, 3);
  });
});

describe("runValuation — two-stage DDM", () => {
  it("equals the closed-form Gordon value when g1 = g_T", () => {
    // d0 = 0.30·1000·0.50 = 150; g = 0.10; COE 0.20 → V = D1/(r−g) = 165/0.10
    const r = runValuation(scenario());
    expect(r.fairValueDDM).toBeCloseTo(1650, 4);
  });
});

describe("runValuation — degenerate guards", () => {
  it("omits the terminal value and warns when COE ≤ g_T", () => {
    const r = runValuation(scenario({ coe: { rf: 0.05, erp: 0, beta: 0 }, terminalGrowth: 0.1 }));
    expect(r.coe).toBeCloseTo(0.05, 6);
    expect(r.terminalValueRI).toBe(0);
    expect(r.warnings.some((w) => w.includes("Residual income"))).toBe(true);
    expect(r.warnings.some((w) => w.includes("DDM"))).toBe(true);
  });

  it("returns null per-share figures when shares are missing", () => {
    const r = runValuation(scenario({ shares: 0 }));
    expect(r.perShareRI).toBeNull();
    expect(r.perShareDDM).toBeNull();
  });

  it("warns on a non-positive book", () => {
    const r = runValuation(scenario({ b0: 0 }));
    expect(r.warnings.some((w) => w.includes("Book equity"))).toBe(true);
  });
});

describe("peer regression (P/B on ROE)", () => {
  it("recovers an exact linear relationship", () => {
    const reg = regressPbOnRoe([
      { ticker: "A", roe: 0.1, pb: 1.0 },
      { ticker: "B", roe: 0.2, pb: 1.5 },
      { ticker: "C", roe: 0.3, pb: 2.0 },
    ])!;
    expect(reg.slope).toBeCloseTo(5, 6);
    expect(reg.intercept).toBeCloseTo(0.5, 6);
    expect(reg.r2).toBeCloseTo(1, 6);
    expect(reg.predict(0.25)).toBeCloseTo(1.75, 6);
  });
  it("returns null with no ROE spread or too few points", () => {
    expect(regressPbOnRoe([{ ticker: "A", roe: 0.2, pb: 1 }])).toBeNull();
    expect(
      regressPbOnRoe([
        { ticker: "A", roe: 0.2, pb: 1 },
        { ticker: "B", roe: 0.2, pb: 2 },
      ]),
    ).toBeNull();
  });
});

describe("stats helpers", () => {
  it("mean / variance / covariance", () => {
    expect(mean([1, 2, 3])).toBeCloseTo(2, 6);
    expect(variance([1, 2, 3])).toBeCloseTo(1, 6); // sample variance
    expect(covariance([1, 2, 3], [1, 2, 3])).toBeCloseTo(1, 6);
  });

  it("linregBeta recovers a known beta and r²", () => {
    const x = [0.01, 0.02, -0.01, 0.03, 0.0];
    const y = x.map((v) => 1.5 * v);
    const fit = linregBeta(y, x)!;
    expect(fit.beta).toBeCloseTo(1.5, 6);
    expect(fit.r2).toBeCloseTo(1, 6);
    expect(fit.alpha).toBeCloseTo(0, 6);
  });

  it("linregBeta returns null without variance in x", () => {
    expect(linregBeta([1, 2], [0.5, 0.5])).toBeNull();
    expect(linregBeta([1], [1])).toBeNull();
  });
});
