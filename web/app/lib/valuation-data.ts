/**
 * Valuation data layer (SERVER ONLY) — assembles the per-bank "seed" the
 * /valuation page hands to the browser, where the actual valuation maths run
 * live as the user edits assumptions (see valuation.ts).
 *
 * Reuses the existing audited-fundamentals + BIST layers read-only:
 *   • bankFundamentals (book equity + TTM net income, thousand TL)
 *   • bistValuation    (price / market cap / P/B / P/E / dividend yield)
 *   • bistPriceHistory (daily closes → weekly returns for the equity beta)
 *   • evdsSeries       (CBRT funding rate → TRY risk-free proxy)
 * It adds two derived inputs that don't exist yet: a regression equity beta vs
 * XU100, and a starting ROE on the same TTM/average-equity basis the cross-bank
 * heatmap uses (so a bank prices consistently across tabs).
 */
import { cachedAll } from "./db";
import { bankFundamentals } from "./bank-fundamentals";
import { bistValuation, bistPriceHistory, type PricePoint } from "./bist";
import { applyLivePrice, type LiveQuote } from "./bist-live";
import { evdsSeries } from "./metrics";
import { linregBeta } from "./valuation";
import { BANK_NAMES } from "./bank_names";

type Kind = "consolidated" | "unconsolidated";

// ---------------------------------------------------------------------------
// Equity beta — weekly returns vs XU100
// ---------------------------------------------------------------------------

export interface BankBeta {
  /** Levered equity beta, or null when there's too little overlapping history. */
  beta: number | null;
  rSquared: number | null;
  /** Number of paired weekly return observations. */
  n: number;
  /** Human note when a fallback was used. */
  note: string | null;
}

const dayNum = (d: string): number => Math.floor(Date.parse(`${d}T00:00:00Z`) / 86_400_000);

/** Last close in each ISO-ish week bucket (7-day buckets from the epoch). Points
 *  must be ascending by date (bistPriceHistory guarantees this), so the last
 *  write per bucket is the latest close in that week. */
function weeklyCloses(points: PricePoint[]): Map<number, number> {
  const m = new Map<number, number>();
  for (const p of points) if (p.value > 0) m.set(Math.floor(dayNum(p.period_date) / 7), p.value);
  return m;
}

/** Contemporaneous weekly simple returns for two series, over weeks present in
 *  BOTH and adjacent (so every return spans the same one-week interval). */
function pairedWeeklyReturns(bank: PricePoint[], idx: PricePoint[]): { y: number[]; x: number[] } {
  const wb = weeklyCloses(bank);
  const wi = weeklyCloses(idx);
  const weeks = [...wb.keys()].filter((k) => wi.has(k)).sort((a, b) => a - b);
  const y: number[] = [];
  const x: number[] = [];
  for (let i = 1; i < weeks.length; i++) {
    if (weeks[i] - weeks[i - 1] !== 1) continue; // skip gaps → equal intervals only
    const b0 = wb.get(weeks[i - 1])!;
    const b1 = wb.get(weeks[i])!;
    const i0 = wi.get(weeks[i - 1])!;
    const i1 = wi.get(weeks[i])!;
    y.push(b1 / b0 - 1);
    x.push(i1 / i0 - 1);
  }
  return { y, x };
}

const MIN_BETA_OBS = 30;

/**
 * Regression beta of a bank's weekly return on XU100's, over `yearsBack`. Thin
 * BIST bank trading makes daily betas noisy, so we resample to weekly. Falls
 * back to null (caller substitutes a sector default of 1.0) below MIN_BETA_OBS.
 */
export async function bankBeta(ticker: string, yearsBack = 2): Promise<BankBeta> {
  const [bank, idx] = await Promise.all([
    bistPriceHistory(ticker, yearsBack),
    bistPriceHistory("XU100", yearsBack),
  ]);
  const { y, x } = pairedWeeklyReturns(bank, idx);
  const fit = linregBeta(y, x);
  if (!fit || fit.n < MIN_BETA_OBS) {
    return {
      beta: null,
      rSquared: fit?.r2 ?? null,
      n: fit?.n ?? 0,
      note: "Too little overlapping price history — using a sector default β = 1.0.",
    };
  }
  return { beta: fit.beta, rSquared: fit.r2, n: fit.n, note: null };
}

// ---------------------------------------------------------------------------
// TRY risk-free proxy — CBRT effective funding rate (EVDS TP.APIFON4)
// ---------------------------------------------------------------------------

export interface RiskFree {
  /** Fraction (e.g. 0.40). */
  rf: number;
  asOf: string | null;
  source: string;
}

const RF_FALLBACK = 0.4;

export async function tryRiskFree(): Promise<RiskFree> {
  const rows = await evdsSeries("TP.APIFON4", 1); // last year of the daily funding cost
  const last = rows[rows.length - 1];
  return {
    rf: last ? last.value / 100 : RF_FALLBACK,
    asOf: last?.period_date ?? null,
    source: "CBRT effective cost of funding (TP.APIFON4)",
  };
}

