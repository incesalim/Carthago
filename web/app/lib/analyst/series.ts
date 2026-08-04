/**
 * Shared per-bank series fetchers for the analyst layer. One bundle feeds
 * sections, comparator and (fleet-wide variants) peers, so a memo run reads
 * each table once.
 *
 * Corpus rules inherited from bot-schema.ts / the feasibility test — each one
 * bought with a documented production wrong-answer:
 * - BS total = MAX(amount_total) across BOTH legs, total row `hierarchy = ''`.
 * - Net profit via the pl_roles join, never a label match; P&L is
 *   YTD-cumulative within the year.
 * - Equity closing = the LAST `hierarchy = ''` row of the current block.
 * - stages coverage is a FRACTION; capital ratios are PERCENT.
 * - fx: filter currency='TOTAL', never SUM across currencies.
 */
import { ordOf } from "../period-math";
import type { Queryable } from "./data";

export interface SeriesBundle {
  /** period → MAX(amount_total) across both BS legs. */
  bsTotal: Map<string, number>;
  /** period → amount_fc of each leg's total row. */
  bsFc: Map<string, { assets: number | null; liabilities: number | null }>;
  /** role → (ord → YTD amount). */
  plByRole: Map<string, Map<number, number>>;
  /** All P&L lines for the bank/kind (movers + label searches). */
  plLines: { period: string; hierarchy: string; item_name: string | null; amount: number | null }[];
  /** period → closing total_equity (current block). */
  equityClosing: Map<string, number>;
  /** period → stages row (amounts + coverage fractions). */
  stages: Map<string, StagesRow>;
  /** period → capital row (ratios percent, amounts ₺000). */
  capital: Map<string, CapitalRow>;
  /** period → liquidity row. */
  liquidity: Map<string, LiquidityRow>;
  /** period → free-provision stocks (current + prior-year-end comparative). */
  freeProvision: Map<string, { stock: number | null; prior: number | null }>;
  /** period → first liabilities line (the deposits/funds-collected row). */
  deposits: Map<string, { label: string | null; total: number | null; tl: number | null; fc: number | null }>;
}

export interface StagesRow {
  stage1_amount: number | null;
  stage2_amount: number | null;
  stage3_amount: number | null;
  total_amount: number | null;
  stage3_coverage: number | null;
  stage2_coverage: number | null;
}

export interface CapitalRow {
  cet1_ratio: number | null;
  tier1_ratio: number | null;
  capital_adequacy_ratio: number | null;
  cet1_capital: number | null;
  tier2_capital: number | null;
  total_capital: number | null;
  total_rwa: number | null;
}

export interface LiquidityRow {
  leverage_ratio: number | null;
  lcr_total: number | null;
  lcr_fc: number | null;
  nsfr: number | null;
}

