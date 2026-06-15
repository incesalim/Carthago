/**
 * Per-bank audit-report queries against D1.
 *
 * Reads from bank_audit_balance_sheet / bank_audit_profit_loss /
 * bank_audit_extractions tables. Filter by (bank_ticker, period, kind).
 */
import { cachedAll, getDB } from "./db";

export interface BankSummary {
  bank_ticker: string;
  periods: number;
  reports: number;
  latest_period: string;
  /** Latest-period total assets (unconsolidated), summed from the BRSA
   *  balance-sheet roman subtotals I.–X. — same value the per-bank page shows
   *  as "Total Assets". Thousand-TL units (matches amount_total). Used to
   *  size-rank the /banks index within each type group. Null if the bank has
   *  no unconsolidated balance sheet. */
  total_assets: number | null;
}

export interface BalanceSheetRow {
  statement: string; // assets | liabilities | off_balance
  item_order: number;
  hierarchy: string;
  item_name: string;
  footnote: string | null;
  amount_tl: number | null;
  amount_fc: number | null;
  amount_total: number | null;
}

export interface PlRow {
  item_order: number;
  hierarchy: string;
  item_name: string;
  footnote: string | null;
  amount: number | null;
}

/** Listing of all banks with audit-data coverage, each carrying its latest
 *  total assets so the index can size-rank within type groups. Cached via KV
 *  (`cachedAll`) — the balance-sheet sum scans many rows, so we don't want it
 *  re-running on every page render.
 *
 *  CTE names (`ta`, `ta_latest`) deliberately don't match any table — D1 throws
 *  a "circular reference" 500 if a CTE shadows a table it reads. */
export async function bankSummaries(): Promise<BankSummary[]> {
  return cachedAll<BankSummary>(
    `WITH ta AS (
       SELECT bank_ticker, period, SUM(amount_total) AS total_assets
       FROM bank_audit_balance_sheet
       WHERE kind = 'unconsolidated' AND statement = 'assets'
         AND hierarchy IN ('I.','II.','III.','IV.','V.','VI.','VII.','VIII.','IX.','X.')
       GROUP BY bank_ticker, period
     ),
     ta_latest AS (
       SELECT t.bank_ticker, t.total_assets
       FROM ta t
       JOIN (SELECT bank_ticker, MAX(period) AS mp FROM ta GROUP BY bank_ticker) m
         ON t.bank_ticker = m.bank_ticker AND t.period = m.mp
     )
     SELECT
       e.bank_ticker,
       COUNT(DISTINCT e.period) AS periods,
       COUNT(*) AS reports,
       MAX(e.period) AS latest_period,
       MAX(tl.total_assets) AS total_assets
     FROM bank_audit_extractions e
     LEFT JOIN ta_latest tl ON tl.bank_ticker = e.bank_ticker
     WHERE e.success = 1
     GROUP BY e.bank_ticker
     ORDER BY e.bank_ticker`,
  );
}

/** Available (period, kind) tuples for one bank. */
export async function bankPeriods(
  ticker: string,
): Promise<{ period: string; kind: string; success: number; rows_bs_assets: number; rows_profit_loss: number }[]> {
  const db = await getDB();
  const { results } = await db
    .prepare(
      `SELECT period, kind, success, rows_bs_assets, rows_profit_loss
       FROM bank_audit_extractions
       WHERE bank_ticker = ?
       ORDER BY period DESC, kind`,
    )
    .bind(ticker)
    .all<{ period: string; kind: string; success: number; rows_bs_assets: number; rows_profit_loss: number }>();
  return results;
}

/** Full balance-sheet rows for one bank-period-kind. */
export async function balanceSheet(
  ticker: string,
  period: string,
  kind: "consolidated" | "unconsolidated" = "unconsolidated",
): Promise<BalanceSheetRow[]> {
  const db = await getDB();
  const { results } = await db
    .prepare(
      `SELECT statement, item_order, hierarchy, item_name, footnote,
              amount_tl, amount_fc, amount_total
       FROM bank_audit_balance_sheet
       WHERE bank_ticker = ? AND period = ? AND kind = ?
       ORDER BY statement, item_order`,
    )
    .bind(ticker, period, kind)
    .all<BalanceSheetRow>();
  return results;
}

