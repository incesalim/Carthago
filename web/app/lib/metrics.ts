/**
 * Metrics layer — Option 1 (SQL helpers in TypeScript).
 *
 * Each function returns the structured result of a D1 query. Server
 * Components call these directly. Mirrors the Python `metrics_ext.py`
 * surface where possible.
 *
 * BDDK bank-type taxonomy — MONTHLY tables (balance_sheet, financial_ratios,
 * loans, deposits), per the `bank_types` DB table. NOTE: the weekly bulletin
 * numbers the same groups DIFFERENTLY — see WEEKLY_BANK_TYPES below. Monthly:
 *   10001 = Entire sector
 *   10002 = Deposit banks (Mevduat)
 *   10003 = Participation banks (Katılım)
 *   10004 = Development & investment banks (Kalkınma ve Yatırım)
 *   10005 = Private banks, all types (Yerli Özel)
 *   10006 = State banks, all types (Kamu)
 *   10007 = Foreign banks, all types (Yabancı)
 *   10008 / 10009 / 10010 = deposit banks only — Private / State / Foreign
 * Two partitions each sum to the sector and OVERLAP: by type {10002,10003,
 * 10004}; by ownership {10005,10006,10007}. So 10006 "State" already includes
 * state-owned participation + development banks; the three state *deposit*
 * banks alone are 10009.
 */
import { cachedAll } from "./db";
import type { NimComponentRow } from "./nim-components";
import type { BsRow, PnlRow } from "./profitability";
import { computeWeeklyGrowth, type WeeklyGrowthInput } from "./weekly-growth";

// ---------------------------------------------------------------------------
// Bank-type taxonomy
// ---------------------------------------------------------------------------

// Verified against bank_types table in DB. Mapping is non-obvious — codes
// don't follow ownership/function order. Sourced from bank_types.name_en.
export const BANK_TYPES = {
  SECTOR: "10001",
  DEPOSIT: "10002",
  PARTICIPATION: "10003",
  DEV_INV: "10004",
  PRIVATE: "10005",
  STATE: "10006",
  FOREIGN: "10007",
} as const;

// The headline groups charts compare. CAUTION — NOT a partition: {Private,
// State, Foreign} (10005/6/7) already cover the whole sector by ownership, and
// {Participation, Dev_Inv} overlap with them, so SUMMING/stacking all five
// double-counts (~sector × 1.16). Fine as side-by-side comparison series; for a
// true breakdown use ONE partition (by type, by ownership, or deposit-ownership
// 10008/9/10 + Participation + Dev_Inv).
export const PRIMARY_BANK_TYPES = [
  BANK_TYPES.SECTOR,
  BANK_TYPES.PRIVATE,
  BANK_TYPES.STATE,
  BANK_TYPES.FOREIGN,
  BANK_TYPES.PARTICIPATION,
  BANK_TYPES.DEV_INV,
];

export const BANK_TYPE_LABELS: Record<string, string> = {
  "10001": "Sector",
  "10005": "Domestic", // 10005 = Local Private (Yerli Özel) — domestic private, vs Foreign
  "10006": "State",
  "10007": "Foreign",
  "10003": "Participation",
  "10004": "Dev & Inv",
};

// ---------------------------------------------------------------------------
// Time-series row shape (used by most chart helpers)
// ---------------------------------------------------------------------------

export interface TimeSeriesRow {
  period: string; // 'YYYY-MM'
  bank_type_code: string;
  value: number;
}

/**
 * Largest period across one or more row sets — used to label a tab with the
 * date of its most recent data point. Works for both monthly ('YYYY-MM') and
 * dated ('YYYY-MM-DD') series since ISO strings sort lexicographically.
 * Returns undefined if no row carries a period.
 */
export function latestPeriod(
  ...sets: ReadonlyArray<
    ReadonlyArray<{ period?: string | null; period_date?: string | null }>
  >
): string | undefined {
  let max: string | undefined;
  for (const set of sets) {
    for (const r of set) {
      const p = r.period ?? r.period_date;
      if (p && (max === undefined || p > max)) max = p;
    }
  }
  return max;
}

// ---------------------------------------------------------------------------
// Published ratios — BDDK Table 15 (NPL, CAR, ROA, ROE, NIM, LDR, …)
// Pre-calculated by BDDK; no math needed in our app.
// ---------------------------------------------------------------------------

/**
 * Get a published ratio by EXACT item_name match.
 *
 * `annualize=true` multiplies YTD ratios by 12/month, so e.g. a March YTD value
 * of 1% becomes 4% (annualized). This eliminates the sawtooth pattern in
 * sparklines for YTD ratios (ROA, ROE, NIM) where each year resets.
 */
async function getPublishedRatio(
  itemName: string,
  bankTypes: string[] = PRIMARY_BANK_TYPES,
  tableNumber = 15,
  annualize = false,
): Promise<TimeSeriesRow[]> {
  const placeholders = bankTypes.map(() => "?").join(",");
  const valueExpr = annualize
    ? "ratio_value * 12.0 / month"
    : "ratio_value";
  return cachedAll<TimeSeriesRow>(
    `SELECT
         year || '-' || PRINTF('%02d', month) AS period,
         bank_type_code,
         ${valueExpr} AS value
       FROM financial_ratios
       WHERE table_number = ?
         AND item_name = ?
         AND bank_type_code IN (${placeholders})
       ORDER BY year, month, bank_type_code`,
    [tableNumber, itemName, ...bankTypes],
  );
}

/** NPL ratio (Takipteki Alacaklar Brüt / Toplam Nakdi Krediler). */
export const ratioNpl = (bankTypes?: string[]) =>
  getPublishedRatio(
    "Takipteki Alacaklar (Brüt) / Toplam Nakdi Krediler (%)",
    bankTypes,
  );

/** Loan-to-Deposit ratio. */
export const ratioLdr = (bankTypes?: string[]) =>
  getPublishedRatio(
    "Toplam Nakdi Krediler / Toplam Mevduat (%)",
    bankTypes,
  );

/** NPL coverage ratio. */
export const ratioCoverage = (bankTypes?: string[]) =>
  getPublishedRatio(
    "Takipteki Alacaklar Karşılığı / Brüt Takipteki Alacaklar (%)",
    bankTypes,
  );

/** Capital Adequacy Ratio (Yasal Özkaynak / Risk Ağırlıklı Kalemler Toplamı). */
export const ratioCar = (bankTypes?: string[]) =>
  getPublishedRatio(
    "Yasal Özkaynak / Risk Ağırlıklı Kalemler Toplamı (%)",
    bankTypes,
  );

/** RWA density: net risk-weighted assets / gross. Lower = more diversified
 * risk weights / more low-risk exposure (e.g. govt bonds). */
export const ratioRwaDensity = (bankTypes?: string[]) =>
  getPublishedRatio(
    "Risk Ağırlıklı Kalemler Toplamı (Net) / Risk Ağırlıklı Kalemler Toplamı (Brüt) (%)",
    bankTypes,
  );

