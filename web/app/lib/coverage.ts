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
  /** Report Bölüm ('§1'/'§2'/'§4'/'§5'/'§7') — provenance, and the only field
   *  that says primary statement vs note. Group the matrix on THIS, never on
   *  is_core, which is a severity flag (see src/audit_reports/registry.py). */
  section: string;
  is_core: number;
  has_validator: number;
  section_rank: number;
  sort_order: number;
}

export interface CoverageCell {
  bank_ticker: string;
  period: string;
  kind: string; // 'consolidated' | 'unconsolidated'
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
        `SELECT key, label, source_table, statement, section, is_core, has_validator,
                section_rank, sort_order
         FROM bank_audit_statement_types ORDER BY section_rank, sort_order`,
      )
      .all<StatementTypeRow>();
    return results;
  } catch {
    return [];
  }
}

/** Every coverage cell for one statement type, plus the distinct bank / period
 *  axes the client pivots into a grid. `kind` is one of consolidated /
 *  unconsolidated, or "both" to return both (each cell carries its own kind so
 *  the client can stack the two as paired rows). */
export async function coverageGrid(type: string, kind: string): Promise<CoverageGrid> {
  try {
    const db = await getDB();
    const both = kind === "both";
    const stmt = both
      ? db
          .prepare(
            `SELECT bank_ticker, period, kind, status, row_count, checks_failed, is_manual, pdf_present
             FROM bank_audit_coverage
             WHERE statement_type = ?
             ORDER BY bank_ticker, period, kind`,
          )
          .bind(type)
      : db
          .prepare(
            `SELECT bank_ticker, period, kind, status, row_count, checks_failed, is_manual, pdf_present
             FROM bank_audit_coverage
             WHERE statement_type = ? AND kind = ?
             ORDER BY bank_ticker, period`,
          )
          .bind(type, kind);
    const { results } = await stmt.all<CoverageCell>();
    const cells = results as CoverageCell[];
    const banks = [...new Set(cells.map((r) => r.bank_ticker))].sort();
    // Periods sort lexically — 'YYYYQn' is already chronological.
    const periods = [...new Set(cells.map((r) => r.period))].sort();
    return { banks, periods, cells };
  } catch {
    return { banks: [], periods: [], cells: [] };
  }
}

/** Per (statement_type, kind, status) cell counts across the whole spine — the
 *  feed for the summary table. One GROUP BY instead of one grid fetch per type. */
export interface CoverageSummaryRow {
  statement_type: string;
  kind: string; // 'consolidated' | 'unconsolidated'
  status: string;
  n: number;
}

export async function coverageSummary(): Promise<CoverageSummaryRow[]> {
  try {
    const db = await getDB();
    const { results } = await db
      .prepare(
        `SELECT statement_type, kind, status, COUNT(*) AS n
         FROM bank_audit_coverage
         GROUP BY statement_type, kind, status`,
      )
      .all<CoverageSummaryRow>();
    return results;
  } catch {
    return [];
  }
}

/** Every cell that needs attention (status error / missing) across all lanes —
 *  the feed for the sidebar problem list. Errors first, then missing. */
export interface ProblemCell {
  statement_type: string;
  bank_ticker: string;
  period: string;
  kind: string;
  status: string; // 'error' | 'missing'
  checks_failed: number;
  pdf_present: number;
  is_manual: number;
  row_count: number;
}

export async function coverageProblems(): Promise<ProblemCell[]> {
  try {
    const db = await getDB();
    const { results } = await db
      .prepare(
        `SELECT statement_type, bank_ticker, period, kind, status,
                checks_failed, pdf_present, is_manual, row_count
         FROM bank_audit_coverage
         WHERE status IN ('error', 'missing')
         ORDER BY statement_type, bank_ticker, period, kind`,
      )
      .all<ProblemCell>();
    return results;
  } catch {
    return [];
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
