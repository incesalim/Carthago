/**
 * Audited §4 capital + liquidity ratios, aggregated to a sector view (SERVER
 * ONLY). Fills the FSI-core gaps the dashboard audit flagged: the monthly
 * bulletin carries only total CAR (no CET1) and no LCR/NSFR, but the per-bank
 * BRSA §4 tables (bank_audit_capital / bank_audit_liquidity) do.
 *
 *  - Capital ratios are aggregated correctly from components: sector CET1 =
 *    Σ CET1 capital ÷ Σ RWA "of reporting banks" (same-source, like
 *    market-share.ts). Tier-1 and total (CAR) likewise.
 *  - LCR / NSFR / leverage are per-bank ratios with no stored numerator, so the
 *    sector view is the ASSET-WEIGHTED average across reporting banks (weight =
 *    total assets), clearly labelled as such.
 *
 * Returns TrendChart points (period, bank_type_code = series key, value%).
 * period_type = 'current'; quarterly `YYYYQN`.
 */
import { cachedAll } from "./db";
import { BS_ASSET_ROMAN_HIERARCHIES } from "./standard_lines";
import type { TrendPoint } from "@/app/components/TrendChart";

const DEFAULT_KIND = "unconsolidated";

interface CapRow {
  bank_ticker: string; period: string;
  cet1_capital: number | null; tier1_capital: number | null;
  total_capital: number | null; total_rwa: number | null;
}
interface LiqRow {
  bank_ticker: string; period: string;
  lcr_total: number | null; nsfr: number | null; leverage_ratio: number | null;
}
interface AssetRow { bank_ticker: string; period: string; ta: number | null }

export const AUDIT_CAPITAL_LABELS: Record<string, string> = {
  CET1: "CET1 ratio", TIER1: "Tier-1 ratio", CAR: "Total capital (CAR)",
};
export const AUDIT_LIQUIDITY_LABELS: Record<string, string> = {
  LCR: "LCR (total)", NSFR: "NSFR", LEV: "Leverage ratio",
};

/**
 * Sector CET1 / Tier-1 / CAR (%), per quarter — Σ component ÷ Σ RWA across the
 * banks reporting that quarter. Mathematically sound (capital + RWA are stocks).
 */
export async function sectorCapitalRatios(kind: string = DEFAULT_KIND): Promise<TrendPoint[]> {
  const rows = await cachedAll<CapRow>(
    `SELECT bank_ticker, period, cet1_capital, tier1_capital, total_capital, total_rwa
       FROM bank_audit_capital WHERE kind = ? AND period_type = 'current'`,
    [kind],
  );
  // period → {cet1, tier1, total, rwa} sums (only banks with RWA present)
  const agg = new Map<string, { cet1: number; tier1: number; total: number; rwa: number }>();
  for (const r of rows) {
    if (r.total_rwa == null || r.total_rwa <= 0) continue;
    const a = agg.get(r.period) ?? { cet1: 0, tier1: 0, total: 0, rwa: 0 };
    a.cet1 += r.cet1_capital ?? 0;
    a.tier1 += r.tier1_capital ?? 0;
    a.total += r.total_capital ?? 0;
    a.rwa += r.total_rwa;
    agg.set(r.period, a);
  }
  const out: TrendPoint[] = [];
  for (const period of [...agg.keys()].sort()) {
    const a = agg.get(period)!;
    if (a.rwa <= 0) continue;
    out.push({ period, bank_type_code: "CET1", value: (a.cet1 / a.rwa) * 100 });
    out.push({ period, bank_type_code: "TIER1", value: (a.tier1 / a.rwa) * 100 });
    out.push({ period, bank_type_code: "CAR", value: (a.total / a.rwa) * 100 });
  }
  return out;
}

/** One bank's latest-quarter capital ratios (%), for the by-bank ranking. */
export interface BankCapitalRow {
  bank_ticker: string;
  car: number | null;   // total capital ÷ RWA
  tier1: number | null; // Tier-1 ÷ RWA
  cet1: number | null;  // CET1 ÷ RWA
}

/**
 * Per-bank CAR / Tier-1 / CET1 for the latest audited quarter, ranked by CAR
 * (desc). Each ratio = its capital component ÷ that bank's total RWA — the same
 * arithmetic as the sector aggregate, just not summed. Banks with no RWA are
 * dropped (can't form a ratio). Powers the "By bank" capital-adequacy table.
 */
