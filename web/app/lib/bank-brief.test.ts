import { describe, it, expect } from "vitest";
import {
  bandOf,
  bankFlags,
  engineGate,
  peerRead,
  peerStat,
  realGrowth,
  risingStreak,
  PEER_FIELDS,
} from "./bank-brief";
import type { BankMetricRow } from "./heatmap";

const row = (t: string, over: Partial<BankMetricRow>): BankMetricRow =>
  ({
    bank_ticker: t,
    period: "2026Q1",
    total_assets: null, npl_ratio: null, stage2_share: null, npl_coverage: null,
    provision_intensity: null, cost_of_risk: null, roe: null, roa: null, nim: null,
    ppop_ratio: null, loan_yield: null, deposit_cost: null, spread: null, cost_income: null,
    cet1: null, car: null, lcr: null, fx_nop: null, repricing_gap_1y: null, pb: null, pe: null,
    ...over,
  }) as BankMetricRow;

/** A 10-bank field on CAR (stored in percentage POINTS). */
const field = [
  row("A", { car: 12.3 }), row("B", { car: 13.4 }), row("C", { car: 15.3 }),
  row("D", { car: 16.0 }), row("E", { car: 16.9 }), row("F", { car: 17.1 }),
  row("G", { car: 19.0 }), row("H", { car: 22.0 }), row("I", { car: 40.7 }),
  row("J", { car: 85.2 }),
];

describe("peerStat", () => {
  const spec = PEER_FIELDS.find((f) => f.key === "car")!;

  it("ranks direction-aware and reports the field's shape", () => {
    const s = peerStat(field, "C", "2026Q1", spec)!;
    expect(s.value).toBe(15.3);
    expect(s.n).toBe(10);
    expect(s.rank).toBe(8); // higher CAR is better: only A, B are worse
    expect(s.min).toBe(12.3);
    expect(s.max).toBe(85.2);
    expect(s.median).toBeCloseTo(17.0, 5); // (16.9 + 17.1) / 2
  });

  it("scales fractions to percent (npl 0.0173 → 1.73)", () => {
    const npl = PEER_FIELDS.find((f) => f.key === "npl_ratio")!;
    const rows = Array.from({ length: 9 }, (_, i) => row(`X${i}`, { npl_ratio: 0.02 + i / 1000 }));
    rows.push(row("ME", { npl_ratio: 0.0173 }));
    const s = peerStat(rows, "ME", "2026Q1", npl)!;
    expect(s.value).toBeCloseTo(1.73, 5);
    expect(s.rank).toBe(1); // lower NPL is better
  });

  it("returns null when the field is too thin to rank against", () => {
    expect(peerStat(field.slice(0, 3), "A", "2026Q1", spec)).toBeNull();
  });

  it("returns null when this bank has no value", () => {
    expect(peerStat(field, "MISSING", "2026Q1", spec)).toBeNull();
  });
});

describe("engineGate", () => {
  const full = (p: string) => row("Z", { period: p, spread: 0.064, roe: 0.27 });

  it("is ready when the TTM metrics resolved", () => {
    const g = engineGate([full("2025Q2"), full("2025Q3"), full("2025Q4"), full("2026Q1")]);
    expect(g.ready).toBe(true);
    expect(g.reason).toBeNull();
  });

  it("explains itself for a bank with too little history (the Colendi case)", () => {
    const rows = ["2025Q2", "2025Q3", "2025Q4", "2026Q1"].map((p) =>
      row("NEW", { period: p, spread: null, roe: null, nim: 0.0626 }),
    );
    const g = engineGate(rows);
    expect(g.ready).toBe(false);
    expect(g.filings).toBe(4);
    expect(g.firstPeriod).toBe("2025Q2");
    expect(g.reason).toContain("has filed 4 quarters");
    expect(g.reason).toContain("2025Q2");
  });

  // A development/investment bank (TSKB, KLNMA) takes no deposits, so it has no
  // deposit cost and no spread BY CONSTRUCTION. Gating the section on `spread`
  // suppressed its entire ladder — a perfectly good ROE included — and then told
  // the reader the filings were missing when 34 quarters were on file.
  it("keeps the ladder for a bank that takes no deposits, and says why the spread is absent", () => {
    const rows = ["2025Q2", "2025Q3", "2025Q4", "2026Q1"].map((p) =>
      row("TSKB", { period: p, spread: null, deposit_cost: null, deposits_stock: 0, roe: 0.266, nim: 0.05 }),
    );
    const g = engineGate(rows);
    expect(g.ready).toBe(true);
    expect(g.reason).toBeNull();
    expect(g.fundingNote).toContain("takes no deposits");
    // and it must NOT claim our data is missing — that was the false statement
    expect(g.fundingNote).not.toContain("we hold no deposits line");
  });

  it("distinguishes a real deposits gap from a bank that takes none", () => {
    const rows = ["2025Q2", "2025Q3", "2025Q4", "2026Q1"].map((p) =>
      row("GAP", { period: p, spread: null, deposits_stock: null, roe: 0.2 }),
    );
    const g = engineGate(rows);
    expect(g.ready).toBe(true);
    expect(g.fundingNote).toContain("we hold no deposits line");
  });

  it("leaves no funding note when the spread resolved normally", () => {
    const g = engineGate([full("2025Q4"), full("2026Q1")]);
    expect(g.ready).toBe(true);
    expect(g.fundingNote).toBeNull();
  });
});

