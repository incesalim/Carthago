import { describe, expect, it } from "vitest";
import { toCsv, wideToTable } from "./chart-csv";

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
