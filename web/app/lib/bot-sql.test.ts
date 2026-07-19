import { describe, expect, it } from "vitest";
import {
  DEFAULT_ROW_CAP,
  checkSectorAggregation,
  checkTickerEnumeration,
  enumeratedTickers,
  formatTrNumber,
  renderDataList,
  substituteDataList,
  extractSql,
  formatTable,
  inventedNumbers,
  numbersIn,
  sanitizeSelect,
} from "./bot-sql";

describe("sanitizeSelect — accepts read-only queries", () => {
  it("accepts a plain SELECT and appends a LIMIT", () => {
    const r = sanitizeSelect("SELECT bank_ticker FROM bank_audit_capital");
    expect(r.ok).toBe(true);
    // rowCap + 1: the extra row is how the caller distinguishes "exactly full"
    // from "there was more", so a truncated population can be announced.
    if (r.ok) expect(r.sql).toBe(`SELECT bank_ticker FROM bank_audit_capital LIMIT ${DEFAULT_ROW_CAP + 1}`);
    if (r.ok) expect(r.capImposed).toBe(true);
  });

  it("accepts a WITH … SELECT (CTE)", () => {
    const r = sanitizeSelect("WITH t AS (SELECT 1 AS a) SELECT a FROM t");
    expect(r.ok).toBe(true);
  });

  it("keeps an existing LIMIT", () => {
    const r = sanitizeSelect("SELECT * FROM bank_audit_capital LIMIT 5");
    expect(r.ok).toBe(true);
    if (r.ok) expect(r.sql).toBe("SELECT * FROM bank_audit_capital LIMIT 5");
  });

  it("strips a single trailing semicolon", () => {
    const r = sanitizeSelect("SELECT 1;");
    expect(r.ok).toBe(true);
    if (r.ok) expect(r.sql).not.toContain(";");
  });

  it("rewrites ILIKE → LIKE (SQLite has no ILIKE)", () => {
    const r = sanitizeSelect("SELECT * FROM t WHERE item_name ILIKE '%net%'");
    expect(r.ok).toBe(true);
    if (r.ok) {
      expect(r.sql).toContain("LIKE");
      expect(r.sql.toLowerCase()).not.toContain("ilike");
    }
  });
});

describe("sanitizeSelect — rejects writes and abuse", () => {
  const bad = [
    "INSERT INTO bank_audit_capital VALUES (1)",
    "UPDATE bank_audit_capital SET total_capital=0",
    "DELETE FROM bank_audit_capital",
    "DROP TABLE bank_audit_capital",
    "ALTER TABLE x ADD COLUMN y",
    "CREATE TABLE x (a int)",
    "PRAGMA table_info(x)",
    "ATTACH DATABASE 'x' AS y",
    "REPLACE INTO x VALUES (1)",
    "SELECT 1; DROP TABLE x",
    "SELECT 1 /* */ ; DELETE FROM x", // comment can't hide the 2nd statement
    "SELECT * INTO newt FROM x",
  ];
  for (const sql of bad) {
    it(`rejects: ${sql.slice(0, 40)}`, () => {
      expect(sanitizeSelect(sql).ok).toBe(false);
    });
  }

  it("rejects a comment-smuggled DROP", () => {
    // After comment stripping this is `SELECT 1  DROP TABLE x` → forbidden `drop`.
    const r = sanitizeSelect("SELECT 1 -- \nDROP TABLE x");
    expect(r.ok).toBe(false);
  });

  it("rejects denylisted tables", () => {
    expect(sanitizeSelect("SELECT * FROM bot_usage").ok).toBe(false);
    expect(sanitizeSelect("SELECT * FROM d1_migrations").ok).toBe(false);
  });

  it("rejects over-long queries", () => {
    expect(sanitizeSelect("SELECT " + "a,".repeat(2000) + "b FROM x").ok).toBe(false);
  });

  it("rejects non-SELECT leading token", () => {
    expect(sanitizeSelect("EXPLAIN SELECT 1").ok).toBe(false);
  });
});

describe("extractSql", () => {
  it("pulls a fenced sql block", () => {
    expect(extractSql("here:\n```sql\nSELECT 1 FROM t\n```")).toBe("SELECT 1 FROM t");
  });
  it("pulls a bare SELECT", () => {
    expect(extractSql("SELECT a FROM t WHERE x=1")).toBe("SELECT a FROM t WHERE x=1");
  });
  it("returns null for prose (no query)", () => {
    expect(extractSql("Hi! I can answer questions about banks.")).toBeNull();
  });
});