describe("bankFlags", () => {
  const base = {
    car: null, carQoq: null, carRank: null, assetsQoqPct: null, roe: null, cpi12m: null,
    npl: null, nplRises: 0, nplMedian: null, stage2Share: null, costIncome: null,
    filings: 13, lcr: null, ldr: null,
  };

  it("flags a capital step-down when the buffer is thin (Ziraat)", () => {
    const f = bankFlags({ ...base, car: 15.3, carQoq: -3.4, assetsQoqPct: 2.8, carRank: { rank: 24, n: 34 } });
    const flag = f.find((x) => x.id === "car-step")!;
    expect(flag.kind).toBe("flag");
    expect(flag.detail).toContain("3.4pp");
    expect(flag.detail).toContain("3.3pp buffer");
    expect(flag.rule).toBe("Δcar_qoq < −1pp AND buffer < 8pp");
  });

  it("does NOT flag a big CAR drop when the buffer is fat — it notes it (Colendi)", () => {
    const f = bankFlags({ ...base, car: 40.7, carQoq: -21.0, assetsQoqPct: 16.0 });
    expect(f.find((x) => x.id === "car-step")).toBeUndefined();
    const note = f.find((x) => x.id === "car-normalise")!;
    expect(note.kind).toBe("note");
    expect(note.detail).toContain("28.7pp of buffer remains");
  });

  it("flags a real-terms loss on equity", () => {
    const f = bankFlags({ ...base, roe: 27.0, cpi12m: 32.1 });
    const flag = f.find((x) => x.id === "real-roe")!;
    expect(flag.detail).toContain("5.1pp real loss");
  });

  it("flags NPL drift only from four consecutive rises", () => {
    expect(bankFlags({ ...base, npl: 1.73, nplRises: 3 }).find((x) => x.id === "npl-drift")).toBeUndefined();
    const f = bankFlags({ ...base, npl: 1.73, nplRises: 6, nplMedian: 2.62, stage2Share: 7.7 });
    const flag = f.find((x) => x.id === "npl-drift")!;
    expect(flag.detail).toContain("still better than the field median");
    expect(flag.detail).toContain("7.7%");
  });

  it("flags a bank spending more than it earns", () => {
    const f = bankFlags({ ...base, costIncome: 135.6, filings: 4 });
    expect(f.find((x) => x.id === "below-breakeven")!.detail).toContain("₺1.36 for every ₺1");
  });

  it("reports liquidity as clear rather than silent", () => {
    const f = bankFlags({ ...base, lcr: 176, ldr: 86 });
    const ok = f.find((x) => x.id === "liquidity")!;
    expect(ok.kind).toBe("ok");
    expect(ok.rule).toContain("neither did");
  });
});

describe("phrases and maths", () => {
  it("bands a rank", () => {
    expect(bandOf(2, 36)).toBe("top quartile");
    expect(bandOf(30, 36)).toBe("bottom quartile");
  });

  it("counts a terminal rising streak", () => {
    expect(risingStreak([1.5, 1.6, 1.66, 1.73])).toBe(3);
    expect(risingStreak([1.8, 1.6, 1.66, 1.73])).toBe(2);
    expect(risingStreak([1.9, 1.8])).toBe(0);
  });

  it("deflates growth rather than subtracting it", () => {
    // Ziraat: loans +44.7% nominal with CPI 32.1% → +9.5% real, not +12.6pp.
    expect(realGrowth(44.7, 32.1)).toBeCloseTo(9.54, 1);
    // Deposits +31.7% nominal → a whisker below flat.
    expect(realGrowth(31.7, 32.1)).toBeCloseTo(-0.3, 1);
  });

  it("writes the capital read from the buffer, not by hand", () => {
    const s = { value: 15.3, median: 17.0, min: 12.3, max: 85.2, rank: 24, n: 34 };
    expect(peerRead("car", s, { buffer: 3.3 })).toContain("thinnest buffers");
    expect(peerRead("car", { ...s, value: 40.7, rank: 3 }, { buffer: 28.7 })).toContain("headroom");
  });
});

describe("the build-out guard", () => {
  const s = { value: 118.0, median: 42.0, min: 28.0, max: 140.0, rank: 33, n: 34 };

  it("calls a young bank spending more than it earns a build-out", () => {
    expect(peerRead("cost_income", s, { filings: 4 })).toContain("build-out");
  });

  it("does NOT call a mature bank's bad year a build-out", () => {
    // The guard fired on cost_income > 100 alone, so a bank twenty quarters old
    // having one loss-making quarter was told it was still finding its feet.
    const read = peerRead("cost_income", s, { filings: 20 });
    expect(read).not.toContain("build-out");
    expect(read).toContain("20 quarters in");
  });

  it("keeps the build-out reading when the age is unknown", () => {
    expect(peerRead("cost_income", s, {})).toContain("build-out");
  });
});
