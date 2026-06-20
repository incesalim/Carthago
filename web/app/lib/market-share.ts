/**
 * Market share & concentration — data layer (SERVER ONLY).
 *
 * Competitive-dynamics view over the same bank_audit_* tables as heatmap.ts.
 * For every (bank, period) it computes each bank's share of total assets,
 * loans, and deposits, plus an asset-size rank and the sector HHI per period.
 *
 * Denominator = the SUM across the banks that REPORTED that period, NOT the
 * BDDK monthly sector aggregate. The audited universe is ~32 banks ≈ 98% of
 * sector assets, so "share of the covered universe" ≈ sector share — and using
 * the same source for numerator and denominator avoids the unit/timing mismatch
 * (audit thousand-TL quarter-end vs BDDK million-TL month-end) and the
 * bank-type double-count trap of the published aggregates. Shares are therefore
 * "of reporting banks"; surface that caveat where it's shown.
 *
 * Period format is `YYYYQN` (no dash); lexical sort is chronological.
 * Balances are thousand TL — shares are unit-free so the scale cancels.
 */
import { cachedAll } from "./db";
import { BS_ASSET_ROMAN_HIERARCHIES } from "./standard_lines";

const DEFAULT_KIND = "unconsolidated";

/** One bank in one quarter, with absolute balances and shares-of-reporting. */
export interface ShareRow {
  bank_ticker: string;
  period: string;
  assets: number | null;
  loans: number | null;
  deposits: number | null;
  /** Fraction (0–1) of the period's reporting-bank total. Null if the bank or
   *  the period total is missing/non-positive. */
  assets_share: number | null;
  loans_share: number | null;
  deposits_share: number | null;
  /** 1 = largest by assets among banks reporting that period. */
  assets_rank: number | null;
}

/** Herfindahl–Hirschman index per period (Σ shareᵢ² × 10 000, 0–10 000). */
export interface HhiPoint {
  period: string;
  assets_hhi: number | null;
  loans_hhi: number | null;
  deposits_hhi: number | null;
  /** Banks contributing an asset figure that period (the HHI/share base). */
  n_banks: number;
}

interface RawRow { bank_ticker: string; period: string; v: number | null }

/**
 * Per-(bank, period) absolute assets / loans / deposits across every quarter.
 * Three narrow GROUP BY scans (cached 12h via cachedAll), merged on CPU. Assets
 * = the BS asset Roman subtotals I.–X. (same basis as heatmap/bankSummaries);
 * loans = asset sub-item 2.1; deposits = liability Roman I.
 */
async function fleetBalances(kind: string): Promise<Map<string, { assets: number | null; loans: number | null; deposits: number | null }>> {
  const romanPh = BS_ASSET_ROMAN_HIERARCHIES.map(() => "?").join(",");
  const [assets, loans, deposits] = await Promise.all([
    cachedAll<RawRow>(
      `SELECT bank_ticker, period, SUM(amount_total) AS v
         FROM bank_audit_balance_sheet
        WHERE kind = ? AND statement = 'assets'
          AND hierarchy IN (${romanPh})
        GROUP BY bank_ticker, period`,
      [kind, ...BS_ASSET_ROMAN_HIERARCHIES],
    ),
    cachedAll<RawRow>(
      `SELECT bank_ticker, period, MAX(amount_total) AS v
         FROM bank_audit_balance_sheet
        WHERE kind = ? AND statement = 'assets' AND hierarchy = '2.1'
        GROUP BY bank_ticker, period`,
      [kind],
    ),
    cachedAll<RawRow>(
      `SELECT bank_ticker, period, MAX(amount_total) AS v
         FROM bank_audit_balance_sheet
        WHERE kind = ? AND statement = 'liabilities' AND hierarchy = 'I.'
        GROUP BY bank_ticker, period`,
      [kind],
    ),
  ]);
  const out = new Map<string, { assets: number | null; loans: number | null; deposits: number | null }>();
  const ensure = (k: string) => {
    let r = out.get(k);
    if (!r) { r = { assets: null, loans: null, deposits: null }; out.set(k, r); }
    return r;
  };
  for (const r of assets) ensure(`${r.bank_ticker}|${r.period}`).assets = r.v;
  for (const r of loans) ensure(`${r.bank_ticker}|${r.period}`).loans = r.v;
  for (const r of deposits) ensure(`${r.bank_ticker}|${r.period}`).deposits = r.v;
  return out;
}

/**
 * Full share panel: one ShareRow per (bank, period). Shares are computed within
 * each period against the sum over the banks reporting a positive figure for
 * that metric, and asset rank is dense-ranked largest-first.
 */
