/**
 * GET /api/app/v1/overview — the home screen.
 *
 * This is the phone's version of the Desk brief on `/`: vitals, movers, the
 * macro transmission, rule-based flags, capital standings, what lands next.
 *
 * Every derivation is IMPORTED, not reimplemented. `realRate`, `cpiFromIndex`,
 * `streak`, `overviewInsights` and the ratio queries are the exact functions the
 * website renders from, so the app and the site cannot drift into quoting
 * different numbers for the same metric — which is the failure mode that makes
 * a second client worse than no second client. If a figure needs new maths, it
 * gets added to app/lib and both surfaces read it.
 *
 * What is NOT carried over: the prose. The website's transmission notes are JSX
 * with inline links; the client renders its own copy from the same operands, so
 * this hands over `{ key, value, unit }` and the ingredients, not sentences.
 */
import { bankSummaries } from "@/app/lib/audit";
import { perBankCapital } from "@/app/lib/audit-ratios";
import { aheadSlots } from "@/app/lib/ahead-data";
import { BANK_NAMES, BANK_COUNT } from "@/app/lib/bank_names";
import {
  cpiFromIndex,
  lastVal,
  monthLabel,
  streak,
  valAgo,
  windowExtremes,
} from "@/app/lib/desk";
import { overviewInsights } from "@/app/lib/insights";
import { LDR_PUBLISHED } from "@/app/lib/ldr";
import { getMarketTicker } from "@/app/lib/market-ticker";
import {
  BANK_TYPES,
  evdsSeries,
  ratioCar,
  ratioLdr,
  ratioNim,
  ratioNpl,
  ratioRoa,
  ratioRoe,
  totalAssets,
  totalAssetsYoY,
  totalDepositsYoY,
  totalLoansYoY,
  type TimeSeriesRow,
} from "@/app/lib/metrics";
import { realRate } from "@/app/lib/real-terms";
import {
  appApiDisabled,
  disabledResponse,
  jsonResponse,
  wireSeries,
} from "../_shared";

export { OPTIONS } from "../_shared";
export const dynamic = "force-dynamic";

/** 12-month change in percentage points, or null if either end is missing. */
function change12(s: TimeSeriesRow[]): number | null {
  const now = lastVal(s);
  const ago = valAgo(s, 12);
  return now != null && ago != null ? now - ago : null;
}

