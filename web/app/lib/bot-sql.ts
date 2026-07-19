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
  | { ok: true; sql: string }
  | { ok: false; error: string };

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

  // Enforce a row cap on the top-level query. If the model already wrote a
  // LIMIT anywhere we leave it (the JS-side slice in the caller is the real
  // backstop); otherwise append one.
  if (!/\blimit\b/i.test(lower)) {
    sql = `${sql} LIMIT ${rowCap}`;
  }

  return { ok: true, sql };
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
  for (const m of clean.matchAll(/bank_ticker\s*=\s*'([^']+)'/gi)) {
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
  if (mentioned.length) return { ok: true, sql };

  return {
    ok: false,
    error:
      `the query hardcodes ${tickers.length} bank tickers the question never ` +
      `named (${tickers.slice(0, 5).join(", ")}…). Do not choose which banks to ` +
      `include — let the WHERE clause select them, so every bank with data is ` +
      `covered`,
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

/** Turkish thousand separators: 43520620 -> "43.520.620". Decimals keep a comma. */
export function formatTrNumber(v: number): string {
  const neg = v < 0;
  const abs = Math.abs(v);
  const whole = Math.trunc(abs);
  const frac = abs - whole;
  let s = String(whole).replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  if (frac > 0) s += "," + frac.toFixed(2).slice(2).replace(/0+$/, "");
  return (neg ? "-" : "") + s;
}

/**
 * Render query rows as a numbered list, from the DATA rather than from prose.
 *
 * Takes the first non-numeric column as the label and the first numeric one as
 * the value — which covers the shape this matters for (ticker + figure). Returns
 * null when the rows aren't that shape, so the caller leaves the answer alone.
 */
export function renderDataList(rows: Record<string, unknown>[]): string | null {
  if (!rows.length) return null;
  const cols = Object.keys(rows[0]);
  const isNum = (c: string) =>
    rows.every((r) => r[c] === null || typeof r[c] === "number");
  const valueCol = cols.find(isNum);
  const labelCol = cols.find((c) => c !== valueCol);
  if (!valueCol || !labelCol) return null;

  return rows
    .map((r, i) => {
      const v = r[valueCol];
      const shown = typeof v === "number" ? formatTrNumber(v) : "—";
      return `${i + 1}. ${String(r[labelCol] ?? "")} — ${shown}`;
    })
    .join("\n");
}

/** A prose line that is really a data row the model retyped. */
const LIST_LINE = /^\s*(?:\d+[.)]|[-•*])\s+\S/;

/**
 * Replace the model's hand-typed list with one rendered from the actual rows,
 * keeping everything else it wrote (caption, units, caveats).
 *
 * The model retypes every figure into prose, so a long ranking is 38 chances to
 * drop a digit, and two runs of the same question formatted differently because
 * the provider chain answered from different models. Rendering the list from the
 * rows makes both impossible: the numbers are the queried ones by construction,
 * and the layout no longer depends on which model replied.
 *
 * Conservative by design — only fires on a genuine ranking (enough rows, and the
 * model clearly produced a list), and returns the prose untouched otherwise.
 */
export function substituteDataList(
  prose: string,
  rows: Record<string, unknown>[],
  minRows = 5,
): string {
  if (rows.length < minRows) return prose;
  const lines = prose.split("\n");
  const listCount = lines.filter((l) => LIST_LINE.test(l)).length;
  if (listCount < 3) return prose; // not a listing — leave it alone

  const rendered = renderDataList(rows);
  if (!rendered) return prose;

  const before: string[] = [];
  const after: string[] = [];
  let seen = false;
  for (const l of lines) {
    if (LIST_LINE.test(l)) { seen = true; continue; }
    (seen ? after : before).push(l);
  }
  return [
    before.join("\n").trim(),
    rendered,
    after.join("\n").trim(),
  ].filter(Boolean).join("\n\n");
}

/** Every distinct numeric token in `text` (ignores thousands separators). */
export function numbersIn(text: string): number[] {
  const out: number[] = [];
  for (const m of text.replace(/,/g, "").matchAll(/-?\d+(?:\.\d+)?/g)) {
    out.push(parseFloat(m[0]));
  }
  return out;
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
