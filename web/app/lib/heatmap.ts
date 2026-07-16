/**
 * Cross-bank performance heatmap — data layer (SERVER ONLY).
 *
 * Sits beside audit.ts and reuses the same bank_audit_* tables + the cachedAll
 * KV cache. Builds ONE panel (one row per bank×period) from four GROUP BY
 * queries, then derives ROE/ROA/NIM/Cost-Income. Both the snapshot and the
 * over-time views derive from this single panel.
 *
 * Period format is `YYYYQN` with NO dash (2025Q4, 2026Q1). String MAX(period)
 * sorts correctly lexically. P&L amounts are YTD cumulative. Every income-
 * statement ratio is put on the SAME trailing-twelve-month basis: the P&L flow is
 * de-cumulated to single quarters, the last four summed, and divided by an
 * average balance over the five trailing quarter-ends — the standard, less-noisy
 * basis (a YTD×4/q annualization quadruples a single Q1). ROE = TTM net income ÷
 * avg equity; ROA = TTM net income ÷ avg assets; NIM = TTM net interest ÷ avg
 * assets; the margin engine (loan yield / deposit cost / spread / cost of risk /
 * PPOP) works the same way; Cost/Income = |TTM opex| ÷ |TTM gross operating
 * profit| (a ratio of two flows). Any missing input or non-positive denominator →
 * null cell, never a wrong ratio.
 *
 * CTE / naming caveat (see audit.ts): never name a CTE after a table it reads —
 * D1 throws a circular-reference 500.
 */
import { cachedAll } from "./db";
import { BS_ASSET_ROMAN_HIERARCHIES } from "./standard_lines";
import { isPeerExcluded } from "./bank_names";
import type { Direction } from "./heatmap-normalize";
import type { LiveQuote } from "./bist-live";

export type MetricKey =
  | "total_assets"
  | "npl_ratio"
  | "stage2_share"
  | "npl_coverage"
  | "provision_intensity"
  | "cost_of_risk"
  | "roe"
  | "roa"
  | "nim"
  | "ppop_ratio"
  | "loan_yield"
  | "deposit_cost"
  | "spread"
  | "cost_income"
  | "cet1"
  | "car"
  | "lcr"
  | "fx_nop"
  | "repricing_gap_1y"
  | "pb"
  | "pe";

/** Metric families — the scorecard's row groups, top to bottom. */
export const METRIC_FAMILIES = [
  "Scale",
  "Asset quality",
  "Returns",
  "Margin engine",
  "Capital & liquidity",
  "Market risk",
  "Valuation",
] as const;

export type MetricFamily = (typeof METRIC_FAMILIES)[number];

export interface MetricDef {
  key: MetricKey;
  label: string;
  short: string;
  /** "pct" = stored as a FRACTION (0.155 → 15.5%); "pts" = stored in percentage
   *  POINTS already (15.5 → 15.5%), which is how the audited §4 ratios arrive. */
  unit: "pct" | "pts" | "trn" | "bn" | "raw" | "mult";
  decimals: number;
  direction: Direction;
  /** Scorecard row group. */
  family: MetricFamily;
  /** How the number is MADE — printed under the metric name (automation
   *  honesty, DESIGN.md rule 6). Mirrors the derivations documented above. */
  rule: string;
  /** Plot the strip's axis on a log scale — only for the wildly skewed
   *  size metric, where a linear axis buries 30 banks against zero. */
  log?: boolean;
}

/** Ordered — drives the heatmap columns + each column's good/bad direction.
 *  `total_assets` MUST stay first: the grid sizes-ranks within type groups by
 *  raw[indexOf total_assets]. */
