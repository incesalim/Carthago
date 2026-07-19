/**
 * Guardrails for the LLM-generated SQL the Telegram bot runs against D1.
 *
 * The DB is the SAME one the pipeline writes, so the ONLY acceptable statements
 * are read-only single SELECTs. Everything here is defence-in-depth against a
 * prompt-injected or hallucinated write: we never trust the model, we gate the
 * SQL. The whole dataset is already public via the dashboard, so the risks we
 * guard are (a) writes/DDL corrupting data and (b) runaway result size.
 */

/** Tables that exist but must not be exposed to a public querier. */
export const DENY_TABLES = new Set(["bot_usage", "d1_migrations"]);

// Data-modifying / DDL / dangerous verbs. Matched as whole words (case-insensitive)
// after comments are stripped. None is a table/column name in our schema, so a
// legitimate SELECT never contains them.
const FORBIDDEN = [
  "insert", "update", "delete", "drop", "alter", "create", "replace",
  "attach", "detach", "pragma", "vacuum", "reindex", "trigger", "grant",
  "revoke", "truncate", "into", "commit", "rollback", "savepoint",
];

export const MAX_SQL_LEN = 2000;
export const DEFAULT_ROW_CAP = 200;

export type SanitizeResult =
  | { ok: true; sql: string; capImposed?: boolean }
  | { ok: false; error: string };

/**
 * Remove parenthesised groups so a clause can be tested at the TOP level only.
 *
 * `WHERE period IN (SELECT … ORDER BY period DESC LIMIT 8)` contains the word
 * LIMIT, but the outer query has none — testing the raw string let that pass
 * uncapped.
 */
export function stripParenGroups(sql: string): string {
  let out = sql, prev = "";
  while (out !== prev) {
    prev = out;
    out = out.replace(/\([^()]*\)/g, " ");
  }
  return out;
}

/** Remove `/* … *​/` and `-- …` comments so they can't hide keywords or `;`. */
export function stripSqlComments(sql: string): string {
  return sql
    .replace(/\/\*[\s\S]*?\*\//g, " ")
    .replace(/--[^\n\r]*/g, " ");
}

/**
 * Validate that `raw` is a single read-only SELECT/WITH statement and return a
 * capped, executable form. Rejects anything that could write, run multiple
 * statements, touch a denied table, or is over-long.
 */
export function sanitizeSelect(
  raw: string,
  rowCap: number = DEFAULT_ROW_CAP,
): SanitizeResult {
  if (!raw || !raw.trim()) return { ok: false, error: "empty query" };

  // Work on a comment-free copy for all safety checks.
  let sql = stripSqlComments(raw).trim();
  // SQLite/D1 has no ILIKE; models emit it often. Rewriting to LIKE is safe
  // (ILIKE would only ever error) and keeps the query working.
  sql = sql.replace(/\bilike\b/gi, "LIKE");
  if (sql.length > MAX_SQL_LEN) {
    return { ok: false, error: "query too long" };
  }

  // Strip a single trailing semicolon; any remaining one means multi-statement.
  sql = sql.replace(/;\s*$/, "");
  if (sql.includes(";")) {
    return { ok: false, error: "only a single statement is allowed" };
  }

  if (!/^\s*(with|select)\b/i.test(sql)) {
    return { ok: false, error: "only SELECT / WITH queries are allowed" };
  }

  const lower = sql.toLowerCase();
  for (const kw of FORBIDDEN) {
    if (new RegExp(`\\b${kw}\\b`).test(lower)) {
      return { ok: false, error: `disallowed keyword: ${kw}` };
    }
  }
  for (const t of DENY_TABLES) {
    if (new RegExp(`\\b${t}\\b`).test(lower)) {
      return { ok: false, error: `table not available: ${t}` };
    }
  }

  // Row cap. Two things went wrong here before:
  //
  //  1. The LIMIT test ran against the WHOLE statement, so a LIMIT inside a
  //     subquery suppressed the outer cap entirely.
  //  2. When the cap DID apply, it silently truncated the population and the
  //     caller reported the truncated count as if it were the whole result. On
  //     a real "NPL ratio since 2024, all banks" query that is 327 rows cut to
  //     200 — dropping Ziraat, VakıfBank, Yapı Kredi, TEB and TSKB with no
  //     error and no warning.
  //
  // So: look for a TOP-LEVEL limit only, clamp the model's own to rowCap, and
  // fetch ONE extra row so the caller can tell "exactly full" from "there was
  // more" and say so.
  const topLevel = stripParenGroups(sql);
  const own = topLevel.match(/\blimit\s+(\d+)/i);
  if (own) {
    const asked = parseInt(own[1], 10);
    if (asked > rowCap) {
      sql = sql.replace(/\blimit\s+\d+(?![\s\S]*\blimit\b)/i, `LIMIT ${rowCap + 1}`);
      return { ok: true, sql, capImposed: true };
    }
    return { ok: true, sql, capImposed: false };
  }
  return { ok: true, sql: `${sql} LIMIT ${rowCap + 1}`, capImposed: true };
}

/** Fold Turkish letters to ASCII so "Garanti"/"GARANTİ"/"İş" compare cleanly. */
function foldTr(s: string): string {
  return s
    .replace(/[İIı]/g, "i").replace(/[Şş]/g, "s").replace(/[Ğğ]/g, "g")
    .replace(/[Üü]/g, "u").replace(/[Öö]/g, "o").replace(/[Çç]/g, "c")
    .toLowerCase();
}

/**
 * Bank tickers the SQL pins to literal values, e.g. `bank_ticker IN ('A','B')`
 * or `p.bank_ticker = 'A' OR p.bank_ticker = 'B'`.
 */
export function enumeratedTickers(sql: string): string[] {
  const out = new Set<string>();
  const clean = stripSqlComments(sql);
  for (const m of clean.matchAll(
    /bank_ticker\s+in\s*\(([^)]*)\)/gi,
  )) {
    for (const lit of m[1].matchAll(/'([^']+)'/g)) out.add(lit[1].toUpperCase());
  }
  // NOT IN narrows just as effectively, and a LIKE chain or a VALUES list is the
  // same choice wearing a different hat.
  for (const m of clean.matchAll(/bank_ticker\s+not\s+in\s*\(([^)]*)\)/gi)) {
    for (const lit of m[1].matchAll(/'([^']+)'/g)) out.add(lit[1].toUpperCase());
  }
  for (const m of clean.matchAll(/bank_ticker\s*(?:=|<>|!=|like)\s*'([^'%_]+)'/gi)) {
    out.add(m[1].toUpperCase());
  }
  return [...out];
}

