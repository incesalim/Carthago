/**
 * Read side of the audit coverage matrix. All three tables are built by
 * scripts/sync_audit_expected.py (full rebuild each refresh-audit run); the
 * Worker only reads them. Every query is wrapped so a not-yet-migrated D1
 * (tables absent) degrades to empty rather than 500-ing the admin page.
 */
import { getDB } from "./db";

export interface StatementTypeRow {
  key: string;
  label: string;
  source_table: string;
  statement: string | null;
  is_core: number;
  has_validator: number;
  sort_order: number;
}

export interface CoverageCell {
  bank_ticker: string;
  period: string;
  status: string; // 'not_expected' | 'missing' | 'error' | 'manual' | 'ok'
  row_count: number;
  checks_failed: number;
  is_manual: number;
  pdf_present: number;
}

export interface CoverageGrid {
  banks: string[];
  periods: string[];
  cells: CoverageCell[];
}

export interface CellDetail {
  extraction:
    | {
        note: string | null;
        success: number;
        rows_bs_assets: number | null;
        rows_bs_liabilities: number | null;
        rows_off_balance: number | null;
        rows_profit_loss: number | null;
        extracted_at: string | null;
      }
    | null;
  validation: {
    statement: string;
    checks_failed: number;
    checks_passed: number;
    failed_detail: string | null;
  }[];
  coverage: {
    statement_type: string;
    status: string;
    row_count: number;
    is_manual: number;
    pdf_present: number;
  }[];
}

/** The statement-type registry, mirrored into D1 — drives the matrix selector. */
export async function statementTypes(): Promise<StatementTypeRow[]> {
  try {
    const db = await getDB();
    const { results } = await db
      .prepare(
        `SELECT key, label, source_table, statement, is_core, has_validator, sort_order
         FROM bank_audit_statement_types ORDER BY sort_order`,
      )
      .all<StatementTypeRow>();
    return results;
  } catch {
    return [];
  }
}

/** Every coverage cell for one statement type + kind, plus the distinct bank /
 *  period axes the client pivots into a grid. */
export async function coverageGrid(type: string, kind: string): Promise<CoverageGrid> {
  try {
    const db = await getDB();
    const { results } = await db
      .prepare(
        `SELECT bank_ticker, period, status, row_count, checks_failed, is_manual, pdf_present
         FROM bank_audit_coverage
         WHERE statement_type = ? AND kind = ?
         ORDER BY bank_ticker, period`,
      )
      .bind(type, kind)
      .all<CoverageCell>();
    const cells = results as CoverageCell[];
    const banks = [...new Set(cells.map((r) => r.bank_ticker))].sort();
    // Periods sort lexically — 'YYYYQn' is already chronological.
    const periods = [...new Set(cells.map((r) => r.period))].sort();
    return { banks, periods, cells };
  } catch {
    return { banks: [], periods: [], cells: [] };
  }
}

/** Drill-down for one (bank, period, kind): the extraction log row, every
 *  validation statement (with failed_detail), and the per-type coverage. */
export async function coverageCellDetail(
  bank: string,
  period: string,
  kind: string,
): Promise<CellDetail> {
  const empty: CellDetail = { extraction: null, validation: [], coverage: [] };
  try {
    const db = await getDB();
    const extraction = await db
      .prepare(
        `SELECT note, success, rows_bs_assets, rows_bs_liabilities, rows_off_balance,
                rows_profit_loss, extracted_at
         FROM bank_audit_extractions
         WHERE bank_ticker = ? AND period = ? AND kind = ?`,
      )
      .bind(bank, period, kind)
      .first<CellDetail["extraction"]>();
    const { results: validation } = await db
      .prepare(
        `SELECT statement, checks_failed, checks_passed, failed_detail
         FROM bank_audit_validation
         WHERE bank_ticker = ? AND period = ? AND kind = ?
         ORDER BY statement`,
      )
      .bind(bank, period, kind)
      .all<CellDetail["validation"][number]>();
    const { results: coverage } = await db
      .prepare(
        `SELECT statement_type, status, row_count, is_manual, pdf_present
         FROM bank_audit_coverage
         WHERE bank_ticker = ? AND period = ? AND kind = ?`,
      )
      .bind(bank, period, kind)
      .all<CellDetail["coverage"][number]>();
    return { extraction: extraction ?? null, validation, coverage };
  } catch {
    return empty;
  }
}
