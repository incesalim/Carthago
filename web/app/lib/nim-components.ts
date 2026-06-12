/**
 * NIM components — decomposes net interest margin into the eight interest
 * income / expense buckets of the BDDK monthly income statement, expressed as
 * % of average total assets (annualized). Replicates the Garanti BBVA Research
 * "NIM components of private banks" chart (verified to 0.1pp on every bucket).
 *
 * Pure TypeScript (no DB imports) so both the server page and the client
 * chart components can share the types and series metadata.
 *
 * Source rows are cumulative-YTD income amounts (million TL) + month-end
 * total assets, per (year, month, bank_type_code) — see nimComponentsRaw()
 * in metrics.ts. Expense items are stored POSITIVE in the bulletin and are
 * negated here; the chart stacks them below zero.
 *
 * Income-statement item_order mapping (currency='TL', amount_total):
 *   cust_loans    = 1 (Kredilerden Alınan Faizler) + 6 (Takipteki Alacaklar)
 *                   — items 2–5 are consumer sub-lines of 1, NOT added
 *   banks_cb      = 7 (Bankalardan) + 8 (Para Piyasası)
 *   securities    = 9 + 10 + 11 (GUD/itfa menkul değerler) + 12 (ters repo)
 *   other_inc     = 13 (finansal kiralama) + 14 (diğer)
 *   dep_exp       = 16 (Mevduata Verilen Faizler / katılım fonları kar payı)
 *   interbank_exp = 17 (Bankalara) + 18 (Para Piyasası)
 *   debt_exp      = 19 (ihraç edilen menkul kıymetler) + 20 (repo)
 *   other_exp     = 21 (finansal kiralama) + 22 (diğer)
 *   (15/23/24 are subtotals — excluded.)
 *
 * BBVA's bucket quirks, matched deliberately: reverse-repo income sits in
 * "fixed-income securities" and repo funding expense in "debt issued".
 */

export type NimKey =
  | "cust_loans"
  | "banks_cb"
  | "securities"
  | "other_inc"
  | "dep_exp"
  | "interbank_exp"
  | "debt_exp"
  | "other_exp";

/** Raw row returned by nimComponentsRaw() — YTD sums per period and group. */
export interface NimComponentRow {
  year: number;
  month: number;
  bank_type_code: string;
  cust_loans: number | null;
  banks_cb: number | null;
  securities: number | null;
  other_inc: number | null;
  dep_exp: number | null;
  interbank_exp: number | null;
  debt_exp: number | null;
  other_exp: number | null;
  assets: number | null;
}

/** Stack order: incomes bottom-up from the biggest bucket, then expenses. */
export const NIM_SERIES: ReadonlyArray<{
  key: NimKey;
  label: string;
  sign: 1 | -1;
}> = [
  { key: "cust_loans", label: "Customer loans", sign: 1 },
  { key: "banks_cb", label: "Banks & money market", sign: 1 },
  { key: "securities", label: "Fixed-income securities", sign: 1 },
  { key: "other_inc", label: "Other interest income", sign: 1 },
  { key: "dep_exp", label: "Customer deposits", sign: -1 },
  { key: "interbank_exp", label: "Interbank & money market", sign: -1 },
  { key: "debt_exp", label: "Debt issued & repo", sign: -1 },
  { key: "other_exp", label: "Other interest expense", sign: -1 },
];

/**
 * Selectable bank groups. "Private" (default) is the BBVA definition:
 * domestic-private + foreign DEPOSIT banks (10008+10010) — NOT ownership code
 * 10005, which spans all bank types and misses the chart by 0.3–0.6pp.
 * {private, state} ∪ participation ∪ dev&inv partitions the sector exactly;
 * the two sub-cuts of Private are offered for drill-down.
 */
export const NIM_GROUPS: ReadonlyArray<{
  key: string;
  label: string;
  codes: string[];
}> = [
  { key: "private", label: "Private", codes: ["10008", "10010"] },
  { key: "domestic", label: "Private · Domestic", codes: ["10008"] },
  { key: "foreign", label: "Private · Foreign", codes: ["10010"] },
  { key: "state", label: "State", codes: ["10009"] },
  { key: "participation", label: "Participation", codes: ["10003"] },
  { key: "devinv", label: "Dev & Inv", codes: ["10004"] },
  { key: "sector", label: "Sector", codes: ["10001"] },
];

export const DEFAULT_NIM_GROUP = "private";

/** One bar/point: signed component values (expenses negative) + their sum. */
export type NimBarPoint = { x: string; net: number } & Record<NimKey, number>;

export interface NimGroupDataset {
  /** Full-year bars 2021… plus a trailing "YYYY ann." YTD-annualized bar. */
  annual: NimBarPoint[];
  /** Monthly trailing-12-month series (first valid point 2021-01). */
  ttm: NimBarPoint[];
}

