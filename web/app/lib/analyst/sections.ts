/**
 * Task 2.1 — the 11-section deterministic assembly. For one (bank, period,
 * kind) this builds everything a bank analyst looks at, from stored rows only:
 * no LLM anywhere in this module, and every value traceable to a query.
 *
 * Two blocks here exist specifically to force the "second question" the
 * feasibility test identified as the analyst gap:
 * - `asset_quality.coverage_decomposition` — the mix-vs-erosion split of a
 *   coverage fall (the ŞEKERBANK memo's core table), precomputed so the model
 *   contextualizes a derivation instead of attempting arithmetic.
 * - `capital.trajectory` — CET1/CAR/gap/leverage per quarter, so a Tier-2
 *   issuance plugging a core-capital hole is visible as a table, not an
 *   inference.
 *
 * Sections that the stored data CANNOT fill (securities breakdown, per-bank
 * digital stats, deposit concentration…) say so in `_gaps` — the agent's
 * awareness of its own blind spots. Null means "not held", never zero.
 */
import {
  BANK_NAMES,
  BANK_TYPE_BY_TICKER,
  PEER_EXCLUDED_TICKERS,
} from "../bank_names";
import { ordOf, periodFromOrd, singleQuarter, ttmEndingAt, yoyPct } from "../period-math";
import { realRate } from "../real-terms";
import type { Queryable } from "./data";
import { firstRow } from "./data";
import {
  fetchSeriesBundle,
  findPlLine,
  foldTr,
  trailingAverage,
  type SeriesBundle,
} from "./series";

/* ------------------------------------------------------------------ types */

export interface SectionBase {
  _gaps: string[];
}

export interface AnalystSections {
  business: SectionBase & {
    bank_name: string;
    licence_class: "deposit" | "participation" | "devinv" | "unknown";
    ownership: {
      shareholders: { name: string; share_pct: number | null }[];
      subsidiaries: { name: string; activity: string | null; share_pct: number | null }[];
      free_float_pct: number | null;
    };
    profile: { branches: number | null; personnel: number | null; as_of: string | null };
    market_share: {
      assets_pct: number | null;
      loans_pct: number | null;
      deposits_pct: number | null;
      peer_rank_by_assets: number | null;
      peer_count: number;
    };
  };
  macro: SectionBase & {
    funding_rate_pct: number | null;
    cpi_yoy_pct: number | null;
    usd_try: number | null;
    regulation_categories: string[];
    /** BDDK's own sector aggregates (family B, monthly, million TL / percent)
     *  at the latest month ≤ quarter end — "is it the bank or the sector". */
    sector: {
      as_of: string | null;
      total_assets_million_tl: number | null;
      bank_share_of_sector_assets_pct: number | null;
      roe_pct: number | null;
      npl_ratio_pct: number | null;
      car_pct: number | null;
      nim_pct: number | null;
    };
  };
  earnings: SectionBase & {
    total_assets: number | null;
    assets_yoy_pct: number | null;
    assets_yoy_real_pct: number | null;
    net_income_ytd: number | null;
    net_income_quarterly: number | null;
    net_income_ttm: number | null;
    net_income_yoy_pct: number | null;
    roe_ttm_pct: number | null;
    roe_real_pct: number | null;
    roa_ttm_pct: number | null;
    free_provision: {
      stock: number | null;
      prior_year_end_stock: number | null;
      release_ytd: number | null;
      release_pct_of_ytd_income: number | null;
      ttm_release: number | null;
      roe_ex_release_pct: number | null;
      /** Stock + YTD release per quarter, oldest→newest — the ALBRK ₺7.0bn
       *  release lives in this history, not in the latest quarter. The
       *  ex-release figures are precomputed so re-basing a distorted YoY
       *  comparison is a quote, not an inference the model must attempt. */
      history: {
        period: string;
        stock: number | null;
        release_ytd: number | null;
        net_income_ytd: number | null;
        release_pct_of_income: number | null;
        income_ex_release: number | null;
      }[];
    };
    core_margin: {
      label: string | null;
      ytd: number | null;
      quarterly_series: { period: string; amount: number | null }[];
      yoy_ytd_pct: number | null;
    };
    operating_income_ttm: number | null;
    net_fees_ytd: number | null;
    opex: { personnel_ytd: number | null; other_ytd: number | null; cost_income_ttm_pct: number | null };
    /** Per-stage GROSS ECL provision expense, YTD as filed — the sum
     *  reproduces the "gross expected credit losses" figure banks present
     *  (verified: GARAN 2026Q1 sums to the disclosed ₺30.5bn). Reversals are
     *  NOT separable — the net charge stays a stated gap. */
    ecl: {
      stage1_ytd: number | null;
      stage2_ytd: number | null;
      stage3_ytd: number | null;
      total_ytd: number | null;
      ttm_total: number | null;
      cost_of_risk_ttm_pct: number | null;
    };
    net_income_quarterly_series: { period: string; amount: number | null }[];
    pl_movers: { item_name: string; ytd: number; prior_year_ytd: number; yoy_pct: number }[];
  };
  asset_quality: SectionBase & {
    gross_loans: number | null;
    npl_ratio_pct: number | null;
    stage2_ratio_pct: number | null;
    stage3_coverage_pct: number | null;
    stage2_coverage_pct: number | null;
    npl_by_bucket: {
      group: string;
      gross: number | null;
      share_pct: number | null;
      coverage_pct: number | null;
    }[];
    coverage_decomposition: {
      window_start: string;
      coverage_then_pct: number;
      coverage_now_pct: number;
      total_fall_pp: number;
      counterfactual_now_balances_then_rates_pct: number;
      mix_pp: number;
      erosion_pp: number;
    } | null;
    npl_movement: {
      group: string;
      opening: number | null;
      additions_ytd: number | null;
      transfers_in_ytd: number | null;
      transfers_out_ytd: number | null;
      collections_ytd: number | null;
      write_offs_ytd: number | null;
      sold_ytd: number | null;
      closing: number | null;
    }[];
    additions_quarterly: { period: string; group: string; amount: number | null }[];
    zero_write_offs_all_periods: boolean | null;
    npl_by_sector: { sector: string; stage3: number | null; as_of: string }[];
    history: { period: string; npl_pct: number | null; stage2_pct: number | null; coverage_pct: number | null }[];
  };
  currency: SectionBase & {
    net_fx_position: number | null;
    net_on_balance: number | null;
    net_off_balance: number | null;
    by_currency: { ccy: string; net_position: number | null }[];
    fx_assets: number | null;
    fx_liabilities: number | null;
    usd_try: number | null;
  };
  funding: SectionBase & {
    deposits_label: string | null;
    deposits_total: number | null;
    deposits_tl: number | null;
    deposits_fc: number | null;
    ldr_pct: number | null;
    lcr_total_pct: number | null;
    lcr_fc_pct: number | null;
    nsfr_pct: number | null;
    leverage_pct: number | null;
  };
  capital: SectionBase & {
    cet1_pct: number | null;
    tier1_pct: number | null;
    car_pct: number | null;
    car_minus_cet1_pp: number | null;
    noncore_share_of_car: number | null;
    cet1_capital: number | null;
    tier2_capital: number | null;
    total_capital: number | null;
    rwa: number | null;
    total_equity: number | null;
    equity_to_assets_pct: number | null;
    trajectory: { period: string; cet1: number | null; car: number | null; gap_pp: number | null; leverage: number | null }[];
    /** WHY the ratio moved — the hand memos' "RWA +60% against capital +26%"
     *  derivation, precomputed so causality is a quote, not an inference. */
    ratio_drivers: {
      cet1_capital_qoq_pct: number | null;
      rwa_qoq_pct: number | null;
      cet1_capital_yoy_pct: number | null;
      rwa_yoy_pct: number | null;
    };
  };
  securities: SectionBase & { total: null; breakdown_available: false };
  management: SectionBase & {
    call_date: string | null;
    call_period: string | null;
    title: string | null;
    /** VERBATIM executive turns from the earnings-call transcript, selected
     *  by topic keyword — management's claims, never verified figures. */
    excerpts: { topic: string; quote: string }[];
  };
  comparability: SectionBase & {
    reporting_unit: string | null;
    unit_source: string;
    assurance_level: string;
    assurance_source: string;
    consolidation_basis: string;
    opinion_type: string | null;
    opinion_category: string | null;
    auditor: string | null;
    basis_text_lead: string | null;
    qualified_streak: number;
    signals_this_period: { signal_id: string; signal_type: string; severity: string; payload: string }[];
  };
  governance: SectionBase & {
    controlling_shareholder: string | null;
    controlling_share_pct: number | null;
    free_float_pct: number | null;
    qualified_streak: number;
    is_free_provision_qualified: boolean | null;
  };
  valuation: SectionBase & {
    roe_ttm_pct: number | null;
    roe_real_pct: number | null;
    roe_ex_free_provision_pct: number | null;
    price_to_book: null;
  };
  meta: {
    bank_ticker: string;
    bank_name: string;
    period: string;
    kind: string;
    generated_at: string;
    extracted_at: string | null;
    validation_failing_statements: string[];
  };
}