/** Off-balance-sheet derivative exposure / total assets. */
export const ratioOffBsDerivatives = (bankTypes?: string[]) =>
  getPublishedRatio(
    "(Bilanço Dışı Riskler - Türev Finansal Araçlar) / Toplam Aktifler (%)",
    bankTypes,
  );

/** Net Interest Margin (annualized — YTD × 12/month). */
export const ratioNim = (bankTypes?: string[]) =>
  getPublishedRatio(
    "Net Faiz Geliri (Gideri) / Ortalama Toplam Aktifler (%)",
    bankTypes,
    15,
    true, // annualize
  );

/** Return on Assets (annualized — YTD × 12/month). */
export const ratioRoa = (bankTypes?: string[]) =>
  getPublishedRatio(
    "Dönem Net Kârı (Zararı) / Ortalama Toplam Aktifler (%)",
    bankTypes,
    15,
    true,
  );

/** Return on Equity (annualized — YTD × 12/month). */
export const ratioRoe = (bankTypes?: string[]) =>
  getPublishedRatio(
    "Dönem Net Kârı (Zararı) / Ortalama Özkaynaklar (%)",
    bankTypes,
    15,
    true,
  );

/** OPEX / Avg Total Assets (annualized — YTD × 12/month). */
export const ratioOpex = (bankTypes?: string[]) =>
  getPublishedRatio(
    "İşletme Giderleri / Ortalama Toplam Aktifler (%)",
    bankTypes,
    15,
    true,
  );

/** Fees & Commissions / Total Revenue (%). YTD ratio — both num + den
 * cumulate within year, so the ratio itself is already comparable across
 * months without annualization. */
export const ratioFeesToRevenue = (bankTypes?: string[]) =>
  getPublishedRatio(
    "Ücret, Komisyon ve Bankacılık Hizmetleri Gelirleri / Toplam Gelirler (%)",
    bankTypes,
  );

/** Non-interest income / non-interest expense (cost coverage). */
export const ratioNonInterestCoverage = (bankTypes?: string[]) =>
  getPublishedRatio(
    "Faiz Dışı Gelirler / Faiz Dışı Giderler (%)",
    bankTypes,
  );

/** Fees & Commissions / OPEX (fee-led cost coverage). */
export const ratioFeesToOpex = (bankTypes?: string[]) =>
  getPublishedRatio(
    "Ücret, Komisyon ve Bankacılık Hizmetleri Gelirleri / İşletme Giderleri (%)",
    bankTypes,
  );

// ---------------------------------------------------------------------------
// Balance-sheet direct queries
// ---------------------------------------------------------------------------

async function getBalanceItem(
  itemName: string,
  bankTypes: string[] = PRIMARY_BANK_TYPES,
  currency: "TL" | "USD" = "TL",
): Promise<TimeSeriesRow[]> {
  const placeholders = bankTypes.map(() => "?").join(",");
  return cachedAll<TimeSeriesRow>(
    `SELECT
         year || '-' || PRINTF('%02d', month) AS period,
         bank_type_code,
         amount_total AS value
       FROM balance_sheet
       WHERE item_name = ?
         AND currency = ?
         AND bank_type_code IN (${placeholders})
       ORDER BY year, month, bank_type_code`,
    [itemName, currency, ...bankTypes],
  );
}

/** Sector / per-group total assets (in million TL — divide by 1e6 for trillion). */
export const totalAssets = (bankTypes?: string[]) =>
  getBalanceItem("TOPLAM AKTİFLER", bankTypes);

/** Sector / per-group total liabilities. */
export const totalLiabilities = (bankTypes?: string[]) =>
  getBalanceItem("TOPLAM YABANCI KAYNAKLAR", bankTypes);

/** Sector / per-group total equity. */
export const totalEquity = (bankTypes?: string[]) =>
  getBalanceItem("TOPLAM ÖZKAYNAKLAR", bankTypes);

/** Equity YoY growth. */
export async function equityYoY(
  bankTypes: string[] = PRIMARY_BANK_TYPES,
): Promise<TimeSeriesRow[]> {
  return _growthYoY(
    { table: "balance_sheet", amountColumn: "amount_total", itemName: "TOPLAM ÖZKAYNAKLAR" },
    bankTypes,
  );
}

/**
 * Liabilities / Equity (leverage) ratio per period.
 */
export async function leverage(
  bankTypes: string[] = PRIMARY_BANK_TYPES,
): Promise<TimeSeriesRow[]> {
  const placeholders = bankTypes.map(() => "?").join(",");
  return cachedAll<TimeSeriesRow>(
    `WITH x AS (
         SELECT year, month, bank_type_code, item_name, amount_total
         FROM balance_sheet
         WHERE currency = 'TL'
           AND bank_type_code IN (${placeholders})
           AND item_name IN ('TOPLAM YABANCI KAYNAKLAR', 'TOPLAM ÖZKAYNAKLAR')
       )
       SELECT
         a.year || '-' || PRINTF('%02d', a.month) AS period,
         a.bank_type_code,
         CASE WHEN b.amount_total > 0
              THEN (a.amount_total * 100.0 / b.amount_total)
              ELSE NULL END AS value
       FROM x a
       JOIN x b
         ON b.year = a.year AND b.month = a.month
        AND b.bank_type_code = a.bank_type_code
        AND a.item_name = 'TOPLAM YABANCI KAYNAKLAR'
        AND b.item_name = 'TOPLAM ÖZKAYNAKLAR'
       ORDER BY a.year, a.month, a.bank_type_code`,
    [...bankTypes],
  );
}

// ---------------------------------------------------------------------------
// Loans + deposits
// ---------------------------------------------------------------------------

/** Loans + deposits use `total_amount`/`total_tl`/`total_fx` (note: balance_sheet uses
 *  the inverted naming `amount_total`/`amount_tl`/`amount_fx`). */
async function getLoanColumn(
  itemName: string,
  column: "total_amount" | "total_tl" | "total_fx" | "npl_amount",
  bankTypes: string[] = PRIMARY_BANK_TYPES,
): Promise<TimeSeriesRow[]> {
  const placeholders = bankTypes.map(() => "?").join(",");
  return cachedAll<TimeSeriesRow>(
    `SELECT
         year || '-' || PRINTF('%02d', month) AS period,
         bank_type_code,
         ${column} AS value
       FROM loans
       WHERE item_name = ?
         AND currency = 'TL'
         AND bank_type_code IN (${placeholders})
       ORDER BY year, month, bank_type_code`,
    [itemName, ...bankTypes],
  );
}