describe("number helpers", () => {
  it("numbersIn ignores thousands separators", () => {
    expect(numbersIn("total 1,234,567 and 8.5")).toEqual([1234567, 8.5]);
  });
  it("inventedNumbers flags an unknown figure", () => {
    expect(inventedNumbers("profit was 999", [100, 200])).toEqual(["999"]);
  });
  it("inventedNumbers accepts a known figure", () => {
    expect(inventedNumbers("profit was 200", [100, 200])).toEqual([]);
  });
  it("inventedNumbers ignores label-bound digits (Stage-3, 1-year)", () => {
    expect(inventedNumbers("Stage-3 rose over the 1-year horizon", [])).toEqual([]);
  });
});

describe("formatTable", () => {
  it("renders a header + rows", () => {
    const t = formatTable([{ a: 1, b: "x" }, { a: 2, b: "y" }]);
    expect(t).toContain("a");
    expect(t).toContain("b");
    expect(t.split("\n").length).toBeGreaterThanOrEqual(4);
  });
  it("handles empty input", () => {
    expect(formatTable([])).toBe("(no rows)");
  });
});

describe("checkTickerEnumeration — the model must not pick the banks", () => {
  const NAMES = { GARAN: "Garanti BBVA", AKBNK: "Akbank", ISCTR: "İşbank", HALKB: "Halkbank" };

  it("rejects a self-chosen bank list when the question named none", () => {
    // The real failure: asked to rank all banks, the model queried ~10 and
    // answered for 8 while 27 had data.
    const r = checkTickerEnumeration(
      "SELECT bank_ticker FROM bank_audit_profile WHERE bank_ticker IN ('AKBNK','GARAN','HALKB','ISCTR')",
      "şube başına personele göre bankaları sırala",
      NAMES,
    );
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.error).toContain("hardcodes bank tickers the question never named");
  });

  it("allows a list the user actually asked for, by ticker or by name", () => {
    expect(checkTickerEnumeration(
      "SELECT * FROM t WHERE bank_ticker IN ('GARAN','AKBNK')",
      "compare Garanti and Akbank", NAMES,
    ).ok).toBe(true);
    expect(checkTickerEnumeration(
      "SELECT * FROM t WHERE bank_ticker IN ('GARAN','AKBNK')",
      "GARAN vs AKBNK", NAMES,
    ).ok).toBe(true);
  });

  it("folds Turkish letters so İşbank matches ISCTR", () => {
    expect(checkTickerEnumeration(
      "SELECT * FROM t WHERE bank_ticker IN ('ISCTR','AKBNK')",
      "İşbank ve Akbank karşılaştır", NAMES,
    ).ok).toBe(true);
  });

  it("allows a single-bank query regardless", () => {
    expect(checkTickerEnumeration(
      "SELECT * FROM t WHERE bank_ticker = 'AKBNK'", "en karlı banka", NAMES,
    ).ok).toBe(true);
  });

  it("allows an unrestricted ranking — the shape we want", () => {
    expect(checkTickerEnumeration(
      "SELECT bank_ticker, personnel FROM bank_audit_profile WHERE period='2026Q1' ORDER BY personnel DESC",
      "bankaları sırala", NAMES,
    ).ok).toBe(true);
  });

  it("catches the OR-chain spelling too", () => {
    const r = checkTickerEnumeration(
      "SELECT * FROM t WHERE bank_ticker='AKBNK' OR bank_ticker='GARAN'",
      "rank banks by assets", NAMES,
    );
    expect(r.ok).toBe(false);
  });
});

describe("enumeratedTickers", () => {
  it("reads IN lists and equality, ignoring comments", () => {
    expect(enumeratedTickers("WHERE bank_ticker IN ('A','B') -- ,'C'").sort()).toEqual(["A", "B"]);
    expect(enumeratedTickers("WHERE p.bank_ticker = 'akbnk'")).toEqual(["AKBNK"]);
  });

  it("returns nothing for an unrestricted query", () => {
    expect(enumeratedTickers("SELECT bank_ticker FROM t GROUP BY bank_ticker")).toEqual([]);
  });
});

describe("formatTrNumber", () => {
  it("groups thousands Turkish-style and keeps the sign", () => {
    expect(formatTrNumber(43520620)).toBe("43.520.620");
    expect(formatTrNumber(-504991)).toBe("-504.991");
    expect(formatTrNumber(877011)).toBe("877.011");
    expect(formatTrNumber(0)).toBe("0");
  });

  it("renders a decimal with a comma", () => {
    expect(formatTrNumber(20.85)).toBe("20,85");
  });
});