/**
 * Reject SQL that decides FOR ITSELF which banks to answer about.
 *
 * The bot was asked to rank all banks by branch productivity and answered for
 * eight, having written its own `IN (…)` list of roughly ten tickers. It then
 * reported the gaps *within its own list* ("GARAN and HALKB have no data") as
 * though they were gaps in the dataset — so a partial answer read as an
 * exhaustive one. Twenty-seven banks had the data.
 *
 * The rule: if the query pins bank_ticker to two or more literals and the user
 * named none of them, the model chose the population rather than the database.
 * A question that DOES name banks ("compare Garanti and Akbank") is untouched,
 * and a single-bank query is always allowed.
 *
 * `names` maps ticker -> display name so "Garanti" in the question satisfies
 * 'GARAN' in the SQL.
 */
export function checkTickerEnumeration(
  sql: string,
  question: string,
  names: Record<string, string> = {},
): SanitizeResult {
  const tickers = enumeratedTickers(sql);
  if (tickers.length < 2) return { ok: true, sql };

  const q = foldTr(question);
  const mentioned = tickers.filter((t) => {
    if (q.includes(foldTr(t))) return true;
    const name = names[t];
    // Match on the distinctive first word ("Garanti" for "Garanti BBVA"), which
    // is how people actually refer to these banks.
    return !!name && q.includes(foldTr(name.split(/\s+/)[0]));
  });
  // EVERY pinned ticker must have been named. Accepting the list because ONE
  // matched is bug #2 with a one-word bypass: "how does Garanti compare with
  // the other banks?" + IN ('GARAN','AKBNK','ISCTR','HALKB','YKBNK') answers
  // for 5 of 38 and reads as exhaustive.
  if (mentioned.length === tickers.length) return { ok: true, sql };
  const unnamed = tickers.filter((t) => !mentioned.includes(t));

  return {
    ok: false,
    error:
      `the query hardcodes bank tickers the question never named ` +
      `(${unnamed.slice(0, 5).join(", ")}${unnamed.length > 5 ? "…" : ""}). Do not ` +
      `choose which banks to include — let the WHERE clause select them, so ` +
      `every bank with data is covered`,
  };
}