/* ------------------------------------------------------------ helpers */

/** Licence class — mirrors bank-brief.ts's internal peerClassOf: ownership
 *  codes 10005/6/7 are all deposit banks; 10003 participation; 10004 dev&inv. */
export function licenceClassOf(ticker: string): "deposit" | "participation" | "devinv" | "unknown" {
  switch (BANK_TYPE_BY_TICKER[ticker]) {
    case "10005":
    case "10006":
    case "10007":
      return "deposit";
    case "10003":
      return "participation";
    case "10004":
      return "devinv";
    default:
      return "unknown";
  }
}

const QUARTER_END_MONTH: Record<string, string> = { "1": "03", "2": "06", "3": "09", "4": "12" };

/** 'YYYYQN' → 'YYYY-MM-99' upper bound for evds period_date comparisons. */
function quarterEndBound(period: string): string {
  const y = period.slice(0, 4);
  const m = QUARTER_END_MONTH[period.slice(5)];
  return `${y}-${m}-99`;
}

function pct(x: number | null | undefined, digits = 2): number | null {
  return x == null ? null : Number(x.toFixed(digits));
}

const CORE_MARGIN_RE = /NET\s*(FAIZ|KAR\s*PAYI|INTEREST|PROFIT\s*SHARE)/;
const NET_FEES_RE = /NET\s*(UCRET|ÜCRET|FEE)/;
// Mirror of src/analyst/classify_basis.py's free-provision family — used only
// as a display fallback when analyst_basis_metadata has not been pushed.
const FP_BASIS_RE = /free\s+provision|general\s+(reserve|provision)|serbest\s+kar|genel\s+kar/i;

/** Display fallback for the qualification category until the pushed
 *  `analyst_basis_metadata.opinion_category` (the Python classifier's verdict)
 *  is available in D1. Free-provision only — the tail stays null. */
export function classifyBasisLead(lead: string | null): "free_provision" | null {
  return lead && FP_BASIS_RE.test(lead) ? "free_provision" : null;
}

async function tableOrEmpty<T>(db: Queryable, sql: string, binds: unknown[]): Promise<T[]> {
  try {
    return await db.all<T>(sql, binds);
  } catch {
    return []; // table not migrated yet (analyst_* before the freeze lifts) — a gap, not an error
  }
}

export interface CoverageBucket {
  group: string;
  gross: number | null;
  provision: number | null;
  share: number | null;
  coverage: number | null;
}

/**
 * The mix-vs-erosion split of a coverage fall — memo B's core derivation.
 * Counterfactual = today's balances at the window-start's within-bucket rates;
 * what that counterfactual explains is MIX (new NPL landing in lightly
 * provisioned buckets), the remainder is genuine within-bucket EROSION.
 * Returns null unless coverage actually fell and every needed cell is present.
 */
export function decomposeCoverage(
  windowStart: string,
  bucketsThen: CoverageBucket[] | null,
  bucketsNow: CoverageBucket[] | null,
): AnalystSections["asset_quality"]["coverage_decomposition"] {
  if (!bucketsNow || !bucketsThen) return null;
  const tot = (rows: CoverageBucket[], f: "gross" | "provision") =>
    rows.reduce((a, r) => a + (r[f] ?? 0), 0);
  const grossNow = tot(bucketsNow, "gross");
  const grossThen = tot(bucketsThen, "gross");
  if (grossNow <= 0 || grossThen <= 0) return null;
  const coverageNow = tot(bucketsNow, "provision") / grossNow;
  const coverageThen = tot(bucketsThen, "provision") / grossThen;
  if (coverageThen <= coverageNow) return null;
  let cfProv = 0;
  for (let i = 0; i < bucketsNow.length; i++) {
    const g = bucketsNow[i].gross;
    const rate = bucketsThen[i]?.coverage;
    if (g == null || rate == null) return null;
    cfProv += g * rate;
  }
  const cf = cfProv / grossNow;
  return {
    window_start: windowStart,
    coverage_then_pct: pct(coverageThen * 100) as number,
    coverage_now_pct: pct(coverageNow * 100) as number,
    total_fall_pp: pct((coverageThen - coverageNow) * 100) as number,
    counterfactual_now_balances_then_rates_pct: pct(cf * 100) as number,
    mix_pp: pct((coverageThen - cf) * 100) as number,
    erosion_pp: pct((cf - coverageNow) * 100) as number,
  };
}

