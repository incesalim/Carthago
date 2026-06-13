/**
 * Cross-bank performance heatmap — data layer (SERVER ONLY).
 *
 * Sits beside audit.ts and reuses the same bank_audit_* tables + the cachedAll
 * KV cache. Builds ONE panel (one row per bank×period) from four GROUP BY
 * queries, then derives ROE/ROA/NIM/Cost-Income. Both the snapshot and the
 * over-time views derive from this single panel.
 *
 * Period format is `YYYYQN` with NO dash (2025Q4, 2026Q1). String MAX(period)
 * sorts correctly lexically. P&L amounts are YTD cumulative. ROE uses a
 * trailing-twelve-month net income (de-cumulated to single quarters and summed
 * over the last 4) divided by the average equity across the last 5 quarter-ends
 * — the standard, less-noisy basis. ROA / NIM still annualize the YTD flow by
 * × (4 / quarterNum) over period-end assets (average-balance is a later
 * refinement); Cost/Income is a ratio of two YTD figures (no annualization).
 * Any missing input or non-positive denominator → null cell, never a wrong ratio.
 *
 * CTE / naming caveat (see audit.ts): never name a CTE after a table it reads —
 * D1 throws a circular-reference 500.
 */
import { cachedAll } from "./db";
import { BS_ASSET_ROMAN_HIERARCHIES } from "./standard_lines";
import type { Direction } from "./heatmap-normalize";
import type { LiveQuote } from "./bist-live";

export type MetricKey =
  | "total_assets"
  | "npl_ratio"
  | "stage2_share"
  | "npl_coverage"
  | "provision_intensity"
  | "roe"
  | "roa"
  | "nim"
  | "cost_income"
  | "pb"
  | "pe";

export interface MetricDef {
  key: MetricKey;
  label: string;
  short: string;
  unit: "pct" | "trn" | "bn" | "raw" | "mult";
  decimals: number;
  direction: Direction;
}

/** Ordered — drives the heatmap columns + each column's good/bad direction.
 *  `total_assets` MUST stay first: the grid sizes-ranks within type groups by
 *  raw[indexOf total_assets]. */