/**
 * Pull an executable query out of an LLM reply. Prefers a ```sql fenced block;
 * falls back to a bare statement that starts with SELECT/WITH. Returns null if
 * the reply carries no query (i.e. it's a plain-text answer).
 */
export function extractSql(text: string): string | null {
  const fenced = text.match(/```(?:sql)?\s*([\s\S]*?)```/i);
  if (fenced && fenced[1].trim()) return fenced[1].trim();
  const m = text.match(/\b(with|select)\b[\s\S]+/i);
  if (m && /\bfrom\b/i.test(m[0])) return m[0].trim();
  return null;
}

/** Format D1 result rows as a compact monospace table for Telegram / the LLM. */
export function formatTable(
  rows: Record<string, unknown>[],
  maxRows = 20,
  maxCell = 40,
): string {
  if (!rows.length) return "(no rows)";
  const cols = Object.keys(rows[0]);
  const cell = (v: unknown): string => {
    if (v === null || v === undefined) return "";
    let s = typeof v === "number" ? String(v) : String(v);
    if (s.length > maxCell) s = s.slice(0, maxCell - 1) + "…";
    return s;
  };
  const shown = rows.slice(0, maxRows);
  const widths = cols.map((c) =>
    Math.max(c.length, ...shown.map((r) => cell(r[c]).length)),
  );
  const line = (vals: string[]) =>
    vals.map((v, i) => v.padEnd(widths[i])).join("  ").trimEnd();
  const out = [line(cols), line(widths.map((w) => "-".repeat(w)))];
  for (const r of shown) out.push(line(cols.map((c) => cell(r[c]))));
  if (rows.length > maxRows) out.push(`… (+${rows.length - maxRows} more rows)`);
  return out.join("\n");
}

/** Sector-aggregate tables, all keyed by the overlapping bank_type_code. */
const SECTOR_TABLES = [
  "balance_sheet", "income_statement", "loans", "deposits",
  "financial_ratios", "other_data", "weekly_series",
];

/**
 * The three partitions of the sector. Each re-covers its parent in full, so
 * mixing codes from two of them — or adding anything to 10001 — double-counts.
 */
const BANK_TYPE_PARTITIONS: Record<string, string[]> = {
  licence: ["10002", "10003", "10004"],
  ownership: ["10005", "10006", "10007"],
  depositSplit: ["10008", "10009", "10010"],
};

/** Literal bank_type_code values the SQL pins, however it spells the filter. */
export function enumeratedBankTypes(sql: string): string[] {
  const clean = stripSqlComments(sql);
  const out = new Set<string>();
  for (const m of clean.matchAll(/bank_type_code\s+in\s*\(([^)]*)\)/gi)) {
    for (const lit of m[1].matchAll(/'(\d+)'/g)) out.add(lit[1]);
  }
  for (const m of clean.matchAll(/bank_type_code\s*=\s*'(\d+)'/gi)) out.add(m[1]);
  return [...out];
}

/**
 * True when a set of bank_type_codes spans more than one view of the sector.
 *
 * 10001 IS the whole sector, so pairing it with anything counts those banks
 * twice; and the three partitions each cover the sector independently, so
 * drawing from two of them does the same.
 */
function mixesPartitions(codes: string[]): boolean {
  if (codes.length < 2) return false;
  if (codes.includes("10001")) return true;
  const hit = Object.values(BANK_TYPE_PARTITIONS)
    .filter((part) => codes.some((c) => part.includes(c))).length;
  return hit > 1;
}

/**
 * Reject an aggregate over the sector tables that doesn't pin bank_type_code.
 *
 * The codes are THREE overlapping partitions of one sector, plus 10001 which is
 * the sector itself. Summing across them counts the same banks repeatedly:
 * asked for the sector's total assets, the bot summed all ten and answered
 * 198,874,433 million TL against a true 51,760,765 — 3.8x too high, and entirely
 * plausible-looking. No error, no warning; the arithmetic was correct and the
 * population was wrong.
 *
 * Allowed: a single-group filter (`bank_type_code = '10001'`), an explicit IN
 * list, or GROUP BY bank_type_code — all of which keep the groups apart.
 * Rejected: SUM/AVG/TOTAL over a sector table with the column unconstrained.
 */