describe("substituteDataList — numbers come from the rows, not the prose", () => {
  const rows = Array.from({ length: 6 }, (_, i) => ({
    bank_ticker: `B${i + 1}`, net_profit: (6 - i) * 1000000,
  }));

  it("replaces a hand-typed ranking with one rendered from the data", () => {
    const prose = "2026Q1 sıralaması:\n1. B1 — 6.000.000\n2. B2 — 5.000.000\n" +
      "3. B3 — 999\n4. B4 — 3.000.000\n5. B5 — 2.000.000\n6. B6 — 1.000.000\n" +
      "Kaynak: BDDK.";
    const out = substituteDataList(prose, rows);
    expect(out).toContain("2026Q1 sıralaması:");   // caption kept
    expect(out).toContain("Kaynak: BDDK.");        // trailing prose kept
    expect(out).not.toContain("999");              // the model's wrong figure is gone
    expect(out).toContain("3. B3 — 4.000.000");    // replaced by the queried value
    expect(out).toContain("6. B6 — 1.000.000");    // every row rendered
  });

  it("keeps a deliberate top-N a top-N instead of appending every row", () => {
    // The model listing 3 of 6 on purpose must not have all 6 pasted under a
    // caption that says "top 3" — the list would contradict the sentence above it.
    const prose = "En büyük 3 banka:\n1. B1 — 6.000.000\n2. B2 — 5.000.000\n3. B3 — 4.000.000";
    const out = substituteDataList(prose, rows);
    expect(out).toContain("3. B3 — 4.000.000");
    expect(out).not.toContain("B4");
  });

  it("declines when the rows are from a different query than the answer", () => {
    // lastRows is whatever ran most recently. A follow-up "SELECT period,
    // COUNT(*)" once replaced a 38-bank ranking with a list of periods, under
    // the ranking's own caption.
    const unrelated = Array.from({ length: 8 }, (_, i) => ({
      period: `2026Q${i + 1}`, n: i + 1,
    }));
    const prose = "Bankalar:\n1. B1 — 6.000.000\n2. B2 — 5.000.000\n3. B3 — 4.000.000";
    expect(substituteDataList(prose, unrelated)).toBe(prose);
  });

  it("renders the column the query sorted by, not the first numeric one", () => {
    // ORDER BY npl_pct with stage3_amount first would print absolute Stage-3
    // amounts under a caption saying "ranked by NPL ratio" — right order,
    // wrong figures, no mismatch signal.
    const npl = [
      { bank_ticker: "B1", stage3_amount: 45123456, npl_pct: 8.1 },
      { bank_ticker: "B2", stage3_amount: 30000000, npl_pct: 6.4 },
      { bank_ticker: "B3", stage3_amount: 20000000, npl_pct: 5.2 },
      { bank_ticker: "B4", stage3_amount: 10000000, npl_pct: 4.0 },
      { bank_ticker: "B5", stage3_amount: 5000000, npl_pct: 2.5 },
    ];
    const prose = "NPL:\n1. B1 — 8,1\n2. B2 — 6,4\n3. B3 — 5,2\n4. B4 — 4\n5. B5 — 2,5";
    const out = substituteDataList(prose, npl, 5,
      "SELECT bank_ticker, stage3_amount, npl_pct FROM t ORDER BY npl_pct DESC");
    expect(out).toContain("1. B1 — 8,1");
    expect(out).not.toContain("45.123.456");
  });

  it("corrects a figure the model mistyped", () => {
    const prose = "x:\n1. B1 — 9.999.999\n2. B2 — 5.000.000\n3. B3 — 4.000.000";
    expect(substituteDataList(prose, rows)).toContain("1. B1 — 6.000.000");
  });

  it("fires on a bolded list — the markdown one model emits and another doesn't", () => {
    // Live regression: `finalize` strips '*' AFTER substitution, so a bolded
    // list slipped past detection and that model's typed figures survived.
    const prose = [
      "2026Q1:",
      "**1. B1** — 9.999.999 bin TL",
      "**2. B2** — 5.000.000 bin TL",
      "**3. B3** — 4.000.000 bin TL",
      "**4. B4** — 3.000.000 bin TL",
      "**5. B5** — 2.000.000 bin TL",
      "**6. B6** — 1.000.000 bin TL",
    ].join("\n");
    const out = substituteDataList(prose, rows);
    expect(out).toContain("1. B1 — 6.000.000");  // corrected from the rows
    expect(out).not.toContain("9.999.999");
    expect(out).toContain("6. B6 — 1.000.000");
  });

  it("fires on a '*' bullet — stripping every asterisk once ate the bullet itself", () => {
    const prose = ["Sıralama:", "* B1 — 9.999.999", "* B2 — 5.000.000",
      "* B3 — 4.000.000", "* B4 — 3.000.000", "* B5 — 2.000.000",
      "* B6 — 1.000.000"].join("\n");
    const out = substituteDataList(prose, rows);
    expect(out).toContain("1. B1 — 6.000.000");
    expect(out).not.toContain("9.999.999");
  });

  it("leaves a short result alone", () => {
    const prose = "x:\n1. A — 1\n2. B — 2\n3. C — 3";
    expect(substituteDataList(prose, rows.slice(0, 2))).toBe(prose);
  });

  it("leaves plain prose alone", () => {
    const prose = "Garanti's net profit in 2026Q1 was 33.316.462 bin TL.";
    expect(substituteDataList(prose, rows)).toBe(prose);
  });

  it("leaves a bare narrative alone even with many rows behind it", () => {
    const prose = "The sector grew. Loans rose faster than deposits.";
    expect(substituteDataList(prose, rows)).toBe(prose);
  });
});

