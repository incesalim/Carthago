/**
 * Balance-of-Payments data layer — reproduces the Albaraka "Ödemeler Dengesi"
 * monthly report (10 figures + summary table) from TCMB EVDS series.
 *
 * Every figure traces to the BPM6 analytic/detailed presentation
 * (TP.ODANA6.*, TP.ODEAYRSUNUM6.*) plus the gold/energy sub-balances
 * (TP.HARICCARIACIK.*). All raw series are monthly, USD million; charts
 * titled "Yıllıklandırılmış" use a trailing-12-month rolling sum, and every
 * value is divided by 1,000 for USD bn. Codes + derivations were verified
 * against the report's Apr-2026 summary table to the rounding.
 *
 * Derivations (no single EVDS series):
 *   ex-energy CA      = TP.HARICCARIACIK.K9 (direct) ≡ Q01 − energy
 *   FDI "other"       = Q108 − Q113  (FDI liab. incurred − real estate)
 *   net foreign inv.  = Q102 + Q114 + Q136  (FDI + portfolio + other, net)
 *   reserves − errors = Q204 − Q31  → the Şekil 10 financing residual
 *   BoP identity:  current account ≡ net foreign inv. + (reserves − errors)
 */
import { evdsMulti, type EvdsRow } from "@/app/lib/metrics";
import { rollingSum, type Point } from "@/app/lib/economy";

const BN = 1 / 1000; // USD million → USD bn

// ---- EVDS codes (all monthly, already in D1 via the daily cron) -----------
const C = {
  ca: "TP.ODANA6.Q01",
  goods: "TP.ODANA6.Q04",
  neo: "TP.ODANA6.Q31",
  core: "TP.HARICCARIACIK.K10", // CA ex gold & energy
  gold: "TP.HARICCARIACIK.K4",
  energy: "TP.HARICCARIACIK.K7",
  exEnergy: "TP.HARICCARIACIK.K9", // CA ex energy
  services: "TP.ODEAYRSUNUM6.Q20",
  travel: "TP.ODEAYRSUNUM6.Q41",
  fdiNet: "TP.ODEAYRSUNUM6.Q102",
  fdiLiab: "TP.ODEAYRSUNUM6.Q108", // FDI inflow (net liab. incurred)
  fdiRealEstate: "TP.ODEAYRSUNUM6.Q113",
  portNet: "TP.ODEAYRSUNUM6.Q114",
  portLiab: "TP.ODEAYRSUNUM6.Q119", // portfolio inflow (net liab. incurred)
  portEquity: "TP.ODEAYRSUNUM6.Q212",
  portDebt: "TP.ODEAYRSUNUM6.Q123",
  otherNet: "TP.ODEAYRSUNUM6.Q136",
  loans: "TP.ODEAYRSUNUM6.Q157", // loans inflow, total
  loansBanks: "TP.ODEAYRSUNUM6.Q166",
  loansGov: "TP.ODEAYRSUNUM6.Q171",
  loansOther: "TP.ODEAYRSUNUM6.Q179",
  tradeCredits: "TP.ODEAYRSUNUM6.Q188",
  deposAssets: "TP.ODEAYRSUNUM6.Q138", // currency & deposits, net asset acq.
  deposLiab: "TP.ODEAYRSUNUM6.Q143", // currency & deposits, net liab. incurred
  reserves: "TP.ODEAYRSUNUM6.Q204",
} as const;

const CODES = Object.values(C);

// ---------------------------------------------------------------------------
// Pure helpers
// ---------------------------------------------------------------------------

/** "2026-04-01" → "04/26". */
function monthLabel(d: string): string {
  return `${d.slice(5, 7)}/${d.slice(2, 4)}`;
}

/** Element-wise op over aligned monthly series (dates present in every input). */
function combine(series: EvdsRow[][], fn: (vals: number[]) => number): EvdsRow[] {
  const maps = series.map((s) => new Map(s.map((r) => [r.period_date, r.value])));
  const base = series[0] ?? [];
  const out: EvdsRow[] = [];
  for (const r of base) {
    if (maps.every((m) => m.has(r.period_date))) {
      out.push({
        period_date: r.period_date,
        value: fn(maps.map((m) => m.get(r.period_date)!)),
      });
    }
  }
  return out;
}

