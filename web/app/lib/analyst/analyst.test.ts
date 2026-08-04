/**
 * Phase 2 of the analyst build — the deterministic assembly layer.
 * The decomposition test pins the EXACT numbers from memo B of
 * docs/knowledge/2026-08-04-analyst-feasibility-test.md: if this drifts, the
 * "second question" artifact the whole build exists for is broken.
 */
import { describe, expect, it } from "vitest";

import { buildComparatives } from "./comparator";
import type { Queryable } from "./data";
import {
  buildAnalystSections,
  decomposeCoverage,
  licenceClassOf,
  type CoverageBucket,
} from "./sections";
import { findPlLine, foldTr, trailingAverage, type SeriesBundle } from "./series";

const bucket = (
  group: string,
  gross: number,
  coverage: number,
): CoverageBucket => ({
  group,
  gross,
  provision: gross * coverage,
  share: null,
  coverage,
});

describe("decomposeCoverage — memo B's core table", () => {
  it("reproduces the ŞEKERBANK 2024Q4→2026Q1 split: 13.2pp mix, 8.2pp erosion", () => {
    const then_ = [bucket("III", 17.9, 0.258), bucket("IV", 14.4, 0.279), bucket("V", 67.7, 0.902)];
    const now = [bucket("III", 24.8, 0.218), bucket("IV", 28.5, 0.249), bucket("V", 46.7, 0.767)];
    const d = decomposeCoverage("2024Q4", then_, now);
    expect(d).not.toBeNull();
    expect(d!.coverage_then_pct).toBeCloseTo(69.7, 1);
    expect(d!.coverage_now_pct).toBeCloseTo(48.3, 1);
    expect(d!.counterfactual_now_balances_then_rates_pct).toBeCloseTo(56.5, 1);
    expect(d!.mix_pp).toBeCloseTo(13.2, 1);
    expect(d!.erosion_pp).toBeCloseTo(8.2, 1);
    expect(d!.mix_pp + d!.erosion_pp).toBeCloseTo(d!.total_fall_pp, 1);
  });

  it("is null when coverage rose (nothing to decompose)", () => {
    const then_ = [bucket("III", 10, 0.2), bucket("IV", 10, 0.3), bucket("V", 80, 0.7)];
    const now = [bucket("III", 10, 0.3), bucket("IV", 10, 0.4), bucket("V", 80, 0.9)];
    expect(decomposeCoverage("2025Q1", then_, now)).toBeNull();
  });

  it("is null when a needed cell is missing — never a guessed zero", () => {
    const then_ = [bucket("III", 10, 0.2), { group: "IV", gross: 10, provision: null, share: null, coverage: null }, bucket("V", 80, 0.9)];
    const now = [bucket("III", 20, 0.2), bucket("IV", 20, 0.2), bucket("V", 60, 0.7)];
    expect(decomposeCoverage("2025Q1", then_, now)).toBeNull();
  });
});

describe("label folding + line search", () => {
  it("matches Turkish, English and fused core-margin labels", () => {
    const lines = [
      { period: "2026Q1", hierarchy: "III.", item_name: "NET FAİZ GELİRİ", amount: 100 },
      { period: "2025Q1", hierarchy: "III.", item_name: "NETPROFIT SHARE INCOME", amount: 90 },
    ];
    const re = /NET\s*(FAIZ|KAR\s*PAYI|INTEREST|PROFIT\s*SHARE)/;
    expect(findPlLine(lines, "2026Q1", re)?.amount).toBe(100);
    expect(findPlLine(lines, "2025Q1", re)?.amount).toBe(90);
    expect(findPlLine(lines, "2024Q1", re)).toBeNull();
  });

  it("folds dotted/dotless i both directions", () => {
    expect(foldTr("faİz")).toBe("FAIZ");
    expect(foldTr("KARŞILIK")).toContain("KAR");
  });
});

describe("trailingAverage — the 5-point convention", () => {
  it("averages available points and honours the 2-point minimum", () => {
    const m = new Map([
      ["2026Q1", 100],
      ["2025Q4", 90],
      ["2025Q2", 80], // 2025Q3 missing — averages the present ones
    ]);
    expect(trailingAverage(m, "2026Q1")).toBeCloseTo(90, 5);
    expect(trailingAverage(new Map([["2026Q1", 100]]), "2026Q1")).toBeNull();
  });
});

describe("licence classes", () => {
  it("collapses ownership codes into licence classes", () => {
    expect(licenceClassOf("GARAN")).toBe("deposit");
    expect(licenceClassOf("ZIRAAT")).toBe("deposit");
    expect(licenceClassOf("ALBRK")).toBe("participation");
    expect(licenceClassOf("TSKB")).toBe("devinv");
  });
});

