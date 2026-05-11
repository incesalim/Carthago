/**
 * Metrics layer — Option 1 (SQL helpers in TypeScript).
 *
 * Each function returns the structured result of a D1 query. Server
 * Components call these directly. Mirrors the Python `metrics_ext.py`
 * surface where possible.
 *
 * BDDK bank-type taxonomy (column `bank_type_code`):
 *   10001 = Sector total
 *   10003 = Private deposit banks (Özel)
 *   10004 = State deposit banks (Kamu)
 *   10005 = Foreign deposit banks (Yabancı)
 *   10006 = Participation banks (Katılım)
 *   10007 = Development & investment banks (Kalkınma & Yatırım)
 */
import { getDB } from "./db";

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

// Bank groups that aren't subsets of each other — useful for sector breakdown.
// (Sector = Private + State + Foreign + Participation + Dev_Inv).
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
  "10005": "Private",
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
  const db = await getDB();
  const placeholders = bankTypes.map(() => "?").join(",");
  const valueExpr = annualize
    ? "ratio_value * 12.0 / month"
    : "ratio_value";
  const { results } = await db
    .prepare(
      `SELECT
         year || '-' || PRINTF('%02d', month) AS period,
         bank_type_code,
         ${valueExpr} AS value
       FROM financial_ratios
       WHERE table_number = ?
         AND item_name = ?
         AND bank_type_code IN (${placeholders})
       ORDER BY year, month, bank_type_code`,
    )
    .bind(tableNumber, itemName, ...bankTypes)
    .all<TimeSeriesRow>();
  return results;
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

// ---------------------------------------------------------------------------
// Balance-sheet direct queries
// ---------------------------------------------------------------------------

async function getBalanceItem(
  itemName: string,
  bankTypes: string[] = PRIMARY_BANK_TYPES,
  currency: "TL" | "USD" = "TL",
): Promise<TimeSeriesRow[]> {
  const db = await getDB();
  const placeholders = bankTypes.map(() => "?").join(",");
  const { results } = await db
    .prepare(
      `SELECT
         year || '-' || PRINTF('%02d', month) AS period,
         bank_type_code,
         amount_total AS value
       FROM balance_sheet
       WHERE item_name = ?
         AND currency = ?
         AND bank_type_code IN (${placeholders})
       ORDER BY year, month, bank_type_code`,
    )
    .bind(itemName, currency, ...bankTypes)
    .all<TimeSeriesRow>();
  return results;
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
  const db = await getDB();
  const placeholders = bankTypes.map(() => "?").join(",");
  const { results } = await db
    .prepare(
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
    )
    .bind(...bankTypes)
    .all<TimeSeriesRow>();
  return results;
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
  const db = await getDB();
  const placeholders = bankTypes.map(() => "?").join(",");
  const { results } = await db
    .prepare(
      `SELECT
         year || '-' || PRINTF('%02d', month) AS period,
         bank_type_code,
         ${column} AS value
       FROM loans
       WHERE item_name = ?
         AND currency = 'TL'
         AND bank_type_code IN (${placeholders})
       ORDER BY year, month, bank_type_code`,
    )
    .bind(itemName, ...bankTypes)
    .all<TimeSeriesRow>();
  return results;
}

