/**
 * BIST (Borsa İstanbul) data layer — reads the bist_* D1 tables populated by
 * src/scrapers/bist_scraper.py (Yahoo Finance EOD).
 *
 *   • Index levels (XU100, XBANK) for the /economy equity-markets chart.
 *   • Per-bank price history + valuation (market cap, P/B, P/E, dividend yield)
 *     for the /banks/[ticker] "Market & Valuation" section.
 *
 * Valuation combines the market price (here) with audited fundamentals
 * (web/app/lib/bank-fundamentals.ts): market cap = close × shares outstanding;
 * P/B vs period-end book equity; P/E vs trailing-12m net income; dividend yield
 * = trailing-12m cash dividends ÷ price. Audit amounts are thousand TL, so they
 * are scaled to TL before dividing the TL market cap.
 */
import { cachedAll } from "./db";
import { bankFundamentals } from "./bank-fundamentals";

export interface PricePoint { period_date: string; value: number }

interface PriceRow { period_date: string; close_price: number | null }
interface DivRow { ex_date: string; amount: number | null }
interface ShareRow { shares_outstanding: number | null; as_of: string | null }

/** The BIST-listed universe with a market cap (one row per bank in bist_shares).
 *  Used to scope the live-quote fetch on /cross-bank. */
export async function listedBistTickers(): Promise<string[]> {
  const rows = await cachedAll<{ symbol: string }>(
    `SELECT symbol FROM bist_shares ORDER BY symbol`,
    [],
  );
  return rows.map((r) => r.symbol);
}

/** Daily close history for one symbol (bank ticker or index code). */
export async function bistPriceHistory(
  symbol: string,
  yearsBack = 8,
): Promise<PricePoint[]> {
  const rows = await cachedAll<PriceRow>(
    `SELECT period_date, close_price
       FROM bist_prices
      WHERE symbol = ? AND close_price IS NOT NULL
        AND period_date >= date('now', '-' || ? || ' years')
      ORDER BY period_date`,
    [symbol, yearsBack],
  );
  return rows.map((r) => ({ period_date: r.period_date, value: r.close_price as number }));
}

/** Index levels keyed by friendly label, for the /economy chart. */
export async function bistIndexHistory(yearsBack = 8): Promise<Record<string, PricePoint[]>> {
  const rows = await cachedAll<{ symbol: string; label: string; period_date: string; close_price: number }>(
    `SELECT symbol, label, period_date, close_price
       FROM bist_prices
      WHERE kind = 'index' AND close_price IS NOT NULL
        AND period_date >= date('now', '-' || ? || ' years')
      ORDER BY period_date`,
    [yearsBack],
  );
  const out: Record<string, PricePoint[]> = {};
  for (const r of rows) {
    const key = r.label || r.symbol;
    (out[key] ??= []).push({ period_date: r.period_date, value: r.close_price });
  }
  return out;
}

export interface BistValuation {
  period_date: string;      // latest trading day
  price: number;            // latest close, TL
  changePct1y: number | null;
  marketCap: number | null; // TL
  pb: number | null;        // price / book
  pe: number | null;        // price / TTM earnings
  dividendYield: number | null; // fraction (0.05 = 5%)
  fundamentalsPeriod: string | null; // quarter behind P/B & P/E, e.g. "2026Q1"
  asOf?: number;   // set when a live price was overlaid (regularMarketTime, unix s)
  isLive?: boolean; // true when price/ratios reflect a live Yahoo quote
}

/**
 * Full valuation for a listed bank, or null when there's no BIST price data
 * (e.g. QNBFB — delisted float on Yahoo) so the page renders no section.
 */
export async function bistValuation(
  ticker: string,
  kind: "consolidated" | "unconsolidated",
): Promise<BistValuation | null> {
  const [prices, divs, shareRows, fundamentals] = await Promise.all([
    cachedAll<PriceRow>(
      `SELECT period_date, close_price FROM bist_prices
        WHERE symbol = ? AND kind = 'bank' AND close_price IS NOT NULL
        ORDER BY period_date`,
      [ticker],
    ),
    cachedAll<DivRow>(
      `SELECT ex_date, amount FROM bist_dividends
        WHERE symbol = ? AND ex_date >= date('now', '-1 years')`,
      [ticker],
    ),
    cachedAll<ShareRow>(
      `SELECT shares_outstanding, as_of FROM bist_shares WHERE symbol = ?`,
      [ticker],
    ),
    bankFundamentals(ticker, kind),
  ]);

  if (prices.length === 0) return null;
  const last = prices[prices.length - 1];
  const price = last.close_price as number;

  // 1y price change: close nearest to (latest − 365d), i.e. the first bar on or
  // after that cutoff.
  const cutoff = new Date(last.period_date);
  cutoff.setFullYear(cutoff.getFullYear() - 1);
  const cutoffStr = cutoff.toISOString().slice(0, 10);
  const prior = prices.find((p) => p.period_date >= cutoffStr && p.close_price != null);
  const changePct1y =
    prior && prior.close_price ? (price / prior.close_price - 1) * 100 : null;

  const shares = shareRows[0]?.shares_outstanding ?? null;
  const marketCap = shares != null && shares > 0 ? price * shares : null; // TL

  // Audit amounts are thousand TL → ×1000 to compare against a TL market cap.
  const equityTL =
    fundamentals.equity != null ? fundamentals.equity * 1000 : null;
  const ttmTL =
    fundamentals.ttmNetIncome != null ? fundamentals.ttmNetIncome * 1000 : null;
  const pb = marketCap != null && equityTL != null && equityTL > 0 ? marketCap / equityTL : null;
  const pe = marketCap != null && ttmTL != null && ttmTL > 0 ? marketCap / ttmTL : null;

  const ttmDiv = divs.reduce((s, d) => s + (d.amount ?? 0), 0);
  const dividendYield = ttmDiv > 0 && price > 0 ? ttmDiv / price : null;

  return {
    period_date: last.period_date,
    price,
    changePct1y,
    marketCap,
    pb,
    pe,
    dividendYield,
    fundamentalsPeriod: fundamentals.period,
  };
}