describe("comparator", () => {
  const emptyBundle = (): SeriesBundle => ({
    bsTotal: new Map(),
    bsFc: new Map(),
    plByRole: new Map(),
    plLines: [],
    equityClosing: new Map(),
    stages: new Map(),
    capital: new Map(),
    liquidity: new Map(),
    freeProvision: new Map(),
    deposits: new Map(),
  });

  it("de-cumulates YTD net income and reports directions", () => {
    const b = emptyBundle();
    b.plByRole.set(
      "period_net",
      new Map([
        [ordFor("2025Q4"), 4000],
        [ordFor("2025Q3"), 2500],
        [ordFor("2026Q1"), 1500],
      ]),
    );
    b.bsTotal.set("2026Q1", 1000).set("2025Q4", 900).set("2025Q1", 600);
    const out = buildComparatives(b, "2026Q1");
    const q = out.find((c) => c.metric === "net_income_quarterly")!;
    expect(q.now).toBe(1500); // Q1 YTD is one quarter
    expect(q.qoq.prior).toBe(1500); // 2025Q4 single = 4000 − 2500
    expect(q.qoq.direction).toBe("flat");
    const assets = out.find((c) => c.metric === "total_assets")!;
    expect(assets.qoq.delta).toBe(100);
    expect(assets.yoy.delta).toBe(400);
    expect(assets.yoy.direction).toBe("up");
  });

  it("null priors never fabricate a zero", () => {
    const b = emptyBundle();
    b.bsTotal.set("2026Q1", 1000);
    const assets = buildComparatives(b, "2026Q1").find((c) => c.metric === "total_assets")!;
    expect(assets.qoq.prior).toBeNull();
    expect(assets.qoq.delta).toBeNull();
    expect(assets.qoq.direction).toBeNull();
  });

  function ordFor(p: string): number {
    return Number(p.slice(0, 4)) * 4 + Number(p.slice(5)) - 1;
  }
});

describe("guardMemo — structural abstention", () => {
  const dataBlock = [
    "npl_ratio_pct: 1.33",
    "stage3_coverage_pct: 48.3",
    "net_income_ttm: 2205403",
    "car_pct: 22.13",
  ].join("\n");

  it("passes a memo whose figures are all in the data (incl. % forms)", async () => {
    const { guardMemo } = await import("./guard");
    const memo =
      "# Coverage collapsed to 48.3%\n\nThe NPL ratio of 1.33% conceals it.\n\n" +
      "TTM net income was 2,205,403 thousand TL against a CAR of 22.13%.";
    const g = guardMemo(memo, dataBlock);
    expect(g.passed).toBe(true);
    expect(g.dropped).toHaveLength(0);
  });

  it("drops the paragraph carrying an invented figure, keeps the rest", async () => {
    const { guardMemo } = await import("./guard");
    const memo =
      "# Coverage collapsed to 48.3%\n\nNPL sits at 5.2% which flatters.\n\nCAR is 22.13%.";
    const g = guardMemo(memo, dataBlock);
    expect(g.passed).toBe(false);
    expect(g.dropped).toHaveLength(1);
    expect(g.dropped[0].unsupported).toContain(5.2);
    expect(g.body).toContain("22.13");
    expect(g.body).not.toContain("5.2%");
  });

  it("never edits a figure — the paragraph goes, verbatim", async () => {
    const { guardMemo } = await import("./guard");
    const memo = "Profit was 9,999,999 thousand TL.";
    const g = guardMemo(memo, dataBlock);
    expect(g.body).toBe("");
    expect(g.dropped[0].paragraph).toBe(memo);
  });
});

describe("prompt rendering", () => {
  it("prints gaps as NOT AVAILABLE and signals with severity", async () => {
    const { renderDataBlock } = await import("./prompt");
    const { buildAnalystSections } = await import("./sections");
    const emptyDb: Queryable = {
      all: async (sql: string) => {
        if (/analyst_/.test(sql)) throw new Error("no such table");
        return [];
      },
    };
    const sections = await buildAnalystSections(emptyDb, "SKBNK", "2026Q1", "unconsolidated");
    const block = renderDataBlock({
      sections,
      peers: {
        licence_class: "deposit",
        peer_count: 0,
        medians: {
          car: null, cet1: null, car_minus_cet1_pp: null, npl_ratio_pct: null,
          stage2_ratio_pct: null, stage3_coverage_pct: null, ldr_pct: null, roe_ttm_pct: null,
        },
      },
      comparatives: [],
    });
    expect(block).toContain("NOT AVAILABLE");
    expect(block).toContain("reporting_unit: bin");
    expect(block).toContain("never zero");
  });
});

describe("buildAnalystSections — resilience on an empty database", () => {
  const emptyDb: Queryable = {
    all: async (sql: string) => {
      if (/analyst_basis_metadata|analyst_signals/.test(sql)) {
        throw new Error("no such table"); // the pre-freeze-lift D1 state
      }
      return [];
    },
  };

  it("resolves with nulls + gaps, and the sweep-horizon unit fallback", async () => {
    const s = await buildAnalystSections(emptyDb, "GARAN", "2026Q1", "unconsolidated");
    expect(s.meta.bank_ticker).toBe("GARAN");
    expect(s.earnings.net_income_ttm).toBeNull();
    expect(s.asset_quality.coverage_decomposition).toBeNull();
    expect(s.comparability.reporting_unit).toBe("bin"); // ≤ sweep horizon
    expect(s.comparability.unit_source).toBe("sweep-2026-08-01");
    expect(s.comparability._gaps.length).toBeGreaterThan(0);
    expect(s.securities.breakdown_available).toBe(false);
  });

  it("never silently assumes thousands past the sweep horizon", async () => {
    const s = await buildAnalystSections(emptyDb, "GARAN", "2026Q2", "unconsolidated");
    expect(s.comparability.reporting_unit).toBeNull();
    expect(s.comparability.unit_source).toBe("pending_regex");
  });
});