/* ------------------------------------------------------------ assembly */

export async function buildAnalystSections(
  db: Queryable,
  bank: string,
  period: string,
  kind: string,
  bundle?: SeriesBundle,
): Promise<AnalystSections> {
  const s = bundle ?? (await fetchSeriesBundle(db, bank, kind));
  const ord = ordOf(period);
  if (ord == null) throw new Error(`bad period ${period} — expected YYYYQN`);
  const prevYearSame = periodFromOrd(ord - 4);

  const [
    kapRows,
    profileRow,
    fleetAssets,
    fleetLoans,
    fleetDeposits,
    evdsRows,
    briefingRow,
    fxRows,
    nplRows,
    sectorRows,
    opinionRows,
    basisRow,
    signalRows,
    metaRow,
    failingRows,
  ] = await Promise.all([
    db.all<{ item: string; holder: string | null; ratio_pct: number | null; activity: string | null }>(
      "SELECT item, holder, ratio_pct, activity FROM kap_ownership WHERE bank_ticker = ?",
      [bank],
    ),
    firstRow<{ branches_total: number | null; personnel: number | null; period: string }>(
      db,
      "SELECT branches_total, personnel, period FROM bank_audit_profile " +
        "WHERE bank_ticker = ? AND kind = ? AND period <= ? " +
        "AND (branches_total IS NOT NULL OR personnel IS NOT NULL) " +
        "ORDER BY period DESC LIMIT 1",
      [bank, kind, period],
    ),
    db.all<{ bank_ticker: string; total: number | null }>(
      "SELECT bank_ticker, MAX(amount_total) AS total FROM bank_audit_balance_sheet " +
        "WHERE period = ? AND kind = ? AND hierarchy = '' " +
        "AND statement IN ('assets','liabilities') GROUP BY bank_ticker",
      [period, kind],
    ),
    db.all<{ bank_ticker: string; total: number | null }>(
      "SELECT bank_ticker, total_amount AS total FROM bank_audit_stages " +
        "WHERE period = ? AND kind = ? AND period_type = 'current'",
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
    db.all<{ code: string; period_date: string; value: number | null }>(
      "SELECT code, period_date, value FROM evds_series " +
        "WHERE code IN ('TP.APIFON4','TP.DK.USD.A','TP.TUKFIY2025.GENEL') AND period_date <= ? " +
        "ORDER BY period_date",
      [quarterEndBound(period)],
    ),
    firstRow<{ categories_json: string | null }>(
      db,
      "SELECT categories_json FROM regulation_briefings ORDER BY generated_at DESC LIMIT 1",
    ).catch(() => null),
    db.all<{ currency: string; net_position: number | null; net_on_balance: number | null; net_off_balance: number | null }>(
      "SELECT currency, net_position, net_on_balance, net_off_balance FROM bank_audit_fx_position " +
        "WHERE bank_ticker = ? AND kind = ? AND period = ? AND period_type = 'current'",
      [bank, kind, period],
    ),
    db.all<{ period: string; group_code: string; opening_balance: number | null; additions: number | null; transfers_in: number | null; transfers_out: number | null; collections: number | null; write_offs: number | null; sold: number | null; closing_balance: number | null }>(
      "SELECT period, group_code, opening_balance, additions, transfers_in, transfers_out, " +
        "collections, write_offs, sold, closing_balance " +
        "FROM bank_audit_npl_movement WHERE bank_ticker = ? AND kind = ? AND period_type = 'current'",
      [bank, kind],
    ),
    db.all<{ sector: string; stage3_amount: number | null; period: string }>(
      "SELECT sector, stage3_amount, period FROM bank_audit_loans_by_sector " +
        "WHERE bank_ticker = ? AND kind = ? AND period_type = 'current' " +
        "AND period = (SELECT MAX(period) FROM bank_audit_loans_by_sector " +
        "WHERE bank_ticker = ? AND kind = ? AND period <= ?) " +
        "AND sector NOT IN ('total','agri_total','mfg_total','svc_total') " +
        "AND stage3_amount IS NOT NULL ORDER BY stage3_amount DESC LIMIT 5",
      [bank, kind, bank, kind, period],
    ),
    db.all<{ period: string; opinion_type: string | null; report_kind: string | null; auditor: string | null; basis_text: string | null }>(
      "SELECT period, opinion_type, report_kind, auditor, basis_text FROM bank_audit_opinion " +
        "WHERE bank_ticker = ? AND kind = ? AND period <= ? ORDER BY period",
      [bank, kind, period],
    ),
    firstRow<{ reporting_unit: string | null; unit_source: string; assurance_level: string; assurance_source: string; opinion_category: string | null }>(
      db,
      "SELECT reporting_unit, unit_source, assurance_level, assurance_source, opinion_category " +
        "FROM analyst_basis_metadata WHERE bank_ticker = ? AND period = ? AND kind = ?",
      [bank, period, kind],
    ).catch(() => null),
    tableOrEmpty<{ signal_id: string; signal_type: string; severity: string; payload: string }>(
      db,
      "SELECT signal_id, signal_type, severity, payload FROM analyst_signals " +
        "WHERE bank_ticker = ? AND period = ? AND kind = ?",
      [bank, period, kind],
    ),
    firstRow<{ extracted_at: string | null }>(
      db,
      "SELECT MAX(extracted_at) AS extracted_at FROM bank_audit_extractions " +
        "WHERE bank_ticker = ? AND kind = ?",
      [bank, kind],
    ),
    db.all<{ statement: string }>(
      "SELECT DISTINCT statement FROM bank_audit_validation " +
        "WHERE bank_ticker = ? AND kind = ? AND period = ? AND checks_failed > 0",
      [bank, kind, period],
    ),
  ]);

  /* -------- macro -------- */
  const latestOf = (code: string): number | null => {
    let v: number | null = null;
    for (const r of evdsRows) if (r.code === code && r.value != null) v = r.value;
    return v;
  };
  const cpiIndexAt = (yyyymm: string): number | null => {
    let v: number | null = null;
    for (const r of evdsRows) {
      if (r.code === "TP.TUKFIY2025.GENEL" && r.value != null && r.period_date.slice(0, 7) <= yyyymm) {
        v = r.value;
      }
    }
    return v;
  };
  const qm = `${period.slice(0, 4)}-${QUARTER_END_MONTH[period.slice(5)]}`;
  const qmPrior = `${Number(period.slice(0, 4)) - 1}-${QUARTER_END_MONTH[period.slice(5)]}`;
  const cpiNow = cpiIndexAt(qm);
  const cpiBase = cpiIndexAt(qmPrior);
  const cpiYoY = cpiNow != null && cpiBase != null && cpiBase > 0 ? (cpiNow / cpiBase - 1) * 100 : null;

  let regulationCategories: string[] = [];
  try {
    const parsed = briefingRow?.categories_json ? JSON.parse(briefingRow.categories_json) : null;
    if (parsed && typeof parsed === "object") regulationCategories = Object.keys(parsed);
  } catch {
    regulationCategories = [];
  }

  // BDDK sector aggregates (family B): code 10001 IS the whole system —
  // never summed. Ratio labels are the VERBATIM strings from bot-schema.ts
  // (LIKE does not fold Turkish; guessing the label cost five queries once).
  // Sector amounts are MILLION TL; per-bank audit amounts are THOUSAND TL —
  // the share calculation converts explicitly.
  const yyyymm = Number(`${period.slice(0, 4)}${QUARTER_END_MONTH[period.slice(5)]}`);
  const sectorRatio = async (label: string): Promise<{ v: number | null; ym: number | null }> => {
    const row = await firstRow<{ ratio_value: number | null; year: number; month: number }>(
      db,
      "SELECT ratio_value, year, month FROM financial_ratios " +
        "WHERE bank_type_code = '10001' AND item_name = ? AND (year * 100 + month) <= ? " +
        "ORDER BY year DESC, month DESC LIMIT 1",
      [label, yyyymm],
    ).catch(() => null);
    return { v: row?.ratio_value ?? null, ym: row ? row.year * 100 + row.month : null };
  };
  const [secRoe, secNpl, secCar, secNim, secAssets] = await Promise.all([
    sectorRatio("Dönem Net Kârı (Zararı) / Ortalama Özkaynaklar (%)"),
    sectorRatio("Takipteki Alacaklar (Brüt) / Toplam Nakdi Krediler (%)"),
    sectorRatio("Yasal Özkaynak / Risk Ağırlıklı Kalemler Toplamı (%)"),
    sectorRatio("Net Faiz Geliri (Gideri) / Ortalama Toplam Aktifler (%)"),
    firstRow<{ amount_total: number | null; year: number; month: number }>(
      db,
      "SELECT amount_total, year, month FROM balance_sheet " +
        "WHERE bank_type_code = '10001' AND currency = 'TL' AND item_name = 'TOPLAM AKTİFLER' " +
        "AND (year * 100 + month) <= ? ORDER BY year DESC, month DESC LIMIT 1",
      [yyyymm],
    ).catch(() => null),
  ]);

  /* -------- earnings -------- */
  const netYtdMap = s.plByRole.get("period_net") ?? new Map<number, number>();
  const netYtd = netYtdMap.get(ord) ?? null;
  const netQuarterly = singleQuarter(netYtdMap, ord);
  const netTtm = ttmEndingAt(netYtdMap, ord);
  const netTtmPrior = ttmEndingAt(netYtdMap, ord - 4);

  const avgEquity = trailingAverage(s.equityClosing, period);
  const avgAssets = trailingAverage(s.bsTotal, period);
  const roeTtm = netTtm != null && avgEquity != null && avgEquity > 0 ? (netTtm / avgEquity) * 100 : null;
  const roaTtm = netTtm != null && avgAssets != null && avgAssets > 0 ? (netTtm / avgAssets) * 100 : null;
  const roeReal = realRate(roeTtm, cpiYoY);

  const fpNow = s.freeProvision.get(period);
  const releaseYtdAt = (p: string): number | null => {
    const row = s.freeProvision.get(p);
    return row && row.stock != null && row.prior != null ? row.prior - row.stock : null;
  };
  const releaseYtd = releaseYtdAt(period);
  const y = Number(period.slice(0, 4));
  // TTM release telescopes the same way profit does: YTD(now) + FY(prior year) − YTD(same quarter prior year).
  const relFyPrior = releaseYtdAt(`${y - 1}Q4`);
  const relPriorSame = releaseYtdAt(prevYearSame);
  const ttmRelease =
    releaseYtd != null && relFyPrior != null && relPriorSame != null
      ? releaseYtd + relFyPrior - relPriorSame
      : null;
  const roeExRelease =
    netTtm != null && ttmRelease != null && avgEquity != null && avgEquity > 0
      ? ((netTtm - ttmRelease) / avgEquity) * 100
      : null;

  const coreNow = findPlLine(s.plLines, period, CORE_MARGIN_RE);
  const corePriorYear = findPlLine(s.plLines, prevYearSame, CORE_MARGIN_RE);
  const coreQuarterly: { period: string; amount: number | null }[] = [];
  {
    const coreYtdByOrd = new Map<number, number>();
    for (let k = 12; k >= 0; k--) {
      const p = periodFromOrd(ord - k);
      const line = findPlLine(s.plLines, p, CORE_MARGIN_RE);
      if (line?.amount != null) coreYtdByOrd.set(ord - k, line.amount);
    }
    for (let k = 8; k >= 0; k--) {
      coreQuarterly.push({ period: periodFromOrd(ord - k), amount: singleQuarter(coreYtdByOrd, ord - k) });
    }
  }

  const fpHistory: AnalystSections["earnings"]["free_provision"]["history"] = [];
  for (let k = 8; k >= 0; k--) {
    const p = periodFromOrd(ord - k);
    const row = s.freeProvision.get(p);
    const rel = releaseYtdAt(p);
    const income = netYtdMap.get(ord - k) ?? null;
    fpHistory.push({
      period: p,
      stock: row?.stock ?? null,
      release_ytd: rel,
      net_income_ytd: income,
      release_pct_of_income:
        rel != null && income != null && income !== 0 ? pct((rel / income) * 100, 1) : null,
      income_ex_release: rel != null && income != null ? income - rel : null,
    });
  }

  const grossMap = s.plByRole.get("gross") ?? new Map<number, number>();
  const operatingIncomeTtm = ttmEndingAt(grossMap, ord);
  const opexPers = s.plByRole.get("opex_personnel") ?? new Map<number, number>();
  const opexOther = s.plByRole.get("opex_other") ?? new Map<number, number>();
  const opexTtmPers = ttmEndingAt(opexPers, ord);
  const opexTtmOther = ttmEndingAt(opexOther, ord);
  const costIncome =
    opexTtmPers != null && opexTtmOther != null && operatingIncomeTtm != null && operatingIncomeTtm !== 0
      ? (Math.abs(opexTtmPers + opexTtmOther) / Math.abs(operatingIncomeTtm)) * 100
      : null;

  const feesLine = findPlLine(s.plLines, period, NET_FEES_RE);

  const movers: AnalystSections["earnings"]["pl_movers"] = [];
  {
    const nowLines = s.plLines.filter((l) => l.period === period && l.amount != null && l.item_name);
    const priorByKey = new Map<string, number>();
    for (const l of s.plLines) {
      if (l.period === prevYearSame && l.amount != null && l.item_name) {
        priorByKey.set(`${l.hierarchy}|${foldTr(l.item_name)}`, l.amount);
      }
    }
    for (const l of nowLines) {
      const prior = priorByKey.get(`${l.hierarchy}|${foldTr(l.item_name as string)}`);
      if (prior == null || Math.abs(prior) < 1000) continue;
      const g = yoyPct(l.amount, prior);
      if (g == null) continue;
      movers.push({ item_name: l.item_name as string, ytd: l.amount as number, prior_year_ytd: prior, yoy_pct: Number(g.toFixed(1)) });
    }
    movers.sort((a, b) => Math.abs(b.ytd - b.prior_year_ytd) - Math.abs(a.ytd - a.prior_year_ytd));
    movers.length = Math.min(movers.length, 5);
  }

  const assetsNow = s.bsTotal.get(period) ?? null;
  const assetsPriorYear = s.bsTotal.get(prevYearSame) ?? null;
  const assetsYoY = yoyPct(assetsNow, assetsPriorYear);

  /* -------- asset quality -------- */
  const st = s.stages.get(period);
  const nplRatio = st?.stage3_amount != null && st.total_amount ? (st.stage3_amount / st.total_amount) * 100 : null;
  const stage2Ratio = st?.stage2_amount != null && st.total_amount ? (st.stage2_amount / st.total_amount) * 100 : null;

  // BRSA groups III/IV/V live in credit_quality's stage1/2/3 columns for the
  // npl_brsa_* sections (a probed, non-obvious fact — do not "fix" it).
  const cqRows = await db.all<{ period: string; section: string; stage1_amount: number | null; stage2_amount: number | null; stage3_amount: number | null }>(
    "SELECT period, section, stage1_amount, stage2_amount, stage3_amount " +
      "FROM bank_audit_credit_quality WHERE bank_ticker = ? AND kind = ? " +
      "AND period_type = 'current' AND section IN ('npl_brsa_gross','npl_brsa_provision')",
    [bank, kind],
  );

  // Per-stage GROSS ECL expense (YTD). Here stage columns ARE IFRS stages.
  const eclRows = await db.all<{ period: string; stage1_amount: number | null; stage2_amount: number | null; stage3_amount: number | null }>(
    "SELECT period, stage1_amount, stage2_amount, stage3_amount " +
      "FROM bank_audit_credit_quality WHERE bank_ticker = ? AND kind = ? " +
      "AND period_type = 'current' AND section = 'loans_ecl_expense'",
    [bank, kind],
  );
  const eclNow = eclRows.find((r) => r.period === period) ?? null;
  const eclSum = (r: { stage1_amount: number | null; stage2_amount: number | null; stage3_amount: number | null } | null): number | null =>
    r && (r.stage1_amount != null || r.stage2_amount != null || r.stage3_amount != null)
      ? (r.stage1_amount ?? 0) + (r.stage2_amount ?? 0) + (r.stage3_amount ?? 0)
      : null;
  const eclYtdByOrd = new Map<number, number>();
  for (const r of eclRows) {
    const o = ordOf(r.period);
    const v = eclSum(r);
    if (o != null && v != null) eclYtdByOrd.set(o, v);
  }
  const eclTtm = ttmEndingAt(eclYtdByOrd, ord);
  const avgLoansForCoR = trailingAverage(
    new Map([...s.stages].map(([p, r]) => [p, r.total_amount] as [string, number]).filter(([, v]) => v != null) as [string, number][]),
    period,
  );
  const costOfRisk =
    eclTtm != null && avgLoansForCoR != null && avgLoansForCoR > 0
      ? (eclTtm / avgLoansForCoR) * 100
      : null;

  // Management commentary — the latest transcribed call for this bank,
  // preferring the report's own quarter. Verbatim executive turns only:
  // attribution is the transcript corpus's weak axis, so no speaker names.
  let management: AnalystSections["management"] = {
    _gaps: ["no transcribed earnings call available for this bank"],
    call_date: null,
    call_period: null,
    title: null,
    excerpts: [],
  };
  try {
    const call =
      (await firstRow<{ period: string; call_date: string; title: string | null; transcript_json: string }>(
        db,
        "SELECT period, call_date, title, transcript_json FROM bank_call_transcripts " +
          "WHERE bank_ticker = ? AND period = ? ORDER BY call_date DESC LIMIT 1",
        [bank, period],
      )) ??
      (await firstRow<{ period: string; call_date: string; title: string | null; transcript_json: string }>(
        db,
        "SELECT period, call_date, title, transcript_json FROM bank_call_transcripts " +
          "WHERE bank_ticker = ? AND call_date <= ? ORDER BY call_date DESC LIMIT 1",
        [bank, `${period.slice(0, 4)}-${QUARTER_END_MONTH[period.slice(5)]}-31`],
      ));
    if (call) {
      const turns = JSON.parse(call.transcript_json) as { role?: string; text?: string }[];
      const TOPICS: [string, RegExp][] = [
        ["margin", /margin|NIM|net interest|spread|funding cost/i],
        ["asset quality", /provision|coverage|NPL|stage|asset quality|cost of risk/i],
        ["outlook", /guidance|outlook|expect|target|forecast/i],
        ["capital", /capital|dividend|CET1|CAR\b/i],
      ];
      const excerpts: { topic: string; quote: string }[] = [];
      for (const [topic, rx] of TOPICS) {
        const turn = turns.find(
          (t) => t.role === "executive" && t.text && rx.test(t.text) && t.text.length > 80,
        );
        if (turn?.text) {
          excerpts.push({ topic, quote: turn.text.slice(0, 420).replace(/\s+/g, " ").trim() + (turn.text.length > 420 ? "…" : "") });
        }
      }
      management = {
        _gaps: call.period === period ? [] : [`latest transcribed call covers ${call.period}, not ${period}`],
        call_date: call.call_date,
        call_period: call.period,
        title: call.title,
        excerpts,
      };
    }
  } catch {
    /* table absent (not pushed to D1 yet / not in this snapshot) — the gap stands */
  }
  const GROUPS = ["III", "IV", "V"] as const;
  const cqAt = (p: string, section: string): (number | null)[] | null => {
    const r = cqRows.find((x) => x.period === p && x.section === section);
    return r ? [r.stage1_amount, r.stage2_amount, r.stage3_amount] : null;
  };
  const bucketRow = (p: string) => {
    const gross = cqAt(p, "npl_brsa_gross");
    const prov = cqAt(p, "npl_brsa_provision");
    if (!gross || !prov) return null;
    const total = gross.reduce<number>((a, b) => a + (b ?? 0), 0);
    if (total <= 0) return null;
    return GROUPS.map((g, i) => ({
      group: g,
      gross: gross[i],
      provision: prov[i],
      share: gross[i] != null ? (gross[i] as number) / total : null,
      coverage: gross[i] != null && gross[i] !== 0 && prov[i] != null ? (prov[i] as number) / (gross[i] as number) : null,
    }));
  };
  const bucketsNow = bucketRow(period);
  const windowStart = periodFromOrd(ord - 4);
  const bucketsThen = bucketRow(windowStart);
  const coverageDecomposition = decomposeCoverage(windowStart, bucketsThen, bucketsNow);

  const nplNow = nplRows.filter((r) => r.period === period);
  const additionsQuarterly: AnalystSections["asset_quality"]["additions_quarterly"] = [];
  for (const g of GROUPS) {
    const byOrd = new Map<number, number>();
    for (const r of nplRows) {
      const o = ordOf(r.period);
      if (r.group_code === g && o != null && r.additions != null) byOrd.set(o, r.additions);
    }
    for (let k = 4; k >= 0; k--) {
      additionsQuarterly.push({
        period: periodFromOrd(ord - k),
        group: g,
        amount: singleQuarter(byOrd, ord - k),
      });
    }
  }
  const anyWo = nplRows.some((r) => (r.write_offs ?? 0) !== 0 || (r.sold ?? 0) !== 0);
  const anyWoKnown = nplRows.some((r) => r.write_offs != null || r.sold != null);

  /* -------- currency -------- */
  const fxTotal = fxRows.find((r) => r.currency === "TOTAL");
  const fcNow = s.bsFc.get(period);

  /* -------- funding -------- */
  const dep = s.deposits.get(period);
  const liq = s.liquidity.get(period);
  const ldr =
    st?.total_amount != null && dep?.total != null && dep.total > 0
      ? (st.total_amount / dep.total) * 100
      : null;

  /* -------- capital -------- */
  const cap = s.capital.get(period);
  const capPrevQ = s.capital.get(periodFromOrd(ord - 1));
  const capPrevY = s.capital.get(prevYearSame);
  const equityNow = s.equityClosing.get(period) ?? null;
  const gapPp = cap?.capital_adequacy_ratio != null && cap.cet1_ratio != null
    ? cap.capital_adequacy_ratio - cap.cet1_ratio
    : null;
  const growthPct = (now: number | null | undefined, prior: number | null | undefined) =>
    now != null && prior != null && prior !== 0 ? pct(((now - prior) / Math.abs(prior)) * 100, 1) : null;
  const netQuarterlySeries: AnalystSections["earnings"]["net_income_quarterly_series"] = [];
  for (let k = 8; k >= 0; k--) {
    netQuarterlySeries.push({
      period: periodFromOrd(ord - k),
      amount: singleQuarter(netYtdMap, ord - k),
    });
  }

  const aqHistory: AnalystSections["asset_quality"]["history"] = [];
  for (let k = 7; k >= 0; k--) {
    const p = periodFromOrd(ord - k);
    const row = s.stages.get(p);
    aqHistory.push({
      period: p,
      npl_pct:
        row?.stage3_amount != null && row.total_amount
          ? pct((row.stage3_amount / row.total_amount) * 100)
          : null,
      stage2_pct:
        row?.stage2_amount != null && row.total_amount
          ? pct((row.stage2_amount / row.total_amount) * 100)
          : null,
      coverage_pct: row?.stage3_coverage != null ? pct(row.stage3_coverage * 100, 1) : null,
    });
  }

  const trajectory: AnalystSections["capital"]["trajectory"] = [];
  for (let k = 9; k >= 0; k--) {
    const p = periodFromOrd(ord - k);
    const c = s.capital.get(p);
    const l = s.liquidity.get(p);
    trajectory.push({
      period: p,
      cet1: c?.cet1_ratio ?? null,
      car: c?.capital_adequacy_ratio ?? null,
      gap_pp:
        c?.capital_adequacy_ratio != null && c.cet1_ratio != null
          ? pct(c.capital_adequacy_ratio - c.cet1_ratio)
          : null,
      leverage: l?.leverage_ratio ?? null,
    });
  }

  /* -------- comparability + governance -------- */
  const opinionNow = opinionRows.find((r) => r.period === period) ?? null;
  let qualifiedStreak = 0;
  for (let i = opinionRows.length - 1; i >= 0; i--) {
    if (opinionRows[i].opinion_type === "qualified") qualifiedStreak++;
    else break;
  }
  const basisLead = opinionNow?.basis_text
    ? opinionNow.basis_text.slice(0, 600).replace(/\s+/g, " ").trim()
    : null;
  const q = period.slice(5);
  const fallbackUnit = ord <= ordOf("2026Q1")! ? "bin" : null;
  const comparability: AnalystSections["comparability"] = {
    _gaps: [],
    reporting_unit: basisRow?.reporting_unit ?? fallbackUnit,
    unit_source: basisRow?.unit_source ?? (fallbackUnit ? "sweep-2026-08-01" : "pending_regex"),
    assurance_level: basisRow?.assurance_level ?? opinionNow?.report_kind ?? (q === "4" ? "audit" : "review"),
    assurance_source: basisRow?.assurance_source ?? (opinionNow?.report_kind ? "opinion" : "expected_rhythm"),
    consolidation_basis: kind,
    opinion_type: opinionNow?.opinion_type ?? null,
    opinion_category:
      basisRow?.opinion_category ?? (basisLead ? (FP_BASIS_RE.test(basisLead) ? "free_provision" : null) : null),
    auditor: opinionNow?.auditor ?? null,
    basis_text_lead: basisLead,
    qualified_streak: qualifiedStreak,
    signals_this_period: signalRows,
  };
  if (!basisRow) comparability._gaps.push("analyst_basis_metadata not in DB — unit/category from fallbacks");
  if (!signalRows.length) comparability._gaps.push("no analyst_signals rows for this partition (table may not be pushed)");

  /* -------- business -------- */
  const shareholders = kapRows
    .filter((r) => r.item === "shareholder" && r.holder && r.holder !== "TOPLAM")
    .map((r) => ({ name: r.holder as string, share_pct: r.ratio_pct }))
    .sort((a, b) => (b.share_pct ?? 0) - (a.share_pct ?? 0));
  const freeFloat = kapRows.find((r) => r.item === "free_float")?.ratio_pct ?? null;

  const peers = (rows: { bank_ticker: string; total: number | null }[]) =>
    rows.filter((r) => !PEER_EXCLUDED_TICKERS.has(r.bank_ticker) && r.total != null) as {
      bank_ticker: string;
      total: number;
    }[];
  const shareOf = (rows: { bank_ticker: string; total: number | null }[]): number | null => {
    const p = peers(rows);
    const mine = p.find((r) => r.bank_ticker === bank)?.total;
    const sum = p.reduce((a, r) => a + r.total, 0);
    return mine != null && sum > 0 ? (mine / sum) * 100 : null;
  };
  const assetPeers = peers(fleetAssets).sort((a, b) => b.total - a.total);
  const myRankIdx = assetPeers.findIndex((r) => r.bank_ticker === bank);

  /* -------- assemble -------- */
  const sections: AnalystSections = {
    business: {
      _gaps: ["per-bank digital-customer counts are not held (TBB stats are sector-level)"],
      bank_name: BANK_NAMES[bank] ?? bank,
      licence_class: licenceClassOf(bank),
      ownership: {
        shareholders: shareholders.slice(0, 6),
        subsidiaries: kapRows
          .filter((r) => r.item === "subsidiary" && r.holder)
          .map((r) => ({ name: r.holder as string, activity: r.activity, share_pct: r.ratio_pct }))
          .slice(0, 10),
        free_float_pct: freeFloat,
      },
      profile: {
        branches: profileRow?.branches_total ?? null,
        personnel: profileRow?.personnel ?? null,
        as_of: profileRow?.period ?? null,
      },
      market_share: {
        assets_pct: pct(shareOf(fleetAssets)),
        loans_pct: pct(shareOf(fleetLoans)),
        deposits_pct: pct(shareOf(fleetDeposits)),
        peer_rank_by_assets: myRankIdx >= 0 ? myRankIdx + 1 : null,
        peer_count: assetPeers.length,
      },
    },
    macro: {
      _gaps: [
        ...(regulationCategories.length ? [] : ["no regulation briefing available"]),
        ...(secAssets ? [] : ["sector bulletin tables not reachable — sector context absent"]),
      ],
      funding_rate_pct: latestOf("TP.APIFON4"),
      cpi_yoy_pct: pct(cpiYoY),
      usd_try: latestOf("TP.DK.USD.A"),
      regulation_categories: regulationCategories,
      sector: {
        as_of: secAssets ? `${secAssets.year}-${String(secAssets.month).padStart(2, "0")}` : null,
        total_assets_million_tl: secAssets?.amount_total ?? null,
        // Bank amounts are THOUSAND TL, sector MILLION TL: share = k / (m × 1000).
        bank_share_of_sector_assets_pct:
          assetsNow != null && secAssets?.amount_total
            ? pct((assetsNow / (secAssets.amount_total * 1000)) * 100)
            : null,
        roe_pct: pct(secRoe.v),
        npl_ratio_pct: pct(secNpl.v),
        car_pct: pct(secCar.v),
        nim_pct: pct(secNim.v),
      },
    },
    earnings: {
      _gaps: [
        "CPI-linker income, swap costs and securities duration are in unextracted footnotes",
        "ECL reversals are not separable from the gross charge — the net provision charge is not held",
        ...(coreNow ? [] : ["core margin line not found by label — participation/legacy template"]),
      ],
      total_assets: assetsNow,
      assets_yoy_pct: pct(assetsYoY),
      assets_yoy_real_pct: pct(realRate(assetsYoY, cpiYoY)),
      net_income_ytd: netYtd,
      net_income_quarterly: netQuarterly,
      net_income_ttm: netTtm,
      net_income_yoy_pct: pct(yoyPct(netTtm, netTtmPrior)),
      roe_ttm_pct: pct(roeTtm),
      roe_real_pct: pct(roeReal),
      roa_ttm_pct: pct(roaTtm),
      free_provision: {
        stock: fpNow?.stock ?? null,
        prior_year_end_stock: fpNow?.prior ?? null,
        release_ytd: releaseYtd,
        release_pct_of_ytd_income:
          releaseYtd != null && netYtd ? pct((releaseYtd / netYtd) * 100, 1) : null,
        ttm_release: ttmRelease,
        roe_ex_release_pct: pct(roeExRelease),
        history: fpHistory,
      },
      core_margin: {
        label: coreNow?.item_name ?? null,
        ytd: coreNow?.amount ?? null,
        quarterly_series: coreQuarterly,
        yoy_ytd_pct: pct(yoyPct(coreNow?.amount ?? null, corePriorYear?.amount ?? null)),
      },
      operating_income_ttm: operatingIncomeTtm,
      net_fees_ytd: feesLine?.amount ?? null,
      opex: {
        personnel_ytd: opexPers.get(ord) ?? null,
        other_ytd: opexOther.get(ord) ?? null,
        cost_income_ttm_pct: pct(costIncome, 1),
      },
      ecl: {
        stage1_ytd: eclNow?.stage1_amount ?? null,
        stage2_ytd: eclNow?.stage2_amount ?? null,
        stage3_ytd: eclNow?.stage3_amount ?? null,
        total_ytd: eclSum(eclNow),
        ttm_total: eclTtm,
        cost_of_risk_ttm_pct: pct(costOfRisk),
      },
      net_income_quarterly_series: netQuarterlySeries,
      pl_movers: movers,
    },
    asset_quality: {
      _gaps: [
        "stage-definition notes (SICR triggers, DPD thresholds) are not extracted — peer stage comparisons carry that caveat",
        "restructured loans and collateral are in unextracted §5 footnotes",
        "gross loans per sector are not stored — sector view is Stage-3 only",
      ],
      gross_loans: st?.total_amount ?? null,
      npl_ratio_pct: pct(nplRatio),
      stage2_ratio_pct: pct(stage2Ratio),
      stage3_coverage_pct: st?.stage3_coverage != null ? pct(st.stage3_coverage * 100, 1) : null,
      stage2_coverage_pct: st?.stage2_coverage != null ? pct(st.stage2_coverage * 100, 1) : null,
      npl_by_bucket: (bucketsNow ?? []).map((b) => ({
        group: b.group,
        gross: b.gross,
        share_pct: b.share != null ? pct(b.share * 100, 1) : null,
        coverage_pct: b.coverage != null ? pct(b.coverage * 100, 1) : null,
      })),
      coverage_decomposition: coverageDecomposition,
      npl_movement: nplNow.map((r) => ({
        group: r.group_code,
        opening: r.opening_balance,
        additions_ytd: r.additions,
        transfers_in_ytd: r.transfers_in,
        transfers_out_ytd: r.transfers_out,
        collections_ytd: r.collections,
        write_offs_ytd: r.write_offs,
        sold_ytd: r.sold,
        closing: r.closing_balance,
      })),
      additions_quarterly: additionsQuarterly,
      zero_write_offs_all_periods: anyWoKnown ? !anyWo : null,
      npl_by_sector: sectorRows.map((r) => ({ sector: r.sector, stage3: r.stage3_amount, as_of: r.period })),
      history: aqHistory,
    },
    currency: {
      _gaps: ["borrower-level FX exposure is not disclosed in filings"],
      net_fx_position: fxTotal?.net_position ?? null,
      net_on_balance: fxTotal?.net_on_balance ?? null,
      net_off_balance: fxTotal?.net_off_balance ?? null,
      by_currency: fxRows
        .filter((r) => r.currency !== "TOTAL")
        .map((r) => ({ ccy: r.currency, net_position: r.net_position })),
      fx_assets: fcNow?.assets ?? null,
      fx_liabilities: fcNow?.liabilities ?? null,
      usd_try: latestOf("TP.DK.USD.A"),
    },
    funding: {
      _gaps: [
        "demand/time deposit split and top-depositor concentration are in unextracted notes",
      ],
      deposits_label: dep?.label ?? null,
      deposits_total: dep?.total ?? null,
      deposits_tl: dep?.tl ?? null,
      deposits_fc: dep?.fc ?? null,
      ldr_pct: pct(ldr, 1),
      lcr_total_pct: liq?.lcr_total ?? null,
      lcr_fc_pct: liq?.lcr_fc ?? null,
      nsfr_pct: liq?.nsfr ?? null,
      leverage_pct: liq?.leverage_ratio ?? null,
    },
    capital: {
      _gaps: ["tangible common equity needs goodwill from unextracted footnotes"],
      cet1_pct: cap?.cet1_ratio ?? null,
      tier1_pct: cap?.tier1_ratio ?? null,
      car_pct: cap?.capital_adequacy_ratio ?? null,
      car_minus_cet1_pp: pct(gapPp),
      noncore_share_of_car:
        gapPp != null && cap?.capital_adequacy_ratio ? pct(gapPp / cap.capital_adequacy_ratio, 3) : null,
      cet1_capital: cap?.cet1_capital ?? null,
      tier2_capital: cap?.tier2_capital ?? null,
      total_capital: cap?.total_capital ?? null,
      rwa: cap?.total_rwa ?? null,
      total_equity: equityNow,
      equity_to_assets_pct:
        equityNow != null && assetsNow ? pct((equityNow / assetsNow) * 100, 1) : null,
      trajectory,
      ratio_drivers: {
        cet1_capital_qoq_pct: growthPct(cap?.cet1_capital, capPrevQ?.cet1_capital),
        rwa_qoq_pct: growthPct(cap?.total_rwa, capPrevQ?.total_rwa),
        cet1_capital_yoy_pct: growthPct(cap?.cet1_capital, capPrevY?.cet1_capital),
        rwa_yoy_pct: growthPct(cap?.total_rwa, capPrevY?.total_rwa),
      },
    },
    securities: {
      _gaps: [
        "securities totals and the fixed/CPI-linked/trading breakdown are in unextracted §4 footnotes",
      ],
      total: null,
      breakdown_available: false,
    },
    comparability,
    management,
    governance: {
      _gaps: ["management turnover and guidance-vs-actuals are not sourced"],
      controlling_shareholder: shareholders[0]?.name ?? null,
      controlling_share_pct: shareholders[0]?.share_pct ?? null,
      free_float_pct: freeFloat,
      qualified_streak: qualifiedStreak,
      is_free_provision_qualified:
        comparability.opinion_category != null
          ? comparability.opinion_category === "free_provision"
          : null,
    },
    valuation: {
      _gaps: ["market prices removed (redistribution terms) — no P/B, P/E or dividend yield"],
      roe_ttm_pct: pct(roeTtm),
      roe_real_pct: pct(roeReal),
      roe_ex_free_provision_pct: pct(roeExRelease),
      price_to_book: null,
    },
    meta: {
      bank_ticker: bank,
      bank_name: BANK_NAMES[bank] ?? bank,
      period,
      kind,
      generated_at: new Date().toISOString(),
      extracted_at: metaRow?.extracted_at ?? null,
      validation_failing_statements: failingRows.map((r) => r.statement),
    },
  };
  return sections;
}
