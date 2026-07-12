import { describe, expect, it } from "vitest";
import {
  impliedRatio,
  nplStockAttribution,
  segmentRatios,
  NPL_ITEMS,
  LOAN_ITEMS,
} from "./asset-quality";
import { deflate, risingRun, type Pt } from "./series";

/** Weekly ISO dates ending at `end`, oldest first. */
function weeks(end: string, n: number): string[] {
  const out: string[] = [];
  let t = Date.parse(end + "T00:00:00Z");
  for (let i = 0; i < n; i++) {
    out.unshift(new Date(t).toISOString().slice(0, 10));
    t -= 7 * 86_400_000;
  }
  return out;
}
const series = (ps: string[], start: number, weekly: number): Pt[] =>
  ps.map((period, i) => ({ period, value: start * Math.pow(1 + weekly, i) }));

const PS = weeks("2026-07-03", 60);

describe("the item map", () => {
  it("does NOT mirror the krediler ids — the trap that gives auto a 1068% NPL ratio", () => {
    // 2.0.4 is SME, not housing. 2.0.6 is provisions, not GPL. 2.0.11 is auto, not SME.
    expect(NPL_ITEMS.SME).toBe("2.0.4");
    expect(NPL_ITEMS.PROVISIONS).toBe("2.0.6");
    expect(NPL_ITEMS.AUTO).toBe("2.0.11");
    expect(NPL_ITEMS.HOUSING).toBe("2.0.10");
    // and they are NOT the positional twins of the loan ids
    expect(NPL_ITEMS.HOUSING).not.toBe(LOAN_ITEMS.HOUSING.replace("1.", "2."));
  });
});

describe("impliedRatio", () => {
  it("is stock ÷ book, per week", () => {
    const stock: Pt[] = [{ period: "2026-07-03", value: 776_000 }];
    const loans: Pt[] = [{ period: "2026-07-03", value: 26_746_000 }];
    expect(impliedRatio(stock, loans)[0].value).toBeCloseTo(2.9, 1);
  });

  it("skips weeks with no book (never divides by zero)", () => {
    const stock: Pt[] = [
      { period: "2026-06-26", value: 100 },
      { period: "2026-07-03", value: 110 },
    ];
    const loans: Pt[] = [{ period: "2026-06-26", value: 1000 }];
    expect(impliedRatio(stock, loans).map((r) => r.period)).toEqual(["2026-06-26"]);
  });
});

/**
 * THE LOAD-BEARING TEST. The first version of this page claimed the growing loan
 * book "hides 1.06pp of NPL ratio" because inflation inflates the denominator.
 * That is wrong: a ratio is deflator-invariant. This test is the documentation.
 */
describe("deflator invariance — why we do NOT claim inflation flatters the ratio", () => {
  it("deflating BOTH legs by CPI leaves the ratio unchanged", () => {
    const cpi = 1.321; // 32.1% y/y
    const stock: Pt[] = [{ period: "2026-07-03", value: 776_000 }];
    const loans: Pt[] = [{ period: "2026-07-03", value: 26_746_000 }];

    const nominal = impliedRatio(stock, loans)[0].value!;
    const real = impliedRatio(
      stock.map((r) => ({ ...r, value: r.value! / cpi })),
      loans.map((r) => ({ ...r, value: r.value! / cpi })),
    )[0].value!;

    expect(real).toBeCloseTo(nominal, 10); // identical — inflation cancels
  });

  it("only REAL book growth dilutes, and it is worth ~0.1pp, not ~1pp", () => {
    const r0 = 2.21; // ratio 52w ago
    const stockGrowth = 0.798; // +79.8%
    const loanGrowth = 0.366; // +36.6%
    const cpi = 0.321; // +32.1%

    const actual = (r0 * (1 + stockGrowth)) / (1 + loanGrowth); // 2.90%
    // Counterfactual A — book frozen in NOMINAL terms. A fiction at 32% CPI.
    const frozenNominal = r0 * (1 + stockGrowth); // 3.97%
    // Counterfactual B — book merely keeps pace with CPI (0% REAL growth).
    const flatReal = (r0 * (1 + stockGrowth)) / (1 + cpi); // 3.01%

    expect(actual).toBeCloseTo(2.9, 1);
    expect(frozenNominal - actual).toBeCloseTo(1.07, 1); // the claim we RETRACTED
    expect(flatReal - actual).toBeCloseTo(0.11, 1); // the honest figure
    expect(flatReal - actual).toBeLessThan(0.2); // never headline this as ~1pp
  });
});