export function checkSectorAggregation(sql: string): SanitizeResult {
  const clean = stripSqlComments(sql);
  const lower = clean.toLowerCase();

  const touchesSector = SECTOR_TABLES.some((t) =>
    new RegExp(`\\b(?:from|join)\\s+${t}\\b`, "i").test(lower),
  );
  if (!touchesSector) return { ok: true, sql };

  // Only aggregation can conflate the groups; a plain SELECT of many rows can't.
  if (!/\b(?:sum|avg|total)\s*\(/i.test(lower)) return { ok: true, sql };

  const codes = enumeratedBankTypes(clean);
  const grouped = /group\s+by[^;]*\bbank_type_code\b/i.test(lower);

  // An IN list is NOT automatically safe: IN ('10001','10002','10003','10004')
  // sums the sector on top of its own licence partition — exactly 2.00x — and
  // reads as a careful, explicit filter.
  if (mixesPartitions(codes)) {
    return {
      ok: false,
      error:
        `it aggregates over bank_type_code ${codes.join(", ")}, which span more ` +
        "than one view of the SAME sector. 10001 is already the whole sector, " +
        "and 10002-10004 (by licence), 10005-10007 (by ownership) and " +
        "10008-10010 each re-cover it, so this counts banks twice. Pick ONE " +
        "code, or one partition, or GROUP BY bank_type_code",
    };
  }

  if (!codes.length && !grouped) {
    return {
      ok: false,
      error:
        "it aggregates a sector table without constraining bank_type_code. Those " +
        "codes are overlapping partitions of the SAME sector, so summing across " +
        "them counts banks two or three times. Use bank_type_code='10001' for the " +
        "whole sector (it is already the total), or GROUP BY bank_type_code",
    };
  }

  // Pinning the bank type is not enough: these tables interleave line items with
  // subtotals and a grand total, so SUM over an unconstrained item column adds
  // the balance sheet to itself — 8.1x on balance_sheet, 2x on loans. Correct
  // arithmetic, wrong population, no error.
  const rowPinned =
    /\b(?:item_order|item_name|is_subtotal|category|item_id)\b\s*(?:=|\bin\b|\blike\b|\bis\b)/i.test(lower) ||
    /group\s+by[^;]*\b(?:item_order|item_name|category|item_id)\b/i.test(lower);
  if (!rowPinned) {
    return {
      ok: false,
      error:
        "it sums a sector table across ALL line items. These tables hold leaf " +
        "lines, subtotals AND a grand total together, so this adds the balance " +
        "sheet to itself (8x on balance_sheet, 2x on loans). Read the labelled " +
        "total row instead — e.g. item_name='TOPLAM AKTİFLER' — or filter " +
        "is_subtotal=0, or GROUP BY item_name",
    };
  }

  return { ok: true, sql };
}

/** Turkish thousand separators: 43520620 -> "43.520.620". Decimals keep a comma. */
export function formatTrNumber(v: number): string {
  const neg = v < 0;
  const abs = Math.abs(v);
  const whole = Math.trunc(abs);
  const frac = abs - whole;
  let s = String(whole).replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  if (frac > 0) {
    // Two decimals is right for money but destroys a fraction: stage coverage is
    // stored as 0.0083, and toFixed(2) makes that "0,01" — or, once trailing
    // zeros are stripped, the malformed "0,". Keep enough significant digits
    // that small values survive, and never emit a bare separator.
    const decimals = abs >= 1 ? 2 : Math.min(6, Math.max(2, -Math.floor(Math.log10(frac)) + 1));
    const fracStr = frac.toFixed(decimals).slice(2).replace(/0+$/, "");
    if (fracStr) s += "," + fracStr;
  }
  return (neg ? "-" : "") + s;
}

/**
 * Render query rows as a numbered list, from the DATA rather than from prose.
 *
 * Takes the first non-numeric column as the label and the first numeric one as
 * the value — which covers the shape this matters for (ticker + figure). Returns
 * null when the rows aren't that shape, so the caller leaves the answer alone.
 */
const LIST_LINE = /^\s*(?:\d+\s*[.)\]]|\(\d+\)|[-–—•·▪‣◦*])\s*\S/;

