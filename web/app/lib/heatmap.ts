/**
 * Cross-bank performance heatmap — data layer (SERVER ONLY).
 *
 * Sits beside audit.ts and reuses the same bank_audit_* tables + the cachedAll
 * KV cache. Builds ONE panel (one row per bank×period) from four GROUP BY
 * queries, then derives ROE/ROA/NIM/Cost-Income. Both the snapshot and the
 * over-time views derive from this single panel.
 *
 * Period format is `YYYYQN` with NO dash (2025Q4, 2026Q1). String MAX(period)
 * sorts correctly lexically. P&L amounts are YTD cumulative, so flow ratios
 * annualize by × (4 / quarterNum); ratios of two YTD figures (Cost/Income) do
 * not. Denominators use period-end assets/equity (average-balance is a later
 * refinement). Any missing or non-positive denominator → null cell, never a
 * wrong ratio.
 *
 * CTE / naming caveat (see audit.ts): never name a CTE after a table it reads —
 * D1 throws a circular-reference 500.
 */
import { cachedAll } from "./db";
import { BS_ASSET_ROMAN_HIERARCHIES, BS_EQUITY_HIERARCHY } from "./standard_lines";
import type { Direction } from "./heatmap-normalize";

export type MetricKey =
  | "total_assets"
  | "npl_ratio"
  | "stage2_share"
  | "npl_coverage"
  | "provision_intensity"
  | "roe"
  | "roa"
  | "nim"
  | "cost_income";

export interface MetricDef {
  key: MetricKey;
  label: string;
  short: string;
  unit: "pct" | "trn" | "raw";
  decimals: number;
  direction: Direction;
}

/** Ordered — drives the heatmap columns + each column's good/bad direction.
 *  `total_assets` MUST stay first: the grid sizes-ranks within type groups by
 *  raw[indexOf total_assets]. */
export const METRIC_DEFS: MetricDef[] = [
  { key: "total_assets",        label: "Total assets",        short: "Assets",     unit: "trn", decimals: 2, direction: "neutral" },
  { key: "npl_ratio",           label: "NPL ratio",           short: "NPL",        unit: "pct", decimals: 2, direction: "higher_worse" },
  { key: "stage2_share",        label: "Stage-2 share",       short: "Stage 2",    unit: "pct", decimals: 2, direction: "higher_worse" },
  { key: "npl_coverage",        label: "NPL coverage",        short: "Coverage",   unit: "pct", decimals: 1, direction: "higher_better" },
  { key: "provision_intensity", label: "Provision intensity", short: "Provisions", unit: "pct", decimals: 2, direction: "neutral" },
  { key: "roe",                 label: "ROE",                 short: "ROE",        unit: "pct", decimals: 1, direction: "higher_better" },
  { key: "roa",                 label: "ROA",                 short: "ROA",        unit: "pct", decimals: 2, direction: "higher_better" },
  { key: "nim",                 label: "NIM (annualized)",    short: "NIM",        unit: "pct", decimals: 2, direction: "higher_better" },
  { key: "cost_income",         label: "Cost / Income",       short: "Cost/Inc",   unit: "pct", decimals: 1, direction: "higher_worse" },
];

export interface BankMetricRow {
  bank_ticker: string;
  period: string;
  total_assets: number | null;
  npl_ratio: number | null;
  stage2_share: number | null;
  npl_coverage: number | null;
  provision_intensity: number | null;
  roe: number | null;
  roa: number | null;
  nim: number | null;
  cost_income: number | null;
}

const DEFAULT_KIND = "unconsolidated";

/**
 * Most recent quarter reported (with a balance sheet) by at least `minBanks`
 * banks — avoids picking a quarter only 1–2 late filers have populated.
 * Lexical MAX over `YYYYQN` is correct. Defaults: minBanks=10, unconsolidated.
 */
export async function latestCommonPeriod(
  minBanks = 10,
  kind: string = DEFAULT_KIND,
): Promise<string | null> {
  const rows = await cachedAll<{ period: string }>(
    `SELECT period, COUNT(DISTINCT bank_ticker) AS n
       FROM bank_audit_balance_sheet
      WHERE kind = ? AND statement = 'assets'
      GROUP BY period
     HAVING n >= ?
      ORDER BY period DESC
      LIMIT 1`,
    [kind, minBanks],
  );
  return rows[0]?.period ?? null;
}

interface RowAssets { bank_ticker: string; period: string; total_assets: number | null }
interface RowStages {
  bank_ticker: string; period: string;
  npl_ratio: number | null; stage2_share: number | null;
  npl_coverage: number | null; provision_intensity: number | null;
}
interface RowPl {
  bank_ticker: string; period: string;
  net_profit: number | null; net_interest: number | null;
  opex: number | null; gross_op_profit: number | null;
}
interface RowEquity { bank_ticker: string; period: string; equity: number | null }

/**
 * Full panel: one row per (bank, period) across every available quarter, with
 * the nine performance metrics. Cached at the query level (12h KV via
 * cachedAll); the merge + derivation is cheap CPU.
 */