export const METRIC_DEFS: MetricDef[] = [
  { key: "total_assets",        label: "Total assets",        short: "Assets",     unit: "bn",  decimals: 0, direction: "neutral" },
  { key: "npl_ratio",           label: "NPL ratio",           short: "NPL",        unit: "pct", decimals: 2, direction: "higher_worse" },
  { key: "stage2_share",        label: "Stage-2 share",       short: "Stage 2",    unit: "pct", decimals: 2, direction: "higher_worse" },
  { key: "npl_coverage",        label: "NPL coverage",        short: "Coverage",   unit: "pct", decimals: 1, direction: "higher_better" },
  { key: "provision_intensity", label: "Provision intensity", short: "Provisions", unit: "pct", decimals: 2, direction: "neutral" },
  { key: "roe",                 label: "ROE (TTM)",           short: "ROE",        unit: "pct", decimals: 1, direction: "higher_better" },
  { key: "roa",                 label: "ROA",                 short: "ROA",        unit: "pct", decimals: 2, direction: "higher_better" },
  { key: "nim",                 label: "NIM (annualized)",    short: "NIM",        unit: "pct", decimals: 2, direction: "higher_better" },
  { key: "cost_income",         label: "Cost / Income",       short: "Cost/Inc",   unit: "pct",  decimals: 1, direction: "higher_worse" },
  // Market valuation (listed banks only — blank for the unlisted majority).
  // Neutral coloring: cheap/expensive isn't good/bad. Snapshot uses the
  // quarter-end close; over-time uses current shares (no historical share
  // counts), so deep-history P/B/P/E is approximate across capital actions.
  { key: "pb",                  label: "Price / Book",        short: "P/B",        unit: "mult", decimals: 2, direction: "neutral" },
  { key: "pe",                  label: "Price / Earnings",    short: "P/E",        unit: "mult", decimals: 1, direction: "neutral" },
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
  pb: number | null;
  pe: number | null;
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
export async function heatmapPanel(
  kind: string = DEFAULT_KIND,
  live?: Map<string, LiveQuote>,
): Promise<BankMetricRow[]> {
  const romanPlaceholders = BS_ASSET_ROMAN_HIERARCHIES.map(() => "?").join(",");

  const [assets, stages, pl, equity, closes, shares] = await Promise.all([
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
    // Broken-breakdown guard: a handful of historical partitions captured only
    // the stage-3 (NPL) sub-table — total_amount was set equal to stage3_amount
    // with stage1/stage2 left null. There `total_amount` is the NPL stock, not
    // the loan base, so stage3/total would render a nonsense NPL = 100% and the
    // provision ratio sits on the wrong denominator. No real bank has 100% of
    // loans in stage 3, so the signature (stage1 & stage2 null, total = stage3)
    // reliably flags these; null both ratios rather than show a wrong one.
    // (stage2_share is already null there — stage2_amount is null. npl_coverage
    // = stage3_coverage is stored independently of total_amount, so it stays.)
    cachedAll<RowStages>(
      `SELECT bank_ticker, period,
              CASE WHEN total_amount > 0 AND NOT brk THEN stage3_amount * 1.0 / total_amount END AS npl_ratio,
              CASE WHEN total_amount > 0 THEN stage2_amount * 1.0 / total_amount END AS stage2_share,
              stage3_coverage AS npl_coverage,
              CASE WHEN total_amount > 0 AND NOT brk THEN total_ecl * 1.0 / total_amount END AS provision_intensity
         FROM (
           SELECT *,
                  (stage1_amount IS NULL AND stage2_amount IS NULL
                   AND total_amount = stage3_amount) AS brk
             FROM bank_audit_stages
            WHERE kind = ? AND period_type = 'current'
         )`,
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
    // D — equity. The equity row's BRSA roman numeral differs by balance-sheet
    // layout: XVI. for deposit banks, but XIV. for participation banks (their
    // liabilities side has fewer roman items). Match the equity row by its
    // LABEL on any roman-numeral line instead of a fixed numeral, so the
    // participation group gets an ROE too (was "—"). The `GLOB '[IVXLCDM]*.'`
    // guard keeps this to roman-numeral rows, excluding the label-bearing
    // "Total Liabilities and Equity" grand total (which carries no hierarchy and
    // would otherwise win MAX()). UPPER+'%ZKAYNAK%' matches "Özkaynaklar" across
    // Turkish casing; '%EQUITY%' matches "Shareholders' Equity".
    cachedAll<RowEquity>(
      `SELECT bank_ticker, period,
              MAX(CASE WHEN hierarchy GLOB '[IVXLCDM]*.'
                        AND (UPPER(item_name) LIKE '%ZKAYNAK%' OR UPPER(item_name) LIKE '%EQUITY%')
                       THEN amount_total END) AS equity
         FROM bank_audit_balance_sheet
        WHERE kind = ? AND statement = 'liabilities'
        GROUP BY bank_ticker, period`,
      [kind],
    ),
    // E — quarter-end close per (bank, quarter): the close on the last trading
    // day inside each calendar quarter, keyed to the audit period format YYYYQN.
    // Drives market cap for P/B & P/E. (kind-independent — prices aren't split
    // by consolidation.)
    cachedAll<{ bank_ticker: string; period: string; close_price: number }>(
      `SELECT symbol AS bank_ticker, quarter AS period, close_price FROM (
         SELECT symbol, close_price,
                strftime('%Y', period_date) || 'Q' ||
                  ((CAST(strftime('%m', period_date) AS INTEGER) + 2) / 3) AS quarter,
                ROW_NUMBER() OVER (
                  PARTITION BY symbol,
                    strftime('%Y', period_date) || 'Q' ||
                      ((CAST(strftime('%m', period_date) AS INTEGER) + 2) / 3)
                  ORDER BY period_date DESC) AS rn
           FROM bist_prices
          WHERE kind = 'bank' AND close_price IS NOT NULL
       ) WHERE rn = 1`,
      [],
    ),
    // F — shares outstanding per listed bank (for market cap = close × shares).
    cachedAll<{ bank_ticker: string; shares_outstanding: number | null }>(
      `SELECT symbol AS bank_ticker, shares_outstanding FROM bist_shares`,
      [],
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
        pb: null, pe: null,
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
  // Market valuation inputs (listed banks only). closeByKey is the quarter-end
  // close per (bank, period); sharesByTicker is current shares outstanding.
  const closeByKey = new Map<string, number>();
  for (const r of closes) closeByKey.set(`${r.bank_ticker}|${r.period}`, r.close_price);
  const sharesByTicker = new Map<string, number>();
  for (const r of shares) if (r.shares_outstanding) sharesByTicker.set(r.bank_ticker, r.shares_outstanding);

  // --- Trailing-twelve-month ROE -------------------------------------------
  // ROE = (sum of the last 4 quarters' net income) / (average equity over the
  // last 5 quarter-ends). TTM income avoids the noisy YTD×(4/q) annualization
  // (which quadruples a single Q1), and a 5-point average equity matches the
  // earnings flow to the capital that earned it instead of a period-end snap.
  // P&L is YTD cumulative, so de-cumulate to single-quarter income first.
  // Index every (bank, ord) where ord is a chronological quarter number.
  const ordOf = (period: string): number | null => {
    const m = /^(\d{4})Q([1-4])$/.exec(period);
    return m ? Number(m[1]) * 4 + (Number(m[2]) - 1) : null;
  };
  const byBank = new Map<string, Map<number, { ytd: number | null; eq: number | null }>>();
  for (const row of map.values()) {
    const ord = ordOf(row.period);
    if (ord == null) continue;
    const key = `${row.bank_ticker}|${row.period}`;
    let b = byBank.get(row.bank_ticker);
    if (!b) { b = new Map(); byBank.set(row.bank_ticker, b); }
    b.set(ord, { ytd: plByKey.get(key)?.net_profit ?? null, eq: equityByKey.get(key) ?? null });
  }
  // Single-quarter net income from YTD: Q1 (ord%4===0) is already one quarter;
  // any other quarter is YTD(this) − YTD(prior), so the prior quarter must exist.
  const singleQ = (b: Map<number, { ytd: number | null; eq: number | null }>, ord: number): number | null => {
    const cur = b.get(ord)?.ytd ?? null;
    if (cur == null) return null;
    if (ord % 4 === 0) return cur;
    const prev = b.get(ord - 1)?.ytd ?? null;
    return prev == null ? null : cur - prev;
  };
  // Trailing-4-quarter net income (thousand TL). Needs a contiguous window; a
  // gap (or the bank's earliest quarters) returns null rather than guessing.
  // Shared by ROE (÷ avg equity) and P/E (market cap ÷ this).
  const ttmNet = (ticker: string, period: string): number | null => {
    const b = byBank.get(ticker);
    const ord = ordOf(period);
    if (!b || ord == null) return null;
    let ttm = 0;
    for (let k = 0; k < 4; k++) {
      const s = singleQ(b, ord - k);
      if (s == null) return null;
      ttm += s;
    }
    return ttm;
  };
  const ttmRoe = (ticker: string, period: string): number | null => {
    const b = byBank.get(ticker);
    const ord = ordOf(period);
    if (!b || ord == null) return null;
    const ttm = ttmNet(ticker, period);
    if (ttm == null) return null;
    // Average equity over the 5 trailing quarter-ends (those present, ≥2).
    const eqs: number[] = [];
    for (let k = 0; k < 5; k++) {
      const e = b.get(ord - k)?.eq ?? null;
      if (e != null && e > 0) eqs.push(e);
    }
    if (eqs.length < 2) return null;
    const avgEq = eqs.reduce((s, x) => s + x, 0) / eqs.length;
    return avgEq > 0 ? ttm / avgEq : null;
  };

  // Derive the metrics. ROE uses TTM net income / average equity (above). ROA /
  // NIM are still YTD flows annualized by 4/quarter over period-end assets, and
  // Cost/Income is a ratio of two YTD flows. Missing inputs (or non-positive
  // denominators) leave the cell null.
  // Most-recent period per bank — live prices only overlay this row (the
  // snapshot + the last over-time point); history stays on quarter-end closes.
  const latestPeriodByBank = new Map<string, string>();
  for (const row of map.values()) {
    const cur = latestPeriodByBank.get(row.bank_ticker);
    if (!cur || row.period > cur) latestPeriodByBank.set(row.bank_ticker, row.period);
  }

  for (const row of map.values()) {
    const key = `${row.bank_ticker}|${row.period}`;
    const p = plByKey.get(key);
    const assetsTotal = row.total_assets;

    const q = Number(/Q([1-4])$/.exec(row.period)?.[1]);
    const ann = q >= 1 && q <= 4 ? 4 / q : null;

    const netProfit = p?.net_profit ?? null;
    const netInterest = p?.net_interest ?? null;
    const opex = p?.opex ?? null;
    const grossOp = p?.gross_op_profit ?? null;

    row.roe = ttmRoe(row.bank_ticker, row.period);
    if (ann != null && netProfit != null && assetsTotal != null && assetsTotal > 0)
      row.roa = (netProfit * ann) / assetsTotal;
    if (ann != null && netInterest != null && assetsTotal != null && assetsTotal > 0)
      row.nim = (netInterest * ann) / assetsTotal;
    // Opex / gross operating profit may be sign-negative in source (expenses
    // stored as negatives); abs both so Cost/Income is a clean positive ratio.
    if (opex != null && grossOp != null && Math.abs(grossOp) > 0)
      row.cost_income = Math.abs(opex) / Math.abs(grossOp);

    // Market valuation (listed banks only; null otherwise). Market cap (TL) =
    // price × shares. Audit amounts are thousand TL → ×1000. The latest period
    // uses the live (delayed) price when a quote is supplied; otherwise (and for
    // all historical rows) the quarter-end close.
    const liveQ = live?.get(row.bank_ticker);
    const isLatest = latestPeriodByBank.get(row.bank_ticker) === row.period;
    const close = (liveQ && isLatest ? liveQ.price : closeByKey.get(key)) ?? null;
    const sh = sharesByTicker.get(row.bank_ticker) ?? null;
    const mktcap = close != null && sh != null && sh > 0 ? close * sh : null;
    const eqRaw = equityByKey.get(key) ?? null;
    const ttm = ttmNet(row.bank_ticker, row.period);
    if (mktcap != null && eqRaw != null && eqRaw > 0) row.pb = mktcap / (eqRaw * 1000);
    if (mktcap != null && ttm != null && ttm > 0) row.pe = mktcap / (ttm * 1000);
  }

  return [...map.values()];
}
