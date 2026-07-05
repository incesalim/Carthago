/**
 * Presentation data — assembles the deck's content by reusing the dashboard's
 * OWN metric functions (metrics.ts) + the deterministic reads (reads.ts), so the
 * KPI tiles and trend charts carry the exact same numbers the site plots. No
 * metric is re-derived here; this module only fetches series and picks the last
 * value / chart points. Consumed by app/api/presentation/route.ts.
 */
import type { DeckChart, DeckData, DeckSection, DeckVital } from "./presentation-deck";
import { computeReads } from "./reads";
import {
  BANK_TYPES,
  WEEKLY_BANK_TYPES,
  ratioCar,
  ratioLdr,
  ratioNim,
  ratioNpl,
  ratioRoe,
  totalAssetsYoY,
  totalDepositsYoY,
  totalLoansYoY,
  weeklyGrowth,
} from "./metrics";
import { fxNopToCapital } from "./market-risk";

const S = [BANK_TYPES.SECTOR];
const WS = [WEEKLY_BANK_TYPES.SECTOR];

type Row = { period: string; value: number | null };
type Point = { period: string; value: number };

/** Non-null, sorted-ascending chart points from a metric series. */
function pts(rows: Row[]): Point[] {
  return rows
    .filter((r): r is Point => r.value != null)
    .map((r) => ({ period: r.period, value: r.value }))
    .sort((a, b) => a.period.localeCompare(b.period));
}

function lastVal(p: Point[]): number | null {
  return p.length ? p[p.length - 1].value : null;
}

/** A chart only if it has enough points to draw a line. */
function chart(label: string, unit: string, p: Point[]): DeckChart | undefined {
  return p.length >= 3 ? { label, unit, points: p } : undefined;
}

export async function presentationData(): Promise<DeckData> {
  const [reads, assetsYoY, loansYoY, depositsYoY, nim, creditWk, depositWk, npl, car, roe, ldr, nop] =
    await Promise.all([
      computeReads(),
      totalAssetsYoY(S),
      totalLoansYoY(S),
      totalDepositsYoY(S),
      ratioNim(S),
      weeklyGrowth("krediler", "1.0.1", "TOTAL", 52, WS, 104),
      weeklyGrowth("mevduat", "4.0.1", "TOTAL", 52, WS, 104),
      ratioNpl(S),
      ratioCar(S),
      ratioRoe(S),
      ratioLdr(S),
      fxNopToCapital().catch(() => [] as Row[]),
    ]);

  const p = {
    creditWk: pts(creditWk),
    depositWk: pts(depositWk),
    npl: pts(npl),
    car: pts(car),
    roe: pts(roe),
    ldr: pts(ldr),
    nop: pts(nop),
    assetsYoY: pts(assetsYoY),
    loansYoY: pts(loansYoY),
    depositsYoY: pts(depositsYoY),
    nim: pts(nim),
  };

  const charts: Record<string, DeckChart | undefined> = {
    credit: chart("Loan growth · y/y %", "%", p.creditWk),
    deposits: chart("Deposit growth · y/y %", "%", p.depositWk),
    "asset-quality": chart("NPL ratio · %", "%", p.npl),
    capital: chart("Capital adequacy · %", "%", p.car),
    profitability: chart("Return on equity · %", "%", p.roe),
    liquidity: chart("Loan-to-deposit · %", "%", p.ldr),
    "market-risk": chart("FX net open position · % of capital", "%", p.nop),
  };

  const sections: DeckSection[] = reads.map((r) => ({
    tab: r.tab,
    headline: r.takeaway.headline,
    items: r.takeaway.items.map((i) => i.text),
    chart: charts[r.tab],
  }));

  const vitals: DeckVital[] = [
    { label: "Assets · y/y", value: lastVal(p.assetsYoY), unit: "%", decimals: 1 },
    { label: "Loans · y/y", value: lastVal(p.loansYoY), unit: "%", decimals: 1 },
    { label: "Deposits · y/y", value: lastVal(p.depositsYoY), unit: "%", decimals: 1 },
    { label: "NPL ratio", value: lastVal(p.npl), unit: "%", decimals: 2 },
    { label: "Capital adequacy", value: lastVal(p.car), unit: "%", decimals: 1 },
    { label: "Net interest margin", value: lastVal(p.nim), unit: "%", decimals: 2 },
    { label: "Return on equity", value: lastVal(p.roe), unit: "%", decimals: 1 },
    { label: "Loan-to-deposit", value: lastVal(p.ldr), unit: "%", decimals: 1 },
  ];

  const asOf =
    reads.find((r) => r.tab === "overview")?.takeaway.asOf ??
    (p.npl.length ? p.npl[p.npl.length - 1].period : "");

  return { asOf, sections, vitals };
}