// ---------------------------------------------------------------------------
// Average equity (trailing 5 quarter-ends) → starting ROE on the heatmap basis
// ---------------------------------------------------------------------------

interface EquityRow {
  equity: number | null;
}

async function avgTrailingEquity(ticker: string, kind: Kind): Promise<number | null> {
  // Same label-based equity match as bank-fundamentals/heatmap (roman numeral
  // varies by layout — XVI. deposit, XIV. participation).
  const rows = await cachedAll<EquityRow>(
    `SELECT MAX(CASE WHEN hierarchy GLOB '[IVXLCDM]*.'
                      AND (UPPER(item_name) LIKE '%ZKAYNAK%' OR UPPER(item_name) LIKE '%EQUITY%')
                     THEN amount_total END) AS equity
       FROM bank_audit_balance_sheet
      WHERE bank_ticker = ? AND kind = ? AND statement = 'liabilities'
      GROUP BY period
      ORDER BY period DESC
      LIMIT 5`,
    [ticker, kind],
  );
  const eqs = rows.map((r) => r.equity).filter((e): e is number => e != null && e > 0);
  if (eqs.length < 2) return null;
  return eqs.reduce((s, e) => s + e, 0) / eqs.length;
}

// ---------------------------------------------------------------------------
// The seed
// ---------------------------------------------------------------------------

export interface ValuationSeed {
  ticker: string;
  name: string;
  /** Fundamentals quarter behind book/ROE, e.g. "2026Q1". */
  period: string | null;

  // fundamentals (thousand TL)
  b0: number | null; // book equity
  ttmNetIncome: number | null;
  /** Starting ROE = TTM net income ÷ average trailing-5-quarter equity, fraction. */
  roe0: number | null;

  // market (TL, live-overlaid where possible)
  shares: number | null;
  price: number | null;
  marketCap: number | null;
  pb: number | null;
  pe: number | null;
  dividendYield: number | null;
  /** Trailing payout = dividend yield × P/E (= D/EPS), fraction; null if unknown. */
  payoutTTM: number | null;

  // cost-of-equity inputs
  /** Resolved beta actually used (sector default 1.0 when estimation failed). */
  beta: number;
  /** Whether `beta` is the regression estimate (true) or the fallback (false). */
  betaEstimated: boolean;
  betaR2: number | null;
  betaN: number;
  betaNote: string | null;
  rf: number;
  rfSource: string;
  rfAsOf: string | null;

  asOf?: number;
  isLive?: boolean;
}

/**
 * Assemble a bank's valuation seed. Returns null when the bank has no BIST price
 * data (unlisted/delisted) — there is nothing to value against the market, so
 * the page omits it. `opts.rf` lets the page fetch the risk-free proxy once and
 * share it across all banks; `opts.live` overlays request-time Yahoo quotes.
 */
export async function valuationSeed(
  ticker: string,
  kind: Kind,
  opts: { live?: Map<string, LiveQuote>; rf?: RiskFree } = {},
): Promise<ValuationSeed | null> {
  const [fund, valuation, beta, avgEquity, rfData] = await Promise.all([
    bankFundamentals(ticker, kind),
    bistValuation(ticker, kind),
    bankBeta(ticker),
    avgTrailingEquity(ticker, kind),
    opts.rf ? Promise.resolve(opts.rf) : tryRiskFree(),
  ]);

  if (!valuation) return null; // no listed price → not valuable here

  const live = opts.live?.get(ticker);
  const v = live ? applyLivePrice(valuation, live) : valuation;

  const b0 = fund.equity; // thousand TL
  const ttm = fund.ttmNetIncome;
  const roe0 =
    ttm != null && avgEquity != null && avgEquity > 0
      ? ttm / avgEquity
      : ttm != null && b0 != null && b0 > 0
        ? ttm / b0 // fallback: TTM ÷ period-end equity
        : null;

  const payoutTTM =
    v.dividendYield != null && v.pe != null ? v.dividendYield * v.pe : null;

  const shares =
    v.marketCap != null && v.price != null && v.price > 0 ? v.marketCap / v.price : null;

  return {
    ticker,
    name: BANK_NAMES[ticker] ?? ticker,
    period: fund.period,
    b0,
    ttmNetIncome: ttm,
    roe0,
    shares,
    price: v.price ?? null,
    marketCap: v.marketCap,
    pb: v.pb,
    pe: v.pe,
    dividendYield: v.dividendYield,
    payoutTTM,
    beta: beta.beta ?? 1.0,
    betaEstimated: beta.beta != null,
    betaR2: beta.rSquared,
    betaN: beta.n,
    betaNote: beta.note,
    rf: rfData.rf,
    rfSource: rfData.source,
    rfAsOf: rfData.asOf,
    asOf: v.asOf,
    isLive: v.isLive,
  };
}