const KEYS = NIM_SERIES.map((s) => s.key);
const SIGN: Record<NimKey, 1 | -1> = Object.fromEntries(
  NIM_SERIES.map((s) => [s.key, s.sign]),
) as Record<NimKey, 1 | -1>;

type Sums = Record<NimKey, number> & { assets: number };

/**
 * Shape raw rows into per-group annual + monthly-TTM stacked-bar datasets.
 * For composite groups a period is emitted only when EVERY member code has a
 * row, so 10008+10010 never silently degrades to a single code.
 */
export function buildNimDatasets(
  rows: NimComponentRow[],
): Record<string, NimGroupDataset> {
  // (code, year, month) → row, plus the latest period seen anywhere.
  const byCode = new Map<string, NimComponentRow>();
  let maxYear = 0;
  let maxMonth = 0;
  for (const r of rows) {
    byCode.set(`${r.bank_type_code}|${r.year}-${r.month}`, r);
    if (r.year > maxYear || (r.year === maxYear && r.month > maxMonth)) {
      maxYear = r.year;
      maxMonth = r.month;
    }
  }

  const out: Record<string, NimGroupDataset> = {};

  for (const group of NIM_GROUPS) {
    // Sum members per period; null components count as 0 only when the row
    // itself exists (BDDK publishes every item line, some legitimately 0).
    const sums = new Map<string, Sums>(); // "year-month" → summed values
    for (let y = 2020; y <= maxYear; y++) {
      for (let m = 1; m <= 12; m++) {
        const members = group.codes.map((c) => byCode.get(`${c}|${y}-${m}`));
        if (members.some((r) => r === undefined || r.assets == null)) continue;
        const s = { assets: 0 } as Sums;
        for (const k of KEYS) s[k] = 0;
        for (const r of members as NimComponentRow[]) {
          s.assets += r.assets ?? 0;
          for (const k of KEYS) s[k] += r[k] ?? 0;
        }
        sums.set(`${y}-${m}`, s);
      }
    }

    const get = (y: number, m: number) => sums.get(`${y}-${m}`);

    /** Average assets over month-ends (fromY,fromM) … (toY,toM) inclusive. */
    const avgAssets = (fromY: number, fromM: number, toY: number, toM: number) => {
      let total = 0;
      let n = 0;
      let y = fromY;
      let m = fromM;
      while (y < toY || (y === toY && m <= toM)) {
        const s = get(y, m);
        if (!s) return null;
        total += s.assets;
        n++;
        m++;
        if (m > 12) { m = 1; y++; }
      }
      return n > 0 ? total / n : null;
    };

    const point = (
      x: string,
      income: Record<NimKey, number>,
      annualizeBy: number,
      avg: number,
    ): NimBarPoint => {
      const p = { x, net: 0 } as NimBarPoint;
      for (const k of KEYS) {
        const v = (SIGN[k] * income[k] * annualizeBy * 100) / avg;
        p[k] = v;
        p.net += v;
      }
      return p;
    };

    // --- Annual bars: Dec YTD over the 13-point average Dec(Y−1)…Dec(Y).
    // 2021 is the first feasible year (needs Dec-2020 assets).
    const annual: NimBarPoint[] = [];
    for (let y = 2021; y <= maxYear; y++) {
      const dec = get(y, 12);
      const avg = avgAssets(y - 1, 12, y, 12);
      if (!dec || avg == null) continue;
      annual.push(point(String(y), dec, 1, avg));
    }
    // Trailing partial year, annualized ×12/m over the m+1-point average —
    // actuals, NOT a forecast (BBVA's "F" bar is theirs alone).
    if (maxMonth < 12) {
      const cur = get(maxYear, maxMonth);
      const avg = avgAssets(maxYear - 1, 12, maxYear, maxMonth);
      if (cur && avg != null) {
        annual.push(point(`${maxYear} ann.`, cur, 12 / maxMonth, avg));
      }
    }

    // --- Monthly TTM: YTD(y,m) + FY(y−1) − YTD(y−1,m), over the 13-month
    // trailing average of assets ending (y,m).
    const ttm: NimBarPoint[] = [];
    for (let y = 2021; y <= maxYear; y++) {
      for (let m = 1; m <= 12; m++) {
        if (y === maxYear && m > maxMonth) break;
        const cur = get(y, m);
        const prevFy = get(y - 1, 12);
        const prevYtd = get(y - 1, m);
        const avg = avgAssets(y - 1, m, y, m); // 13 month-ends incl. both ends
        if (!cur || !prevFy || !prevYtd || avg == null) continue;
        const income = {} as Record<NimKey, number>;
        for (const k of KEYS) income[k] = cur[k] + prevFy[k] - prevYtd[k];
        ttm.push(point(`${y}-${String(m).padStart(2, "0")}`, income, 1, avg));
      }
    }

    out[group.key] = { annual, ttm };
  }

  return out;
}