/** Full P&L rows for one bank-period-kind. */
export async function profitLoss(
  ticker: string,
  period: string,
  kind: "consolidated" | "unconsolidated" = "unconsolidated",
): Promise<PlRow[]> {
  const db = await getDB();
  const { results } = await db
    .prepare(
      `SELECT item_order, hierarchy, item_name, footnote, amount
       FROM bank_audit_profit_loss
       WHERE bank_ticker = ? AND period = ? AND kind = ?
       ORDER BY item_order`,
    )
    .bind(ticker, period, kind)
    .all<PlRow>();
  return results;
}

/** Balance-sheet rows for one bank across multiple periods.
 *  Returned shape: "<statement>::<hierarchy>" → period → amount_total.
 *  Used by the per-bank page to render a multi-column standardized table. */
export async function balanceSheetMultiPeriod(
  ticker: string,
  kind: "consolidated" | "unconsolidated",
  periods: string[],
): Promise<Map<string, Map<string, number | null>>> {
  if (periods.length === 0) return new Map();
  const db = await getDB();
  const placeholders = periods.map(() => "?").join(",");
  const { results } = await db
    .prepare(
      `SELECT statement, period, hierarchy, item_name, amount_total
       FROM bank_audit_balance_sheet
       WHERE bank_ticker = ? AND kind = ?
         AND period IN (${placeholders})
         AND hierarchy != ''`,
    )
    .bind(ticker, kind, ...periods)
    .all<{ statement: string; period: string; hierarchy: string; item_name: string; amount_total: number | null }>();
  const out = new Map<string, Map<string, number | null>>();
  for (const r of results) {
    const key = `${r.statement}::${r.hierarchy}`;
    if (!out.has(key)) out.set(key, new Map());
    // Contra lines ("Expected Credit Losses (-)") are stored as the filing
    // prints them: positive magnitude for most banks, NEGATIVE for the banks
    // that parenthesize the value itself (ING/KLNMA/PASHA/TFKB). Normalize to
    // the magnitude — the displayed label already carries the "(-)".
    const contra = /\(\s*-\s*\)/.test(r.item_name ?? "");
    const v = r.amount_total == null ? null : contra ? Math.abs(r.amount_total) : r.amount_total;
    out.get(key)!.set(r.period, v);
  }
  return out;
}

export interface ValidationCell {
  period: string;
  checks_failed: number;
  checks_passed: number;
}

/** Identity-validation outcome per period for one (bank, kind) — powers the
 *  ⚠ markers on the per-bank tables. `bank_audit_validation` is written by
 *  the extraction pipeline (src/audit_reports/validator.py) and may not exist
 *  in D1 until the Phase-3 backfill lands, so degrade to "no data" on error
 *  instead of failing the page. */
export async function validationByPeriod(
  ticker: string,
  kind: "consolidated" | "unconsolidated",
): Promise<Map<string, Map<string, ValidationCell>>> {
  // Keyed period → statement → cell (NOT summed across statements): a table view
  // must flag only the statement(s) it displays. Summing would mark the Balance
  // Sheet column ⚠ when an unrelated footnote (stages / equity / cash-flow) fails
  // even though assets/liabilities are clean.
  try {
    const db = await getDB();
    const { results } = await db
      .prepare(
        `SELECT period, statement, checks_failed, checks_passed
         FROM bank_audit_validation
         WHERE bank_ticker = ? AND kind = ?`,
      )
      .bind(ticker, kind)
      .all<{ period: string; statement: string; checks_failed: number; checks_passed: number }>();
    const byPeriod = new Map<string, Map<string, ValidationCell>>();
    for (const r of results) {
      let m = byPeriod.get(r.period);
      if (!m) {
        m = new Map();
        byPeriod.set(r.period, m);
      }
      m.set(r.statement, {
        period: r.period,
        checks_failed: r.checks_failed,
        checks_passed: r.checks_passed,
      });
    }
    return byPeriod;
  } catch {
    return new Map();
  }
}

