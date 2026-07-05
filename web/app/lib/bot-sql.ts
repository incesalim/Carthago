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