export const METRIC_DEFS: MetricDef[] = [
  { key: "total_assets",        label: "Total assets",        short: "Assets",     unit: "bn",  decimals: 0, direction: "neutral",      family: "Scale",           log: true, rule: "Σ balance-sheet asset romans I.–X. · log axis" },
  { key: "npl_ratio",           label: "NPL ratio",           short: "NPL",        unit: "pct", decimals: 2, direction: "higher_worse", family: "Asset quality",   rule: "stage-3 ÷ total loans (audited)" },
  { key: "stage2_share",        label: "Stage-2 share",       short: "Stage 2",    unit: "pct", decimals: 2, direction: "higher_worse", family: "Asset quality",   rule: "stage-2 ÷ total loans" },
  { key: "npl_coverage",        label: "NPL coverage",        short: "Coverage",   unit: "pct", decimals: 1, direction: "higher_better",family: "Asset quality",   rule: "stage-3 coverage, as filed" },
  { key: "provision_intensity", label: "Provision intensity", short: "Provisions", unit: "pct", decimals: 2, direction: "neutral",      family: "Asset quality",   rule: "total ECL ÷ total loans" },
  // Cost of risk (TTM credit-provision flow ÷ avg gross loans) — the income-
  // statement counterpart to the balance-sheet provision-intensity stock.
  { key: "cost_of_risk",        label: "Cost of risk (TTM)",  short: "CoR",        unit: "pct", decimals: 2, direction: "higher_worse", family: "Asset quality",   rule: "|TTM ECL flow| ÷ avg gross loans" },
  { key: "roe",                 label: "ROE (TTM)",           short: "ROE",        unit: "pct", decimals: 1, direction: "higher_better",family: "Returns",         rule: "TTM net income ÷ 5-quarter avg equity" },
  { key: "roa",                 label: "ROA (TTM)",           short: "ROA",        unit: "pct", decimals: 2, direction: "higher_better",family: "Returns",         rule: "TTM net income ÷ 5-quarter avg assets" },
  { key: "nim",                 label: "NIM (TTM)",           short: "NIM",        unit: "pct", decimals: 2, direction: "higher_better",family: "Returns",         rule: "TTM net interest ÷ 5-quarter avg assets" },
  // Margin engine — the drivers behind NIM. TTM interest flows over 5-point
  // average balances, the same trailing-year basis as ROE and NIM above. Loan
  // yield = interest on loans (P&L 1.1)
  // ÷ avg gross loans (BS asset 2.1); deposit cost = interest on deposits (P&L
  // 2.1) ÷ avg deposits (BS liability I.); spread is the gap. Yield/cost are
  // neutral (high yield ↔ riskier book; high cost ↔ funding mix), spread is the
  // edge. PPOP = gross operating profit (VIII) − opex, the pre-provision earning
  // power, over avg assets.
  { key: "ppop_ratio",          label: "PPOP / assets (TTM)", short: "PPOP",       unit: "pct", decimals: 2, direction: "higher_better",family: "Returns",         rule: "TTM (gross op. profit − opex) ÷ avg assets" },
  { key: "loan_yield",          label: "Loan yield (TTM)",    short: "Yield",      unit: "pct", decimals: 1, direction: "neutral",      family: "Margin engine",   rule: "TTM interest on loans (1.1) ÷ avg gross loans" },
  { key: "deposit_cost",        label: "Deposit cost (TTM)",  short: "Dep cost",   unit: "pct", decimals: 1, direction: "neutral",      family: "Margin engine",   rule: "TTM interest on deposits (2.1) ÷ avg deposits" },
  { key: "spread",              label: "Loan–deposit spread", short: "Spread",     unit: "pct", decimals: 1, direction: "higher_better",family: "Margin engine",   rule: "loan yield − deposit cost" },
  { key: "cost_income",         label: "Cost / Income (TTM)", short: "Cost/Inc",   unit: "pct",  decimals: 1, direction: "higher_worse",family: "Margin engine",   rule: "|TTM opex| ÷ |TTM gross operating profit|" },
  // Capital + liquidity (audited §4) — solvency/liquidity buffers; higher = stronger.
  { key: "cet1",                label: "CET1 ratio (§4)",     short: "CET1",       unit: "pts", decimals: 1, direction: "higher_better",family: "Capital & liquidity", rule: "audited §4, as filed" },
  { key: "car",                 label: "CAR (§4)",            short: "CAR",        unit: "pts", decimals: 1, direction: "higher_better",family: "Capital & liquidity", rule: "audited §4, as filed" },
  { key: "lcr",                 label: "LCR (§4)",            short: "LCR",        unit: "pts", decimals: 0, direction: "higher_better",family: "Capital & liquidity", rule: "audited §4, total LCR" },
  // Market risk (CAMELS "S") — magnitude of exposure, so higher = more exposed.
  // FX NOP = |net open FX position| / regulatory capital (the regulatory NOP
  // ratio). Repricing gap ≤1y = |Σ rate-sensitive gap in the ≤1y buckets| /
  // total assets — how much of the book reprices within a year, net.
  { key: "fx_nop",              label: "FX net open pos. / capital", short: "FX NOP", unit: "pts", decimals: 1, direction: "higher_worse", family: "Market risk", rule: "|net open FX position| ÷ regulatory capital" },
  { key: "repricing_gap_1y",    label: "Repricing gap ≤1y / assets", short: "Gap ≤1y", unit: "pts", decimals: 1, direction: "higher_worse", family: "Market risk", rule: "|Σ gap in the ≤1y buckets| ÷ rate-sensitive assets" },
  // Market valuation (listed banks only — blank for the unlisted majority).
  // Neutral coloring: cheap/expensive isn't good/bad. Snapshot uses the
  // quarter-end close; over-time uses current shares (no historical share
  // counts), so deep-history P/B/P/E is approximate across capital actions.
  { key: "pb",                  label: "Price / Book",        short: "P/B",        unit: "mult", decimals: 2, direction: "neutral", family: "Valuation", rule: "market cap ÷ equity · listed banks only" },
  { key: "pe",                  label: "Price / Earnings",    short: "P/E",        unit: "mult", decimals: 1, direction: "neutral", family: "Valuation", rule: "market cap ÷ TTM net income · listed banks only" },
];