async function getDepositColumn(
  itemName: string,
  column: "total_amount" | "demand" |
    "maturity_1m" | "maturity_1_3m" | "maturity_3_6m" | "maturity_6_12m" | "maturity_over_12m",
  bankTypes: string[] = PRIMARY_BANK_TYPES,
): Promise<TimeSeriesRow[]> {
  const placeholders = bankTypes.map(() => "?").join(",");
  return cachedAll<TimeSeriesRow>(
    `SELECT
         year || '-' || PRINTF('%02d', month) AS period,
         bank_type_code,
         ${column} AS value
       FROM deposits
       WHERE item_name = ?
         AND currency = 'TL'
         AND bank_type_code IN (${placeholders})
       ORDER BY year, month, bank_type_code`,
    [itemName, ...bankTypes],
  );
}

// Note: loans.item_name in D1 is mixed-case "Toplam Krediler" (not uppercase
// like balance_sheet's "TOPLAM AKTİFLER"). Using the wrong casing returns 0
// rows silently, which was the root cause of blank Credit-page charts.
export const totalLoans = (bankTypes?: string[]) =>
  getLoanColumn("Toplam Krediler", "total_amount", bankTypes);

export const tlLoans = (bankTypes?: string[]) =>
  getLoanColumn("Toplam Krediler", "total_tl", bankTypes);

export const fxLoans = (bankTypes?: string[]) =>
  getLoanColumn("Toplam Krediler", "total_fx", bankTypes);

export const totalDeposits = (bankTypes?: string[]) =>
  getDepositColumn("TOPLAM MEVDUAT", "total_amount", bankTypes);

/** Demand deposits (vadesiz mevduat). */
export const demandDeposits = (bankTypes?: string[]) =>
  getDepositColumn("TOPLAM MEVDUAT", "demand", bankTypes);

/** TL deposits = TP Mevduat (Yurt İçi + Yurt Dışı Yerleşik). */
export async function tlDeposits(
  bankTypes: string[] = PRIMARY_BANK_TYPES,
): Promise<TimeSeriesRow[]> {
  const placeholders = bankTypes.map(() => "?").join(",");
  return cachedAll<TimeSeriesRow>(
    `SELECT
         year || '-' || PRINTF('%02d', month) AS period,
         bank_type_code,
         SUM(total_amount) AS value
       FROM deposits
       WHERE currency = 'TL'
         AND item_name IN (
           'TP Mevduat / Katılım Fonları - Yurt İçi Yerleşik',
           'TP Mevduat / Katılım Fonları - Yurt Dışı Yerleşik'
         )
         AND bank_type_code IN (${placeholders})
       GROUP BY year, month, bank_type_code
       ORDER BY year, month, bank_type_code`,
    [...bankTypes],
  );
}

/** FX deposits in TL equivalent = Döviz Tevdiat (Yurt İçi + Yurt Dışı Yerleşik). */
export async function fxDeposits(
  bankTypes: string[] = PRIMARY_BANK_TYPES,
): Promise<TimeSeriesRow[]> {
  const placeholders = bankTypes.map(() => "?").join(",");
  return cachedAll<TimeSeriesRow>(
    `SELECT
         year || '-' || PRINTF('%02d', month) AS period,
         bank_type_code,
         SUM(total_amount) AS value
       FROM deposits
       WHERE currency = 'TL'
         AND item_name IN (
           'Döviz Tevdiat Hesabı / Katılım Fonları - Yurt İçi Yerleşik',
           'Döviz Tevdiat Hesabı / Katılım Fonları - Yurt Dışı Yerleşik'
         )
         AND bank_type_code IN (${placeholders})
       GROUP BY year, month, bank_type_code
       ORDER BY year, month, bank_type_code`,
    [...bankTypes],
  );
}

/**
 * Deposit maturity composition for sector — long-form rows for stacked area.
 * One row per (period, maturity_bucket).
 */
export async function depositMaturityMix(
  bankType: string = BANK_TYPES.SECTOR,
): Promise<Array<{ period: string } & Record<string, number>>> {
  return cachedAll<{ period: string } & Record<string, number>>(
    `SELECT
         year || '-' || PRINTF('%02d', month) AS period,
         demand, maturity_1m, maturity_1_3m, maturity_3_6m, maturity_6_12m, maturity_over_12m
       FROM deposits
       WHERE item_name = 'TOPLAM MEVDUAT'
         AND currency = 'TL'
         AND bank_type_code = ?
       ORDER BY year, month`,
    [bankType],
  );
}

// ---------------------------------------------------------------------------
// NIM components — income_statement interest buckets + total assets
// ---------------------------------------------------------------------------

/** Bank-type codes the NIM-components chart can aggregate (see NIM_GROUPS in
 * nim-components.ts — "Private" in the BBVA sense is 10008+10010 summed). */
export const NIM_BANK_CODES = [
  "10001", // Sector
  "10003", // Participation
  "10004", // Dev & Inv
  "10008", // Deposit · domestic private
  "10009", // Deposit · state
  "10010", // Deposit · foreign
];

/**
 * Raw inputs for the NIM-components decomposition: cumulative-YTD interest
 * income/expense buckets (income_statement, million TL) and month-end total
 * assets, per (year, month, bank_type_code). Bucket → item_order mapping is
 * documented in nim-components.ts. Expense buckets are stored POSITIVE here;
 * the shaping layer negates them.
 */
export async function nimComponentsRaw(
  bankCodes: string[] = NIM_BANK_CODES,
): Promise<NimComponentRow[]> {
  const placeholders = bankCodes.map(() => "?").join(",");
  // CTE names must NOT shadow the tables they read (D1 "circular reference").
  return cachedAll<NimComponentRow>(
    `WITH inc AS (
         SELECT year, month, bank_type_code,
           SUM(CASE WHEN item_order IN (1,6)        THEN amount_total END) AS cust_loans,
           SUM(CASE WHEN item_order IN (7,8)        THEN amount_total END) AS banks_cb,
           SUM(CASE WHEN item_order IN (9,10,11,12) THEN amount_total END) AS securities,
           SUM(CASE WHEN item_order IN (13,14)      THEN amount_total END) AS other_inc,
           SUM(CASE WHEN item_order = 16            THEN amount_total END) AS dep_exp,
           SUM(CASE WHEN item_order IN (17,18)      THEN amount_total END) AS interbank_exp,
           SUM(CASE WHEN item_order IN (19,20)      THEN amount_total END) AS debt_exp,
           SUM(CASE WHEN item_order IN (21,22)      THEN amount_total END) AS other_exp
         FROM income_statement
         WHERE currency = 'TL'
           AND bank_type_code IN (${placeholders})
         GROUP BY year, month, bank_type_code
       ),
       ast AS (
         SELECT year, month, bank_type_code, amount_total AS assets
         FROM balance_sheet
         WHERE currency = 'TL'
           AND item_name = 'TOPLAM AKTİFLER'
           AND bank_type_code IN (${placeholders})
       )
       SELECT inc.*, ast.assets
       FROM inc
       JOIN ast ON ast.year = inc.year
              AND ast.month = inc.month
              AND ast.bank_type_code = inc.bank_type_code
       ORDER BY inc.year, inc.month, inc.bank_type_code`,
    [...bankCodes, ...bankCodes],
  );
}

