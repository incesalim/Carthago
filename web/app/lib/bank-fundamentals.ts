/**
 * Per-bank audited fundamentals for valuation ratios (P/B, P/E).
 *
 * The methodology mirrors the ROE computation in web/app/lib/heatmap.ts
 * (heatmapPanel) — kept as standalone, single-ticker helpers so the per-bank
 * page can compute P/B and P/E without pulling the whole cross-bank panel:
 *   • Book equity is matched by LABEL on any roman-numeral line (not a fixed
 *     numeral) so participation banks — equity at XIV., not XVI. — resolve too.
 *   • TTM net income de-cumulates the YTD P&L to single quarters and sums the
 *     trailing four. The middle quarters telescope, so the result is robust to
 *     the YTD-vs-3-month column quirks in some historical extractions:
 *     TTM(latest) = YTD(latest) + FY(prior) − YTD(same quarter, prior year).
 *
 * Amounts in the audit tables are in THOUSAND TL — callers multiply by 1000 to
 * get TL before dividing a TL market cap.
 */
import { cachedAll } from "./db";
import { ordOf, ttmEndingAt } from "./period-math";

export interface BankFundamentals {
  /** Most recent quarter with a non-null equity reading, e.g. "2026Q1". */
  period: string | null;
  /** Period-end book equity, thousand TL. */
  equity: number | null;
  /** Trailing-twelve-month net income ending `period`, thousand TL. */
  ttmNetIncome: number | null;
}

interface EquityRow { period: string; equity: number | null }
interface PlRow { period: string; net_profit: number | null }

export async function bankFundamentals(
  ticker: string,
  kind: "consolidated" | "unconsolidated",
): Promise<BankFundamentals> {
  const [equityRows, plRows] = await Promise.all([
    cachedAll<EquityRow>(
      `SELECT period,
              MAX(CASE WHEN hierarchy GLOB '[IVXLCDM]*.'
                        AND (UPPER(item_name) LIKE '%ZKAYNAK%' OR UPPER(item_name) LIKE '%EQUITY%')
                       THEN amount_total END) AS equity
         FROM bank_audit_balance_sheet
        WHERE bank_ticker = ? AND kind = ? AND statement = 'liabilities'
        GROUP BY period`,
      [ticker, kind],
    ),
    cachedAll<PlRow>(
      `SELECT period,
              COALESCE(MAX(CASE WHEN hierarchy = 'XXV.' THEN amount END),
                       MAX(CASE WHEN hierarchy = 'XIX.' THEN amount END)) AS net_profit
         FROM bank_audit_profit_loss
        WHERE bank_ticker = ? AND kind = ?
        GROUP BY period`,
      [ticker, kind],
    ),
  ]);

  // Latest period that actually has an equity figure.
  let latest: { period: string; ord: number; equity: number } | null = null;
  for (const r of equityRows) {
    const ord = ordOf(r.period);
    if (ord == null || r.equity == null) continue;
    if (!latest || ord > latest.ord) latest = { period: r.period, ord, equity: r.equity };
  }
  if (!latest) return { period: null, equity: null, ttmNetIncome: null };

  // YTD net income indexed by chronological quarter ordinal.
  const ytdByOrd = new Map<number, number>();
  for (const r of plRows) {
    const ord = ordOf(r.period);
    if (ord != null && r.net_profit != null) ytdByOrd.set(ord, r.net_profit);
  }
  const ttm = ttmEndingAt(ytdByOrd, latest.ord);

  return { period: latest.period, equity: latest.equity, ttmNetIncome: ttm };
}