describe("renderDataList", () => {
  it("picks the label and value columns", () => {
    expect(renderDataList([{ bank_ticker: "ZIRAAT", amount: 43520620 }]))
      .toBe("1. ZIRAAT — 43.520.620");
  });

  it("returns null when there is no numeric column to show", () => {
    expect(renderDataList([{ a: "x", b: "y" }])).toBeNull();
  });

  it("renders a null value as a dash rather than dropping the row", () => {
    expect(renderDataList([{ t: "A", v: null }, { t: "B", v: 5 }]))
      .toBe("1. A — —\n2. B — 5");
  });
});

describe("checkSectorAggregation — overlapping bank_type_code groups", () => {
  it("rejects the query that reported the sector 3.8x too large", () => {
    const r = checkSectorAggregation(
      "SELECT SUM(amount_total) FROM balance_sheet WHERE year=2026 AND month=5 AND item_order=26",
    );
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.error).toContain("bank_type_code");
  });

  it("allows a single-group filter — 10001 IS the sector total", () => {
    expect(checkSectorAggregation(
      "SELECT SUM(amount_total) FROM balance_sheet WHERE bank_type_code='10001' " +
      "AND item_name='TOPLAM AKTİFLER'",
    ).ok).toBe(true);
  });

  it("allows an explicit IN list and a GROUP BY", () => {
    expect(checkSectorAggregation(
      "SELECT SUM(total_amount) FROM loans WHERE bank_type_code IN ('10002','10003') " +
      "AND item_order=1",
    ).ok).toBe(true);
    expect(checkSectorAggregation(
      "SELECT bank_type_code, item_name, SUM(total_amount) FROM deposits " +
      "GROUP BY bank_type_code, item_name",
    ).ok).toBe(true);
  });

  it("leaves non-aggregating reads alone", () => {
    expect(checkSectorAggregation(
      "SELECT bank_type_code, amount_total FROM balance_sheet WHERE year=2026",
    ).ok).toBe(true);
  });

  it("does not touch the per-bank tables, which have no bank_type_code", () => {
    expect(checkSectorAggregation(
      "SELECT SUM(amount) FROM bank_audit_profit_loss WHERE period='2026Q1'",
    ).ok).toBe(true);
  });

  it("is not fooled by a filter hidden in a comment", () => {
    expect(checkSectorAggregation(
      "SELECT SUM(amount_total) FROM balance_sheet -- bank_type_code='10001'",
    ).ok).toBe(false);
  });
});

describe("regression: the exact queries that shipped wrong answers", () => {
  // Recovered from bot_queries after the bot reported the sector's total assets
  // as 198,874,433 million TL (true figure 51,760,765 — it summed all ten
  // overlapping bank_type_code groups). Kept verbatim so the gate is always
  // tested against what really happened, not a tidied-up approximation.
  const SECTOR_SUM =
    "WITH latest AS ( SELECT year, month FROM balance_sheet ORDER BY year DESC, " +
    "month DESC LIMIT 1 ) SELECT SUM(amount_total) AS total_assets_million_tl " +
    "FROM balance_sheet b JOIN latest l ON b.year = l.year AND b.month = l.month " +
    "WHERE b.item_name = 'TOPLAM AKTİFLER'";

  it("rejects it", () => {
    expect(checkSectorAggregation(SECTOR_SUM).ok).toBe(false);
  });

  it("accepts it once bank_type_code is pinned to the sector row", () => {
    expect(checkSectorAggregation(
      SECTOR_SUM.replace("WHERE b.item_name", "WHERE b.bank_type_code='10001' AND b.item_name"),
    ).ok).toBe(true);
  });
});

