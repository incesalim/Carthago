/**
 * Task 2.2 — licence-class peer context: medians for the ratios the memo
 * compares against, computed from the same corpus rules as sections.ts.
 *
 * Medians, not means (robust to one outlier bank); licence class, not the
 * whole field (comparing a deposit bank to Eximbank is not a peer comparison
 * — bank-brief.ts learned this the hard way); TAKAS excluded from every
 * aggregate (a clearing house, not a lender). A median needs ≥ MIN_PEERS
 * reporters or it is N/A — a "median" of two banks is noise.
 */
import { PEER_EXCLUDED_TICKERS } from "../bank_names";
import { ordOf, ttmEndingAt } from "../period-math";
import type { Queryable } from "./data";
import { licenceClassOf } from "./sections";

export const MIN_PEERS = 3;

export interface PeerRow {
  bank_ticker: string;
  total_assets: number | null;
  car: number | null;
  cet1: number | null;
  npl_ratio_pct: number | null;
  stage2_ratio_pct: number | null;
  stage3_coverage_pct: number | null;
  roe_ttm_pct: number | null;
}

export interface PeerContext {
  licence_class: string;
  peer_count: number;
  medians: {
    car: number | null;
    cet1: number | null;
    car_minus_cet1_pp: number | null;
    npl_ratio_pct: number | null;
    stage2_ratio_pct: number | null;
    stage3_coverage_pct: number | null;
    ldr_pct: number | null;
    roe_ttm_pct: number | null;
  };
  /** The largest class peers BY NAME with their filed figures — a deep-dive
   *  peer table is named banks, not an anonymous median. Includes the subject
   *  bank; sorted by assets, TAKAS excluded like every aggregate. */
  rows: PeerRow[];
}

function median(xs: number[]): number | null {
  if (xs.length < MIN_PEERS) return null;
  const s = [...xs].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return Number((s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2).toFixed(2));
}

