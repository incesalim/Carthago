/**
 * Economy tab data layer — adapts the macro section of the BBVA (Garanti
 * BBVA Research) "Türkiye Economic Outlook" into our EVDS data.
 *
 * Everything here derives chart-ready series from raw `evds_series` rows:
 * y/y and m/m growth from index levels, 12-month rolling sums for flows
 * (current account, budget), %-of-GDP ratios against rolling-4Q nominal
 * GDP, and the ex-ante real policy rate (funding rate deflated by the
 * 12-month-ahead market inflation expectation).
 *
 * Out of scope (no data source here): CDS / OIS / sovereign curves
 * (Bloomberg), the GDP nowcast and FCI (BBVA-proprietary), foreigners'
 * positioning (CBRT securities stats not ingested), and BBVA's scenario
 * sensitivities. (BIST index levels now come from bist.ts / Yahoo — see the
 * "Equity Markets" section on /economy.)
 */
import { evdsMulti, type EvdsRow } from "@/app/lib/metrics";

export interface Point {
  period_date: string;
  value: number;
}

// EVDS codes used by the tab (all already in D1 via the daily cron).
const CODES = [
  // growth & labor
  "TP.GSYIH26.HY.ZH",   // GDP chain-linked volume index, quarterly
  "TP.GSYIH26.HY.CF",   // GDP current prices (TL thousand), quarterly
  "TP.TSANAYMT2021.Y1", // industrial production, SA, 2021=100
  "TP.TIG03",           // employed (thousand persons, SA)
  "TP.TIG06",           // labour force participation rate (SA %)
  "TP.TIG08",           // unemployment rate (SA %)
  // inflation & policy
  "TP.TUKFIY2025.GENEL", // CPI (2025=100)
  "TP.PKAUO.S01.D.U",    // CPI expectation, current year-end
  "TP.PKAUO.S01.I.U",    // CPI expectation, next year-end
  "TP.PKAUO.S01.E.U",    // CPI expectation, 12m ahead
  "TP.APIFON4",          // CBRT effective cost of funding, daily
  // lira & external
  "TP.DK.USD.A",         // USD/TRY, daily
  "TP.RK.T1.Y",          // REER (CPI based, 2003=100)
  "TP.ODANA6.Q01",       // current account (USD m)
  "TP.ODANA6.Q31",       // net errors & omissions (USD m)
  "TP.HARICCARIACIK.K8", // CA ex gold (USD m)
  "TP.HARICCARIACIK.K10",// CA ex gold & energy (USD m)
  // fiscal (TL thousand, monthly)
  "TP.KB.GEN34", // primary balance
  "TP.KB.GEN35", // budget balance
  "TP.KB.GEN39", // cash balance
] as const;

// ---------------------------------------------------------------------------
// Pure transforms
// ---------------------------------------------------------------------------

/** % change vs `lag` observations earlier (12 = y/y monthly, 4 = y/y quarterly). */
export function pctChange(rows: EvdsRow[], lag: number): Point[] {
  const out: Point[] = [];
  for (let i = lag; i < rows.length; i++) {
    const prev = rows[i - lag].value;
    if (prev === 0) continue;
    out.push({
      period_date: rows[i].period_date,
      value: 100 * (rows[i].value / prev - 1),
    });
  }
  return out;
}

/** Rolling sum over the trailing `window` observations, scaled. */
export function rollingSum(rows: EvdsRow[], window: number, scale = 1): Point[] {
  const out: Point[] = [];
  let acc = 0;
  for (let i = 0; i < rows.length; i++) {
    acc += rows[i].value;
    if (i >= window) acc -= rows[i - window].value;
    if (i >= window - 1) {
      out.push({ period_date: rows[i].period_date, value: acc * scale });
    }
  }
  return out;
}

/** Collapse a daily series to monthly averages (dated at month start). */
export function monthlyAverage(rows: EvdsRow[]): Point[] {
  const acc = new Map<string, { sum: number; n: number }>();
  for (const r of rows) {
    const month = `${r.period_date.slice(0, 7)}-01`;
    const cur = acc.get(month) ?? { sum: 0, n: 0 };
    cur.sum += r.value;
    cur.n += 1;
    acc.set(month, cur);
  }
  return Array.from(acc.entries())
    .sort((a, b) => a[0].localeCompare(b[0]))
    .map(([period_date, { sum, n }]) => ({ period_date, value: sum / n }));
}