export async function GET() {
  if (await appApiDisabled()) return disabledResponse();

  const sector = [BANK_TYPES.SECTOR];

  const [
    car, npl, nim, ldr, roe, roa,
    assets, assetsYoY, loansYoY, depositsYoY,
    league, ticker, cpiRaw, fundingRaw, banks, ahead,
  ] = await Promise.all([
    ratioCar(sector),
    ratioNpl(sector),
    ratioNim(sector),
    ratioLdr(sector),
    ratioRoe(sector),
    ratioRoa(sector),
    totalAssets(sector),
    totalAssetsYoY(sector),
    totalLoansYoY(sector),
    totalDepositsYoY(sector),
    perBankCapital(),
    // The tape is a nice-to-have; a market-data hiccup must not blank the whole
    // home screen, which is what an unhandled reject here would do.
    getMarketTicker().catch(() => []),
    evdsSeries("TP.TUKFIY2025.GENEL", 10),
    evdsSeries("TP.APIFON4", 1),
    bankSummaries().catch(() => []),
    aheadSlots(),
  ]);

  // ---- the computed backdrop ------------------------------------------------
  const cpi = cpiFromIndex(
    (cpiRaw as { period_date: string; value: number | null }[]).filter(
      (r): r is { period_date: string; value: number } => r.value != null,
    ),
  );
  const cpiAvgNow = lastVal(cpi.avg12);
  const cpiYoYNow = lastVal(cpi.yoy);
  const funding =
    (fundingRaw as { period_date: string; value: number | null }[])
      .filter((r) => r.value != null)
      .at(-1)?.value ?? null;

  const carNow = lastVal(car);
  const nplNow = lastVal(npl);
  const nimNow = lastVal(nim);
  const ldrNow = lastVal(ldr);
  const roeNow = lastVal(roe);
  const roaNow = lastVal(roa);
  const assetsYoYNow = lastVal(assetsYoY);
  const loansYoYNow = lastVal(loansYoY);

  // Fisher, not subtraction. At a ~32% CPI the g−π shortcut is ~1.8pp adrift,
  // and the website deflates ROE by the 12m AVERAGE (earned across the year)
  // but loan growth by the SPOT y/y (a y/y rate needs a y/y deflator). Both
  // bases are carried in the payload so the client can print which it used.
  const roeReal = realRate(roeNow, cpiAvgNow);
  const creditReal = realRate(loansYoYNow, cpiYoYNow);

  const buffer = carNow != null ? carNow - 12 : null;
  const nplStreak = streak(npl, "up");
  const carSlip = streak(car, "down");
  const carDrift12 = change12(car);
  const nimLow = windowExtremes(nim, 24)?.min ?? null;
  const roePeak = windowExtremes(roe, 13);

  // ---- vitals ---------------------------------------------------------------
  const vitals = [
    { key: "car", label: "Capital adequacy", value: carNow, unit: "%", decimals: 1,
      series: wireSeries(car), change12: change12(car), good: "up" },
    { key: "npl", label: "NPL ratio", value: nplNow, unit: "%", decimals: 2,
      series: wireSeries(npl), change12: change12(npl), good: "down" },
    { key: "nim", label: "Net int. margin", value: nimNow, unit: "%", decimals: 2,
      series: wireSeries(nim), change12: change12(nim), good: "up" },
    { key: "ldr", label: LDR_PUBLISHED.label, value: ldrNow, unit: "%", decimals: 1,
      series: wireSeries(ldr), change12: change12(ldr), good: "neutral" },
    { key: "roe", label: "ROE, ann.", value: roeNow, unit: "%", decimals: 1,
      series: wireSeries(roe), change12: change12(roe), good: "up" },
    { key: "roa", label: "ROA, ann.", value: roaNow, unit: "%", decimals: 2,
      series: wireSeries(roa), change12: change12(roa), good: "up" },
  ];

  // ---- movers (last month → this month) -------------------------------------
  const movers = [
    { key: "roe", label: "ROE, ann.", prev: roe.at(-2)?.value ?? null, curr: roeNow,
      decimals: 1, good: "up",
      note: roePeak && roeNow != null && roePeak.max - roeNow > 1
        ? `cooling from ${roePeak.max.toFixed(1)}% ${monthLabel(roePeak.maxPeriod, false)} peak`
        : null },
    { key: "car", label: "Capital adequacy", prev: car.at(-2)?.value ?? null, curr: carNow,
      decimals: 1, good: "up",
      note: carSlip >= 3 ? `${carSlip} straight monthly slips` : null },
    { key: "npl", label: "NPL ratio", prev: npl.at(-2)?.value ?? null, curr: nplNow,
      decimals: 2, good: "down",
      note: nplStreak >= 2 ? `${nplStreak} consecutive rises` : null },
    { key: "nim", label: "Net interest margin", prev: nim.at(-2)?.value ?? null, curr: nimNow,
      decimals: 2, good: "up", note: null },
    { key: "ldr", label: LDR_PUBLISHED.label, prev: ldr.at(-2)?.value ?? null, curr: ldrNow,
      decimals: 1, good: "neutral", note: null },
    { key: "assets", label: "Assets, y/y", prev: assetsYoY.at(-2)?.value ?? null,
      curr: assetsYoYNow, decimals: 1, good: "neutral",
      note: (() => {
        const real = realRate(assetsYoYNow, cpiYoYNow);
        return real != null && Math.abs(real) < 5 ? "≈ flat in real terms" : null;
      })() },
  ];

  // ---- transmission: the macro backdrop, computed into bank P&L -------------
  const usdtry = (ticker ?? []).find((t) => t.label.toUpperCase().includes("USD"));
  const transmission = [
    cpiAvgNow != null && {
      key: "cpi", label: "CPI, 12m-avg", value: cpiAvgNow, unit: "%", decimals: 1,
      effect: { metric: "roe", nominal: roeNow, real: roeReal, deflator: cpiAvgNow,
                deflatorBasis: "12m-avg CPI", href: "/profitability" },
    },
    funding != null && {
      key: "funding", label: "TCMB funding cost", value: funding, unit: "%", decimals: 1,
      effect: { metric: "nim", nominal: nimNow, low24m: nimLow, href: "/profitability" },
    },
    creditReal != null && {
      key: "credit", label: "Credit, real", value: creditReal, unit: "%", decimals: 1,
      effect: { metric: "loans_yoy", nominal: loansYoYNow, real: creditReal,
                deflator: cpiYoYNow, deflatorBasis: "y/y CPI", href: "/credit" },
    },
    usdtry && {
      key: "usdtry", label: "USD/TRY", value: usdtry.value, unit: null, decimals: 2,
      effect: { metric: "fx_deposit_share", href: "/deposits" },
    },
  ].filter(Boolean);

  // ---- flags: the rule is part of the payload -------------------------------
  // The website prints the rule under each flag (DESIGN.md — automation
  // honesty). The app does too, so the rule travels with the flag rather than
  // being duplicated as a client-side string that can fall out of sync.
  const flags = [
    { code: "real-roe", active: roeReal != null && roeReal < 0,
      rule: "(1+roe)/(1+cpi_12m_avg) − 1 < 0",
      operands: { roe: roeNow, cpi: cpiAvgNow, real: roeReal } },
    { code: "npl-streak", active: nplStreak >= 6,
      rule: "consecutive_rise(npl) ≥ 6m",
      operands: { streak: nplStreak, from: valAgo(npl, nplStreak), to: nplNow } },
    { code: "car-drift", active: carDrift12 != null && carDrift12 < -0.5,
      rule: "Δcar_12m < −0.5pp",
      operands: { buffer, drift12m: carDrift12 } },
    { code: "funding-stretch", active: ldrNow != null && ldrNow > LDR_PUBLISHED.line,
      rule: LDR_PUBLISHED.rule,
      operands: { ldr: ldrNow, line: LDR_PUBLISHED.line } },
  ];

  // ---- capital standings ----------------------------------------------------
  const ranked = league.rows.filter((r) => r.car != null);
  const named = (t: string) => BANK_NAMES[t] ?? t;
  const standings = {
    period: league.period,
    best: ranked.slice(0, 3).map((r, i) => ({
      rank: i + 1, ticker: r.bank_ticker, name: named(r.bank_ticker), car: r.car,
    })),
    thinnest: ranked.slice(-3).reverse().map((r, i) => ({
      rank: i + 1, ticker: r.bank_ticker, name: named(r.bank_ticker), car: r.car,
    })),
  };

  const pulse = overviewInsights({
    assetsYoY, loansYoY, depositsYoY, npl, car, ldr, roe,
  });

  return jsonResponse({
    record: {
      period: npl.at(-1)?.period ?? null,
      label: monthLabel(npl.at(-1)?.period),
      vs: monthLabel(npl.at(-2)?.period, false),
    },
    coverage: { banks: banks.length || BANK_COUNT },
    levels: {
      // ⚠️ UNIT TRAP. `totalAssets()` reads the BDDK monthly bulletin, which is
      // denominated in MILLION TL — while every `bank_audit_*` amount this API
      // also serves (the banks index, stages, free provision) is in THOUSAND
      // TL. Handing the client both under one field name printed the sector at
      // ₺52.7 bn instead of ₺52.7 trn: a clean 1000×, and a plausible-looking
      // number, which is the kind that survives review.
      //
      // Normalised to thousand TL — the canonical unit across this API — so the
      // client has exactly one scale to know about. `units` below states it, so
      // it is checkable rather than conventional.
      totalAssets:
        assets.at(-1)?.value != null ? (assets.at(-1)!.value as number) * 1000 : null,
      assetsYoY: assetsYoYNow,
      loansYoY: loansYoYNow,
      depositsYoY: lastVal(depositsYoY),
    },
    units: {
      /** Every ₺ amount in this payload. Matches the bank_audit_* convention. */
      amounts: "thousand TL",
      /** Every ratio and growth rate. Percentage POINTS, not fractions. */
      rates: "percent",
    },
    tape: (ticker ?? []).map((t) => ({
      label: t.label, value: t.value, changePct: t.changePct,
    })),
    vitals,
    movers,
    transmission,
    flags,
    standings,
    pulse,
    ahead: Object.entries(ahead).map(([kind, slot]) => ({
      kind, when: slot.when, date: slot.date, rule: slot.rule, record: slot.record ?? null,
    })),
  });
}