describe("nplStockAttribution", () => {
  // Disjoint + exhaustive: total = commercial + cards.
  const commercial = series(PS, 300_000, 0.012);
  const cards = series(PS, 60_000, 0.015);
  const total: Pt[] = PS.map((period, i) => ({
    period,
    value: commercial[i].value! + cards[i].value!,
  }));

  it("segment shares of the stock increase sum to 100% — the reconciliation gate", () => {
    const a = nplStockAttribution(total, [
      { key: "commercial", label: "Commercial", rows: commercial },
      { key: "cards", label: "Retail cards", rows: cards },
    ]);
    expect(a.items).toHaveLength(2);
    expect(a.sumShare).toBeCloseTo(100, 6);
    expect(a.totalDelta).toBeGreaterThan(0);
  });

  it("a memo segment (SME ⊂ commercial) is carried but NEVER added to the sum", () => {
    // SME is half of commercial — if it were summed, the total would blow past 100%.
    const sme = commercial.map((r) => ({ ...r, value: r.value! * 0.5 }));
    const a = nplStockAttribution(
      total,
      [
        { key: "commercial", label: "Commercial", rows: commercial },
        { key: "cards", label: "Retail cards", rows: cards },
      ],
      { key: "sme", label: "SME", rows: sme },
    );
    expect(a.sumShare).toBeCloseTo(100, 6); // still 100 — memo excluded
    expect(a.memo).not.toBeNull();
    expect(a.memo!.share).toBeGreaterThan(0);
    expect(a.memo!.share).toBeLessThan(
      a.items.find((i) => i.key === "commercial")!.share + 1e-9,
    ); // a cut cannot exceed its parent
  });
});

describe("segmentRatios", () => {
  it("computes each segment's own NPL ratio and its 52w move", () => {
    const stock = series(PS, 10_000, 0.012); // bad loans compounding
    const loans = series(PS, 500_000, 0.006); // book growing slower
    const [s] = segmentRatios(
      [{ key: "sme", label: "SME", stock, loans }],
      PS[PS.length - 1],
    );
    expect(s.now).toBeGreaterThan(s.base); // ratio rising
    expect(s.delta).toBeCloseTo(s.now - s.base, 10);
    expect(s.stockYoY).toBeGreaterThan(0);
    expect(s.series.length).toBeGreaterThan(50);
  });
});

describe("risingRun", () => {
  it("counts the consecutive monthly rises the NPL flag prints", () => {
    const rows: Pt[] = [
      { period: "2026-01", value: 2.6 },
      { period: "2026-02", value: 2.5 }, // a fall — run breaks here
      { period: "2026-03", value: 2.62 },
      { period: "2026-04", value: 2.65 },
      { period: "2026-05", value: 2.69 },
    ];
    expect(risingRun(rows)).toBe(3);
  });
});

describe("deflate (re-exported from series)", () => {
  it("drops months with no published CPI rather than nowcasting", () => {
    const cpi = new Map([["2026-06", 32.1]]);
    const out = deflate(
      [
        { period: "2026-06-26", value: 79.8 },
        { period: "2026-07-03", value: 79.8 }, // July CPI not out
      ],
      cpi,
    );
    expect(out).toHaveLength(1);
    expect(out[0].value).toBeCloseTo(36.1, 0); // real NPL-stock growth
  });
});