/** Simple value scaling (unit conversions). */
export function scaled(rows: EvdsRow[], scale: number): Point[] {
  return rows.map((r) => ({ period_date: r.period_date, value: r.value * scale }));
}

/**
 * Ex-ante real rate: nominal monthly rate deflated by the 12m-ahead
 * inflation expectation, compounded — ((1+i)/(1+πᵉ) − 1) × 100.
 */
export function exAnteReal(nominal: Point[], expectation: EvdsRow[]): Point[] {
  const exp = new Map(expectation.map((r) => [r.period_date, r.value]));
  const out: Point[] = [];
  for (const p of nominal) {
    const e = exp.get(p.period_date);
    if (e === undefined) continue;
    out.push({
      period_date: p.period_date,
      value: 100 * ((1 + p.value / 100) / (1 + e / 100) - 1),
    });
  }
  return out;
}

/**
 * 12-month rolling fiscal balance as % of rolling-4-quarter nominal GDP.
 * Both sides are in TL thousand, so units cancel. Each month is matched
 * with the most recent completed 4-quarter GDP window at or before it —
 * the same convention BBVA charts use for "% of GDP" monthly fiscal lines.
 */
export function pctOfGdp(monthlyFlow: EvdsRow[], nominalGdpQ: EvdsRow[]): Point[] {
  const gdp4q: Point[] = [];
  for (let i = 3; i < nominalGdpQ.length; i++) {
    gdp4q.push({
      period_date: nominalGdpQ[i].period_date,
      value:
        nominalGdpQ[i].value + nominalGdpQ[i - 1].value +
        nominalGdpQ[i - 2].value + nominalGdpQ[i - 3].value,
    });
  }
  const flow12 = rollingSum(monthlyFlow, 12);
  const out: Point[] = [];
  for (const f of flow12) {
    // latest 4Q GDP window dated at or before this month
    let g: number | undefined;
    for (let i = gdp4q.length - 1; i >= 0; i--) {
      if (gdp4q[i].period_date <= f.period_date) {
        g = gdp4q[i].value;
        break;
      }
    }
    if (!g) continue;
    out.push({ period_date: f.period_date, value: 100 * (f.value / g) });
  }
  return out;
}

// ---------------------------------------------------------------------------
// Loader — one round trip, chart-ready output
// ---------------------------------------------------------------------------

export interface EconomyData {
  gdpGrowth: Point[];          // y/y %, quarterly
  ipGrowth: Point[];           // y/y %, monthly (SA index)
  unemployment: Point[];       // SA %
  participation: Point[];      // SA %
  employedMn: Point[];         // million persons, SA
  cpiYoY: Point[];             // y/y %
  cpiMoM: Point[];             // m/m %
  expCurrentYearEnd: Point[];  // survey, %
  expNextYearEnd: Point[];     // survey, %
  exp12m: Point[];             // survey, %
  fundingMonthly: Point[];     // CBRT effective funding cost, monthly avg %
  realRate: Point[];           // ex-ante real funding rate, %
  usdtry: Point[];             // daily level
  reer: Point[];               // monthly index
  ca12m: Point[];              // 12m rolling, USD bn
  caExGold12m: Point[];        // 12m rolling, USD bn
  caExGoldEnergy12m: Point[];  // 12m rolling, USD bn
  neo12m: Point[];             // net errors & omissions, 12m rolling, USD bn
  budgetPctGdp: Point[];       // 12m rolling, % GDP
  primaryPctGdp: Point[];      // 12m rolling, % GDP
  cashPctGdp: Point[];         // 12m rolling, % GDP
}