describe("row cap — our own truncation must be detectable, not silent", () => {
  it("over-fetches by one so a truncated population can be announced", () => {
    const r = sanitizeSelect("SELECT a FROM t", 200);
    expect(r.ok).toBe(true);
    if (r.ok) {
      expect(r.sql).toContain("LIMIT 201");
      expect(r.capImposed).toBe(true);
    }
  });

  it("caps a LIMIT inside a SUBQUERY at the top level", () => {
    // The old test ran against the whole statement, so this passed uncapped —
    // and a 327-row multi-period ranking came back as 200 with no warning.
    const r = sanitizeSelect(
      "SELECT bank_ticker FROM bank_audit_stages WHERE period IN " +
      "(SELECT DISTINCT period FROM bank_audit_stages ORDER BY period DESC LIMIT 8)",
      200,
    );
    expect(r.ok).toBe(true);
    if (r.ok) {
      expect(r.capImposed).toBe(true);
      expect(r.sql.trim().endsWith("LIMIT 201")).toBe(true);
    }
  });

  it("respects a model LIMIT below the cap and reports no cap", () => {
    const r = sanitizeSelect("SELECT a FROM t LIMIT 40", 200);
    expect(r.ok).toBe(true);
    if (r.ok) {
      expect(r.sql).toContain("LIMIT 40");
      expect(r.capImposed).toBe(false);
    }
  });

  it("clamps a model LIMIT above the cap", () => {
    const r = sanitizeSelect("SELECT a FROM t LIMIT 5000", 200);
    expect(r.ok).toBe(true);
    if (r.ok) {
      expect(r.sql).toContain("LIMIT 201");
      expect(r.capImposed).toBe(true);
    }
  });
});

describe("checkSectorAggregation — overlap is reachable through an IN list", () => {
  it("rejects 10001 combined with its own licence partition (exactly 2x)", () => {
    const r = checkSectorAggregation(
      "SELECT SUM(amount_total) FROM balance_sheet WHERE item_order=26 AND " +
      "bank_type_code IN ('10001','10002','10003','10004')",
    );
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.error).toContain("more than one view");
  });

  it("rejects two partitions mixed (licence + ownership)", () => {
    expect(checkSectorAggregation(
      "SELECT SUM(amount_total) FROM balance_sheet WHERE item_order=26 AND " +
      "bank_type_code IN ('10002','10003','10004','10005','10006','10007')",
    ).ok).toBe(false);
  });

  it("rejects an OR chain drawn from two partitions", () => {
    expect(checkSectorAggregation(
      "SELECT SUM(amount_total) FROM balance_sheet WHERE item_order=26 AND " +
      "(bank_type_code='10002' OR bank_type_code='10005')",
    ).ok).toBe(false);
  });

  it("allows one whole partition", () => {
    expect(checkSectorAggregation(
      "SELECT SUM(amount_total) FROM balance_sheet WHERE item_order=26 AND " +
      "bank_type_code IN ('10002','10003','10004')",
    ).ok).toBe(true);
  });

  it("rejects summing every line item even with the bank type pinned", () => {
    // 8.1x on balance_sheet: leaf lines, subtotals and the grand total together.
    const r = checkSectorAggregation(
      "SELECT SUM(amount_total) FROM balance_sheet WHERE currency='TL' AND " +
      "bank_type_code='10001' AND year=2026 AND month=4",
    );
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.error).toContain("ALL line items");
  });

  it("gates weekly_series too — it carries the same overlapping codes", () => {
    expect(checkSectorAggregation(
      "SELECT SUM(value) FROM weekly_series WHERE period_date='2026-07-10'",
    ).ok).toBe(false);
  });
});

describe("formatTrNumber — fractions must survive", () => {
  it("keeps a small coverage fraction instead of rounding it to 0,01", () => {
    // stage3_coverage is stored as a fraction; toFixed(2) flattened the whole
    // signal and trailing-zero stripping produced the malformed "0,".
    expect(formatTrNumber(0.0083)).toContain("0,008");
    expect(formatTrNumber(0.004)).not.toBe("0,");
    expect(formatTrNumber(0.004)).toContain("0,004");
  });

  it("never emits a bare separator", () => {
    for (const v of [0.004, 0.0001, -0.004, 0.00001]) {
      expect(formatTrNumber(v).endsWith(",")).toBe(false);
    }
  });

  it("still formats money with two decimals", () => {
    expect(formatTrNumber(43520620)).toBe("43.520.620");
    expect(formatTrNumber(20.85)).toBe("20,85");
  });
});