/** Labels the model typed in its list, for comparing against candidate rows. */
function typedLabels(lines: string[]): string[] {
  const out: string[] = [];
  for (const l of lines) {
    if (!LIST_LINE.test(l)) continue;
    const body = l.replace(/^\s*(?:\d+\s*[.)\]]|\(\d+\)|[-–—•·▪‣◦*])\s*/, "");
    const label = body.split(/\s+[—–:-]\s+|\s{2,}/)[0].trim();
    if (label) out.push(label.toUpperCase());
  }
  return out;
}

/**
 * Render query rows as a numbered list, from the DATA rather than from prose.
 *
 * `valueCol` should be the column the answer is actually ABOUT — normally the
 * one the query sorted by. Picking the first numeric column instead prints the
 * wrong figure under a right-looking caption: for
 * `SELECT bank_ticker, period, stage3_amount, total_amount, npl_pct … ORDER BY
 * npl_pct DESC` it emits the absolute Stage-3 amount under "ranked by NPL
 * ratio", correctly ordered and entirely wrong.
 */
export function renderDataList(
  rows: Record<string, unknown>[],
  valueCol?: string,
): string | null {
  if (!rows.length) return null;
  const cols = Object.keys(rows[0]);
  const isNum = (c: string) =>
    rows.some((r) => typeof r[c] === "number") &&
    rows.every((r) => r[c] === null || typeof r[c] === "number");
  const numeric = cols.filter(isNum);
  const value = valueCol && numeric.includes(valueCol) ? valueCol : numeric[0];
  const label = cols.find((c) => c !== value && !isNum(c)) ?? cols.find((c) => c !== value);
  if (!value || !label) return null;

  return rows
    .map((r, i) => {
      const v = r[value];
      const shown = typeof v === "number" ? formatTrNumber(v) : "—";
      return `${i + 1}. ${String(r[label] ?? "")} — ${shown}`;
    })
    .join("\n");
}

/** The column an ORDER BY sorts on — the one the answer is really about. */
export function orderByColumn(sql: string): string | undefined {
  const m = stripSqlComments(sql).match(/order\s+by\s+([a-z_][a-z0-9_]*)/i);
  return m ? m[1].toLowerCase() : undefined;
}

/**
 * Replace the model's hand-typed list with one rendered from the actual rows,
 * keeping everything else it wrote (caption, units, caveats).
 *
 * The model retypes every figure into prose, so a long ranking is 38 chances to
 * drop a digit, and two runs of the same question formatted differently because
 * the provider chain answered from different models. Rendering the list from the
 * rows makes both impossible.
 *
 * Three things keep it honest, each learned from a real failure:
 *  • LABEL OVERLAP — `rows` is whatever the LAST query returned, which is not
 *    always the query the answer is about. Without this check a follow-up
 *    "SELECT period, COUNT(*)" replaced a 38-bank ranking with a list of periods
 *    under the ranking's caption.
 *  • RESPECTING A DELIBERATE TOP-N — if the model listed 5 of 38 rows on
 *    purpose, render the first 5, not all 38, or the list contradicts the
 *    caption above it.
 *  • valueCol from ORDER BY — see renderDataList.
 */
