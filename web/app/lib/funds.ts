/**
 * Data layer for the /funds tab — TEFAS fund-market sector aggregates.
 * Reads the four `tefas_*` tables populated by scripts/update_tefas.py
 * (daily grain, aggregated at ingest from the per-fund TEFAS endpoints).
 *
 * The lane holds ~1,500 trading days; every time series here samples the
 * MONTH-END trading day per fund type (~72 points) and charts by 'YYYY-MM'
 * so the per-type samples align even when their last trading day differs.
 * AUM is stored in raw TL — rescaled to ₺ trillion / billion at query time.
 *
 * GYF/GSYF are excluded from all time series: those funds aren't daily-priced,
 * so a single date's SUM would only count the funds that happened to report.
 */
import { cachedAll } from "./db";
import type { TrendPoint } from "@/app/components/TrendChart";
import type { StackPoint } from "@/app/components/StackedArea";

/** Fund types that are daily-priced and safe to chart over time. */
export const TREND_TYPES = ["YAT", "EMK", "BYF"] as const;

export const TYPE_LABELS: Record<string, string> = {
  YAT: "Mutual funds",
  EMK: "Pension funds",
  BYF: "ETFs",
  GYF: "Real-estate funds",
  GSYF: "Venture-capital funds",
};

const TL_TO_TRN = 1 / 1e12;
const TL_TO_BN = 1 / 1e9;

interface MonthlyTypeRow {
  period: string; // 'YYYY-MM'
  fon_tipi: string;
  aum_try: number | null;
  investors: number | null;
  funds: number | null;
}

/** Month-end sector totals per fund type (SUM over managers). */
export async function monthlyByType(): Promise<MonthlyTypeRow[]> {
  return cachedAll<MonthlyTypeRow>(
    `WITH month_ends AS (
       SELECT fon_tipi, substr(date, 1, 7) AS ym, MAX(date) AS d
         FROM tefas_manager_daily
        WHERE fon_tipi IN ('YAT','EMK','BYF')
        GROUP BY fon_tipi, substr(date, 1, 7)
     )
     SELECT me.ym AS period, t.fon_tipi,
            SUM(t.aum_try) AS aum_try,
            SUM(t.investor_count) AS investors,
            SUM(t.fund_count) AS funds
       FROM tefas_manager_daily t
       JOIN month_ends me ON t.fon_tipi = me.fon_tipi AND t.date = me.d
      GROUP BY me.ym, t.fon_tipi
      ORDER BY period`,
  );
}

/** Total AUM by fund type as a stacked series (₺ trillion). */
export function aumStack(rows: MonthlyTypeRow[]): StackPoint[] {
  const byPeriod = new Map<string, StackPoint>();
  for (const r of rows) {
    if (!byPeriod.has(r.period)) byPeriod.set(r.period, { period: r.period });
    byPeriod.get(r.period)![r.fon_tipi] = (r.aum_try ?? 0) * TL_TO_TRN;
  }
  return [...byPeriod.values()].sort((a, b) =>
    String(a.period).localeCompare(String(b.period)));
}

/** Long-form per-type series for TrendChart (investors in millions, or fund counts). */
export function typeTrend(
  rows: MonthlyTypeRow[],
  field: "investors" | "funds",
  scale = 1,
): TrendPoint[] {
  return rows.map((r) => ({
    period: r.period,
    bank_type_code: r.fon_tipi,
    value: r[field] == null ? null : r[field]! * scale,
  }));
}

// ── Fund categories (from fund names; YAT only on the page) ─────────────────

/** Stack order: the money-market boom story leads. Small categories merge
 *  into "rest" so the stack stays readable. */
export const CATEGORY_SERIES = [
  { key: "money_market", label: "Money market" },
  { key: "debt", label: "Debt" },
  { key: "equity", label: "Equity" },
  { key: "hedge", label: "Hedge (serbest)" },
  { key: "precious_metals", label: "Precious metals" },
  { key: "rest", label: "Other" },
] as const;

const MAIN_CATEGORIES = new Set<string>(
  CATEGORY_SERIES.map((s) => s.key).filter((k) => k !== "rest"),
);

export async function categoryStack(fonTipi: string): Promise<StackPoint[]> {
  const rows = await cachedAll<{ period: string; category: string; aum_try: number | null }>(
    `WITH month_ends AS (
       SELECT substr(date, 1, 7) AS ym, MAX(date) AS d
         FROM tefas_category_daily
        WHERE fon_tipi = ?1
        GROUP BY substr(date, 1, 7)
     )
     SELECT me.ym AS period, t.category, SUM(t.aum_try) AS aum_try
       FROM tefas_category_daily t
       JOIN month_ends me ON t.date = me.d
      WHERE t.fon_tipi = ?1
      GROUP BY me.ym, t.category
      ORDER BY period`,
    [fonTipi],
  );
  const byPeriod = new Map<string, StackPoint>();
  for (const r of rows) {
    if (!byPeriod.has(r.period)) {
      const p: StackPoint = { period: r.period };
      for (const s of CATEGORY_SERIES) p[s.key] = 0;
      byPeriod.set(r.period, p);
    }
    const p = byPeriod.get(r.period)!;
    const key = MAIN_CATEGORIES.has(r.category) ? r.category : "rest";
    p[key] = (Number(p[key]) || 0) + (r.aum_try ?? 0) * TL_TO_TRN;
  }
  return [...byPeriod.values()].sort((a, b) =>
    String(a.period).localeCompare(String(b.period)));
}