export async function heatmapPanel(kind: string = DEFAULT_KIND): Promise<BankMetricRow[]> {
  const romanPlaceholders = BS_ASSET_ROMAN_HIERARCHIES.map(() => "?").join(",");

  const [assets, stages, pl, equity] = await Promise.all([
    // A — total assets: sum of the BS asset Roman subtotals I.–X. (= bankSummaries).
    cachedAll<RowAssets>(
      `SELECT bank_ticker, period, SUM(amount_total) AS total_assets
         FROM bank_audit_balance_sheet
        WHERE kind = ? AND statement = 'assets'
          AND hierarchy IN (${romanPlaceholders})
        GROUP BY bank_ticker, period`,
      [kind, ...BS_ASSET_ROMAN_HIERARCHIES],
    ),
    // B — stage ratios (one row per bank/period already); guard divide-by-zero.
    cachedAll<RowStages>(
      `SELECT bank_ticker, period,
              CASE WHEN total_amount > 0 THEN stage3_amount * 1.0 / total_amount END AS npl_ratio,
              CASE WHEN total_amount > 0 THEN stage2_amount * 1.0 / total_amount END AS stage2_share,
              stage3_coverage AS npl_coverage,
              CASE WHEN total_amount > 0 THEN total_ecl * 1.0 / total_amount END AS provision_intensity
         FROM bank_audit_stages
        WHERE kind = ? AND period_type = 'current'`,
      [kind],
    ),
    // C — P&L pivot by BRSA hierarchy (labels vary TR/EN, codes don't).
    cachedAll<RowPl>(
      `SELECT bank_ticker, period,
              COALESCE(MAX(CASE WHEN hierarchy = 'XXV.' THEN amount END),
                       MAX(CASE WHEN hierarchy = 'XIX.' THEN amount END))  AS net_profit,
              MAX(CASE WHEN hierarchy = 'III.' THEN amount END)            AS net_interest,
              MAX(CASE WHEN hierarchy = 'XI.'  THEN amount END)
                + MAX(CASE WHEN hierarchy = 'XII.' THEN amount END)        AS opex,
              MAX(CASE WHEN hierarchy = 'VIII.' THEN amount END)           AS gross_op_profit
         FROM bank_audit_profit_loss
        WHERE kind = ?
        GROUP BY bank_ticker, period`,
      [kind],
    ),
    // D — equity: BS liabilities XVI. (value column amount_total).
    cachedAll<RowEquity>(
      `SELECT bank_ticker, period,
              MAX(CASE WHEN hierarchy = '${BS_EQUITY_HIERARCHY}' THEN amount_total END) AS equity
         FROM bank_audit_balance_sheet
        WHERE kind = ? AND statement = 'liabilities'
        GROUP BY bank_ticker, period`,
      [kind],
    ),
  ]);

  const map = new Map<string, BankMetricRow>();
  const ensure = (ticker: string, period: string): BankMetricRow => {
    const key = `${ticker}|${period}`;
    let row = map.get(key);
    if (!row) {
      row = {
        bank_ticker: ticker, period,
        total_assets: null, npl_ratio: null, stage2_share: null,
        npl_coverage: null, provision_intensity: null,
        roe: null, roa: null, nim: null, cost_income: null,
      };
      map.set(key, row);
    }
    return row;
  };

  for (const r of assets) ensure(r.bank_ticker, r.period).total_assets = r.total_assets;
  for (const r of stages) {
    const row = ensure(r.bank_ticker, r.period);
    row.npl_ratio = r.npl_ratio;
    row.stage2_share = r.stage2_share;
    row.npl_coverage = r.npl_coverage;
    row.provision_intensity = r.provision_intensity;
  }

  const plByKey = new Map<string, RowPl>();
  for (const r of pl) {
    plByKey.set(`${r.bank_ticker}|${r.period}`, r);
    ensure(r.bank_ticker, r.period);
  }
  const equityByKey = new Map<string, number | null>();
  for (const r of equity) {
    equityByKey.set(`${r.bank_ticker}|${r.period}`, r.equity);
    ensure(r.bank_ticker, r.period);
  }

  // Derive ROE / ROA / NIM / Cost-Income. P&L flows are YTD → annualize by
  // 4/quarter; denominators use period-end assets/equity. Missing or
  // non-positive denominators (or an unparsable quarter) leave the cell null.
  for (const row of map.values()) {
    const key = `${row.bank_ticker}|${row.period}`;
    const p = plByKey.get(key);
    const eq = equityByKey.get(key) ?? null;
    const assetsTotal = row.total_assets;

    const q = Number(/Q([1-4])$/.exec(row.period)?.[1]);
    const ann = q >= 1 && q <= 4 ? 4 / q : null;

    const netProfit = p?.net_profit ?? null;
    const netInterest = p?.net_interest ?? null;
    const opex = p?.opex ?? null;
    const grossOp = p?.gross_op_profit ?? null;

    if (ann != null && netProfit != null && assetsTotal != null && assetsTotal > 0)
      row.roa = (netProfit * ann) / assetsTotal;
    if (ann != null && netProfit != null && eq != null && eq > 0)
      row.roe = (netProfit * ann) / eq;
    if (ann != null && netInterest != null && assetsTotal != null && assetsTotal > 0)
      row.nim = (netInterest * ann) / assetsTotal;
    // Opex / gross operating profit may be sign-negative in source (expenses
    // stored as negatives); abs both so Cost/Income is a clean positive ratio.
    if (opex != null && grossOp != null && Math.abs(grossOp) > 0)
      row.cost_income = Math.abs(opex) / Math.abs(grossOp);
  }

  return [...map.values()];
}