export function substituteDataList(
  prose: string,
  rows: Record<string, unknown>[],
  minRows = 5,
  sql?: string,
): string {
  if (rows.length < minRows) return prose;
  // Strip PAIRED emphasis only. Stripping every '*' also ate leading bullets,
  // which made "* ZIRAAT — 1000" undetectable and left that model's figures
  // untouched while another model's were re-rendered.
  const lines = prose.replace(/\*\*/g, "").replace(/`/g, "").split("\n");
  const listLines = lines.filter((l) => LIST_LINE.test(l));
  if (listLines.length < 3) return prose;

  const value = sql ? orderByColumn(sql) : undefined;
  const rendered = renderDataList(rows, value);
  if (!rendered) return prose;

  // Do the rows actually correspond to what the model listed?
  const typed = typedLabels(lines);
  const rowText = JSON.stringify(rows).toUpperCase();
  const hits = typed.filter((t) => t.length > 1 && rowText.includes(t)).length;
  if (!typed.length || hits / typed.length < 0.5) return prose;

  // A deliberate top-N stays a top-N.
  const slice = typed.length < rows.length ? rows.slice(0, typed.length) : rows;
  const finalList = renderDataList(slice, value);
  if (!finalList) return prose;

  const before: string[] = [];
  const after: string[] = [];
  let seen = false;
  for (const l of lines) {
    if (LIST_LINE.test(l)) { seen = true; continue; }
    (seen ? after : before).push(l);
  }
  return [
    before.join("\n").trim(),
    finalList,
    after.join("\n").trim(),
  ].filter(Boolean).join("\n\n");
}

export function numbersIn(text: string): number[] {
  const out: number[] = [];
  for (const m of text.replace(/,/g, "").matchAll(/-?\d+(?:\.\d+)?/g)) {
    out.push(parseFloat(m[0]));
  }
  return out;
}

/**
 * Figures written in TURKISH notation, as the bot's own replies are:
 * '.' groups thousands and ',' is the decimal separator.
 *
 * Parsing those as English splits every correct figure into fragments —
 * "51.760.765" reads as 51.760 and 765, neither of which is in the data. That
 * made the invented-number guard fire on every well-formed answer, spend its one
 * correction round on noise, and then wave through the genuinely wrong figure
 * that followed (%36,21 where the truth was %35,96).
 *
 * Dates and periods are blanked first: "2025-05" and "2026Q1" are labels, not
 * quantities, and flagging them is the same false positive in another costume.
 */
export function numbersInProse(text: string): number[] {
  const masked = text
    .replace(/\d{4}-\d{2}(?:-\d{2})?/g, " ")   // 2025-05, 2026-05-31
    .replace(/\d{4}\s*Q\d/gi, " ");            // 2026Q1
  const out: number[] = [];
  for (const m of masked.matchAll(/-?\d[\d.]*(?:,\d+)?/g)) {
    const n = parseFloat(m[0].replace(/\./g, "").replace(",", "."));
    if (Number.isFinite(n)) out.push(n);
  }
  return out;
}

/**
 * Figures in a Turkish-formatted answer that appear nowhere in the data.
 *
 * `allowed` comes from the JSON rows, where numbers are plain — so the two
 * sides are parsed differently on purpose.
 *
 * Only sizeable figures are checked. Ranks, list numbers and small counts are
 * legitimately absent from the rows, and flagging them is what turns a guard
 * into noise.
 */
export function unsupportedFigures(answer: string, allowed: number[]): number[] {
  return numbersInProse(answer).filter(
    (n) =>
      Math.abs(n) >= 1000 &&
      !allowed.some(
        (a) =>
          Math.abs(a - n) < 0.01 ||
          Math.abs(Math.abs(a) - n) < 0.01 ||
          Math.abs(a - n) / Math.max(Math.abs(a), 1) < 0.0001,
      ),
  );
}

/**
 * Numbers in `answer` that don't (approximately) appear in `allowed` and aren't
 * bound to a label (e.g. "Stage-3", "CET1", "1-year"). Used only to flag a
 * synthesized sentence as possibly-approximate — the raw data table shown
 * alongside is the ground truth.
 */
export function inventedNumbers(answer: string, allowed: number[]): string[] {
  const DASHES = "-‐‑‒–—";
  const clean = answer.replace(/,/g, "");
  const out: string[] = [];
  for (const m of clean.matchAll(/-?\d+(?:\.\d+)?/g)) {
    const start = m.index ?? 0;
    // label-bound on the left? (e.g. "Stage-3")
    let j = start - 1;
    while (j >= 0 && DASHES.includes(clean[j])) j -= 1;
    if (j >= 0 && /[a-z]/i.test(clean[j])) continue;
    // label-bound on the right? (e.g. "1-year")
    const end = start + m[0].length;
    if (end < clean.length && DASHES.includes(clean[end]) && /[a-z]/i.test(clean[end + 1] ?? "")) {
      continue;
    }
    const n = parseFloat(m[0]);
    const known = allowed.some(
      (a) => Math.abs(a - n) < 0.01 || Math.abs(Math.abs(a) - n) < 0.01,
    );
    if (!known) out.push(m[0]);
  }
  return out;
}
