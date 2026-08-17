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
import { peerExclusionSql, peersOnly } from "./bank_names";
import { BS_ASSET_ROMAN_HIERARCHIES } from "./standard_lines";
import type { TrendPoint } from "@/app/components/TrendChart";

const DEFAULT_KIND = "unconsolidated";

export interface CapRow {
  bank_ticker: string; period: string;
  cet1_capital: number | null; additional_tier1_capital?: number | null;
  tier1_capital: number | null;
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
 * CET1, where the row itself doesn't carry it: Tier-1 − AT1. The identity is
 * definitional (Tier-1 = CET1 + AT1), and it reproduces the bank's own printed
 * CET1 ratio — ISCTR 2026Q1: (420,695,564 − 22,061,250) / 3,396,087,828 =
 * 11.74%, exactly the ratio it prints.
 */
function cet1Of(r: CapRow): number | null {
  if (r.cet1_capital != null && r.cet1_capital > 0) return r.cet1_capital;
  if (r.tier1_capital != null && r.tier1_capital > 0) {
    return r.tier1_capital - (r.additional_tier1_capital ?? 0);
  }
  return null;
}

/**
 * Sector CET1 / Tier-1 / CAR (%), per quarter — Σ component ÷ Σ RWA across the
 * banks reporting that quarter. Mathematically sound (capital + RWA are stocks).
 *
 * COVERAGE MUST MATCH PER COMPONENT. A bank missing one component but carrying
 * RWA used to add its RWA to *every* denominator while adding 0 to that
 * component's numerator — silently understating the ratio. ISCTR's cet1_capital
 * is absent for 2025Q4/2026Q1 while its RWA is 10.6% of the sector's, which
 * dragged the published CET1 to 10.56% when the true figure is 11.79%. So each
 * ratio now sums numerator AND denominator over the banks that actually report
 * that component (after recovering CET1 from Tier-1 − AT1 where possible).
 *
 * PEER UNIVERSE. This is the choke point where per-bank rows become one sector
 * number, so the peer exclusion belongs here: a CCP's capital against a CCP's
 * RWA is a real ratio for that institution and a category error inside a
 * banking-sector aggregate (DESIGN.md — compare like with like).
 */
export function aggregateCapital(rows: readonly CapRow[]): TrendPoint[] {
  type Acc = { num: number; den: number };
  const zero = (): Acc => ({ num: 0, den: 0 });
  const agg = new Map<string, { cet1: Acc; tier1: Acc; car: Acc }>();
  for (const r of peersOnly(rows)) {
    if (r.total_rwa == null || r.total_rwa <= 0) continue;
    const a = agg.get(r.period) ?? { cet1: zero(), tier1: zero(), car: zero() };
    const add = (acc: Acc, v: number | null | undefined) => {
      if (v == null || v <= 0) return; // no component → this bank's RWA sits out
      acc.num += v;
      acc.den += r.total_rwa as number;
    };
    add(a.cet1, cet1Of(r));
    add(a.tier1, r.tier1_capital);
    add(a.car, r.total_capital);
    agg.set(r.period, a);
  }
  const out: TrendPoint[] = [];
  for (const period of [...agg.keys()].sort()) {
    const a = agg.get(period)!;
    const push = (code: string, acc: Acc) => {
      if (acc.den > 0) out.push({ period, bank_type_code: code, value: (acc.num / acc.den) * 100 });
    };
    push("CET1", a.cet1);
    push("TIER1", a.tier1);
    push("CAR", a.car);
  }
  return out;
}

export async function sectorCapitalRatios(kind: string = DEFAULT_KIND): Promise<TrendPoint[]> {
  const rows = await cachedAll<CapRow>(
    `SELECT bank_ticker, period, cet1_capital, additional_tier1_capital, tier1_capital,
            total_capital, total_rwa
       FROM bank_audit_capital WHERE kind = ? AND period_type = 'current'`,
    [kind],
  );
  return aggregateCapital(rows);
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
 *
 * This is a RANKING, so the peer universe applies: Takasbank's CAR is computed
 * against a clearing house's risk-weighted assets and would seat it in a league
 * of lenders.
 *
 * ⚠️ This used to claim "its own figure stays on `/banks/TAKAS`". It does not,
 * and has not since the vitals were sourced from the heatmap: `heatmap.ts`
 * hands a peer-excluded ticker a throwaway row (so no rank, colour scale or
 * percentile can be computed off it), the bank page reads its vitals from that
 * row, and the whole block therefore renders empty. `/banks/TAKAS` shows no
 * CAR, no CET1 and no total assets, though D1 holds all three — verified
 * 2026-08-17 against every bank page (CAR 21.7%, assets ₺457bn).
 *
 * The page is honest about it rather than silent: it prints "deliberately
 * excluded from the peer ratio panel — market infrastructure, not a lender"
 * and points at Financials, where the statements are. So this is a product
 * question, not a bug: showing a peer-excluded bank its own figures means
 * letting its row into the heatmap map and excluding it at every ranking site
 * instead of at the source, which is the more fragile of the two designs.
 */
export async function perBankCapital(
  kind: string = DEFAULT_KIND,
): Promise<{ period: string | null; rows: BankCapitalRow[] }> {
  const period = await auditRatioLatestPeriod(kind);
  if (period == null) return { period: null, rows: [] };
  const rows = await cachedAll<CapRow>(
    `SELECT bank_ticker, period, cet1_capital, additional_tier1_capital, tier1_capital,
            total_capital, total_rwa
       FROM bank_audit_capital
      WHERE kind = ? AND period_type = 'current' AND period = ?`,
    [kind, period],
  );
  if (rows.length === 0) return { period: null, rows: [] };
  const pct = (n: number | null, rwa: number) => (n != null ? (n / rwa) * 100 : null);
  const out: BankCapitalRow[] = [];
  for (const r of peersOnly(rows)) {
    if (r.total_rwa == null || r.total_rwa <= 0) continue;
    out.push({
      bank_ticker: r.bank_ticker,
      car: pct(r.total_capital, r.total_rwa),
      tier1: pct(r.tier1_capital, r.total_rwa),
      // Same recovery as the sector aggregate — a blank CET1 cell would otherwise
      // print an empty ratio for a bank whose Tier-1 and AT1 are both on the page.
      cet1: pct(cet1Of(r), r.total_rwa),
    });
  }
  out.sort((a, b) => (b.car ?? -Infinity) - (a.car ?? -Infinity));
  return { period, rows: out };
}

/**
 * Sector LCR / NSFR / leverage (%), per quarter — asset-weighted average across
 * reporting banks (LCR/NSFR are ratios with no stored numerator, so a Σ/Σ isn't
 * possible; asset-weighting reflects the system better than a simple mean).
 *
 * Peers only. A CCP's funding ratios answer a different question than a
 * deposit-funded bank's: Takasbank prints NSFR of 46–93% across recent quarters,
 * which is not a bank in breach — it has no deposits to be stable about — and
 * averaging it into the sector line reads as one.
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
  for (const r of peersOnly(liq)) {
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

/**
 * Latest quarter reported by at least `minBanks` peer banks (for dataThrough,
 * and for the by-bank ranking's period). Peers only — this stamps the freshness
 * of the ratios above, so it must be the latest quarter of the population those
 * ratios are drawn from.
 *
 * The quorum is the point. A bare `MAX(period)` follows the FIRST filer of a new
 * quarter: TEB published 2026Q2 on its own, and an unguarded max would have
 * ranked the sector's capital adequacy on a table of one bank — on `/capital`
 * and on the home page — for the weeks until the rest of the fleet filed. All 38
 * banks report capital each quarter, so 10 clears within days of the season
 * opening and never gates a settled quarter. Same guard as
 * `latestCommonPeriod` (heatmap) and `marketRiskLatestPeriod` (market risk).
 */
export async function auditRatioLatestPeriod(
  kind: string = DEFAULT_KIND,
  minBanks = 10,
): Promise<string | null> {
  const peers = peerExclusionSql();
  const rows = await cachedAll<{ period: string }>(
    `SELECT period, COUNT(DISTINCT bank_ticker) AS n
       FROM bank_audit_capital
      WHERE kind = ? AND period_type = 'current'${peers.clause}
      GROUP BY period HAVING n >= ? ORDER BY period DESC LIMIT 1`,
    [kind, ...peers.params, minBanks],
  );
  return rows[0]?.period ?? null;
}