// ---------------------------------------------------------------------------
// Sector P&L + the deposit mix (the /profitability engine)
// ---------------------------------------------------------------------------

/**
 * The sector's monthly income statement, by item_order. CUMULATIVE year-to-date
 * — de-cumulate before reading any of it as a month (lib/profitability.ts).
 * item_order is the BDDK statement's own numbering; if it ever shifts, the
 * bridge's reconciliation against item 53 fails loudly and the page says so.
 */
export async function sectorPnl(
  bankType: string = BANK_TYPES.SECTOR,
): Promise<PnlRow[]> {
  return cachedAll<PnlRow>(
    `SELECT year, month,
        SUM(CASE WHEN item_order = 16 THEN amount_total END) AS dep_int,
        SUM(CASE WHEN item_order = 24 THEN amount_total END) AS nii,
        SUM(CASE WHEN item_order = 25 THEN amount_total END) AS prov,
        SUM(CASE WHEN item_order = 34 THEN amount_total END) AS fees,
        SUM(CASE WHEN item_order = 45 THEN amount_total END) AS opex,
        SUM(CASE WHEN item_order = 50 THEN amount_total END) AS other,
        SUM(CASE WHEN item_order = 52 THEN amount_total END) AS tax,
        SUM(CASE WHEN item_order = 53 THEN amount_total END) AS net
       FROM income_statement
      WHERE currency = 'TL' AND bank_type_code = ?
      GROUP BY year, month
      ORDER BY year, month`,
    [bankType],
  );
}

/**
 * The deposit mix and equity behind the engine: demand deposits pay nothing, so
 * the blended cost of the base sits far below the rate actually paid on the time
 * book. Item names are the bulletin's own (the trailing asterisks are BDDK's).
 */
export async function sectorDepositMix(
  bankType: string = BANK_TYPES.SECTOR,
): Promise<BsRow[]> {
  return cachedAll<BsRow>(
    `SELECT year, month,
        SUM(CASE WHEN item_name = 'a) Vadesiz Mevduat'        THEN amount_total END) AS demand,
        SUM(CASE WHEN item_name = 'b) Vadeli Mevduat'         THEN amount_total END) AS time_dep,
        SUM(CASE WHEN item_name = 'Mevduat (Katılım Fonu)***' THEN amount_total END) AS total_dep,
        SUM(CASE WHEN item_name = 'TOPLAM ÖZKAYNAKLAR'        THEN amount_total END) AS equity
       FROM balance_sheet
      WHERE currency = 'TL' AND bank_type_code = ?
      GROUP BY year, month
      ORDER BY year, month`,
    [bankType],
  );
}

// ---------------------------------------------------------------------------
// Consumer-credit segments (Table 4 of monthly bulletin)
// ---------------------------------------------------------------------------

/** Consumer credit mix for stacked area: housing / auto / GPL / retail cards. */
export async function consumerMix(
  bankType: string = BANK_TYPES.SECTOR,
): Promise<Array<{ period: string; housing: number; auto: number; gpl: number; cards: number }>> {
  return cachedAll<{ period: string; housing: number; auto: number; gpl: number; cards: number }>(
    `SELECT
         year || '-' || PRINTF('%02d', month) AS period,
         SUM(CASE WHEN item_name = 'Tüketici Kredileri - Konut'    THEN total_amount END) AS housing,
         SUM(CASE WHEN item_name = 'Tüketici Kredileri - Taşıt'    THEN total_amount END) AS auto,
         SUM(CASE WHEN item_name = 'Tüketici Kredileri - İhtiyaç'  THEN total_amount END) AS gpl,
         SUM(CASE WHEN item_name = 'Bireysel Kredi Kartları (10+11)' THEN total_amount END) AS cards
       FROM loans
       WHERE table_number = 4
         AND currency = 'TL'
         AND bank_type_code = ?
       GROUP BY year, month
       ORDER BY year, month`,
    [bankType],
  );
}

/** YoY of one consumer segment, sector only. */
export async function consumerSegmentYoY(
  itemName: string,
): Promise<TimeSeriesRow[]> {
  return _growthYoYExact(
    "loans",
    "total_amount",
    itemName,
    [BANK_TYPES.SECTOR],
  );
}

/** Consumer-segment NPL composition (stock in million TL, sector). */
export async function consumerNplMix(): Promise<
  Array<{ period: string; housing: number; auto: number; gpl: number; cards: number }>
> {
  return cachedAll<{ period: string; housing: number; auto: number; gpl: number; cards: number }>(
    `SELECT
         year || '-' || PRINTF('%02d', month) AS period,
         SUM(CASE WHEN item_name = 'Takipteki Konut Kredileri'         THEN total_amount END) AS housing,
         SUM(CASE WHEN item_name = 'Takipteki Taşıt Kredileri'         THEN total_amount END) AS auto,
         SUM(CASE WHEN item_name = 'Takipteki İhtiyaç Kredileri'       THEN total_amount END) AS gpl,
         SUM(CASE WHEN item_name = 'Takipteki Bireysel Kredi Kartları' THEN total_amount END) AS cards
       FROM loans
       WHERE table_number = 4
         AND currency = 'TL'
         AND bank_type_code = '10001'
       GROUP BY year, month
       ORDER BY year, month`,
  );
}

/** Per-segment NPL ratio (%) for consumer products, sector only.
 * Numerator: "Takipteki <X>" total_amount
 * Denominator: corresponding performing "Tüketici Kredileri - <X>" (or cards)
 */
export async function consumerNplRatios(): Promise<
  Array<{ period: string; housing: number | null; auto: number | null; gpl: number | null; cards: number | null }>
