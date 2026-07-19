/**
 * Resolution for the public data API: series code -> observations.
 *
 * A series code (`BDDK.T01.I005.10001.TOT`) is an IDENTIFIER, not a query. It
 * is never parsed into SQL directly — it's looked up in `api_series`, which
 * holds the real filter values (source table, table number, item key, bank type,
 * value column). That indirection is what lets a published code keep working
 * when the underlying storage shifts: `other_data` keys items by item_name
 * because its item_order collides inside table 12, and no caller should ever
 * have to know that.
 *
 * Everything here is read-only and every value column is resolved from the
 * catalog, never from caller input — see `buildObservationQuery`.
 */
import { allDirect } from "./db";

/** Max series a single /series call may request, mirroring EVDS's own cap. */
export const MAX_SERIES_PER_REQUEST = 20;
/** Max observations returned per series before truncation. ~50 years monthly. */
export const MAX_OBS_PER_SERIES = 2000;

export interface SeriesMeta {
  series_code: string;
  dataset: string;
  frequency: "monthly" | "weekly";
  source_table: string;
  table_number: number | null;
  category: string | null;
  item_key: string;
  item_name: string;
  /** BDDK's own English label. Null where BDDK publishes none (all weekly
   *  datasets, and the few other_data lines whose item_order collides). */
  item_name_en: string | null;
  bank_type_code: string;
  report_currency: string | null;
  value_column: string;
  unit: string | null;
  start_date: string | null;
  end_date: string | null;
  obs_count: number | null;
}

export interface Observation {
  date: string;
  value: number | null;
}

/** A code is 5 dot-separated segments: BDDK.<DATASET>.<ITEM>.<BANKTYPE>.<COL>. */
const CODE_RE = /^BDDK\.[A-Z0-9]+\.I[0-9_]+\.[0-9]{5}\.[A-Z0-9]+$/;

export function isValidCodeShape(code: string): boolean {
  return CODE_RE.test(code);
}

/**
 * Split the EVDS-style dash-joined `series` parameter.
 *
 * EVDS joins codes with `-`; our codes contain no dashes, so the split is
 * unambiguous. Blank segments (`A--B`, trailing `-`) are dropped rather than
 * erroring — a stray separator shouldn't fail an otherwise valid request.
 */
export function parseSeriesParam(raw: string): string[] {
  return raw
    .split("-")
    .map((s) => s.trim().toUpperCase())
    .filter(Boolean);
}

/**
 * Parse an EVDS-style `DD-MM-YYYY` date into `YYYY-MM-DD`.
 *
 * Also accepts ISO `YYYY-MM-DD`, because that is what every programmatic caller
 * reaches for first and rejecting it would be hostile for no gain. Returns null
 * on anything else — the caller decides whether that's an error or "unbounded".
 */
export function parseDate(raw: string | null): string | null {
  if (!raw) return null;
  const s = raw.trim();
  let m = s.match(/^(\d{2})-(\d{2})-(\d{4})$/);
  if (m) return `${m[3]}-${m[2]}-${m[1]}`;
  m = s.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (m) return s;
  return null;
}

/** Look up catalog rows for the requested codes, in the order requested. */
export async function fetchSeriesMeta(codes: string[]): Promise<SeriesMeta[]> {
  if (!codes.length) return [];
  const placeholders = codes.map(() => "?").join(",");
  const rows = await allDirect<SeriesMeta>(
    `SELECT series_code, dataset, frequency, source_table, table_number,
            category, item_key, item_name, item_name_en, bank_type_code,
            report_currency, value_column, unit, start_date, end_date, obs_count
       FROM api_series
      WHERE series_code IN (${placeholders})`,
    codes,
  );
  const byCode = new Map(rows.map((r) => [r.series_code, r]));
  return codes.map((c) => byCode.get(c)).filter((r): r is SeriesMeta => !!r);
}

/**
 * Physical columns a series may read, per source table.
 *
 * `value_column` comes from our own catalog, not from the caller — but it is
 * still interpolated into SQL rather than bound (SQLite can't parameterise an
 * identifier), so it is checked against this allowlist first. Defence in depth:
 * a corrupted catalog row must not become injection.
 */
const ALLOWED_VALUE_COLUMNS: Record<string, Set<string>> = {
  balance_sheet: new Set(["amount_tl", "amount_fx", "amount_total"]),
  income_statement: new Set(["amount_tl", "amount_fx", "amount_total"]),
  loans: new Set([
    "short_term_tl", "short_term_fx", "short_term_total",
    "medium_long_tl", "medium_long_fx", "medium_long_total",
    "total_tl", "total_fx", "total_amount", "npl_amount",
    "non_cash_amount", "customer_count",
  ]),
  deposits: new Set([
    "bracket_10k", "bracket_50k", "bracket_250k", "bracket_1m",
    "bracket_over_1m", "demand", "maturity_1m", "maturity_1_3m",
    "maturity_3_6m", "maturity_6_12m", "maturity_over_12m", "total_amount",
  ]),
  financial_ratios: new Set(["ratio_value"]),
  // other_data stores its value dimension as rows; the column is always the same.
  other_data: new Set(["value_numeric"]),
  // weekly_series likewise — value_column holds the currency LEG, not a column.
  weekly_series: new Set(["value"]),
};

