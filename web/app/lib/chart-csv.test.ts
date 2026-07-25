import { describe, expect, it } from "vitest";
import { chartSummary, srTableIsUseful, toCsv, wideToTable } from "./chart-csv";

const BOM = "﻿";

describe("wideToTable", () => {
  it("pivots wide rows into header + matrix in series order", () => {
    const rows = [
      { period: "2025-01", a: 1.2, b: 3.4 },
      { period: "2025-02", a: 5.6, b: 7.8 },
    ];
    const t = wideToTable(rows, { key: "period", label: "Period" }, [
      { key: "a", label: "Series A" },
      { key: "b", label: "Series B" },
    ]);
    expect(t.columns).toEqual(["Period", "Series A", "Series B"]);
    expect(t.rows).toEqual([
      ["2025-01", 1.2, 3.4],
      ["2025-02", 5.6, 7.8],
    ]);
  });

  it("maps missing / null / NaN cells to null", () => {
    const rows = [{ period: "2025-01", a: 1, b: NaN }];
    const t = wideToTable(rows, { key: "period", label: "Period" }, [
      { key: "a", label: "A" },
      { key: "b", label: "B" },
      { key: "c", label: "C" }, // absent from the row
    ]);
    expect(t.rows).toEqual([["2025-01", 1, null, null]]);
  });
});

describe("toCsv", () => {
  it("emits a BOM, CRLF rows, and raw numbers", () => {
    const csv = toCsv({
      columns: ["Period", "Value"],
      rows: [
        ["2025-01", 1234.5],
        ["2025-02", null],
      ],
    });
    expect(csv).toBe(`${BOM}Period,Value\r\n2025-01,1234.5\r\n2025-02,`);
  });

  it("quotes fields with commas, quotes, or newlines (RFC-4180)", () => {
    const csv = toCsv({
      columns: ["Label", "Note"],
      rows: [['He said "hi"', "a,b"]],
    });
    expect(csv).toBe(`${BOM}Label,Note\r\n"He said ""hi""","a,b"`);
  });
});

/**
 * The text alternative. Charts on this site render entirely client-side —
 * `ResponsiveContainer` ships an empty div from the server — so this summary is
 * the ONLY thing a screen reader gets from a chart. It is built from the same
 * table the CSV uses, which is what stops it drifting from the drawn line.
 */
describe("chartSummary", () => {
  const T = {
    columns: ["Period", "Sector", "Private"],
    rows: [
      ["2025-01", 16.5, 14.2],
      ["2025-02", 16.9, 13.8],
      ["2025-03", 16.1, 14.9],
    ] as (string | number | null)[][],
  };

  it("names the span, and each series' start, end and band", () => {
    const s = chartSummary(T);
    expect(s).toContain("3 rows");
    expect(s).toContain("Period from 2025-01 to 2025-03");
    expect(s).toContain("Sector: 16.5 at the start, 16.1 at the end, ranging 16.1 to 16.9");
    expect(s).toContain("Private: 14.2 at the start, 14.9 at the end");
  });

  it("states no direction word — a direction is a claim, and claims are computed", () => {
    // lib/prose.ts owns direction language, next to the series that settles it.
    // A summary that said "fell" would be asserting one here, unchecked.
    expect(chartSummary(T)).not.toMatch(/\b(rose|fell|climbed|dropped|grew|shrank)\b/i);
  });

  it("rounds for speech rather than storage", () => {
    const s = chartSummary({ columns: ["Period", "Ratio"], rows: [["2025-01", 16.104346]] });
    expect(s).toContain("16.1"); // not 16.104346
    expect(s).not.toContain("16.104346");
  });

  it("scales decimals to magnitude", () => {
    const s = chartSummary({ columns: ["Period", "Assets"], rows: [["2025-01", 1234567.89]] });
    expect(s).toContain("1234568");
  });

  it("says a series is empty rather than inventing a range", () => {
    expect(chartSummary({ columns: ["Period", "Gap"], rows: [["2025-01", null]] })).toContain(
      "Gap: no values",
    );
  });

  it("caps the series it lists and counts the rest", () => {
    const cols = ["Period", ...Array.from({ length: 12 }, (_, i) => `S${i}`)];
    const s = chartSummary({ columns: cols, rows: [["2025-01", ...cols.slice(1).map(() => 1)]] });
    expect(s).toContain("and 4 more series");
  });

  it("is empty for an empty table, so nothing renders", () => {
    expect(chartSummary({ columns: [], rows: [] })).toBe("");
    expect(chartSummary({ columns: ["Period", "X"], rows: [] })).toBe("");
  });
});

describe("srTableIsUseful", () => {
  const rows = (n: number, cols = 2) =>
    Array.from({ length: n }, (_, i) => [String(i), ...Array(cols - 1).fill(1)]);

  it("includes the median chart — 37 rows x 2 columns, measured on /economy", () => {
    expect(srTableIsUseful({ columns: ["Period", "Value"], rows: rows(37) })).toBe(true);
  });

  it("excludes the 753-row daily series: reading it aloud is an obstacle, not access", () => {
    expect(srTableIsUseful({ columns: ["Date", "Value"], rows: rows(753) })).toBe(false);
  });

  it("excludes a short but very wide table on total cells", () => {
    expect(srTableIsUseful({ columns: Array(40).fill("c"), rows: rows(40, 40) })).toBe(false);
  });

  it("excludes an empty table", () => {
    expect(srTableIsUseful({ columns: ["Period", "Value"], rows: [] })).toBe(false);
  });

  it("the summary points at whichever alternative actually rendered", () => {
    expect(chartSummary({ columns: ["Period", "V"], rows: rows(10) })).toContain(
      "full data follows as a table",
    );
    expect(chartSummary({ columns: ["Period", "V"], rows: rows(753) })).toContain(
      "CSV download",
    );
  });
});
