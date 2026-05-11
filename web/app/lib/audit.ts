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