// ── Portfolio allocation (AUM-weighted asset mix) ───────────────────────────

/** Display rollup of the ~11 stored asset classes into a readable stack. */
export const ALLOCATION_SERIES = [
  { key: "money_market", label: "Deposits, repo & money market" },
  { key: "gov_debt", label: "Government debt" },
  { key: "corp_debt", label: "Corporate debt" },
  { key: "equity", label: "Equity" },
  { key: "participation", label: "Participation (sukuk & accounts)" },
  { key: "precious_metals", label: "Precious metals" },
  { key: "fund_units", label: "Fund units" },
  { key: "other", label: "Other" },
] as const;

const ALLOCATION_DISPLAY: Record<string, string> = {
  equity_tr: "equity",
  equity_foreign: "equity",
  gov_debt_tr: "gov_debt",
  gov_debt_fx: "gov_debt",
  corp_debt: "corp_debt",
  foreign_debt: "corp_debt",
  participation: "participation",
  money_market: "money_market",
  precious_metals: "precious_metals",
  fund_units: "fund_units",
  other: "other",
};

export async function allocationStack(fonTipi: string): Promise<StackPoint[]> {
  const rows = await cachedAll<{ period: string; asset_class: string; pct: number | null }>(
    `WITH month_ends AS (
       SELECT substr(date, 1, 7) AS ym, MAX(date) AS d
         FROM tefas_allocation_daily
        WHERE fon_tipi = ?1
        GROUP BY substr(date, 1, 7)
     )
     SELECT me.ym AS period, t.asset_class, t.weighted_pct AS pct
       FROM tefas_allocation_daily t
       JOIN month_ends me ON t.date = me.d
      WHERE t.fon_tipi = ?1
      ORDER BY period`,
    [fonTipi],
  );
  const byPeriod = new Map<string, StackPoint>();
  for (const r of rows) {
    if (!byPeriod.has(r.period)) {
      const p: StackPoint = { period: r.period };
      for (const s of ALLOCATION_SERIES) p[s.key] = 0;
      byPeriod.set(r.period, p);
    }
    const p = byPeriod.get(r.period)!;
    const key = ALLOCATION_DISPLAY[r.asset_class] ?? "other";
    // Repo borrowing can make money_market slightly negative; clamp at 0 so
    // the percent stack doesn't fold — the distortion is < 1pp of the mix.
    p[key] = Math.max(0, (Number(p[key]) || 0) + (r.pct ?? 0));
  }
  return [...byPeriod.values()].sort((a, b) =>
    String(a.period).localeCompare(String(b.period)));
}

// ── Real (CPI-deflated) AUM index ───────────────────────────────────────────

/** Total fund AUM (YAT+EMK+BYF) nominal vs CPI-deflated, indexed to 100 at
 *  the first common month. CPI: TP.TUKFIY2025.GENEL (already in evds_series). */
export async function realAumIndex(rows: MonthlyTypeRow[]): Promise<TrendPoint[]> {
  const cpi = await cachedAll<{ period_date: string; value: number }>(
    `SELECT period_date, value FROM evds_series
      WHERE code = 'TP.TUKFIY2025.GENEL' AND value IS NOT NULL
      ORDER BY period_date`,
  );
  const cpiByMonth = new Map(cpi.map((r) => [r.period_date.slice(0, 7), r.value]));
  const totals = new Map<string, number>();
  for (const r of rows) {
    totals.set(r.period, (totals.get(r.period) ?? 0) + (r.aum_try ?? 0));
  }
  const months = [...totals.keys()].sort().filter((m) => cpiByMonth.has(m));
  if (months.length === 0) return [];
  const baseAum = totals.get(months[0])!;
  const baseCpi = cpiByMonth.get(months[0])!;
  const out: TrendPoint[] = [];
  for (const m of months) {
    const nominal = (totals.get(m)! / baseAum) * 100;
    out.push({ period: m, bank_type_code: "nominal", value: nominal });
    out.push({
      period: m,
      bank_type_code: "real",
      value: nominal / (cpiByMonth.get(m)! / baseCpi),
    });
  }
  return out;
}

export const AUM_INDEX_LABELS: Record<string, string> = {
  nominal: "Nominal",
  real: "Real (CPI-deflated)",
};

// ── Largest funds (latest snapshot) ─────────────────────────────────────────

export interface TopFundRow {
  fon_tipi: string;
  date: string;
  rank: number;
  fon_kodu: string;
  fon_unvan: string | null;
  manager: string | null;
  aum_bn: number | null;
  investor_count: number | null;
}

/** Latest top-15 per fund type, AUM in ₺ billion. */
export async function topFunds(): Promise<TopFundRow[]> {
  return cachedAll<TopFundRow>(
    `WITH latest AS (
       SELECT fon_tipi, MAX(date) AS d FROM tefas_top_funds GROUP BY fon_tipi
     )
     SELECT t.fon_tipi, t.date, t.rank, t.fon_kodu, t.fon_unvan, t.manager,
            t.aum_try * ${TL_TO_BN} AS aum_bn, t.investor_count
       FROM tefas_top_funds t
       JOIN latest l ON t.fon_tipi = l.fon_tipi AND t.date = l.d
      ORDER BY t.fon_tipi, t.rank`,
  );
}