> {
  return cachedAll<{ period: string; housing: number | null; auto: number | null; gpl: number | null; cards: number | null }>(
    `WITH s AS (
         SELECT year, month, item_name, SUM(total_amount) AS amt
         FROM loans
         WHERE table_number = 4
           AND currency = 'TL'
           AND bank_type_code = '10001'
           AND item_name IN (
             'Takipteki Konut Kredileri',         'Tüketici Kredileri - Konut',
             'Takipteki Taşıt Kredileri',         'Tüketici Kredileri - Taşıt',
             'Takipteki İhtiyaç Kredileri',       'Tüketici Kredileri - İhtiyaç',
             'Takipteki Bireysel Kredi Kartları', 'Bireysel Kredi Kartları (10+11)'
           )
         GROUP BY year, month, item_name
       )
       SELECT
         year || '-' || PRINTF('%02d', month) AS period,
         CASE WHEN MAX(CASE WHEN item_name='Tüketici Kredileri - Konut' THEN amt END) > 0
              THEN MAX(CASE WHEN item_name='Takipteki Konut Kredileri' THEN amt END) * 100.0 /
                   MAX(CASE WHEN item_name='Tüketici Kredileri - Konut' THEN amt END)
              END AS housing,
         CASE WHEN MAX(CASE WHEN item_name='Tüketici Kredileri - Taşıt' THEN amt END) > 0
              THEN MAX(CASE WHEN item_name='Takipteki Taşıt Kredileri' THEN amt END) * 100.0 /
                   MAX(CASE WHEN item_name='Tüketici Kredileri - Taşıt' THEN amt END)
              END AS auto,
         CASE WHEN MAX(CASE WHEN item_name='Tüketici Kredileri - İhtiyaç' THEN amt END) > 0
              THEN MAX(CASE WHEN item_name='Takipteki İhtiyaç Kredileri' THEN amt END) * 100.0 /
                   MAX(CASE WHEN item_name='Tüketici Kredileri - İhtiyaç' THEN amt END)
              END AS gpl,
         CASE WHEN MAX(CASE WHEN item_name='Bireysel Kredi Kartları (10+11)' THEN amt END) > 0
              THEN MAX(CASE WHEN item_name='Takipteki Bireysel Kredi Kartları' THEN amt END) * 100.0 /
                   MAX(CASE WHEN item_name='Bireysel Kredi Kartları (10+11)' THEN amt END)
              END AS cards
       FROM s
       GROUP BY year, month
       ORDER BY year, month`,
  );
}

/** Commercial NPL ratios (SME, Commercial total, Non-SME) from weekly_series.
 * NPL items: 2.0.4 (SME), 2.0.5 (Commercial total)
 * Denominators: 1.0.11 (SME loans), 1.0.12 (Commercial loans)
 * Non-SME = (Commercial NPL − SME NPL) / (Commercial loans − SME loans). */
export async function commercialNplRatios(): Promise<
  Array<{ period: string; sme: number | null; commercial: number | null; non_sme: number | null }>
> {
  return cachedAll<{ period: string; sme: number | null; commercial: number | null; non_sme: number | null }>(
    `WITH s AS (
         SELECT period_date AS period, item_id, value
         FROM weekly_series
         WHERE bank_type_code = '10001' AND currency = 'TOTAL'
           AND item_id IN ('1.0.11', '1.0.12', '2.0.4', '2.0.5')
       )
       SELECT
         period,
         CASE WHEN MAX(CASE WHEN item_id='1.0.11' THEN value END) > 0
              THEN MAX(CASE WHEN item_id='2.0.4' THEN value END) * 100.0 /
                   MAX(CASE WHEN item_id='1.0.11' THEN value END)
              END AS sme,
         CASE WHEN MAX(CASE WHEN item_id='1.0.12' THEN value END) > 0
              THEN MAX(CASE WHEN item_id='2.0.5' THEN value END) * 100.0 /
                   MAX(CASE WHEN item_id='1.0.12' THEN value END)
              END AS commercial,
         CASE WHEN MAX(CASE WHEN item_id='1.0.12' THEN value END) >
                   MAX(CASE WHEN item_id='1.0.11' THEN value END)
              THEN (MAX(CASE WHEN item_id='2.0.5' THEN value END) -
                    MAX(CASE WHEN item_id='2.0.4' THEN value END)) * 100.0 /
                   (MAX(CASE WHEN item_id='1.0.12' THEN value END) -
                    MAX(CASE WHEN item_id='1.0.11' THEN value END))
              END AS non_sme
       FROM s
       GROUP BY period
       ORDER BY period`,
  );
}

// ---------------------------------------------------------------------------
// SME loans (Table 6)
// ---------------------------------------------------------------------------

/** Consumer-segment YoY growth lines (housing/auto/GPL/cards), sector only. */
export async function consumerSegmentYoYAll(): Promise<
  Array<{ period: string; housing: number | null; auto: number | null; gpl: number | null; cards: number | null }>
> {
  return cachedAll<{ period: string; housing: number | null; auto: number | null; gpl: number | null; cards: number | null }>(
    `WITH s AS (
         SELECT year, month, item_name, SUM(total_amount) AS amt
         FROM loans
         WHERE table_number = 4
           AND currency = 'TL'
           AND bank_type_code = '10001'
           AND item_name IN (
             'Tüketici Kredileri - Konut', 'Tüketici Kredileri - Taşıt',
             'Tüketici Kredileri - İhtiyaç', 'Bireysel Kredi Kartları (10+11)'
           )
         GROUP BY year, month, item_name
       ), wide AS (
         SELECT year, month,
           MAX(CASE WHEN item_name='Tüketici Kredileri - Konut'     THEN amt END) AS housing,
           MAX(CASE WHEN item_name='Tüketici Kredileri - Taşıt'     THEN amt END) AS auto,
           MAX(CASE WHEN item_name='Tüketici Kredileri - İhtiyaç'   THEN amt END) AS gpl,
           MAX(CASE WHEN item_name='Bireysel Kredi Kartları (10+11)' THEN amt END) AS cards
         FROM s GROUP BY year, month
       )
       SELECT
         a.year || '-' || PRINTF('%02d', a.month) AS period,
         CASE WHEN b.housing > 0 THEN (a.housing - b.housing) * 100.0 / b.housing END AS housing,
         CASE WHEN b.auto    > 0 THEN (a.auto    - b.auto)    * 100.0 / b.auto    END AS auto,
         CASE WHEN b.gpl     > 0 THEN (a.gpl     - b.gpl)     * 100.0 / b.gpl     END AS gpl,
         CASE WHEN b.cards   > 0 THEN (a.cards   - b.cards)   * 100.0 / b.cards   END AS cards
       FROM wide a
       JOIN wide b ON b.year = a.year - 1 AND b.month = a.month
       ORDER BY a.year, a.month`,
  );
}

/** Credit cards split — Retail Cards vs Corporate Cards level, sector only. */
export async function cardsSplit(): Promise<
  Array<{ period: string; retail: number | null; corporate: number | null }>
> {
  return cachedAll<{ period: string; retail: number | null; corporate: number | null }>(
    `SELECT
         year || '-' || PRINTF('%02d', month) AS period,
         MAX(CASE WHEN item_name='Bireysel Kredi Kartları (10+11)' THEN total_amount END) AS retail,
         MAX(CASE WHEN item_name='Kurumsal Kredi Kartları (28+29)**' THEN total_amount END) AS corporate
       FROM loans
       WHERE table_number = 4
         AND currency = 'TL'
         AND bank_type_code = '10001'
         AND item_name IN ('Bireysel Kredi Kartları (10+11)', 'Kurumsal Kredi Kartları (28+29)**')
       GROUP BY year, month
       ORDER BY year, month`,
  );
}

/** SME breakdown by size — Micro / Small / Medium level, sector only. */
export async function smeBreakdown(): Promise<
  Array<{ period: string; micro: number | null; small: number | null; medium: number | null }>
