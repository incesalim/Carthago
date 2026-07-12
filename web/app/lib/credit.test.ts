import { describe, expect, it } from "vitest";
import {
  baseFor,
  contributions,
  creditBridge,
  deflate,
  fxAdjustedGrowth,
  sumSeries,
  toMap,
  trailingRun,
  trailingRunVs,
  type Pt,
} from "./credit";

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

/** A level series growing at a constant weekly rate. */
function series(periods: string[], start: number, weeklyRate: number): Pt[] {
  return periods.map((period, i) => ({ period, value: start * Math.pow(1 + weeklyRate, i) }));
}

describe("baseFor", () => {
  it("pairs by date and tolerates a skipped week either side", () => {
    const m = toMap([
      { period: "2025-07-04", value: 100 },
      { period: "2026-07-03", value: 130 },
    ]);
    // 2026-07-03 minus 364d = 2025-07-04 exactly.
    expect(baseFor(m, "2026-07-03")?.value).toBe(100);
  });

  it("returns null rather than reaching past ±1 week", () => {
    const m = toMap([
      { period: "2025-05-01", value: 100 }, // way outside the window
      { period: "2026-07-03", value: 130 },
    ]);
    expect(baseFor(m, "2026-07-03")).toBeNull();
  });
});

describe("deflate", () => {
  it("uses the exact Fisher form, not g − pi", () => {
    const cpi = new Map([["2026-06", 32]]);
    const [r] = deflate([{ period: "2026-06-26", value: 36.6 }], cpi);
    // (1.366 / 1.32) - 1 = 3.48%, NOT 36.6 - 32 = 4.6
    expect(r.value).toBeCloseTo(3.48, 1);
  });

  it("DROPS weeks whose month has no published CPI — never nowcasts", () => {
    const cpi = new Map([["2026-06", 32]]);
    const out = deflate(
      [
        { period: "2026-06-26", value: 36.6 },
        { period: "2026-07-03", value: 36.6 }, // July CPI not out yet
      ],
      cpi,
    );
    expect(out.map((r) => r.period)).toEqual(["2026-06-26"]);
  });
});

describe("fxAdjustedGrowth", () => {
  it("strips pure lira depreciation: a flat book that only revalues shows ~0 growth", () => {
    const ps = weeks("2026-07-03", 53);
    // TL book flat at 100. FX book flat at 10 USD, but USD/TRY doubles 20 → 40,
    // so the reported TL-equivalent FX book doubles 200 → 400 on paper.
    const tl: Pt[] = ps.map((period) => ({ period, value: 100 }));
    const fx: Pt[] = ps.map((period, i) => ({ period, value: i === ps.length - 1 ? 400 : 200 }));
    const usd = ps.map((period_date, i) => ({
      period_date,
      value: i === ps.length - 1 ? 40 : 20,
    }));

    const out = fxAdjustedGrowth(tl, fx, usd);
    const last = out.at(-1)!;
    // Nominal would print (100+400)/(100+200) - 1 = +66.7%. Held at the base
    // rate the FX book is unchanged, so real volume growth is 0.
    expect(last.value).toBeCloseTo(0, 6);
  });
});

describe("creditBridge", () => {
  const ps = weeks("2026-07-03", 60);
  const nominal: Pt[] = ps.map((period) => ({ period, value: 36.6 }));
  const fxAdj: Pt[] = ps.map((period) => ({ period, value: 29.3 }));
  const cpi = new Map([
    ["2026-05", 32.1],
    ["2026-06", 32.1],
  ]); // no July CPI

  it("composes both adjustments into a figure neither twin shows", () => {
    const b = creditBridge(nominal, fxAdj, cpi);
    // (1.293 / 1.321) - 1 = -2.1%
    expect(b.realFxAdj).toBeCloseTo(-2.12, 1);
    // and each twin alone tells a different, rosier story
    expect(b.real).toBeCloseTo(3.4, 1);
    expect(b.fxAdj).toBeCloseTo(29.3, 1);
  });

  it("reports the CPI lag instead of hiding it", () => {
    const b = creditBridge(nominal, fxAdj, cpi);
    expect(b.asOfNominal).toBe("2026-07-03"); // loans printed through July
    expect(b.asOfReal).toBe("2026-06-26"); // but CPI only through June
    expect(b.lagged).toBe(true);
  });

  it("legs reconcile the endpoints: nominal − currency − inflation = real", () => {
    const b = creditBridge(nominal, fxAdj, cpi);
    const nominalAtReal = 36.6;
    expect(nominalAtReal - b.currencyPp! - b.inflationPp!).toBeCloseTo(b.realFxAdj!, 6);
  });
});

describe("contributions", () => {
  const ps = weeks("2026-07-03", 60);
  // Disjoint, exhaustive books: total = a + b.
  const a = series(ps, 1000, 0.01);
  const b = series(ps, 500, 0.002);
  const total: Pt[] = ps.map((period, i) => ({
    period,
    value: (a[i].value ?? 0) + (b[i].value ?? 0),
  }));

  it("decomposes the headline exactly — the sum IS the growth rate", () => {
    const c = contributions(total, [
      { key: "a", label: "A", rows: a },
      { key: "b", label: "B", rows: b },
    ]);
    expect(c.totalPp).not.toBeNull();
    // This reconciliation is the proof the cut is right; it is what makes the
    // attribution bars trustworthy rather than decorative.
    expect(c.sumPp).toBeCloseTo(c.totalPp!, 6);
  });

  it("a shrinking book contributes negative pp", () => {
    const shrinking = series(ps, 500, -0.005);
    const tot: Pt[] = ps.map((period, i) => ({
      period,
      value: (a[i].value ?? 0) + (shrinking[i].value ?? 0),
    }));
    const c = contributions(tot, [
      { key: "a", label: "A", rows: a },
      { key: "s", label: "S", rows: shrinking },
    ]);
    expect(c.items.find((i) => i.key === "s")!.pp).toBeLessThan(0);
    expect(c.sumPp).toBeCloseTo(c.totalPp!, 6);
  });
});

describe("sumSeries", () => {
  it("adds books period-by-period and skips periods a leg is missing", () => {
    const out = sumSeries(
      [
        { period: "2026-06-26", value: 10 },
        { period: "2026-07-03", value: 12 },
      ],
      [{ period: "2026-06-26", value: 5 }], // no July leg
    );
    expect(out).toEqual([{ period: "2026-06-26", value: 15 }]);
  });
});

describe("trailing runs", () => {
  it("counts consecutive trailing weeks that satisfy the rule", () => {
    const rows: Pt[] = [
      { period: "2026-06-05", value: 1 },
      { period: "2026-06-12", value: -1 },
      { period: "2026-06-19", value: -2 },
      { period: "2026-06-26", value: -3 },
    ];
    expect(trailingRun(rows, (v) => v < 0)).toBe(3);
  });

  it("compares against another series by date", () => {
    const cards: Pt[] = [
      { period: "2026-06-19", value: 40 },
      { period: "2026-06-26", value: 46 },
    ];
    const sector: Pt[] = [
      { period: "2026-06-19", value: 42 }, // cards BELOW sector -> run breaks here
      { period: "2026-06-26", value: 36 },
    ];
    expect(trailingRunVs(cards, sector, (v, o) => v > o)).toBe(1);
  });
});
