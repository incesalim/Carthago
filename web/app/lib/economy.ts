/**
 * Economy tab data layer — the macro backdrop, derived from raw `evds_series`
 * rows: y/y and m/m growth from index levels, 12-month rolling sums for flows
 * (current account, budget), %-of-GDP ratios against rolling-4Q nominal GDP, the
 * ex-ante real policy rate (funding rate deflated by the 12-month-ahead market
 * inflation expectation), the policy→deposit→loan transmission chain, and the
 * reserve buffer (via lib/reserves.ts, which /liquidity shares).
 *
 * Out of scope (no data source here): CDS / OIS / sovereign curves (Bloomberg),
 * the GDP nowcast and FCI composite (BBVA-proprietary). (BIST index levels were
 * carried here until 2026-08-01, sourced from Yahoo; that feed was removed
 * because its terms forbid redistribution, and nothing replaces it until a
 * licensed source exists.)
 *
 * Non-resident portfolio positioning WAS listed here as "not ingested". It has
 * been in D1 since the bie_mknethar lane landed and `lib/portfolio-flows.ts`
 * reads it — the note was stale, and a stale scope note is how a page stays
 * primitive: nobody adds what the file says isn't there.
 */
import { evdsMulti } from "@/app/lib/metrics";
import { RESERVE_CODES, reserveBuffer, importCoverMonths } from "@/app/lib/reserves";
import {
  monthlyAverage,
  pctChange,
  rolling4qGdp,
  rollingSum,
  scaled,
  spread,
  stepAt,
  sumByDate,
  trailingMean,
  exAnteReal,
  pctOfGdp,
  type EconomyData,
  type Point,
} from "@/app/lib/economy-calc";

// The pure half — transforms and the forecast scorecard — lives in
// economy-calc.ts so it can be unit-tested without a D1 import in the module
// graph. Re-exported here so every existing importer is unchanged.
export * from "@/app/lib/economy-calc";

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
  "TP.PKAUO.S01.E.U",    // CPI expectation, 12m ahead (market participants)
  "TP.HANEBEK.HAN14A",   // CPI expectation, 12m ahead (households)
  "TP.APIFON4",          // CBRT effective cost of funding, daily
  "TP.PY.P02.1H",        // policy rate (1-week repo), daily
  // the transmission chain (weekly bank pricing)
  "TP.TRY.MT06",  // TL deposit rate, total
  "TP.KTF17",     // commercial loan rate
  "TP.KTFTUK",    // consumer loan rate
  "TP.KTF12",     // housing loan rate
  // lira & external
  "TP.DK.USD.A",         // USD/TRY, daily
  "TP.DK.EUR.A",         // EUR/TRY, daily
  "TP.RK.T1.Y",          // REER (CPI based, 2003=100)
  "TP.ODANA6.Q01",       // current account (USD m)
  "TP.ODANA6.Q31",       // net errors & omissions (USD m)
  "TP.HARICCARIACIK.K8", // CA ex gold (USD m)
  "TP.HARICCARIACIK.K10",// CA ex gold & energy (USD m)
  "TP.ITHALATBEC.9999",  // customs imports, total (USD k) — reserve import cover
  // residents' FC (the dollarization the households choose)
  "TP.HPBITABLO4.4", // households USD deposits (USD m)
  "TP.HPBITABLO4.5", // households EUR deposits (USD eq, USD m)
  "TP.HPBITABLO4.7", // households precious metals (USD m)
  // fiscal (TL thousand, monthly)
  "TP.KB.GEN34", // primary balance
  "TP.KB.GEN35", // budget balance
  "TP.KB.GEN39", // cash balance
  // the reserve buffer (gross / net / net-excl-swaps)
  ...RESERVE_CODES,
] as const;

// ---------------------------------------------------------------------------
// Loader — one round trip, chart-ready output
// ---------------------------------------------------------------------------


