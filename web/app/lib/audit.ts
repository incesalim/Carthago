/**
 * Per-bank audit-report queries against D1.
 *
 * Reads from bank_audit_balance_sheet / bank_audit_profit_loss /
 * bank_audit_extractions tables. Filter by (bank_ticker, period, kind).
 */
import { getDB } from "./db";

export interface BankSummary {
  bank_ticker: string;
  periods: number;
  reports: number;
  latest_period: string;
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

/** Listing of all banks with audit-data coverage. */
export async function bankSummaries(): Promise<BankSummary[]> {
  const db = await getDB();
  const { results } = await db
    .prepare(
      `SELECT
         bank_ticker,
         COUNT(DISTINCT period) AS periods,
         COUNT(*) AS reports,
         MAX(period) AS latest_period
       FROM bank_audit_extractions
       WHERE success = 1
       GROUP BY bank_ticker
       ORDER BY bank_ticker`,
    )
    .all<BankSummary>();
  return results;
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
      `SELECT statement, period, hierarchy, amount_total
       FROM bank_audit_balance_sheet
       WHERE bank_ticker = ? AND kind = ?
         AND period IN (${placeholders})
         AND hierarchy != ''`,
    )
    .bind(ticker, kind, ...periods)
    .all<{ statement: string; period: string; hierarchy: string; amount_total: number | null }>();
  const out = new Map<string, Map<string, number | null>>();
  for (const r of results) {
    const key = `${r.statement}::${r.hierarchy}`;
    if (!out.has(key)) out.set(key, new Map());
    out.get(key)!.set(r.period, r.amount_total);
  }
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
