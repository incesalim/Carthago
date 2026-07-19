import { describe, expect, it } from "vitest";
import {
  buildObservationQuery,
  isValidCodeShape,
  parseDate,
  parseSeriesParam,
  toCsv,
  type SeriesMeta,
} from "./api-series";

const meta = (over: Partial<SeriesMeta>): SeriesMeta => ({
  series_code: "BDDK.T01.I005.10001.TOT",
  dataset: "T01",
  frequency: "monthly",
  source_table: "balance_sheet",
  table_number: 1,
  category: null,
  item_key: "5",
  item_name: "Krediler",
  item_name_en: "Loans",
  bank_type_code: "10001",
  report_currency: "TL",
  value_column: "amount_total",
  unit: "million TL",
  start_date: "2020-01-31",
  end_date: "2026-04-30",
  obs_count: 76,
  ...over,
});

describe("code shape", () => {
  it("accepts a monthly code", () => {
    expect(isValidCodeShape("BDDK.T01.I005.10001.TOT")).toBe(true);
  });

  it("accepts a weekly code with an underscored outline id", () => {
    expect(isValidCodeShape("BDDK.WLOAN.I1_0_11.10001.TL")).toBe(true);
  });

  it("rejects a code with the wrong segment count", () => {
    expect(isValidCodeShape("BDDK.T01.I005.10001")).toBe(false);
    expect(isValidCodeShape("BDDK.T01.I005.10001.TOT.EXTRA")).toBe(false);
  });

  it("rejects a non-BDDK prefix and a malformed bank type", () => {
    expect(isValidCodeShape("EVDS.T01.I005.10001.TOT")).toBe(false);
    expect(isValidCodeShape("BDDK.T01.I005.100.TOT")).toBe(false);
  });

  it("rejects SQL smuggled into a code", () => {
    expect(isValidCodeShape("BDDK.T01.I005.10001.TOT; DROP TABLE x")).toBe(false);
    expect(isValidCodeShape("BDDK.T01.I005.10001.'||x")).toBe(false);
  });
});

describe("parseSeriesParam", () => {
  it("splits the EVDS-style dash-joined list", () => {
    expect(parseSeriesParam("BDDK.T01.I005.10001.TOT-BDDK.T02.I001.10001.TL"))
      .toEqual(["BDDK.T01.I005.10001.TOT", "BDDK.T02.I001.10001.TL"]);
  });

  it("upper-cases and drops blank segments from stray separators", () => {
    expect(parseSeriesParam("bddk.t01.i005.10001.tot--"))
      .toEqual(["BDDK.T01.I005.10001.TOT"]);
  });
});

describe("parseDate", () => {
  it("parses EVDS DD-MM-YYYY", () => {
    expect(parseDate("31-12-2025")).toBe("2025-12-31");
  });

  it("passes ISO through", () => {
    expect(parseDate("2025-12-31")).toBe("2025-12-31");
  });

  it("returns null for junk or absent input", () => {
    expect(parseDate(null)).toBeNull();
    expect(parseDate("December 2025")).toBeNull();
    expect(parseDate("2025")).toBeNull();
  });
});

describe("buildObservationQuery", () => {
  it("builds a balance-sheet query bound by item, bank type and currency", () => {
    const q = buildObservationQuery(meta({}), null, null)!;
    expect(q.sql).toContain("FROM balance_sheet");
    expect(q.sql).toContain("amount_total AS value");
    // balance_sheet is not partitioned by table_number
    expect(q.sql).not.toContain("table_number");
    expect(q.binds).toEqual([5, "10001", "TL"]);
  });

  it("adds the table_number filter for a partitioned source", () => {
    const q = buildObservationQuery(
      meta({ source_table: "loans", table_number: 3, value_column: "total_tl" }),
      null, null,
    )!;
    expect(q.sql).toContain("AND table_number = ?");
    expect(q.binds).toEqual([5, "10001", 3, "TL"]);
  });

  it("omits the currency filter for financial_ratios, which has no such column", () => {
    const q = buildObservationQuery(
      meta({
        source_table: "financial_ratios", table_number: 15,
        value_column: "ratio_value",
      }),
      null, null,
    )!;
    expect(q.sql).not.toContain("currency");
    expect(q.binds).toEqual([5, "10001", 15]);
  });

  it("keys other_data by item_name, since its item_order collides in table 12", () => {
    const q = buildObservationQuery(
      meta({
        source_table: "other_data", table_number: 12,
        item_key: "Sermaye Yeterliliği Standart Oranı",
        value_column: "Toplam",
      }),
      null, null,
    )!;
    expect(q.sql).toContain("AND item_name = ?");
    expect(q.sql).toContain("AND column_name = ?");
    expect(q.binds).toEqual([
      12, "Toplam", "Sermaye Yeterliliği Standart Oranı", "10001", "TL",
    ]);
  });

  it("queries weekly_series by category, outline id and currency leg", () => {
    const q = buildObservationQuery(
      meta({
        frequency: "weekly", source_table: "weekly_series", table_number: null,
        category: "krediler", item_key: "1.0.11", report_currency: null,
        value_column: "TL",
      }),
      null, null,
    )!;
    expect(q.sql).toContain("FROM weekly_series");
    expect(q.sql).toContain("period_date AS date");
    expect(q.binds).toEqual(["krediler", "1.0.11", "10001", "TL"]);
  });

  it("appends date bounds when given", () => {
    const q = buildObservationQuery(meta({}), "2024-01-01", "2025-12-31")!;
    expect(q.binds).toEqual([5, "10001", "TL", "2024-01-01", "2025-12-31"]);
  });

  it("dates monthly observations to the period END, not the 1st", () => {
    const q = buildObservationQuery(meta({}), null, null)!;
    expect(q.sql).toContain("'+1 month', '-1 day'");
  });

  it("fails closed on a value column outside the allowlist", () => {
    expect(buildObservationQuery(
      meta({ value_column: "amount_total; DROP TABLE x" }), null, null,
    )).toBeNull();
    expect(buildObservationQuery(
      meta({ value_column: "downloaded_at" }), null, null,
    )).toBeNull();
  });

  it("fails closed on a source table we don't serve", () => {
    expect(buildObservationQuery(
      meta({ source_table: "bot_usage" }), null, null,
    )).toBeNull();
  });
});

describe("toCsv", () => {
  it("outer-joins dates across series so columns line up", () => {
    const csv = toCsv(
      [meta({ series_code: "A" }), meta({ series_code: "B" })],
      [
        [{ date: "2025-01-31", value: 1 }, { date: "2025-02-28", value: 2 }],
        [{ date: "2025-02-28", value: 9 }],
      ],
    );
    expect(csv.split("\n")).toEqual([
      "date,A,B",
      "2025-01-31,1,",
      "2025-02-28,2,9",
    ]);
  });

  it("renders a null observation as an empty cell, not the string null", () => {
    const csv = toCsv([meta({ series_code: "A" })],
      [[{ date: "2025-01-31", value: null }]]);
    expect(csv.split("\n")[1]).toBe("2025-01-31,");
  });
});