/** Trailing-12-month rolling sum, scaled to USD bn. */
const roll12 = (rows: EvdsRow[]): Point[] => rollingSum(rows, 12, BN);

/** Raw monthly values scaled to USD bn. */
const monthly = (rows: EvdsRow[]): Point[] =>
  rows.map((r) => ({ period_date: r.period_date, value: r.value * BN }));

export type BarRow = Record<string, number | string>;

/** Pivot N columns of monthly Points into the last `months` wide rows keyed by x. */
function barRows(cols: { key: string; rows: Point[] }[], months: number): BarRow[] {
  const dates = Array.from(
    new Set(cols.flatMap((c) => c.rows.map((r) => r.period_date))),
  ).sort();
  const window = dates.slice(-months);
  const maps = cols.map((c) => ({
    key: c.key,
    m: new Map(c.rows.map((r) => [r.period_date, r.value])),
  }));
  return window.map((d) => {
    const row: BarRow = { x: monthLabel(d) };
    for (const { key, m } of maps) {
      const v = m.get(d);
      if (v !== undefined) row[key] = v;
    }
    return row;
  });
}

/** Latest value of a series (USD bn). */
function latestBn(rows: EvdsRow[]): number | null {
  const r = rows.at(-1);
  return r ? r.value * BN : null;
}

/** Latest trailing-12m sum (USD bn). */
function latest12Bn(rows: EvdsRow[]): number | null {
  if (rows.length < 12) return null;
  return rows.slice(-12).reduce((a, r) => a + r.value, 0) * BN;
}

// ---------------------------------------------------------------------------
// Summary table — Apr-26 vs Apr-25, monthly + 12-month cumulative (USD million)
// ---------------------------------------------------------------------------
export interface TableRow {
  label: string;
  /** [now monthly, now 12m, year-ago monthly, year-ago 12m] in USD million. */
  cells: [number | null, number | null, number | null, number | null];
}

function tableCells(rows: EvdsRow[]): TableRow["cells"] {
  const n = rows.length;
  if (n < 24) return [null, null, null, null];
  const sum = (end: number) =>
    rows.slice(end - 12, end).reduce((a, r) => a + r.value, 0);
  return [
    rows[n - 1].value, // now monthly
    sum(n), // now 12m
    rows[n - 13].value, // year-ago monthly
    sum(n - 12), // year-ago 12m
  ];
}

// ---------------------------------------------------------------------------
// Loader
// ---------------------------------------------------------------------------
export interface BopData {
  asOfLabel: string; // "April 2026"
  // cover KPIs (USD bn)
  caMonthly: number | null;
  ca12m: number | null;
  coreMonthly: number | null;
  // Şekil 1–2, 7–9 (line, 12m rolling, USD bn)
  s1: Record<string, Point[]>;
  s2: Record<string, Point[]>;
  s7: Record<string, Point[]>;
  s8: Record<string, Point[]>;
  s9: Record<string, Point[]>;
  // Şekil 3–6, 10 (bars, monthly, USD bn)
  s3: BarRow[];
  s4: BarRow[];
  s5: BarRow[];
  s6: BarRow[];
  s10: BarRow[];
  table: TableRow[];
}

const SHORT = 28; // months on the financial-account bar charts (Jan-24 → latest)
const LONG = 63; // months on the financing chart (≈ 2021 → latest)

const MONTHS_EN = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