export async function buildPeerContext(
  db: Queryable,
  bank: string,
  period: string,
  kind: string,
): Promise<PeerContext> {
  const cls = licenceClassOf(bank);
  const ord = ordOf(period);
  if (ord == null) throw new Error(`bad period ${period}`);

  const inClass = (t: string) => !PEER_EXCLUDED_TICKERS.has(t) && licenceClassOf(t) === cls;

  const [capRows, stagesRows, depRows, plRows, eqRows, assetRows] = await Promise.all([
    db.all<{ bank_ticker: string; cet1_ratio: number | null; capital_adequacy_ratio: number | null }>(
      "SELECT bank_ticker, cet1_ratio, capital_adequacy_ratio FROM bank_audit_capital " +
        "WHERE period = ? AND kind = ? AND period_type = 'current'",
      [period, kind],
    ),
    db.all<{ bank_ticker: string; stage2_amount: number | null; stage3_amount: number | null; total_amount: number | null; stage3_coverage: number | null }>(
      "SELECT bank_ticker, stage2_amount, stage3_amount, total_amount, stage3_coverage " +
        "FROM bank_audit_stages WHERE period = ? AND kind = ? AND period_type = 'current'",
      [period, kind],
    ),
    db.all<{ bank_ticker: string; total: number | null }>(
      "SELECT bank_ticker, amount_total AS total FROM (" +
        "SELECT bank_ticker, amount_total, ROW_NUMBER() OVER " +
        "(PARTITION BY bank_ticker ORDER BY item_order) rn " +
        "FROM bank_audit_balance_sheet WHERE period = ? AND kind = ? " +
        "AND statement = 'liabilities' AND hierarchy != ''" +
        ") WHERE rn = 1",
      [period, kind],
    ),
    // Eight quarters of fleet YTD net profit — enough for a TTM at `period`.
    db.all<{ bank_ticker: string; period: string; amount: number | null }>(
      "SELECT p.bank_ticker, p.period, p.amount FROM bank_audit_profit_loss p " +
        "JOIN bank_audit_pl_roles r ON r.bank_ticker = p.bank_ticker AND r.period = p.period " +
        "AND r.kind = p.kind AND r.hierarchy = p.hierarchy " +
        "WHERE r.role = 'period_net' AND p.kind = ? AND p.period <= ?",
      [kind, period],
    ),
    db.all<{ bank_ticker: string; period: string; total_equity: number | null }>(
      "SELECT bank_ticker, period, total_equity FROM (" +
        "SELECT bank_ticker, period, total_equity, ROW_NUMBER() OVER " +
        "(PARTITION BY bank_ticker, period ORDER BY item_order DESC) rn " +
        "FROM bank_audit_equity_change WHERE kind = ? AND period_type = 'current' " +
        "AND hierarchy = '' AND total_equity IS NOT NULL AND period <= ?" +
        ") WHERE rn = 1",
      [kind, period],
    ),
    db.all<{ bank_ticker: string; total: number | null }>(
      "SELECT bank_ticker, MAX(amount_total) AS total FROM bank_audit_balance_sheet " +
        "WHERE period = ? AND kind = ? AND hierarchy = '' " +
        "AND statement IN ('assets','liabilities') GROUP BY bank_ticker",
      [period, kind],
    ),
  ]);

  const cars: number[] = [];
  const cet1s: number[] = [];
  const gaps: number[] = [];
  for (const r of capRows) {
    if (!inClass(r.bank_ticker)) continue;
    if (r.capital_adequacy_ratio != null) cars.push(r.capital_adequacy_ratio);
    if (r.cet1_ratio != null) cet1s.push(r.cet1_ratio);
    if (r.capital_adequacy_ratio != null && r.cet1_ratio != null) {
      gaps.push(r.capital_adequacy_ratio - r.cet1_ratio);
    }
  }

  const npls: number[] = [];
  const stage2s: number[] = [];
  const covs: number[] = [];
  const loansByBank = new Map<string, number>();
  for (const r of stagesRows) {
    if (!inClass(r.bank_ticker)) continue;
    if (r.total_amount != null && r.total_amount > 0) {
      loansByBank.set(r.bank_ticker, r.total_amount);
      if (r.stage3_amount != null) npls.push((r.stage3_amount / r.total_amount) * 100);
      if (r.stage2_amount != null) stage2s.push((r.stage2_amount / r.total_amount) * 100);
    }
    if (r.stage3_coverage != null) covs.push(r.stage3_coverage * 100);
  }

  const ldrs: number[] = [];
  for (const r of depRows) {
    if (!inClass(r.bank_ticker) || r.total == null || r.total <= 0) continue;
    const loans = loansByBank.get(r.bank_ticker);
    if (loans != null) ldrs.push((loans / r.total) * 100);
  }

  const ytdByBank = new Map<string, Map<number, number>>();
  for (const r of plRows) {
    const o = ordOf(r.period);
    if (o == null || r.amount == null || !inClass(r.bank_ticker)) continue;
    let m = ytdByBank.get(r.bank_ticker);
    if (!m) ytdByBank.set(r.bank_ticker, (m = new Map()));
    m.set(o, r.amount);
  }
  const eqByBank = new Map<string, Map<string, number>>();
  for (const r of eqRows) {
    if (!inClass(r.bank_ticker) || r.total_equity == null) continue;
    let m = eqByBank.get(r.bank_ticker);
    if (!m) eqByBank.set(r.bank_ticker, (m = new Map()));
    m.set(r.period, r.total_equity);
  }
  const roes: number[] = [];
  for (const [t, ytd] of ytdByBank) {
    const ttm = ttmEndingAt(ytd, ord);
    if (ttm == null) continue;
    const eq = eqByBank.get(t);
    if (!eq) continue;
    const pts: number[] = [];
    for (let k = 0; k < 5; k++) {
      const p = `${Math.floor((ord - k) / 4)}Q${((ord - k) % 4) + 1}`;
      const v = eq.get(p);
      if (v != null) pts.push(v);
    }
    if (pts.length < 2) continue;
    const avg = pts.reduce((a, b) => a + b, 0) / pts.length;
    if (avg > 0) roes.push((ttm / avg) * 100);
  }

  // Per-bank peer table: the class ranked by assets, each with its own filed
  // figures (per-bank ROE reuses the TTM machinery above).
  const roeByBank = new Map<string, number>();
  for (const [t, ytd] of ytdByBank) {
    const ttm = ttmEndingAt(ytd, ord);
    const eq = eqByBank.get(t);
    if (ttm == null || !eq) continue;
    const pts: number[] = [];
    for (let k = 0; k < 5; k++) {
      const p = `${Math.floor((ord - k) / 4)}Q${((ord - k) % 4) + 1}`;
      const v = eq.get(p);
      if (v != null) pts.push(v);
    }
    if (pts.length < 2) continue;
    const avg = pts.reduce((a, b) => a + b, 0) / pts.length;
    if (avg > 0) roeByBank.set(t, Number(((ttm / avg) * 100).toFixed(2)));
  }
  const capByBank = new Map(capRows.map((r) => [r.bank_ticker, r]));
  const stagesByBank = new Map(stagesRows.map((r) => [r.bank_ticker, r]));
  const rows: PeerRow[] = assetRows
    .filter((r) => inClass(r.bank_ticker) && r.total != null)
    .sort((a, b) => (b.total ?? 0) - (a.total ?? 0))
    .slice(0, 10)
    .map((r) => {
      const c = capByBank.get(r.bank_ticker);
      const st = stagesByBank.get(r.bank_ticker);
      return {
        bank_ticker: r.bank_ticker,
        total_assets: r.total,
        car: c?.capital_adequacy_ratio ?? null,
        cet1: c?.cet1_ratio ?? null,
        npl_ratio_pct:
          st?.stage3_amount != null && st.total_amount
            ? Number(((st.stage3_amount / st.total_amount) * 100).toFixed(2))
            : null,
        stage2_ratio_pct:
          st?.stage2_amount != null && st.total_amount
            ? Number(((st.stage2_amount / st.total_amount) * 100).toFixed(2))
            : null,
        stage3_coverage_pct:
          st?.stage3_coverage != null ? Number((st.stage3_coverage * 100).toFixed(1)) : null,
        roe_ttm_pct: roeByBank.get(r.bank_ticker) ?? null,
      };
    });

  return {
    licence_class: cls,
    peer_count: new Set(
      capRows.map((r) => r.bank_ticker).filter(inClass),
    ).size,
    rows,
    medians: {
      car: median(cars),
      cet1: median(cet1s),
      car_minus_cet1_pp: median(gaps),
      npl_ratio_pct: median(npls),
      stage2_ratio_pct: median(stage2s),
      stage3_coverage_pct: median(covs),
      ldr_pct: median(ldrs),
      roe_ttm_pct: median(roes),
    },
  };
}