/** Representative `item_name` per `<statement>::<hierarchy>` for one bank, taken
 *  from the most recent of `periods`. Used to disambiguate balance-sheet lines
 *  whose BRSA hierarchy CODE is reused for different content across banks — e.g.
 *  asset 2.3 is "Factoring Receivables" for AKBNK/İş but "Securities at Amortized
 *  Cost" for Garanti/participation banks, and 2.4 is "Other Financial Assets" vs
 *  "Expected Credit Losses (-)". The code alone can't label them. */
export async function balanceSheetLineNames(
  ticker: string,
  kind: "consolidated" | "unconsolidated",
  periods: string[],
): Promise<Map<string, string>> {
  if (periods.length === 0) return new Map();
  const db = await getDB();
  const placeholders = periods.map(() => "?").join(",");
  const { results } = await db
    .prepare(
      `SELECT statement, hierarchy, item_name, period
       FROM bank_audit_balance_sheet
       WHERE bank_ticker = ? AND kind = ?
         AND period IN (${placeholders})
         AND hierarchy != '' AND item_name IS NOT NULL`,
    )
    .bind(ticker, kind, ...periods)
    .all<{ statement: string; hierarchy: string; item_name: string; period: string }>();
  // Keep the name from the latest period each key appears in.
  const best = new Map<string, { period: string; name: string }>();
  for (const r of results) {
    const key = `${r.statement}::${r.hierarchy}`;
    const cur = best.get(key);
    if (!cur || r.period > cur.period) best.set(key, { period: r.period, name: r.item_name });
  }
  const out = new Map<string, string>();
  for (const [k, v] of best) out.set(k, v.name);
  return out;
}

/** P&L rows for one bank across multiple periods.
 *  Returned shape: hierarchy → period → amount. */
export async function profitLossMultiPeriod(
  ticker: string,
  kind: "consolidated" | "unconsolidated",
  periods: string[],
): Promise<Map<string, Map<string, number | null>>> {
  if (periods.length === 0) return new Map();
  const db = await getDB();
  const placeholders = periods.map(() => "?").join(",");
  const { results } = await db
    .prepare(
      `SELECT period, hierarchy, amount
       FROM bank_audit_profit_loss
       WHERE bank_ticker = ? AND kind = ?
         AND period IN (${placeholders})
         AND hierarchy != ''`,
    )
    .bind(ticker, kind, ...periods)
    .all<{ period: string; hierarchy: string; amount: number | null }>();
  const out = new Map<string, Map<string, number | null>>();
  for (const r of results) {
    if (!out.has(r.hierarchy)) out.set(r.hierarchy, new Map());
    out.get(r.hierarchy)!.set(r.period, r.amount);
  }
  return out;
}

/** Full P&L rows for one bank across multiple periods, keyed by period.
 *  Unlike `profitLossMultiPeriod` this keeps `item_name` (the Sankey's sign
 *  normalization needs the "(-)" contra marker) and returns a plain object so
 *  it can cross the RSC boundary into a client component. */
export async function profitLossRowsMultiPeriod(
  ticker: string,
  kind: "consolidated" | "unconsolidated",
  periods: string[],
): Promise<Record<string, PlRow[]>> {
  if (periods.length === 0) return {};
  const db = await getDB();
  const placeholders = periods.map(() => "?").join(",");
  const { results } = await db
    .prepare(
      `SELECT period, item_order, hierarchy, item_name, footnote, amount
       FROM bank_audit_profit_loss
       WHERE bank_ticker = ? AND kind = ?
         AND period IN (${placeholders})
         AND hierarchy != ''
       ORDER BY period, item_order`,
    )
    .bind(ticker, kind, ...periods)
    .all<PlRow & { period: string }>();
  const out: Record<string, PlRow[]> = {};
  for (const r of results) {
    const { period, ...row } = r;
    (out[period] ??= []).push(row);
  }
  return out;
}