export async function getBopData(yearsBack = 9): Promise<BopData> {
  const s = await evdsMulti([...CODES], yearsBack);
  const g = (code: string) => s[code] ?? [];

  // derived monthly series
  const fdiOther = combine([g(C.fdiLiab), g(C.fdiRealEstate)], (v) => v[0] - v[1]);
  const netForeignInv = combine(
    [g(C.fdiNet), g(C.portNet), g(C.otherNet)],
    (v) => v[0] + v[1] + v[2],
  );
  const reservesMinusNeo = combine([g(C.reserves), g(C.neo)], (v) => v[0] - v[1]);

  const latest = g(C.ca).at(-1)?.period_date ?? "";
  const [yy, mm] = [latest.slice(0, 4), Number(latest.slice(5, 7))];
  const asOfLabel = latest ? `${MONTHS_EN[mm - 1]} ${yy}` : "";

  return {
    asOfLabel,
    caMonthly: latestBn(g(C.ca)),
    ca12m: latest12Bn(g(C.ca)),
    coreMonthly: latestBn(g(C.core)),

    // Şekil 1 — Current account (12m, bn$): CA, ex-energy, core
    s1: {
      "Current account": roll12(g(C.ca)),
      "ex energy": roll12(g(C.exEnergy)),
      "Core (ex gold & energy)": roll12(g(C.core)),
    },
    // Şekil 2 — Goods & tourism (12m, bn$)
    s2: {
      "Trade balance (goods)": roll12(g(C.goods)),
      "Net tourism (travel)": roll12(g(C.travel)),
    },
    // Şekil 7 — Trade credits (12m, bn$)
    s7: { "Trade credits (net liab.)": roll12(g(C.tradeCredits)) },
    // Şekil 8 — Currency & deposits (12m, bn$)
    s8: {
      "Net acquisition of assets": roll12(g(C.deposAssets)),
      "Net incurrence of liabilities": roll12(g(C.deposLiab)),
    },
    // Şekil 9 — Net errors & omissions (12m, bn$)
    s9: { "Net errors & omissions": roll12(g(C.neo)) },

    // Şekil 3 — Capital inflows (monthly, bn$) — net liab. incurred basis
    s3: barRows(
      [
        { key: "fdi", rows: monthly(g(C.fdiLiab)) },
        { key: "portfolio", rows: monthly(g(C.portLiab)) },
        { key: "loans", rows: monthly(g(C.loans)) },
        { key: "trade", rows: monthly(g(C.tradeCredits)) },
      ],
      SHORT,
    ),
    // Şekil 4 — Direct investment (monthly bars + 12m line on right axis)
    s4: barRows(
      [
        { key: "realEstate", rows: monthly(g(C.fdiRealEstate)) },
        { key: "other", rows: monthly(fdiOther) },
        { key: "twelveM", rows: roll12(g(C.fdiLiab)) },
      ],
      SHORT,
    ),
    // Şekil 5 — Portfolio investment (monthly bars + 12m line on right axis)
    s5: barRows(
      [
        { key: "equity", rows: monthly(g(C.portEquity)) },
        { key: "debt", rows: monthly(g(C.portDebt)) },
        { key: "twelveM", rows: roll12(g(C.portLiab)) },
      ],
      SHORT,
    ),
    // Şekil 6 — Loans by borrower sector (monthly, bn$)
    s6: barRows(
      [
        { key: "banks", rows: monthly(g(C.loansBanks)) },
        { key: "gov", rows: monthly(g(C.loansGov)) },
        { key: "other", rows: monthly(g(C.loansOther)) },
      ],
      SHORT,
    ),
    // Şekil 10 — Financing of the current account deficit (monthly, bn$)
    s10: barRows(
      [
        { key: "need", rows: monthly(g(C.ca)) },
        { key: "nfi", rows: monthly(netForeignInv) },
        { key: "resNeo", rows: monthly(reservesMinusNeo) },
      ],
      LONG,
    ),

    // Summary table (USD million) — mirrors the report's page-4 grid
    table: [
      { label: "Current account", cells: tableCells(g(C.ca)) },
      { label: "Gold balance", cells: tableCells(g(C.gold)) },
      { label: "Energy balance", cells: tableCells(g(C.energy)) },
      { label: "Core balance (ex gold & energy)", cells: tableCells(g(C.core)) },
      { label: "Trade balance (goods)", cells: tableCells(g(C.goods)) },
      { label: "Services balance", cells: tableCells(g(C.services)) },
      { label: "Travel income (net)", cells: tableCells(g(C.travel)) },
      { label: "Direct investment (net)", cells: tableCells(g(C.fdiNet)) },
      { label: "Portfolio investment (net)", cells: tableCells(g(C.portNet)) },
      { label: "Other investment (net)", cells: tableCells(g(C.otherNet)) },
      { label: "Net errors & omissions", cells: tableCells(g(C.neo)) },
      { label: "Reserve assets", cells: tableCells(g(C.reserves)) },
    ],
  };
}
