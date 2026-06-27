/**
 * Data layer for the /franchise tab — bank franchise & operational statistics
 * extracted from annual reports (Faaliyet Raporları). Reads `faaliyet_franchise`
 * (one row per disclosed stat) + `faaliyet_extractions` (coverage log), populated
 * by scripts/update_faaliyet.py. Deterministic extraction; every value carries a
 * `confidence` flag, so the table surfaces low-confidence cells visually.
 *
 * Values are stored with a `unit` (count | count_th | count_mn); the pivot
 * rescales each to an absolute headcount in SQL so columns are comparable.
 */
import { cachedAll } from "./db";

/** Absolute-count rescale for the stored unit. */
const RESCALE = "CASE unit WHEN 'count_mn' THEN 1000000 WHEN 'count_th' THEN 1000 ELSE 1 END";

function pivot(metric: string, alias: string): string {
  return `MAX(CASE WHEN metric_key='${metric}' THEN value * (${RESCALE}) END) AS ${alias}`;
}

export interface FranchiseRow {
  bank_ticker: string;
  fiscal_year: number;
  atm_count: number | null;
  pos_count: number | null;
  merchant_count: number | null;
  customer_active: number | null;
  customer_total: number | null;
  cards_total: number | null;
  min_confidence: string | null;
}

/** Latest fiscal year's current-period franchise snapshot, one row per bank. */
export async function latestFranchiseByBank(): Promise<FranchiseRow[]> {
  return cachedAll<FranchiseRow>(
    `WITH latest AS (
       SELECT bank_ticker, MAX(fiscal_year) AS fy
         FROM faaliyet_franchise
        WHERE period_type = 'current'
        GROUP BY bank_ticker
     )
     SELECT f.bank_ticker, f.fiscal_year,
            ${pivot("atm_count", "atm_count")},
            ${pivot("pos_count", "pos_count")},
            ${pivot("merchant_count", "merchant_count")},
            ${pivot("customer_active", "customer_active")},
            ${pivot("customer_total", "customer_total")},
            ${pivot("cards_total", "cards_total")},
            MIN(f.confidence) AS min_confidence
       FROM faaliyet_franchise f
       JOIN latest l ON f.bank_ticker = l.bank_ticker AND f.fiscal_year = l.fy
      WHERE f.period_type = 'current'
      GROUP BY f.bank_ticker, f.fiscal_year
      ORDER BY atm_count DESC NULLS LAST, f.bank_ticker`,
  );
}

export interface FranchiseCoverage {
  banks: number | null;
  reports: number | null;
  ocr_skipped: number | null;
  min_year: number | null;
  max_year: number | null;
}

/** Coverage rollup for the page header (banks covered, year span, OCR gaps). */
export async function franchiseCoverage(): Promise<FranchiseCoverage> {
  const rows = await cachedAll<FranchiseCoverage>(
    `SELECT COUNT(DISTINCT bank_ticker) AS banks,
            SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) AS reports,
            SUM(CASE WHEN is_ocr = 1 THEN 1 ELSE 0 END) AS ocr_skipped,
            MIN(fiscal_year) AS min_year,
            MAX(fiscal_year) AS max_year
       FROM faaliyet_extractions`,
  );
  return rows[0] ?? { banks: 0, reports: 0, ocr_skipped: 0, min_year: null, max_year: null };
}