async function getDepositColumn(
  itemName: string,
  column: "total_amount" | "demand" |
    "maturity_1m" | "maturity_1_3m" | "maturity_3_6m" | "maturity_6_12m" | "maturity_over_12m",
  bankTypes: string[] = PRIMARY_BANK_TYPES,
): Promise<TimeSeriesRow[]> {
  const db = await getDB();
  const placeholders = bankTypes.map(() => "?").join(",");
  const { results } = await db
    .prepare(
      `SELECT
         year || '-' || PRINTF('%02d', month) AS period,
         bank_type_code,
         ${column} AS value
       FROM deposits
       WHERE item_name = ?
         AND currency = 'TL'
         AND bank_type_code IN (${placeholders})
       ORDER BY year, month, bank_type_code`,
    )
    .bind(itemName, ...bankTypes)
    .all<TimeSeriesRow>();
  return results;
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

/**
 * Deposit maturity composition for sector — long-form rows for stacked area.
 * One row per (period, maturity_bucket).
 */
export async function depositMaturityMix(
  bankType: string = BANK_TYPES.SECTOR,
): Promise<Array<{ period: string } & Record<string, number>>> {
  const db = await getDB();
  const { results } = await db
    .prepare(
      `SELECT
         year || '-' || PRINTF('%02d', month) AS period,
         demand, maturity_1m, maturity_1_3m, maturity_3_6m, maturity_6_12m, maturity_over_12m
       FROM deposits
       WHERE item_name = 'TOPLAM MEVDUAT'
         AND currency = 'TL'
         AND bank_type_code = ?
       ORDER BY year, month`,
    )
    .bind(bankType)
    .all<{ period: string; demand: number; maturity_1m: number;
            maturity_1_3m: number; maturity_3_6m: number;
            maturity_6_12m: number; maturity_over_12m: number }>();
  return results;
}

// ---------------------------------------------------------------------------
// Consumer-credit segments (Table 4 of monthly bulletin)
// ---------------------------------------------------------------------------

/** Consumer credit mix for stacked area: housing / auto / GPL / retail cards. */
export async function consumerMix(
  bankType: string = BANK_TYPES.SECTOR,
): Promise<Array<{ period: string; housing: number; auto: number; gpl: number; cards: number }>> {
  const db = await getDB();
  const { results } = await db
    .prepare(
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
    )
    .bind(bankType)
    .all<{ period: string; housing: number; auto: number; gpl: number; cards: number }>();
  return results;
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

// ---------------------------------------------------------------------------
// SME loans (Table 6)
// ---------------------------------------------------------------------------

/** SME total loans by bank type, from Table 6. */
export async function smeLoans(
  bankTypes: string[] = PRIMARY_BANK_TYPES,
): Promise<TimeSeriesRow[]> {
  const db = await getDB();
  const placeholders = bankTypes.map(() => "?").join(",");
  const { results } = await db
    .prepare(
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
    )
    .bind(...bankTypes)
    .all<TimeSeriesRow>();
  return results;
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
  const db = await getDB();
  const placeholders = bankTypes.map(() => "?").join(",");
  const { results } = await db
    .prepare(
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
    )
    .bind(itemName, ...bankTypes)
    .all<TimeSeriesRow>();
  return results;
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
  const db = await getDB();
  const placeholders = bankTypes.map(() => "?").join(",");
  const { results } = await db
    .prepare(
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
    )
    .bind(spec.itemName, ...bankTypes)
    .all<TimeSeriesRow>();
  return results;
}

/** Month-over-month % change. */
async function _growthMoM(spec: GrowthSpec, bankTypes: string[]) {
  const db = await getDB();
  const placeholders = bankTypes.map(() => "?").join(",");
  const { results } = await db
    .prepare(
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
    )
    .bind(spec.itemName, ...bankTypes)
    .all<TimeSeriesRow>();
  return results;
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
  "10003": "Private",
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
  const db = await getDB();
  const placeholders = bankTypes.map(() => "?").join(",");
  const { results } = await db
    .prepare(
      `SELECT
         period_date AS period,
         bank_type_code,
         value
       FROM weekly_series
       WHERE category = ? AND item_id = ? AND currency = ?
         AND bank_type_code IN (${placeholders})
         AND period_date >= date('now', '-' || ? || ' days')
       ORDER BY period_date, bank_type_code`,
    )
    .bind(category, itemId, currency, ...bankTypes, weeksBack * 7)
    .all<WeeklyRow>();
  return results;
}

/**
 * Annualized growth over a rolling window (4w/13w/52w).
 * SQL returns (value, prev_value); annualization (52/N exponent) computed
 * in TypeScript because D1 sandboxes block POWER().
 */
export async function weeklyGrowth(
  category: string,
  itemId: string,
  currency: "TL" | "FX" | "TOTAL" = "TOTAL",
  windowWeeks: 4 | 13 | 52 = 13,
  bankTypes: string[] = Object.values(WEEKLY_BANK_TYPES),
  weeksBack = 156,
): Promise<WeeklyRow[]> {
  const db = await getDB();
  const placeholders = bankTypes.map(() => "?").join(",");
  const { results } = await db
    .prepare(
      `WITH s AS (
         SELECT
           period_date, bank_type_code, value,
           LAG(value, ?) OVER (PARTITION BY bank_type_code ORDER BY period_date) AS prev_value
         FROM weekly_series
         WHERE category = ? AND item_id = ? AND currency = ?
           AND bank_type_code IN (${placeholders})
       )
       SELECT period_date AS period, bank_type_code, value, prev_value
       FROM s
       WHERE prev_value IS NOT NULL
         AND period_date >= date('now', '-' || ? || ' days')
       ORDER BY period_date, bank_type_code`,
    )
    .bind(windowWeeks, category, itemId, currency, ...bankTypes, weeksBack * 7)
    .all<{ period: string; bank_type_code: string; value: number; prev_value: number }>();

  type Row = { period: string; bank_type_code: string; value: number; prev_value: number };
  const rows = results as Row[];
  const exponent = 52 / windowWeeks;
  const out: WeeklyRow[] = [];
  for (const r of rows) {
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
  const db = await getDB();
  const { results } = await db
    .prepare(
      `SELECT period_date, value
       FROM evds_series
       WHERE code = ?
         AND period_date >= date('now', '-' || ? || ' years')
         AND value IS NOT NULL
       ORDER BY period_date`,
    )
    .bind(code, yearsBack)
    .all<EvdsRow>();
  return results;
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