> {
  return cachedAll<{ period: string; micro: number | null; small: number | null; medium: number | null }>(
    `SELECT
         year || '-' || PRINTF('%02d', month) AS period,
         MAX(CASE WHEN item_name='Mikro İşletmelere Kullandırılan Krediler'           THEN total_amount END) AS micro,
         MAX(CASE WHEN item_name='Küçük İşletmelere Kullandırılan Krediler'          THEN total_amount END) AS small,
         MAX(CASE WHEN item_name='Orta Büyüklükteki İşletmelere Kullandırılan Krediler' THEN total_amount END) AS medium
       FROM loans
       WHERE table_number = 6
         AND currency = 'TL'
         AND bank_type_code = '10001'
       GROUP BY year, month
       ORDER BY year, month`,
  );
}

/** TL loans YoY by bank type. */
export const tlLoansYoY = (bankTypes: string[] = PRIMARY_BANK_TYPES) =>
  _growthYoYExact("loans", "total_tl", "Toplam Krediler", bankTypes);

/** SME total loans by bank type, from Table 6. */
export async function smeLoans(
  bankTypes: string[] = PRIMARY_BANK_TYPES,
): Promise<TimeSeriesRow[]> {
  const placeholders = bankTypes.map(() => "?").join(",");
  return cachedAll<TimeSeriesRow>(
    `SELECT
         year || '-' || PRINTF('%02d', month) AS period,
         bank_type_code,
         total_amount AS value
       FROM loans
       WHERE table_number = 6
         AND item_name = 'Toplam KOBİ Kredileri (2+3+4)'
         AND currency = 'TL'
         AND bank_type_code IN (${placeholders})
       ORDER BY year, month, bank_type_code`,
    [...bankTypes],
  );
}

/** SME YoY growth. */
export async function smeLoansYoY(
  bankTypes: string[] = PRIMARY_BANK_TYPES,
): Promise<TimeSeriesRow[]> {
  return _growthYoYExact("loans", "total_amount", "Toplam KOBİ Kredileri (2+3+4)", bankTypes);
}

// Generic YoY helper that takes a literal item_name string (no SPECS lookup).
async function _growthYoYExact(
  table: "loans" | "deposits" | "balance_sheet",
  amountCol: string,
  itemName: string,
  bankTypes: string[],
): Promise<TimeSeriesRow[]> {
  const placeholders = bankTypes.map(() => "?").join(",");
  return cachedAll<TimeSeriesRow>(
    `WITH s AS (
         SELECT year, month, bank_type_code, ${amountCol} AS amt
         FROM ${table}
         WHERE item_name = ? AND currency = 'TL'
           AND bank_type_code IN (${placeholders})
       )
       SELECT
         a.year || '-' || PRINTF('%02d', a.month) AS period,
         a.bank_type_code,
         CASE WHEN b.amt > 0 THEN ((a.amt - b.amt) * 100.0 / b.amt) ELSE NULL END AS value
       FROM s a
       JOIN s b ON b.bank_type_code = a.bank_type_code
              AND b.year = a.year - 1
              AND b.month = a.month
       ORDER BY a.year, a.month, a.bank_type_code`,
    [itemName, ...bankTypes],
  );
}

// ---------------------------------------------------------------------------
// Latest-value helpers (for KPI cards)
// ---------------------------------------------------------------------------

/**
 * Pull the latest single-period value for a given metric and bank type.
 * Useful for KPI cards that just need the headline number.
 */
export async function latestValue(
  fetcher: (bankTypes?: string[]) => Promise<TimeSeriesRow[]>,
  bankType: string = BANK_TYPES.SECTOR,
): Promise<TimeSeriesRow | null> {
  const rows = await fetcher([bankType]);
  return rows.at(-1) ?? null;
}

// ---------------------------------------------------------------------------
// Derived metrics — computed in SQL (Option 1)
// ---------------------------------------------------------------------------

type GrowthSpec = {
  table: "balance_sheet" | "loans" | "deposits";
  amountColumn: string; // "amount_total" for balance_sheet, "total_amount" for loans/deposits
  itemName: string;
};

const SPECS: Record<string, GrowthSpec> = {
  total_assets: { table: "balance_sheet", amountColumn: "amount_total", itemName: "TOPLAM AKTİFLER" },
  total_loans:  { table: "loans",         amountColumn: "total_amount", itemName: "Toplam Krediler" },
  total_deposits: { table: "deposits",    amountColumn: "total_amount", itemName: "TOPLAM MEVDUAT" },
};

/** Year-over-year % change (vs same month last year). */
async function _growthYoY(spec: GrowthSpec, bankTypes: string[]) {
  const placeholders = bankTypes.map(() => "?").join(",");
  return cachedAll<TimeSeriesRow>(
    `WITH s AS (
         SELECT year, month, bank_type_code, ${spec.amountColumn} AS amt
         FROM ${spec.table}
         WHERE item_name = ? AND currency = 'TL'
           AND bank_type_code IN (${placeholders})
       )
       SELECT
         a.year || '-' || PRINTF('%02d', a.month) AS period,
         a.bank_type_code,
         CASE WHEN b.amt > 0 THEN ((a.amt - b.amt) * 100.0 / b.amt) ELSE NULL END AS value
       FROM s a
       JOIN s b ON b.bank_type_code = a.bank_type_code
              AND b.year = a.year - 1
              AND b.month = a.month
       ORDER BY a.year, a.month, a.bank_type_code`,
    [spec.itemName, ...bankTypes],
  );
}

/** Month-over-month % change. */
async function _growthMoM(spec: GrowthSpec, bankTypes: string[]) {
  const placeholders = bankTypes.map(() => "?").join(",");
  return cachedAll<TimeSeriesRow>(
    `WITH s AS (
         SELECT
           year || '-' || PRINTF('%02d', month) AS period,
           bank_type_code,
           ${spec.amountColumn} AS amt,
           LAG(${spec.amountColumn}) OVER (PARTITION BY bank_type_code ORDER BY year, month) AS prev_amt
         FROM ${spec.table}
         WHERE item_name = ? AND currency = 'TL'
           AND bank_type_code IN (${placeholders})
       )
       SELECT period, bank_type_code,
              CASE WHEN prev_amt > 0 THEN ((amt - prev_amt) * 100.0 / prev_amt) ELSE NULL END AS value
       FROM s
       WHERE prev_amt IS NOT NULL
       ORDER BY period, bank_type_code`,
    [spec.itemName, ...bankTypes],
  );
}

export const totalAssetsYoY = (bankTypes: string[] = PRIMARY_BANK_TYPES) =>
  _growthYoY(SPECS.total_assets, bankTypes);
export const totalAssetsMoM = (bankTypes: string[] = PRIMARY_BANK_TYPES) =>
  _growthMoM(SPECS.total_assets, bankTypes);
export const totalLoansYoY = (bankTypes: string[] = PRIMARY_BANK_TYPES) =>
  _growthYoY(SPECS.total_loans, bankTypes);
export const totalLoansMoM = (bankTypes: string[] = PRIMARY_BANK_TYPES) =>
  _growthMoM(SPECS.total_loans, bankTypes);