export async function getEconomyData(yearsBack = 8): Promise<EconomyData> {
  const s = await evdsMulti([...CODES], yearsBack);
  const g = (code: string) => s[code] ?? [];

  const fundingMonthly = monthlyAverage(g("TP.APIFON4"));
  const exp12mRows = g("TP.PKAUO.S01.E.U");
  const exp12m = scaled(exp12mRows, 1);
  const hhExp12m = scaled(g("TP.HANEBEK.HAN14A"), 1);
  const depositRate = monthlyAverage(g("TP.TRY.MT06"));
  const loanCommercial = monthlyAverage(g("TP.KTF17"));

  // Current account as % of GDP, both sides in USD. The CA is already USD;
  // nominal GDP is TL, so the 4Q window is converted at the average USD/TRY over
  // the SAME window rather than the spot rate — a spot conversion of a year of
  // TL output would price four quarters at one day's lira.
  const usdMonthly = monthlyAverage(g("TP.DK.USD.A"));
  const gdp4q = rolling4qGdp(g("TP.GSYIH26.HY.CF"));
  const ca12m = rollingSum(g("TP.ODANA6.Q01"), 12, 1 / 1000);
  const caPctGdp: Point[] = [];
  for (const c of ca12m) {
    const gdpTl = stepAt(gdp4q, c.period_date);
    const fx = trailingMean(usdMonthly, c.period_date, 12);
    if (!gdpTl || !fx) continue;
    // GDP is TL thousand → ÷1e6 for TL bn ÷ fx = USD bn.
    const gdpUsdBn = gdpTl / 1e6 / fx;
    caPctGdp.push({ period_date: c.period_date, value: 100 * (c.value / gdpUsdBn) });
  }

  const imports12m = rollingSum(g("TP.ITHALATBEC.9999"), 12, 1 / 1e6); // USD k → bn
  const reserves = reserveBuffer(s);

  // The scorecard scores against the latest year the CPI series actually has,
  // never a year typed into the file — a hardcoded forecast year silently starts
  // scoring a year we hold no data for the January it rolls over.
  const cpiYoY = pctChange(g("TP.TUKFIY2025.GENEL"), 12);
  const scoreYear = cpiYoY.at(-1)?.period_date.slice(0, 4) ?? "";

  return {
    gdpGrowth: pctChange(g("TP.GSYIH26.HY.ZH"), 4),
    ipGrowth: pctChange(g("TP.TSANAYMT2021.Y1"), 12),
    unemployment: scaled(g("TP.TIG08"), 1),
    participation: scaled(g("TP.TIG06"), 1),
    employedMn: scaled(g("TP.TIG03"), 1 / 1000),
    cpiYoY,
    cpiMoM: pctChange(g("TP.TUKFIY2025.GENEL"), 1),
    expCurrentYearEnd: scaled(g("TP.PKAUO.S01.D.U"), 1),
    expNextYearEnd: scaled(g("TP.PKAUO.S01.I.U"), 1),
    exp12m,
    hhExp12m,
    expGap: spread(hhExp12m, exp12m),
    fundingMonthly,
    policyRate: monthlyAverage(g("TP.PY.P02.1H")),
    realRate: exAnteReal(fundingMonthly, exp12mRows),
    depositRate,
    realDepositRate: exAnteReal(depositRate, exp12mRows),
    loanCommercial,
    loanConsumer: monthlyAverage(g("TP.KTFTUK")),
    loanHousing: monthlyAverage(g("TP.KTF12")),
    loanDepositSpread: spread(loanCommercial, depositRate),
    usdtry: scaled(g("TP.DK.USD.A"), 1),
    eurtry: scaled(g("TP.DK.EUR.A"), 1),
    reer: scaled(g("TP.RK.T1.Y"), 1),
    ca12m,
    caExGold12m: rollingSum(g("TP.HARICCARIACIK.K8"), 12, 1 / 1000),
    caExGoldEnergy12m: rollingSum(g("TP.HARICCARIACIK.K10"), 12, 1 / 1000),
    neo12m: rollingSum(g("TP.ODANA6.Q31"), 12, 1 / 1000),
    caPctGdp,
    budgetPctGdp: pctOfGdp(g("TP.KB.GEN35"), g("TP.GSYIH26.HY.CF")),
    primaryPctGdp: pctOfGdp(g("TP.KB.GEN34"), g("TP.GSYIH26.HY.CF")),
    cashPctGdp: pctOfGdp(g("TP.KB.GEN39"), g("TP.GSYIH26.HY.CF")),
    // GDP arrives as TL thousand, so ÷1e9 lands in ₺ trillion.
    nominalGdp4q: gdp4q.map((p) => ({ period_date: p.period_date, value: p.value / 1e9 })),
    reserves,
    importCover: importCoverMonths(reserves.latest?.gross ?? null, imports12m.at(-1)?.value ?? null),
    imports12m,
    householdFx: sumByDate([g("TP.HPBITABLO4.4"), g("TP.HPBITABLO4.5")], 1 / 1000),
    householdGold: scaled(g("TP.HPBITABLO4.7"), 1 / 1000),
    scoreYear,
  };
}