export async function fetchSeriesBundle(
  db: Queryable,
  bank: string,
  kind: string,
): Promise<SeriesBundle> {
  const [bsRows, plRoleRows, plLines, eqRows, stagesRows, capRows, liqRows, fpRows, depRows] =
    await Promise.all([
      db.all<{ period: string; statement: string; amount_total: number | null; amount_fc: number | null }>(
        "SELECT period, statement, amount_total, amount_fc FROM bank_audit_balance_sheet " +
          "WHERE bank_ticker = ? AND kind = ? AND hierarchy = '' " +
          "AND statement IN ('assets','liabilities')",
        [bank, kind],
      ),
      db.all<{ period: string; role: string; amount: number | null }>(
        "SELECT p.period, r.role, p.amount FROM bank_audit_profit_loss p " +
          "JOIN bank_audit_pl_roles r ON r.bank_ticker = p.bank_ticker AND r.period = p.period " +
          "AND r.kind = p.kind AND r.hierarchy = p.hierarchy " +
          "WHERE p.bank_ticker = ? AND p.kind = ?",
        [bank, kind],
      ),
      db.all<{ period: string; hierarchy: string; item_name: string | null; amount: number | null }>(
        "SELECT period, hierarchy, item_name, amount FROM bank_audit_profit_loss " +
          "WHERE bank_ticker = ? AND kind = ? ORDER BY period, item_order",
        [bank, kind],
      ),
      db.all<{ period: string; total_equity: number | null }>(
        "SELECT period, total_equity FROM (" +
          "SELECT period, total_equity, ROW_NUMBER() OVER (PARTITION BY period ORDER BY item_order DESC) rn " +
          "FROM bank_audit_equity_change WHERE bank_ticker = ? AND kind = ? " +
          "AND period_type = 'current' AND hierarchy = '' AND total_equity IS NOT NULL" +
          ") WHERE rn = 1",
        [bank, kind],
      ),
      db.all<{ period: string } & StagesRow>(
        "SELECT period, stage1_amount, stage2_amount, stage3_amount, total_amount, " +
          "stage2_coverage, stage3_coverage FROM bank_audit_stages " +
          "WHERE bank_ticker = ? AND kind = ? AND period_type = 'current'",
        [bank, kind],
      ),
      db.all<{ period: string } & CapitalRow>(
        "SELECT period, cet1_ratio, tier1_ratio, capital_adequacy_ratio, cet1_capital, " +
          "tier2_capital, total_capital, total_rwa FROM bank_audit_capital " +
          "WHERE bank_ticker = ? AND kind = ? AND period_type = 'current'",
        [bank, kind],
      ),
      db.all<{ period: string } & LiquidityRow>(
        "SELECT period, leverage_ratio, lcr_total, lcr_fc, nsfr FROM bank_audit_liquidity " +
          "WHERE bank_ticker = ? AND kind = ? AND period_type = 'current'",
        [bank, kind],
      ),
      db.all<{ period: string; free_provision: number | null; free_provision_prior: number | null }>(
        "SELECT period, free_provision, free_provision_prior FROM bank_audit_free_provision " +
          "WHERE bank_ticker = ? AND kind = ?",
        [bank, kind],
      ),
      db.all<{ period: string; item_name: string | null; amount_total: number | null; amount_tl: number | null; amount_fc: number | null }>(
        "SELECT period, item_name, amount_total, amount_tl, amount_fc FROM (" +
          "SELECT period, item_name, amount_total, amount_tl, amount_fc, " +
          "ROW_NUMBER() OVER (PARTITION BY period ORDER BY item_order) rn " +
          "FROM bank_audit_balance_sheet WHERE bank_ticker = ? AND kind = ? " +
          "AND statement = 'liabilities' AND hierarchy != ''" +
          ") WHERE rn = 1",
        [bank, kind],
      ),
    ]);

  const bsTotal = new Map<string, number>();
  const bsFc = new Map<string, { assets: number | null; liabilities: number | null }>();
  for (const r of bsRows) {
    if (r.amount_total != null) {
      const cur = bsTotal.get(r.period);
      if (cur == null || r.amount_total > cur) bsTotal.set(r.period, r.amount_total);
    }
    const fc = bsFc.get(r.period) ?? { assets: null, liabilities: null };
    if (r.statement === "assets") fc.assets = r.amount_fc;
    else fc.liabilities = r.amount_fc;
    bsFc.set(r.period, fc);
  }

  const plByRole = new Map<string, Map<number, number>>();
  for (const r of plRoleRows) {
    const ord = ordOf(r.period);
    if (ord == null || r.amount == null) continue;
    let m = plByRole.get(r.role);
    if (!m) plByRole.set(r.role, (m = new Map()));
    m.set(ord, r.amount);
  }

  const toMap = <T extends { period: string }>(rows: T[]): Map<string, T> => {
    const m = new Map<string, T>();
    for (const r of rows) m.set(r.period, r);
    return m;
  };

  const freeProvision = new Map<string, { stock: number | null; prior: number | null }>();
  for (const r of fpRows) {
    freeProvision.set(r.period, { stock: r.free_provision, prior: r.free_provision_prior });
  }

  const deposits = new Map<string, { label: string | null; total: number | null; tl: number | null; fc: number | null }>();
  for (const r of depRows) {
    deposits.set(r.period, { label: r.item_name, total: r.amount_total, tl: r.amount_tl, fc: r.amount_fc });
  }

  const equityClosing = new Map<string, number>();
  for (const r of eqRows) if (r.total_equity != null) equityClosing.set(r.period, r.total_equity);

  return {
    bsTotal,
    bsFc,
    plByRole,
    plLines,
    equityClosing,
    stages: toMap(stagesRows),
    capital: toMap(capRows),
    liquidity: toMap(liqRows),
    freeProvision,
    deposits,
  };
}

/** Fold Turkish dotted/dotless i so ASCII patterns match both languages. */
export function foldTr(s: string): string {
  return s.replace(/İ/g, "I").replace(/ı/g, "i").replace(/Â/g, "A").replace(/â/g, "a").toUpperCase();
}

/**
 * Find a P&L line by folded-label pattern for one period — the LAST resort
 * idiom (bot-schema: prefer structure; labels vary, fuse and blank). Returns
 * the FIRST match in statement order.
 */
export function findPlLine(
  lines: SeriesBundle["plLines"],
  period: string,
  pattern: RegExp,
): { item_name: string | null; amount: number | null } | null {
  for (const l of lines) {
    if (l.period !== period) continue;
    if (l.item_name && pattern.test(foldTr(l.item_name))) return l;
  }
  return null;
}

/** Averages the up-to-`n` most recent non-null points at or before `period`
 *  (5-point average convention from heatmap's ttmRoe: ≥2 points required). */
export function trailingAverage(
  byPeriod: Map<string, number>,
  period: string,
  n = 5,
  minPoints = 2,
): number | null {
  const ord = ordOf(period);
  if (ord == null) return null;
  const vals: number[] = [];
  for (let k = 0; k < n; k++) {
    const p = `${Math.floor((ord - k) / 4)}Q${((ord - k) % 4) + 1}`;
    const v = byPeriod.get(p);
    if (v != null) vals.push(v);
  }
  if (vals.length < minPoints) return null;
  return vals.reduce((a, b) => a + b, 0) / vals.length;
}