export async function marketSharePanel(kind: string = DEFAULT_KIND): Promise<ShareRow[]> {
  const balances = await fleetBalances(kind);

  // Group keys by period to total + rank within each quarter.
  const byPeriod = new Map<string, { ticker: string; assets: number | null; loans: number | null; deposits: number | null }[]>();
  for (const [key, b] of balances) {
    const [ticker, period] = key.split("|");
    if (!byPeriod.has(period)) byPeriod.set(period, []);
    byPeriod.get(period)!.push({ ticker, ...b });
  }

  const rows: ShareRow[] = [];
  for (const [period, banks] of byPeriod) {
    const sum = (f: (x: typeof banks[number]) => number | null) =>
      banks.reduce((s, x) => s + (f(x) != null && f(x)! > 0 ? f(x)! : 0), 0);
    const totA = sum((x) => x.assets);
    const totL = sum((x) => x.loans);
    const totD = sum((x) => x.deposits);
    // Dense asset rank, largest first; banks with no asset figure are unranked.
    const ranked = [...banks]
      .filter((x) => x.assets != null && x.assets > 0)
      .sort((a, b) => (b.assets ?? 0) - (a.assets ?? 0));
    const rankOf = new Map<string, number>();
    ranked.forEach((x, i) => rankOf.set(x.ticker, i + 1));

    for (const x of banks) {
      rows.push({
        bank_ticker: x.ticker,
        period,
        assets: x.assets,
        loans: x.loans,
        deposits: x.deposits,
        assets_share: x.assets != null && totA > 0 ? x.assets / totA : null,
        loans_share: x.loans != null && totL > 0 ? x.loans / totL : null,
        deposits_share: x.deposits != null && totD > 0 ? x.deposits / totD : null,
        assets_rank: rankOf.get(x.ticker) ?? null,
      });
    }
  }
  return rows;
}

/** Sector HHI per period from a share panel (pure; no DB). Σ shareᵢ² × 10 000:
 *  <1500 unconcentrated, 1500–2500 moderate, >2500 concentrated (US DOJ bands). */
export function hhiSeries(rows: ShareRow[]): HhiPoint[] {
  const byPeriod = new Map<string, ShareRow[]>();
  for (const r of rows) {
    if (!byPeriod.has(r.period)) byPeriod.set(r.period, []);
    byPeriod.get(r.period)!.push(r);
  }
  const hhi = (rs: ShareRow[], f: (r: ShareRow) => number | null): number | null => {
    let s = 0;
    let any = false;
    for (const r of rs) {
      const v = f(r);
      if (v != null) { s += v * v; any = true; }
    }
    return any ? s * 10000 : null;
  };
  return [...byPeriod.entries()]
    .sort((a, b) => (a[0] < b[0] ? -1 : 1))
    .map(([period, rs]) => ({
      period,
      assets_hhi: hhi(rs, (r) => r.assets_share),
      loans_hhi: hhi(rs, (r) => r.loans_share),
      deposits_hhi: hhi(rs, (r) => r.deposits_share),
      n_banks: rs.filter((r) => r.assets_share != null).length,
    }));
}

/** One bank's share trend over time (sorted by period) — for the per-bank page. */
export function bankShareSeries(rows: ShareRow[], ticker: string): ShareRow[] {
  return rows
    .filter((r) => r.bank_ticker === ticker)
    .sort((a, b) => (a.period < b.period ? -1 : 1));
}

export interface LeagueEntry {
  bank_ticker: string;
  assets: number | null;
  assets_share: number | null;
  loans_share: number | null;
  deposits_share: number | null;
  rank: number | null;
  /** Rank improvement vs the prior quarter (+1 = climbed one place); null if the
   *  bank wasn't ranked last quarter. */
  rank_change: number | null;
}

/** League table for one period: banks ordered largest-first by assets, each
 *  carrying its quarter-over-quarter rank move. `rows` is a full share panel. */
export function leagueTable(rows: ShareRow[], period: string): LeagueEntry[] {
  const priorPeriod = [...new Set(rows.map((r) => r.period))]
    .filter((p) => p < period)
    .sort()
    .pop();
  const priorRank = new Map<string, number>();
  if (priorPeriod) {
    for (const r of rows) {
      if (r.period === priorPeriod && r.assets_rank != null) priorRank.set(r.bank_ticker, r.assets_rank);
    }
  }
  return rows
    .filter((r) => r.period === period && r.assets_rank != null)
    .sort((a, b) => (a.assets_rank ?? 0) - (b.assets_rank ?? 0))
    .map((r) => {
      const prev = priorRank.get(r.bank_ticker);
      return {
        bank_ticker: r.bank_ticker,
        assets: r.assets,
        assets_share: r.assets_share,
        loans_share: r.loans_share,
        deposits_share: r.deposits_share,
        rank: r.assets_rank,
        rank_change: prev != null && r.assets_rank != null ? prev - r.assets_rank : null,
      };
    });
}
