import { describe, expect, it } from "vitest";
import {
  DEFAULT_ROW_CAP,
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
    if (r.ok) expect(r.sql).toBe(`SELECT bank_ticker FROM bank_audit_capital LIMIT ${DEFAULT_ROW_CAP}`);
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
    if (!r.ok) expect(r.error).toContain("hardcodes 4 bank tickers");
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
    const prose = "2026Q1 sıralaması:\n1. B1 — 6.000.000\n2. B2 — 5.000.000\n3. WRONG — 999\nKaynak: BDDK.";
    const out = substituteDataList(prose, rows);
    expect(out).toContain("2026Q1 sıralaması:");   // caption kept
    expect(out).toContain("Kaynak: BDDK.");        // trailing prose kept
    expect(out).not.toContain("WRONG");            // the model's line is gone
    expect(out).toContain("6. B6 — 1.000.000");    // all rows rendered, not just typed ones
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
    ].join("\n");
    const out = substituteDataList(prose, rows);
    expect(out).toContain("1. B1 — 6.000.000");  // corrected from the rows
    expect(out).not.toContain("9.999.999");
    expect(out).toContain("6. B6 — 1.000.000");  // all 6 rows, not the 3 typed
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