export const totalDepositsYoY = (bankTypes: string[] = PRIMARY_BANK_TYPES) =>
  _growthYoY(SPECS.total_deposits, bankTypes);
export const totalDepositsMoM = (bankTypes: string[] = PRIMARY_BANK_TYPES) =>
  _growthMoM(SPECS.total_deposits, bankTypes);

// ---------------------------------------------------------------------------
// Weekly bulletin (weekly_series) — different code semantics than monthly
// ---------------------------------------------------------------------------

/**
 * IMPORTANT: weekly_series uses DIFFERENT semantics for bank_type_code than
 * the monthly tables. The codes are reshuffled:
 *
 *   weekly:   10001=Sector, 10003=Private,    10004=State,
 *             10005=Foreign, 10006=Participation, 10007=Dev&Inv
 *   monthly:  10001=Sector, 10003=Participation, 10004=Dev&Inv,
 *             10005=Private, 10006=State, 10007=Foreign
 */
export const WEEKLY_BANK_TYPES = {
  SECTOR: "10001",
  PRIVATE: "10003",
  STATE: "10004",
  FOREIGN: "10005",
  PARTICIPATION: "10006",
  DEV_INV: "10007",
} as const;

export const WEEKLY_BANK_TYPE_LABELS: Record<string, string> = {
  "10001": "Sector",
  "10003": "Domestic", // weekly 10003 = domestic private deposit banks, vs Foreign
  "10004": "State",
  "10005": "Foreign",
  "10006": "Participation",
  "10007": "Dev & Inv",
};

export interface WeeklyRow {
  period: string;
  bank_type_code: string;
  value: number;
}

/** Get a weekly metric by category + item_id, optionally limited window. */
export async function weeklySeries(
  category: string,
  itemId: string,
  currency: "TL" | "FX" | "TOTAL" = "TOTAL",
  bankTypes: string[] = Object.values(WEEKLY_BANK_TYPES),
  weeksBack = 156,  // ~3 years
): Promise<WeeklyRow[]> {
  const placeholders = bankTypes.map(() => "?").join(",");
  return cachedAll<WeeklyRow>(
    `SELECT
         period_date AS period,
         bank_type_code,
         value
       FROM weekly_series
       WHERE category = ? AND item_id = ? AND currency = ?
         AND bank_type_code IN (${placeholders})
         AND period_date >= date('now', '-' || ? || ' days')
       ORDER BY period_date, bank_type_code`,
    [category, itemId, currency, ...bankTypes, weeksBack * 7],
  );
}

/**
 * Annualized growth over a rolling window (4w/13w/52w).
 * SQL returns the raw series; pairing + annualization happen in TypeScript
 * (D1 sandboxes block POWER()). Pairing is by DATE, not row offset, so a
 * hole in one group's history can't silently stretch the window — see
 * computeWeeklyGrowth in weekly-growth.ts.
 */
export async function weeklyGrowth(
  category: string,
  itemId: string,
  currency: "TL" | "FX" | "TOTAL" = "TOTAL",
  windowWeeks: 4 | 13 | 52 = 13,
  bankTypes: string[] = Object.values(WEEKLY_BANK_TYPES),
  weeksBack = 156,
): Promise<WeeklyRow[]> {
  const placeholders = bankTypes.map(() => "?").join(",");
  // Fetch windowWeeks + 1 extra weeks of history so points near the start of
  // the display window still find their comparison base.
  const rows = await cachedAll<WeeklyGrowthInput>(
    `SELECT period_date AS period, bank_type_code, value
       FROM weekly_series
       WHERE category = ? AND item_id = ? AND currency = ?
         AND bank_type_code IN (${placeholders})
         AND period_date >= date('now', '-' || ? || ' days')
       ORDER BY period_date, bank_type_code`,
    [category, itemId, currency, ...bankTypes, (weeksBack + windowWeeks + 1) * 7],
  );
  const cutoff = new Date(Date.now() - weeksBack * 7 * 86_400_000)
    .toISOString()
    .slice(0, 10);
  return computeWeeklyGrowth(rows, windowWeeks, cutoff);
}

// Thin 52-week (≈ YoY) wrappers so weekly growth plugs into `latestPerBank`,
// which expects a `(bankTypes?) => Promise<TimeSeriesRow[]>` fetcher. Used by
// the "latest by group" bars on /credit and /deposits, now that those pages
// source loans/deposits from the weekly bulletin. WeeklyRow is structurally a
// TimeSeriesRow; passing `bankTypes` through (undefined → weeklyGrowth default)
// keeps the optional-param signature `latestPerBank` requires.
export const weeklyTotalLoansYoY = (bankTypes?: string[]) =>
  weeklyGrowth("krediler", "1.0.1", "TOTAL", 52, bankTypes, 104);

export const weeklyTotalDepositsYoY = (bankTypes?: string[]) =>
  weeklyGrowth("mevduat", "4.0.1", "TOTAL", 52, bankTypes, 104);

// ---------------------------------------------------------------------------
// Liquidity — public-vs-private cuts of the weekly bulletin (BBVA framing)
//
// BBVA's "Banking Sector Outlook" liquidity section splits the system into
// PUBLIC (state banks) vs PRIVATE (private + foreign banks). Folding foreign
// into private reproduces the report's own figures (verified: deposit
// dollarization 35.6% public / 39.8% private vs the report's "~36% / ~40%";
// FC loan/deposit ratio public > private). These codes are weekly_series
// semantics (see WEEKLY_BANK_TYPES) — different from the monthly tables.
// ---------------------------------------------------------------------------

export const LIQ_OWNERSHIP = {
  PUBLIC: ["10004"], // State deposit banks
  PRIVATE: ["10003", "10005"], // Private + Foreign deposit banks
} as const;

export const LIQ_OWNERSHIP_LABELS: Record<string, string> = {
  PUBLIC: "Public",
  PRIVATE: "Private",
};

export const LIQ_DOLLARIZATION_LABELS: Record<string, string> = {
  SECTOR: "Sector",
  PUBLIC: "Public",
  PRIVATE: "Private",
};

// SQL fragment: bucket weekly_series bank_type_code into PUBLIC/PRIVATE.
const OWNERSHIP_BUCKET =
  "CASE WHEN bank_type_code = '10004' THEN 'PUBLIC' ELSE 'PRIVATE' END";

/**
 * Loan/deposit-style ratio (numerator / denominator × 100) of two weekly
 * metrics, bucketed into PUBLIC vs PRIVATE. Numerator and denominator are
 * summed across each group's bank types BEFORE dividing.
 *
 * Drives the TL and FC loan-to-deposit charts (num = loans krediler/1.0.1,
 * den = deposits mevduat/4.0.1).
 */