export interface ObservationQuery {
  sql: string;
  binds: unknown[];
}

/**
 * Build the observation query for one catalogued series.
 *
 * Monthly rows are dated to the period END (`2026-04-30`), because a BDDK
 * monthly figure is a month-end stock, not something that happened on the 1st.
 * Weekly rows already carry their own `period_date`.
 *
 * Returns null if the catalog row names a table or column we don't serve, which
 * should be impossible and therefore must fail closed rather than improvise.
 */
export function buildObservationQuery(
  meta: SeriesMeta,
  from: string | null,
  to: string | null,
): ObservationQuery | null {
  const allowed = ALLOWED_VALUE_COLUMNS[meta.source_table];
  if (!allowed) return null;

  const monthEnd =
    "date(printf('%04d-%02d-01', year, month), '+1 month', '-1 day')";

  if (meta.source_table === "weekly_series") {
    if (!allowed.has("value")) return null;
    const binds: unknown[] = [
      meta.category, meta.item_key, meta.bank_type_code, meta.value_column,
    ];
    let sql =
      `SELECT period_date AS date, value FROM weekly_series
        WHERE category = ? AND item_id = ? AND bank_type_code = ?
          AND currency = ?`;
    if (from) { sql += " AND period_date >= ?"; binds.push(from); }
    if (to) { sql += " AND period_date <= ?"; binds.push(to); }
    sql += ` ORDER BY period_date LIMIT ${MAX_OBS_PER_SERIES}`;
    return { sql, binds };
  }

  if (meta.source_table === "other_data") {
    if (!allowed.has("value_numeric")) return null;
    const binds: unknown[] = [
      meta.table_number, meta.value_column, meta.item_key,
      meta.bank_type_code, meta.report_currency ?? "TL",
    ];
    let sql =
      `SELECT ${monthEnd} AS date, value_numeric AS value FROM other_data
        WHERE table_number = ? AND column_name = ? AND item_name = ?
          AND bank_type_code = ? AND currency = ?`;
    if (from) { sql += ` AND ${monthEnd} >= ?`; binds.push(from); }
    if (to) { sql += ` AND ${monthEnd} <= ?`; binds.push(to); }
    sql += ` ORDER BY year, month LIMIT ${MAX_OBS_PER_SERIES}`;
    return { sql, binds };
  }

  if (!allowed.has(meta.value_column)) return null;

  // financial_ratios has no currency column — ratios are unit-free.
  const hasCurrency = meta.source_table !== "financial_ratios";
  // loans / deposits / financial_ratios partition one physical table by
  // table_number; balance_sheet and income_statement are whole tables.
  const partitioned = ["loans", "deposits", "financial_ratios"].includes(
    meta.source_table,
  );

  const binds: unknown[] = [];
  let sql =
    `SELECT ${monthEnd} AS date, ${meta.value_column} AS value
       FROM ${meta.source_table} WHERE item_order = ? AND bank_type_code = ?`;
  binds.push(Number(meta.item_key), meta.bank_type_code);
  if (partitioned) { sql += " AND table_number = ?"; binds.push(meta.table_number); }
  if (hasCurrency) {
    sql += " AND currency = ?";
    binds.push(meta.report_currency ?? "TL");
  }
  if (from) { sql += ` AND ${monthEnd} >= ?`; binds.push(from); }
  if (to) { sql += ` AND ${monthEnd} <= ?`; binds.push(to); }
  sql += ` ORDER BY year, month LIMIT ${MAX_OBS_PER_SERIES}`;
  return { sql, binds };
}

/** Fetch observations for one series. Empty array if it resolves to nothing. */
export async function fetchObservations(
  meta: SeriesMeta,
  from: string | null,
  to: string | null,
): Promise<Observation[]> {
  const q = buildObservationQuery(meta, from, to);
  if (!q) return [];
  const rows = await allDirect<{ date: string; value: number | null }>(
    q.sql,
    q.binds,
  );
  return rows.map((r) => ({ date: r.date, value: r.value }));
}

/**
 * Render series + observations as CSV: one row per date, one column per series,
 * dates outer-joined across every series so a spreadsheet lines up.
 */
export function toCsv(
  metas: SeriesMeta[],
  obs: Observation[][],
): string {
  const dates = new Set<string>();
  for (const series of obs) for (const o of series) dates.add(o.date);
  const sorted = [...dates].sort();

  const lookup = obs.map((series) => {
    const m = new Map<string, number | null>();
    for (const o of series) m.set(o.date, o.value);
    return m;
  });

  const esc = (s: string) => (/[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s);
  const lines = [["date", ...metas.map((m) => m.series_code)].map(esc).join(",")];
  for (const d of sorted) {
    const cells = lookup.map((m) => {
      const v = m.get(d);
      return v === undefined || v === null ? "" : String(v);
    });
    lines.push([d, ...cells].join(","));
  }
  return lines.join("\n");
}