export async function perBankCapital(
  kind: string = DEFAULT_KIND,
): Promise<{ period: string | null; rows: BankCapitalRow[] }> {
  const rows = await cachedAll<CapRow>(
    `SELECT bank_ticker, period, cet1_capital, tier1_capital, total_capital, total_rwa
       FROM bank_audit_capital
      WHERE kind = ? AND period_type = 'current'
        AND period = (SELECT MAX(period) FROM bank_audit_capital
                       WHERE kind = ? AND period_type = 'current')`,
    [kind, kind],
  );
  if (rows.length === 0) return { period: null, rows: [] };
  const period = rows[0].period;
  const pct = (n: number | null, rwa: number) => (n != null ? (n / rwa) * 100 : null);
  const out: BankCapitalRow[] = [];
  for (const r of rows) {
    if (r.total_rwa == null || r.total_rwa <= 0) continue;
    out.push({
      bank_ticker: r.bank_ticker,
      car: pct(r.total_capital, r.total_rwa),
      tier1: pct(r.tier1_capital, r.total_rwa),
      cet1: pct(r.cet1_capital, r.total_rwa),
    });
  }
  out.sort((a, b) => (b.car ?? -Infinity) - (a.car ?? -Infinity));
  return { period, rows: out };
}

/**
 * Sector LCR / NSFR / leverage (%), per quarter — asset-weighted average across
 * reporting banks (LCR/NSFR are ratios with no stored numerator, so a Σ/Σ isn't
 * possible; asset-weighting reflects the system better than a simple mean).
 */
export async function sectorLiquidityRatios(kind: string = DEFAULT_KIND): Promise<TrendPoint[]> {
  const romanPlaceholders = BS_ASSET_ROMAN_HIERARCHIES.map(() => "?").join(",");
  const [liq, assets] = await Promise.all([
    cachedAll<LiqRow>(
      `SELECT bank_ticker, period, lcr_total, nsfr, leverage_ratio
         FROM bank_audit_liquidity WHERE kind = ? AND period_type = 'current'`,
      [kind],
    ),
    cachedAll<AssetRow>(
      `SELECT bank_ticker, period, SUM(amount_total) AS ta
         FROM bank_audit_balance_sheet
        WHERE kind = ? AND statement = 'assets' AND hierarchy IN (${romanPlaceholders})
        GROUP BY bank_ticker, period`,
      [kind, ...BS_ASSET_ROMAN_HIERARCHIES],
    ),
  ]);
  const wByKey = new Map<string, number>();
  for (const a of assets) if (a.ta && a.ta > 0) wByKey.set(`${a.bank_ticker}|${a.period}`, a.ta);

  // period → per-metric {weightedSum, weight}
  type Acc = { sum: number; w: number };
  const agg = new Map<string, { lcr: Acc; nsfr: Acc; lev: Acc }>();
  const add = (acc: Acc, val: number | null, w: number) => {
    if (val != null && w > 0) { acc.sum += val * w; acc.w += w; }
  };
  for (const r of liq) {
    const w = wByKey.get(`${r.bank_ticker}|${r.period}`) ?? 0;
    if (w <= 0) continue;
    const a = agg.get(r.period) ?? { lcr: { sum: 0, w: 0 }, nsfr: { sum: 0, w: 0 }, lev: { sum: 0, w: 0 } };
    add(a.lcr, r.lcr_total, w);
    add(a.nsfr, r.nsfr, w);
    add(a.lev, r.leverage_ratio, w);
    agg.set(r.period, a);
  }
  const out: TrendPoint[] = [];
  for (const period of [...agg.keys()].sort()) {
    const a = agg.get(period)!;
    if (a.lcr.w > 0) out.push({ period, bank_type_code: "LCR", value: a.lcr.sum / a.lcr.w });
    if (a.nsfr.w > 0) out.push({ period, bank_type_code: "NSFR", value: a.nsfr.sum / a.nsfr.w });
    if (a.lev.w > 0) out.push({ period, bank_type_code: "LEV", value: a.lev.sum / a.lev.w });
  }
  return out;
}

/** Latest quarter present in the audited capital table (for dataThrough). */
export async function auditRatioLatestPeriod(kind: string = DEFAULT_KIND): Promise<string | null> {
  const rows = await cachedAll<{ period: string }>(
    `SELECT MAX(period) AS period FROM bank_audit_capital WHERE kind = ? AND period_type = 'current'`,
    [kind],
  );
  return rows[0]?.period ?? null;
}