export async function weeklyOwnershipRatio(
  numCategory: string,
  numItemId: string,
  denCategory: string,
  denItemId: string,
  currency: "TL" | "FX" | "TOTAL" = "TL",
  weeksBack = 156,
): Promise<TimeSeriesRow[]> {
  return cachedAll<TimeSeriesRow>(
    `WITH num AS (
         SELECT period_date, ${OWNERSHIP_BUCKET} AS grp, SUM(value) AS v
         FROM weekly_series
         WHERE category = ? AND item_id = ? AND currency = ?
           AND bank_type_code IN ('10003','10004','10005')
         GROUP BY period_date, grp
       ),
       den AS (
         SELECT period_date, ${OWNERSHIP_BUCKET} AS grp, SUM(value) AS v
         FROM weekly_series
         WHERE category = ? AND item_id = ? AND currency = ?
           AND bank_type_code IN ('10003','10004','10005')
         GROUP BY period_date, grp
       )
       SELECT num.period_date AS period,
              num.grp        AS bank_type_code,
              num.v * 100.0 / den.v AS value
       FROM num JOIN den ON num.period_date = den.period_date AND num.grp = den.grp
       WHERE den.v > 0
         AND num.period_date >= date('now', '-' || ? || ' days')
       ORDER BY period, bank_type_code`,
    [
      numCategory, numItemId, currency,
      denCategory, denItemId, currency,
      weeksBack * 7,
    ],
  );
}

/**
 * Annualized growth of a weekly metric bucketed into PUBLIC vs PRIVATE,
 * summing the group's bank types before computing growth (so the two lines
 * are exactly Public vs Private, not per-bank-type). Annualization exponent
 * (52/window) is applied in TS because D1 blocks POWER().
 */
export async function weeklyGrowthByOwnership(
  category: string,
  itemId: string,
  currency: "TL" | "FX" | "TOTAL" = "TL",
  windowWeeks: 4 | 13 | 52 = 52,
  weeksBack = 156,
): Promise<TimeSeriesRow[]> {
  const results = await cachedAll<{ period: string; bank_type_code: string; value: number; prev_value: number }>(
    `WITH summed AS (
         SELECT period_date, ${OWNERSHIP_BUCKET} AS grp, SUM(value) AS value
         FROM weekly_series
         WHERE category = ? AND item_id = ? AND currency = ?
           AND bank_type_code IN ('10003','10004','10005')
         GROUP BY period_date, grp
       ),
       s AS (
         SELECT period_date, grp, value,
                LAG(value, ?) OVER (PARTITION BY grp ORDER BY period_date) AS prev_value
         FROM summed
       )
       SELECT period_date AS period, grp AS bank_type_code, value, prev_value
       FROM s
       WHERE prev_value IS NOT NULL
         AND period_date >= date('now', '-' || ? || ' days')
       ORDER BY period, bank_type_code`,
    [category, itemId, currency, windowWeeks, weeksBack * 7],
  );

  const exponent = 52 / windowWeeks;
  const out: TimeSeriesRow[] = [];
  for (const r of results) {
    if (r.prev_value > 0) {
      out.push({
        period: r.period,
        bank_type_code: r.bank_type_code,
        value: (Math.pow(r.value / r.prev_value, exponent) - 1) * 100,
      });
    }
  }
  return out;
}

/**
 * Deposit dollarization — FX share of total deposits, FX / (TL + FX) × 100.
 * Returns three series keyed by bank_type_code: SECTOR, PUBLIC, PRIVATE.
 * FX deposits are stored TL-equivalent in weekly_series, which is exactly
 * what the FX-share ratio needs.
 */
export async function weeklyDollarization(
  weeksBack = 156,
): Promise<TimeSeriesRow[]> {
  return cachedAll<TimeSeriesRow>(
    `WITH base AS (
         SELECT period_date,
                CASE bank_type_code
                  WHEN '10001' THEN 'SECTOR'
                  WHEN '10004' THEN 'PUBLIC'
                  ELSE 'PRIVATE'
                END AS grp,
                currency, SUM(value) AS v
         FROM weekly_series
         WHERE category = 'mevduat' AND item_id = '4.0.1'
           AND currency IN ('TL','FX')
           AND bank_type_code IN ('10001','10003','10004','10005')
         GROUP BY period_date, grp, currency
       ),
       piv AS (
         SELECT period_date, grp,
                SUM(CASE WHEN currency = 'FX' THEN v ELSE 0 END) AS fx,
                SUM(CASE WHEN currency = 'TL' THEN v ELSE 0 END) AS tl
         FROM base GROUP BY period_date, grp
       )
       SELECT period_date AS period, grp AS bank_type_code,
              fx * 100.0 / (fx + tl) AS value
       FROM piv
       WHERE (fx + tl) > 0
         AND period_date >= date('now', '-' || ? || ' days')
       ORDER BY period, bank_type_code`,
    [weeksBack * 7],
  );
}

// ---------------------------------------------------------------------------
// EVDS — TCMB macro / rate series
// ---------------------------------------------------------------------------

export interface EvdsRow {
  period_date: string;
  value: number;
}

/**
 * Fetch one EVDS series by code, optionally limited to last N years.
 */
export async function evdsSeries(
  code: string,
  yearsBack = 5,
): Promise<EvdsRow[]> {
  return cachedAll<EvdsRow>(
    `SELECT period_date, value
       FROM evds_series
       WHERE code = ?
         AND period_date >= date('now', '-' || ? || ' years')
         AND value IS NOT NULL
       ORDER BY period_date`,
    [code, yearsBack],
  );
}

/**
 * Fetch multiple EVDS series in parallel, return as a map keyed by code.
 */
export async function evdsMulti(
  codes: string[],
  yearsBack = 5,
): Promise<Record<string, EvdsRow[]>> {
  const results = await Promise.all(codes.map((c) => evdsSeries(c, yearsBack)));
  const out: Record<string, EvdsRow[]> = {};
  codes.forEach((c, i) => {
    out[c] = results[i];
  });
  return out;
}

// ---------------------------------------------------------------------------
// "Latest" snapshot per bank type — for bar charts comparing groups
// ---------------------------------------------------------------------------

/**
 * For a time-series helper, pick the latest value per bank type.
 * Useful for "X by bank type" bar charts.
 */
export async function latestPerBank(
  fetcher: (bankTypes?: string[]) => Promise<TimeSeriesRow[]>,
  bankTypes: string[] = PRIMARY_BANK_TYPES.filter((c) => c !== BANK_TYPES.SECTOR),
): Promise<{ bank_type_code: string; period: string; value: number }[]> {
  const rows = await fetcher(bankTypes);
  const byBank = new Map<string, { bank_type_code: string; period: string; value: number }>();
  for (const r of rows) {
    if (r.value == null) continue;
    const cur = byBank.get(r.bank_type_code);
    if (!cur || r.period > cur.period) {
      byBank.set(r.bank_type_code, { bank_type_code: r.bank_type_code, period: r.period, value: r.value });
    }
  }
  return Array.from(byBank.values());
}