export interface BankMetricRow {
  bank_ticker: string;
  period: string;
  total_assets: number | null;
  npl_ratio: number | null;
  stage2_share: number | null;
  npl_coverage: number | null;
  provision_intensity: number | null;
  cost_of_risk: number | null;
  roe: number | null;
  /** Free-provision-adjusted ROE: reported earnings less the discretionary
   *  serbest-karşılık build/release, same average-equity basis as `roe`. */
  roeAdjusted: number | null;
  /** Free-provision (serbest karşılık) STOCK, thousand TL; 0 = holds none. */
  freeProvision: number | null;
  roa: number | null;
  nim: number | null;
  ppop_ratio: number | null;
  loan_yield: number | null;
  deposit_cost: number | null;
  spread: number | null;
  /** Deposits stock (thousand TL) at this period, straight off the balance sheet.
   *  0 means the bank genuinely takes NO deposits — development/investment banks
   *  (TSKB, KLNMA) fund themselves in the market and file `MEVDUAT` as 0, so they
   *  have no deposit cost and no spread BY CONSTRUCTION. null means we hold no
   *  deposits line at all. `deposit_cost`/`spread` collapse both cases to null,
   *  which is why the engine gate needs this to tell "inapplicable" from "missing". */
  deposits_stock: number | null;
  cost_income: number | null;
  cet1: number | null;
  car: number | null;
  lcr: number | null;
  fx_nop: number | null;
  repricing_gap_1y: number | null;
  pb: number | null;
  pe: number | null;
}