export async function getEconomyData(yearsBack = 8): Promise<EconomyData> {
  const s = await evdsMulti([...CODES], yearsBack);
  const fundingMonthly = monthlyAverage(s["TP.APIFON4"] ?? []);

  return {
    gdpGrowth: pctChange(s["TP.GSYIH26.HY.ZH"] ?? [], 4),
    ipGrowth: pctChange(s["TP.TSANAYMT2021.Y1"] ?? [], 12),
    unemployment: scaled(s["TP.TIG08"] ?? [], 1),
    participation: scaled(s["TP.TIG06"] ?? [], 1),
    employedMn: scaled(s["TP.TIG03"] ?? [], 1 / 1000),
    cpiYoY: pctChange(s["TP.TUKFIY2025.GENEL"] ?? [], 12),
    cpiMoM: pctChange(s["TP.TUKFIY2025.GENEL"] ?? [], 1),
    expCurrentYearEnd: scaled(s["TP.PKAUO.S01.D.U"] ?? [], 1),
    expNextYearEnd: scaled(s["TP.PKAUO.S01.I.U"] ?? [], 1),
    exp12m: scaled(s["TP.PKAUO.S01.E.U"] ?? [], 1),
    fundingMonthly,
    realRate: exAnteReal(fundingMonthly, s["TP.PKAUO.S01.E.U"] ?? []),
    usdtry: scaled(s["TP.DK.USD.A"] ?? [], 1),
    reer: scaled(s["TP.RK.T1.Y"] ?? [], 1),
    ca12m: rollingSum(s["TP.ODANA6.Q01"] ?? [], 12, 1 / 1000),
    caExGold12m: rollingSum(s["TP.HARICCARIACIK.K8"] ?? [], 12, 1 / 1000),
    caExGoldEnergy12m: rollingSum(s["TP.HARICCARIACIK.K10"] ?? [], 12, 1 / 1000),
    neo12m: rollingSum(s["TP.ODANA6.Q31"] ?? [], 12, 1 / 1000),
    budgetPctGdp: pctOfGdp(s["TP.KB.GEN35"] ?? [], s["TP.GSYIH26.HY.CF"] ?? []),
    primaryPctGdp: pctOfGdp(s["TP.KB.GEN34"] ?? [], s["TP.GSYIH26.HY.CF"] ?? []),
    cashPctGdp: pctOfGdp(s["TP.KB.GEN39"] ?? [], s["TP.GSYIH26.HY.CF"] ?? []),
  };
}

// ---------------------------------------------------------------------------
// BBVA baseline scenario (static) — Garanti BBVA Research, "Türkiye
// Economic Outlook", March 2026, p. 42. Forecast column = 2026.
// ---------------------------------------------------------------------------

export const BBVA_BASELINE = {
  asOf: "March 2026",
  source: "Garanti BBVA Research — Türkiye Economic Outlook 1Q26",
  years: ["2023", "2024", "2025", "2026 (f)"],
  rows: [
    { label: "GDP growth (avg)", values: ["5.0%", "3.3%", "3.6%", "4.0%"] },
    { label: "Unemployment rate (avg)", values: ["9.4%", "8.7%", "8.4%", "9.0%"] },
    { label: "Inflation (avg)", values: ["53.9%", "58.5%", "34.9%", "28.0%"] },
    { label: "Inflation (eop)", values: ["64.8%", "44.4%", "30.9%", "25.0%"] },
    { label: "CBRT cost of funding (avg)", values: ["20.5%", "49.6%", "43.6%", "35.8%"] },
    { label: "CBRT cost of funding (eop)", values: ["42.5%", "47.5%", "38.0%", "32.0%"] },
    { label: "USD/TRY (avg)", values: ["23.7", "32.8", "39.5", "47.3"] },
    { label: "USD/TRY (eop)", values: ["29.4", "35.3", "42.8", "52.0"] },
    { label: "EUR/TRY (avg)", values: ["25.7", "35.5", "44.7", "55.7"] },
    { label: "EUR/TRY (eop)", values: ["32.6", "36.7", "50.3", "62.2"] },
    { label: "Current account (% GDP)", values: ["-3.6%", "-1.0%", "-1.9%", "-2.4%"] },
    { label: "CG primary balance (% GDP)", values: ["-2.6%", "-1.9%", "0.4%", "0.1%"] },
    { label: "CG budget balance (% GDP)", values: ["-5.1%", "-4.7%", "-2.9%", "-3.5%"] },
  ],
} as const;
