import { describe, expect, it } from "vitest";
import {
  DEFAULT_ROW_CAP,
  checkTickerEnumeration,
  enumeratedTickers,
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