/**
 * Time series of a specific BS line for one bank.
 * Matches `item_name` exactly. Returns (period, amount_total) tuples.
 */
export async function bsItemTimeSeries(
  ticker: string,
  itemName: string,
  kind: "consolidated" | "unconsolidated" = "unconsolidated",
): Promise<{ period: string; value: number }[]> {
  const db = await getDB();
  const { results } = await db
    .prepare(
      `SELECT period, amount_total AS value
       FROM bank_audit_balance_sheet
       WHERE bank_ticker = ? AND kind = ? AND item_name = ?
         AND amount_total IS NOT NULL
       ORDER BY period`,
    )
    .bind(ticker, kind, itemName)
    .all<{ period: string; value: number }>();
  return results;
}

/**
 * Bank profile (branches + personnel) — latest extraction across periods.
 * Picks the most-recent (period, kind) for the ticker; period_type=current
 * is implied (the profile extractor only emits current-period values).
 */
export interface BankProfile {
  bank_ticker: string;
  period: string;
  kind: string;
  branches_domestic: number | null;
  branches_foreign: number | null;
  branches_total: number | null;
  personnel: number | null;
}

export async function bankProfile(ticker: string): Promise<BankProfile | null> {
  const db = await getDB();
  const { results } = await db
    .prepare(
      `SELECT bank_ticker, period, kind, branches_domestic, branches_foreign,
              branches_total, personnel
       FROM bank_audit_profile
       WHERE bank_ticker = ?
       ORDER BY period DESC, kind
       LIMIT 1`,
    )
    .bind(ticker)
    .all<BankProfile>();
  return results[0] ?? null;
}


/**
 * Latest TFRS 9 stage view for one bank (consolidated|unconsolidated).
 * Reads bank_audit_stages — already a consolidated view across the 4
 * source sections in bank_audit_credit_quality.
 */
export interface BankStages {
  bank_ticker: string;
  period: string;
  kind: string;
  period_type: string;
  stage1_amount: number | null;
  stage2_amount: number | null;
  stage3_amount: number | null;
  total_amount: number | null;
  stage1_ecl: number | null;
  stage2_ecl: number | null;
  stage3_ecl: number | null;
  total_ecl: number | null;
  stage1_coverage: number | null;
  stage2_coverage: number | null;
  stage3_coverage: number | null;
}

export async function bankStagesLatest(
  ticker: string,
  kind: "consolidated" | "unconsolidated" = "unconsolidated",
): Promise<BankStages | null> {
  const db = await getDB();
  const { results } = await db
    .prepare(
      `SELECT bank_ticker, period, kind, period_type,
              stage1_amount, stage2_amount, stage3_amount, total_amount,
              stage1_ecl, stage2_ecl, stage3_ecl, total_ecl,
              stage1_coverage, stage2_coverage, stage3_coverage
       FROM bank_audit_stages
       WHERE bank_ticker = ? AND kind = ? AND period_type = 'current'
       ORDER BY period DESC
       LIMIT 1`,
    )
    .bind(ticker, kind)
    .all<BankStages>();
  return results[0] ?? null;
}


/**
 * For a given bank, the SUM of all top-level (single-Roman) hierarchy
 * items at item_order = 1, 2, 3, … in the assets statement.
 * Approximates "Total Assets" when the actual TOTAL row is missing.
 */
export async function totalAssetsApprox(
  ticker: string,
  kind: "consolidated" | "unconsolidated" = "unconsolidated",
): Promise<{ period: string; value: number }[]> {
  const db = await getDB();
  const { results } = await db
    .prepare(
      `SELECT period, SUM(amount_total) AS value
       FROM bank_audit_balance_sheet
       WHERE bank_ticker = ? AND kind = ? AND statement = 'assets'
         AND hierarchy LIKE '%' AND hierarchy GLOB '[IVX]*.' /* single Roman */
       GROUP BY period
       ORDER BY period`,
    )
    .bind(ticker, kind)
    .all<{ period: string; value: number }>();
  return results;
}