// Repricing buckets ≤ 1 year (for the cumulative ≤1y gap heatmap column).
const LE1Y_BUCKETS = new Set(["lt_1m", "1_3m", "3_12m"]);

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
  ii_loans: number | null; ie_deposits: number | null; ecl_prov: number | null;
}
interface RowEquity { bank_ticker: string; period: string; equity: number | null }
interface RowBalance { bank_ticker: string; period: string; amount: number | null }

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

  const [assets, stages, pl, equity, closes, shares, latestCloses, loanRows, depositRows,
         capRows, fxRows, rpRows, liqRows, fpRows] = await Promise.all([
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
    // C — P&L pivot. The margin lines are numeric sub-codes, stable across
    // deposit/participation templates (see standard_lines.ts PL_LINES): 1.1 =
    // interest on loans (Kredilerden Alınan Faizler), 2.1 = interest on deposits
    // (Mevduata Verilen Faizler). All amounts are YTD.
    //
    // The SUBTOTALS are joined through bank_audit_pl_roles, NOT hardcoded — a
    // BRSA roman ordinal does not mean the same line at every filer. The
    // compressed template some participation banks file puts net-operating at
    // XII and period-net at XXIV (not XIII/XXV), so the ordinals this query used
    // to name silently read the wrong ROW: `COALESCE(XXV., XIX.)` reported
    // DUNYAK's net profit as 0 for six quarters — XXV. is NULL there, so it fell
    // through to XIX. = discontinued-ops income, which is nil — and `XI. + XII.`
    // summed other-opex plus net operating PROFIT as "opex" (9 partitions).
    // Same lesson as the equity query below: match what a row IS, not where it
    // sits. bank_audit_pl_roles is resolved by validator.pl_roles() (which has
    // the Turkish fold SQL's ASCII-only UPPER() lacks) and rebuilt beside the
    // validation from the same stored rows, so the two cannot drift.
    //
    // III./VIII./IX. stay ordinal-keyed on purpose: net-interest is III and
    // gross-operating is VIII in 1050/1050 partitions, and the first deduction
    // roman after gross is always the provision line — verified, not assumed.
    // opex keeps the `a + b` shape (not SUM) so a missing leg still NULLs the
    // metric rather than silently understating it; the two legs never disagree
    // in sign across the corpus, and the caller abs()es.
    cachedAll<RowPl>(
      `SELECT p.bank_ticker, p.period,
              MAX(CASE WHEN r.role = 'period_net' THEN p.amount END)        AS net_profit,
              MAX(CASE WHEN p.hierarchy = 'III.' THEN p.amount END)         AS net_interest,
              MAX(CASE WHEN r.role = 'opex_personnel' THEN p.amount END)
                + MAX(CASE WHEN r.role = 'opex_other' THEN p.amount END)    AS opex,
              MAX(CASE WHEN p.hierarchy = 'VIII.' THEN p.amount END)        AS gross_op_profit,
              MAX(CASE WHEN p.hierarchy = '1.1'  THEN p.amount END)         AS ii_loans,
              MAX(CASE WHEN p.hierarchy = '2.1'  THEN p.amount END)         AS ie_deposits,
              MAX(CASE WHEN p.hierarchy = 'IX.'  THEN p.amount END)         AS ecl_prov
         FROM bank_audit_profit_loss p
         LEFT JOIN bank_audit_pl_roles r
                ON r.bank_ticker = p.bank_ticker AND r.period = p.period
               AND r.kind = p.kind AND r.hierarchy = p.hierarchy
        WHERE p.kind = ?
        GROUP BY p.bank_ticker, p.period`,
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
    // G — the single latest stored EOD close per bank. The snapshot's "current"
    // P/B & P/E use this (reliable, ~1-day fresh) rather than the months-old
    // quarter-end close, with the live Yahoo price overlaid on top when present.
    cachedAll<{ bank_ticker: string; close_price: number }>(
      `SELECT bank_ticker, close_price FROM (
         SELECT symbol AS bank_ticker, close_price,
                ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY period_date DESC) AS rn
           FROM bist_prices
          WHERE kind = 'bank' AND close_price IS NOT NULL
       ) WHERE rn = 1`,
      [],
    ),
    // H — gross loans per (bank, period): BS asset sub-item 2.1 ("Loans"), the
    // denominator for loan yield + cost of risk. Stable hierarchy across the
    // deposit/participation templates. Narrow scan (one hierarchy).
    cachedAll<RowBalance>(
      `SELECT bank_ticker, period, MAX(amount_total) AS amount
         FROM bank_audit_balance_sheet
        WHERE kind = ? AND statement = 'assets' AND hierarchy = '2.1'
        GROUP BY bank_ticker, period`,
      [kind],
    ),
    // I — customer deposits per (bank, period): BS liability Roman I. ("Deposits
    // / Funds Collected"), the cost-of-funds denominator. Roman I. is deposits
    // for both deposit and participation banks.
    cachedAll<RowBalance>(
      `SELECT bank_ticker, period, MAX(amount_total) AS amount
         FROM bank_audit_balance_sheet
        WHERE kind = ? AND statement = 'liabilities' AND hierarchy = 'I.'
        GROUP BY bank_ticker, period`,
      [kind],
    ),
    // J — regulatory capital (§4) per (bank, period): FX-NOP denominator + CET1 /
    // CAR ratios (the heatmap columns the audit flagged as missing).
    cachedAll<{ bank_ticker: string; period: string; total_capital: number | null; cet1_ratio: number | null; capital_adequacy_ratio: number | null }>(
      `SELECT bank_ticker, period, total_capital, cet1_ratio, capital_adequacy_ratio
         FROM bank_audit_capital WHERE kind = ? AND period_type = 'current'`,
      [kind],
    ),
    // K — FX net open position (TOTAL currency) per (bank, period).
    cachedAll<{ bank_ticker: string; period: string; net_position: number | null }>(
      `SELECT bank_ticker, period, net_position FROM bank_audit_fx_position
        WHERE kind = ? AND period_type = 'current' AND currency = 'TOTAL'`,
      [kind],
    ),
    // L — repricing gap + RSA per (bank, period, bucket).
    cachedAll<{ bank_ticker: string; period: string; bucket: string; gap: number | null; rate_sensitive_assets: number | null }>(
      `SELECT bank_ticker, period, bucket, gap, rate_sensitive_assets FROM bank_audit_repricing
        WHERE kind = ? AND period_type = 'current'`,
      [kind],
    ),
    // M — liquidity (§4): LCR / NSFR per (bank, period).
    cachedAll<{ bank_ticker: string; period: string; lcr_total: number | null; nsfr: number | null }>(
      `SELECT bank_ticker, period, lcr_total, nsfr FROM bank_audit_liquidity
        WHERE kind = ? AND period_type = 'current'`,
      [kind],
    ),
    // N — free-provision (serbest karşılık) STOCK per (bank, period). A missing
    // row is NOT a zero: free_provision.py emits an explicit 0 when the report
    // says the bank holds none (66 such rows), so absence means no determination
    // was made for that (bank, period, kind) — only 16 of 38 banks have one at
    // 2026Q1. Reading absence as zero invents a full release of whatever stock
    // the bank last disclosed (ZIRAAT: a phantom ₺9bn), so ttmRoeAdjusted below
    // requires an explicit determination at BOTH ends of the window.
    cachedAll<{ bank_ticker: string; period: string; free_provision: number | null }>(
      `SELECT bank_ticker, period, free_provision FROM bank_audit_free_provision
        WHERE kind = ?`,
      [kind],
    ),
  ]);

  const map = new Map<string, BankMetricRow>();
  const ensure = (ticker: string, period: string): BankMetricRow => {
    // Peer-excluded banks (Takasbank — a clearing/CCP institution, not a lender)
    // must never enter the panel: every rank, colour scale and peer percentile
    // downstream is computed off this map. Hand callers a throwaway row so their
    // writes land nowhere. See PEER_EXCLUDED_TICKERS in bank_names.ts.
    if (isPeerExcluded(ticker)) return {} as BankMetricRow;
    const key = `${ticker}|${period}`;
    let row = map.get(key);
    if (!row) {
      row = {
        bank_ticker: ticker, period,
        total_assets: null, npl_ratio: null, stage2_share: null,
        npl_coverage: null, provision_intensity: null, cost_of_risk: null,
        roe: null, roeAdjusted: null, freeProvision: null, roa: null, nim: null,
        ppop_ratio: null, loan_yield: null, deposit_cost: null, spread: null,
        deposits_stock: null, cost_income: null,
        cet1: null, car: null, lcr: null,
        fx_nop: null, repricing_gap_1y: null,
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
  // Free-provision stock (thousand TL) per (bank, period). No entry ⇒ UNKNOWN,
  // not zero — a null value is a non-determination too, so it stays out of the map
  // and ttmRoeAdjusted declines to compute rather than invent a release.
  const fpByKey = new Map<string, number>();
  for (const r of fpRows) {
    if (r.free_provision != null) fpByKey.set(`${r.bank_ticker}|${r.period}`, r.free_provision);
  }
  // Margin-engine balance denominators (gross loans, deposits) per (bank, period).
  const loansByKey = new Map<string, number | null>();
  for (const r of loanRows) {
    loansByKey.set(`${r.bank_ticker}|${r.period}`, r.amount);
    ensure(r.bank_ticker, r.period);
  }
  const depositsByKey = new Map<string, number | null>();
  for (const r of depositRows) {
    depositsByKey.set(`${r.bank_ticker}|${r.period}`, r.amount);
    ensure(r.bank_ticker, r.period);
  }
  // Market-risk inputs (direct per bank/period from the §4 tables). Absolute
  // magnitude for the heatmap so higher = more exposed.
  const capByKey = new Map<string, number>();
  const cet1ByKey = new Map<string, number>();
  const carByKey = new Map<string, number>();
  for (const r of capRows) {
    const k = `${r.bank_ticker}|${r.period}`;
    if (r.total_capital) capByKey.set(k, r.total_capital);
    if (r.cet1_ratio != null) { cet1ByKey.set(k, r.cet1_ratio); ensure(r.bank_ticker, r.period); }
    if (r.capital_adequacy_ratio != null) carByKey.set(k, r.capital_adequacy_ratio);
  }
  const lcrByKey = new Map<string, number>();
  for (const r of liqRows) if (r.lcr_total != null) {
    lcrByKey.set(`${r.bank_ticker}|${r.period}`, r.lcr_total);
    ensure(r.bank_ticker, r.period);
  }
  const fxNopByKey = new Map<string, number>();
  for (const r of fxRows) if (r.net_position != null) {
    fxNopByKey.set(`${r.bank_ticker}|${r.period}`, Math.abs(r.net_position));
    ensure(r.bank_ticker, r.period);
  }
  const rpGapByKey = new Map<string, number>();
  const rpAssetsByKey = new Map<string, number>();
  for (const r of rpRows) {
    const k = `${r.bank_ticker}|${r.period}`;
    if (r.bucket === "total") {
      if (r.rate_sensitive_assets != null) rpAssetsByKey.set(k, r.rate_sensitive_assets);
    } else if (LE1Y_BUCKETS.has(r.bucket) && r.gap != null) {
      rpGapByKey.set(k, (rpGapByKey.get(k) ?? 0) + r.gap);
    }
    ensure(r.bank_ticker, r.period);
  }
  // Market valuation inputs (listed banks only). closeByKey is the quarter-end
  // close per (bank, period); sharesByTicker is current shares outstanding.
  const closeByKey = new Map<string, number>();
  for (const r of closes) closeByKey.set(`${r.bank_ticker}|${r.period}`, r.close_price);
  const sharesByTicker = new Map<string, number>();
  for (const r of shares) if (r.shares_outstanding) sharesByTicker.set(r.bank_ticker, r.shares_outstanding);
  const latestCloseByTicker = new Map<string, number>();
  for (const r of latestCloses) latestCloseByTicker.set(r.bank_ticker, r.close_price);

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
  // Free-provision-ADJUSTED ROE: strip the discretionary serbest-karşılık game
  // out of earnings. Building a free provision depresses reported profit; releasing
  // one inflates it (the ALBRK Q1-2025 mechanism). Over the trailing year the P&L
  // distortion telescopes to the STOCK change, so add it back:
  //   adjusted TTM net income = reported TTM net income + (FP_now − FP_4q_ago).
  // Same 5-quarter average-equity denominator as ROE, so the two are directly
  // comparable and the gap = the earnings-management contribution.
  //
  // BOTH endpoints must carry an explicit determination. A gap in the lane is not
  // evidence of a release: absent-as-zero fabricated a ₺9bn ZIRAAT release out of
  // a period we simply never extracted, and printed it as a −1.41pp ROE haircut on
  // the live page. Unknown is unknown → null → the row does not print.
  const ttmRoeAdjusted = (ticker: string, period: string): number | null => {
    const b = byBank.get(ticker);
    const ord = ordOf(period);
    if (!b || ord == null) return null;
    const ttm = ttmNet(ticker, period);
    if (ttm == null) return null;
    const eqs: number[] = [];
    for (let k = 0; k < 5; k++) {
      const e = b.get(ord - k)?.eq ?? null;
      if (e != null && e > 0) eqs.push(e);
    }
    if (eqs.length < 2) return null;
    const avgEq = eqs.reduce((s, x) => s + x, 0) / eqs.length;
    if (avgEq <= 0) return null;
    const startOrd = ord - 4;
    const startPeriod = `${Math.floor(startOrd / 4)}Q${(startOrd % 4) + 1}`;
    const fpNow = fpByKey.get(`${ticker}|${period}`);
    const fpStart = fpByKey.get(`${ticker}|${startPeriod}`);
    if (fpNow == null || fpStart == null) return null;
    return (ttm + (fpNow - fpStart)) / avgEq;
  };

  // --- Margin engine (loan yield / deposit cost / spread / CoR / PPOP) -------
  // Same trailing-year basis as ROE: TTM interest/provision FLOWS (YTD lines
  // de-cumulated to single quarters, last 4 summed) over 5-point average
  // BALANCES. One record per (bank, ord) holds every margin input so the generic
  // ttmFlow/avgStock helpers below can read any field. ppop (a flow) is
  // pre-computed = gross operating profit (VIII) − |opex| (the personnel +
  // other-opex lines, resolved per filer via bank_audit_pl_roles), both YTD.
  interface MarginRec {
    iiLoans: number | null;     // YTD interest on loans (P&L 1.1)
    ieDeposits: number | null;  // YTD interest on deposits (P&L 2.1)
    eclProv: number | null;     // YTD ECL provisions (P&L IX.)
    ppop: number | null;        // YTD pre-provision operating profit (VIII − |opex|)
    netInterest: number | null; // YTD net interest income (P&L III.) — for NIM
    opexAbs: number | null;     // |YTD opex| (personnel + other-opex) — for Cost/Income
    grossOp: number | null;     // YTD gross operating profit (P&L VIII.) — for Cost/Income
    loans: number | null;       // gross loans stock (BS asset 2.1)
    deposits: number | null;    // deposits stock (BS liability I.)
    assets: number | null;      // total assets stock
  }
  const marginByBank = new Map<string, Map<number, MarginRec>>();
  for (const row of map.values()) {
    const ord = ordOf(row.period);
    if (ord == null) continue;
    const key = `${row.bank_ticker}|${row.period}`;
    const p = plByKey.get(key);
    const grossOp = p?.gross_op_profit ?? null;
    const opex = p?.opex ?? null;
    const ppop = grossOp != null && opex != null ? grossOp - Math.abs(opex) : null;
    let b = marginByBank.get(row.bank_ticker);
    if (!b) { b = new Map(); marginByBank.set(row.bank_ticker, b); }
    b.set(ord, {
      iiLoans: p?.ii_loans ?? null,
      ieDeposits: p?.ie_deposits ?? null,
      // |IX.| at the YTD snapshot, like opex above: several banks flip the
      // stored sign of the provision line mid-history (paren-negative era vs
      // positive-magnitude era — see check_audit_quality pl_sign). Taking the
      // magnitude only after de-cumulation would mix conventions inside one
      // TTM window and produce a garbage CoR for the 4 quarters around a flip.
      eclProv: p?.ecl_prov != null ? Math.abs(p.ecl_prov) : null,
      ppop,
      netInterest: p?.net_interest ?? null,
      // |opex| at the YTD snapshot, like ppop/eclProv above: opex flips stored
      // sign mid-history (paren-negative vs positive-magnitude era), so take the
      // magnitude BEFORE de-cumulation — abs after would mix conventions inside
      // one TTM window.
      opexAbs: opex != null ? Math.abs(opex) : null,
      grossOp,
      loans: loansByKey.get(key) ?? null,
      deposits: depositsByKey.get(key) ?? null,
      assets: row.total_assets,
    });
  }
  // De-cumulate one YTD field to a single quarter (Q1 is already one quarter).
  const singleQField = (b: Map<number, MarginRec>, ord: number, f: (r: MarginRec) => number | null): number | null => {
    const cur = b.get(ord) ? f(b.get(ord)!) : null;
    if (cur == null) return null;
    if (ord % 4 === 0) return cur;
    const prevR = b.get(ord - 1);
    const prev = prevR ? f(prevR) : null;
    return prev == null ? null : cur - prev;
  };
  // Trailing-4-quarter sum of a YTD field; null on any gap in the window.
  const ttmFlow = (b: Map<number, MarginRec> | undefined, ord: number | null, f: (r: MarginRec) => number | null): number | null => {
    if (!b || ord == null) return null;
    let t = 0;
    for (let k = 0; k < 4; k++) {
      const s = singleQField(b, ord - k, f);
      if (s == null) return null;
      t += s;
    }
    return t;
  };
  // Average of a stock field over the 5 trailing quarter-ends present (≥2).
  const avgStock = (b: Map<number, MarginRec> | undefined, ord: number | null, f: (r: MarginRec) => number | null): number | null => {
    if (!b || ord == null) return null;
    const xs: number[] = [];
    for (let k = 0; k < 5; k++) {
      const r = b.get(ord - k);
      const v = r ? f(r) : null;
      if (v != null && v > 0) xs.push(v);
    }
    if (xs.length < 2) return null;
    return xs.reduce((s, x) => s + x, 0) / xs.length;
  };

  // Derive the metrics. Every income-statement ratio is TTM: the P&L flow is
  // de-cumulated to single quarters, the last four summed, and divided by a
  // 5-point average balance — ROE ÷ avg equity, ROA / NIM ÷ avg assets, the
  // margin engine ÷ avg loans/deposits/assets, and Cost/Income = a ratio of two
  // TTM flows. Missing inputs (or non-positive denominators) leave the cell null.
  // Most-recent period per bank — live prices only overlay this row (the
  // snapshot + the last over-time point); history stays on quarter-end closes.
  const latestPeriodByBank = new Map<string, string>();
  for (const row of map.values()) {
    const cur = latestPeriodByBank.get(row.bank_ticker);
    if (!cur || row.period > cur) latestPeriodByBank.set(row.bank_ticker, row.period);
  }

  for (const row of map.values()) {
    const key = `${row.bank_ticker}|${row.period}`;

    row.roe = ttmRoe(row.bank_ticker, row.period);
    row.roeAdjusted = ttmRoeAdjusted(row.bank_ticker, row.period);
    row.freeProvision = fpByKey.get(`${row.bank_ticker}|${row.period}`) ?? null;

    // Income-statement ratios — TTM flows over 5-point average balances (same
    // basis as ROE), stored as FRACTIONS (the "pct" formatter ×100s them).
    // cost_of_risk / cost_income take the magnitude of their flow (sign
    // convention varies by bank; net releases and operating losses are rare).
    // Each leaves the cell null on any missing input.
    const mb = marginByBank.get(row.bank_ticker);
    const mord = ordOf(row.period);
    const ttmNetIncome = ttmNet(row.bank_ticker, row.period);
    const ttmNetInterest = ttmFlow(mb, mord, (r) => r.netInterest);
    const ttmOpex = ttmFlow(mb, mord, (r) => r.opexAbs);
    const ttmGrossOp = ttmFlow(mb, mord, (r) => r.grossOp);
    const ttmIiLoans = ttmFlow(mb, mord, (r) => r.iiLoans);
    const ttmIeDep = ttmFlow(mb, mord, (r) => r.ieDeposits);
    const ttmEcl = ttmFlow(mb, mord, (r) => r.eclProv);
    const ttmPpop = ttmFlow(mb, mord, (r) => r.ppop);
    const avgLoans = avgStock(mb, mord, (r) => r.loans);
    const avgDeposits = avgStock(mb, mord, (r) => r.deposits);
    const avgAssets = avgStock(mb, mord, (r) => r.assets);
    // Raw stock, NOT the average: avgStock() drops non-positive values, so a bank
    // with zero deposits averages to null and is indistinguishable from one we
    // hold no data for. The gate needs the 0 itself.
    row.deposits_stock = mord != null ? (mb?.get(mord)?.deposits ?? null) : null;

    // Returns — TTM income over 5-point average assets.
    if (ttmNetIncome != null && avgAssets != null && avgAssets > 0)
      row.roa = ttmNetIncome / avgAssets;
    if (ttmNetInterest != null && avgAssets != null && avgAssets > 0)
      row.nim = ttmNetInterest / avgAssets;
    // Cost / income — |TTM opex| ÷ |TTM gross operating profit|, two flows.
    if (ttmOpex != null && ttmGrossOp != null && Math.abs(ttmGrossOp) > 0)
      row.cost_income = Math.abs(ttmOpex) / Math.abs(ttmGrossOp);

    // Margin engine — the NIM drivers, same TTM basis.
    if (ttmIiLoans != null && avgLoans != null && avgLoans > 0)
      row.loan_yield = ttmIiLoans / avgLoans;
    if (ttmIeDep != null && avgDeposits != null && avgDeposits > 0)
      row.deposit_cost = ttmIeDep / avgDeposits;
    if (row.loan_yield != null && row.deposit_cost != null)
      row.spread = row.loan_yield - row.deposit_cost;
    if (ttmEcl != null && avgLoans != null && avgLoans > 0)
      row.cost_of_risk = Math.abs(ttmEcl) / avgLoans;
    if (ttmPpop != null && avgAssets != null && avgAssets > 0)
      row.ppop_ratio = ttmPpop / avgAssets;

    // Market valuation (listed banks only; null otherwise). Market cap (TL) =
    // price × shares. Audit amounts are thousand TL → ×1000. Price precedence:
    //  • latest period → live (delayed) quote → latest stored EOD close → q-end
    //  • historical periods → that quarter's quarter-end close (point-in-time)
    const liveQ = live?.get(row.bank_ticker);
    const isLatest = latestPeriodByBank.get(row.bank_ticker) === row.period;
    const close = (
      isLatest
        ? (liveQ?.price ?? latestCloseByTicker.get(row.bank_ticker) ?? closeByKey.get(key))
        : closeByKey.get(key)
    ) ?? null;
    const sh = sharesByTicker.get(row.bank_ticker) ?? null;
    const mktcap = close != null && sh != null && sh > 0 ? close * sh : null;
    const eqRaw = equityByKey.get(key) ?? null;
    if (mktcap != null && eqRaw != null && eqRaw > 0) row.pb = mktcap / (eqRaw * 1000);
    if (mktcap != null && ttmNetIncome != null && ttmNetIncome > 0) row.pe = mktcap / (ttmNetIncome * 1000);

    // Capital + liquidity (audited §4) — ratios already in percent.
    row.cet1 = cet1ByKey.get(key) ?? null;
    row.car = carByKey.get(key) ?? null;
    row.lcr = lcrByKey.get(key) ?? null;

    // Market risk (CAMELS "S") — exposure-magnitude ratios (percent).
    const capV = capByKey.get(key);
    const fxV = fxNopByKey.get(key);
    if (capV != null && capV > 0 && fxV != null) row.fx_nop = (fxV / capV) * 100;
    const rpaV = rpAssetsByKey.get(key);
    const rpgV = rpGapByKey.get(key);
    if (rpaV != null && rpaV > 0 && rpgV != null) row.repricing_gap_1y = (Math.abs(rpgV) / rpaV) * 100;
  }

  return [...map.values()];
}
