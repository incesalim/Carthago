/**
 * Non-resident securities-flows data layer — the dataset behind the widely
 * cited weekly "foreign investors net bought/sold X" chart.
 *
 * Source: TCMB "Yurt Dışı Yerleşikler Menkul Kıymet İstatistikleri" (EVDS
 * datagroup bie_mknethar, weekly Friday, USD million). We carry four series:
 *   M7 — net equity transactions (weekly flow; net buy +, net sell −)
 *   M8 — net GDDS (government domestic debt securities / DİBS) transactions
 *   M1 — equity holdings (stock)
 *   M2 — GDDS holdings (stock)
 *
 * Net-transaction series are already the WEEKLY net flow — no de-cumulation
 * needed. Verified against the press chart (M7 2026-06-12 = −117.8 ≙ "sold
 * $118m equities"). Distinct from — and more timely than — the monthly BoP
 * portfolio line (bop.ts Şekil 5), which is net-liabilities-incurred basis.
 */
import { evdsMulti, type EvdsRow } from "@/app/lib/metrics";
import { type Point } from "@/app/lib/economy";
import { type BarRow } from "@/app/lib/bop";

const BN = 1 / 1000; // USD million → USD bn

const C = {
  netEquity: "TP.MKNETHAR.M7",
  netGdds: "TP.MKNETHAR.M8",
  stockEquity: "TP.MKNETHAR.M1",
  stockGdds: "TP.MKNETHAR.M2",
} as const;

const CODES = Object.values(C);

const WEEKS = 110; // ~2 years of weekly bars (matches the source chart's span)

export interface PortfolioFlowsData {
  asOfLabel: string; // "12 Jun 2026"
  netEquityLatest: number | null; // USD m, last week
  netGddsLatest: number | null; // USD m, last week
  equityHoldings: number | null; // USD bn, latest
  /** Weekly signed bars: { x: "YYYY-MM-DD", equity, bonds } (USD m). */
  flows: BarRow[];
  /** Holdings line (USD bn), keyed by label. */
  holdings: Record<string, Point[]>;
}

const MONTHS_EN = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

/** "2026-06-12" → "12 Jun 2026". */
function dayLabel(d: string): string {
  return `${Number(d.slice(8, 10))} ${MONTHS_EN[Number(d.slice(5, 7)) - 1]} ${d.slice(0, 4)}`;
}

export async function getPortfolioFlowsData(yearsBack = 6): Promise<PortfolioFlowsData> {
  const s = await evdsMulti([...CODES], yearsBack);
  const g = (code: string) => s[code] ?? [];

  const eq = g(C.netEquity);
  const gd = g(C.netGdds);
  const stEq = g(C.stockEquity);
  const stGd = g(C.stockGdds);

  // Weekly signed bars (equity + bonds), last WEEKS Fridays.
  const eqMap = new Map(eq.map((r) => [r.period_date, r.value]));
  const gdMap = new Map(gd.map((r) => [r.period_date, r.value]));
  const dates = Array.from(
    new Set([...eq, ...gd].map((r) => r.period_date)),
  ).sort();
  const window = dates.slice(-WEEKS);
  const flows: BarRow[] = window.map((d) => {
    const row: BarRow = { x: d };
    const e = eqMap.get(d);
    if (e !== undefined) row.equity = e;
    const b = gdMap.get(d);
    if (b !== undefined) row.bonds = b;
    return row;
  });

  const toBn = (rows: EvdsRow[]): Point[] =>
    rows.map((r) => ({ period_date: r.period_date, value: r.value * BN }));

  const latest = eq.at(-1)?.period_date ?? gd.at(-1)?.period_date ?? "";

  return {
    asOfLabel: latest ? dayLabel(latest) : "",
    netEquityLatest: eq.at(-1)?.value ?? null,
    netGddsLatest: gd.at(-1)?.value ?? null,
    equityHoldings: stEq.at(-1) ? stEq.at(-1)!.value * BN : null,
    flows,
    holdings: {
      "Equity": toBn(stEq),
      "Govt bonds (DİBS)": toBn(stGd),
    },
  };
}
