/**
 * Central-government budget data layer — reproduces the Albaraka "Bütçe
 * Görünümü" monthly report from TÜİK/Treasury budget series in EVDS
 * (merkezi yönetim bütçesi, cat 1503: bie_kbmgel revenues + bie_kbmgid
 * expenses). Distinct from the cash general-budget TP.KB.GEN* codes.
 *
 * EVDS values scale ÷1e3 → million TL (the report table) and ÷1e6 → bn TL
 * (the figures/KPIs). The budget balance, primary balance and non-tax
 * revenues have no direct series — derived here (revenues − expenditure,
 * revenues − primary expenditure, revenues − tax). All verified to the
 * report's Apr-2026 table.
 */
import { evdsMulti, type EvdsRow } from "@/app/lib/metrics";
import { rollingSum, type Point } from "@/app/lib/economy";
import { type BarRow } from "@/app/lib/bop";

const BN = 1 / 1e6; // raw → bn TL
const MN = 1 / 1e3; // raw → million TL

const C = {
  rev: "TP.KB.GEL001",
  tax: "TP.KB.GEL003",
  incomeTax: "TP.KB.GEL005",
  corpTax: "TP.KB.GEL010",
  mtv: "TP.KB.GEL016",
  domVat: "TP.KB.GEL018",
  otv: "TP.KB.GEL021",
  otvPetrol: "TP.KB.GEL022",
  impVat: "TP.KB.GEL033",
  stamp: "TP.KB.GEL035",
  fees: "TP.KB.GEL036",
  enterprise: "TP.KB.GEL038",
  interestShares: "TP.KB.GEL061",
  exp: "TP.KB.GID001",
  primExp: "TP.KB.GID002",
  personnel: "TP.KB.GID003",
  socSec: "TP.KB.GID008",
  goods: "TP.KB.GID014",
  currentTransfers: "TP.KB.GID026",
  capExp: "TP.KB.GID110",
  capTransfers: "TP.KB.GID116",
  lending: "TP.KB.GID131",
  interestExp: "TP.KB.GID152",
} as const;

// The deflator and the denominator. Neither is a budget series, and that is the
// point: at a ~30% price level every nominal line on this page is mostly a chart
// of the deflator (DESIGN.md — "every nominal ₺ level ships with its real twin"),
// and "tax revenues up 28%" is a real CUT that reads as growth.
const CPI = "TP.TUKFIY2025.GENEL";
const GDP_CF = "TP.GSYIH26.HY.CF";

const CODES = [...Object.values(C), CPI, GDP_CF];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

// ---------------------------------------------------------------------------
// Pure helpers
// ---------------------------------------------------------------------------

/** "2026-04-01" → "Apr 2026". */
function monthLabel(d: string): string {
  return `${MONTHS[Number(d.slice(5, 7)) - 1]} ${d.slice(0, 4)}`;
}

/** Element-wise op over aligned monthly series. */
function combine(series: EvdsRow[][], fn: (vals: number[]) => number): EvdsRow[] {
  const maps = series.map((s) => new Map(s.map((r) => [r.period_date, r.value])));
  const out: EvdsRow[] = [];
  for (const r of series[0] ?? []) {
    if (maps.every((m) => m.has(r.period_date))) {
      out.push({ period_date: r.period_date, value: fn(maps.map((m) => m.get(r.period_date)!)) });
    }
  }
  return out;
}

const roll12Bn = (rows: EvdsRow[]): Point[] => rollingSum(rows, 12, BN);
const monthlyBn = (rows: EvdsRow[]): Point[] =>
  rows.map((r) => ({ period_date: r.period_date, value: r.value * BN }));

/** y/y % change of a monthly series (lag 12). */
function yoyPct(rows: EvdsRow[]): Point[] {
  const out: Point[] = [];
  for (let i = 12; i < rows.length; i++) {
    const prev = rows[i - 12].value;
    if (!prev) continue;
    out.push({ period_date: rows[i].period_date, value: 100 * (rows[i].value / prev - 1) });
  }
  return out;
}

/**
 * y/y % change of a monthly series DEFLATED by CPI — the real growth rate.
 *
 * Both the flow and the price index are taken at the same two dates, so this is
 * (nominal ratio ÷ price ratio − 1): what the money actually bought, year on
 * year. A nominal budget line at 28% growth against a 30% price level is a real
 * contraction, and the nominal chart cannot show that.
 */
function realYoY(rows: EvdsRow[], cpi: EvdsRow[]): Point[] {
  const p = new Map(cpi.map((r) => [r.period_date, r.value]));
  const out: Point[] = [];
  for (let i = 12; i < rows.length; i++) {
    const prevV = rows[i - 12].value;
    const pNow = p.get(rows[i].period_date);
    const pPrev = p.get(rows[i - 12].period_date);
    if (!prevV || !pNow || !pPrev) continue;
    const nominal = rows[i].value / prevV;
    const prices = pNow / pPrev;
    out.push({ period_date: rows[i].period_date, value: 100 * (nominal / prices - 1) });
  }
  return out;
}

/**
 * A 12-month rolling flow as % of trailing-4-quarter nominal GDP.
 *
 * Both sides are TL (thousand vs thousand), so units cancel. Each month takes
 * the most recent completed 4-quarter GDP window at or before it — a monthly
 * flow against a quarterly stock needs the stock stepped, never interpolated.
 */
function pctOfGdp(monthlyFlow: EvdsRow[], gdpQ: EvdsRow[]): Point[] {
  const gdp4q: { d: string; v: number }[] = [];
  for (let i = 3; i < gdpQ.length; i++) {
    gdp4q.push({
      d: gdpQ[i].period_date,
      v: gdpQ[i].value + gdpQ[i - 1].value + gdpQ[i - 2].value + gdpQ[i - 3].value,
    });
  }
  const flow12 = rollingSum(monthlyFlow, 12);
  const out: Point[] = [];
  for (const f of flow12) {
    let g: number | undefined;
    for (let i = gdp4q.length - 1; i >= 0; i--) {
      if (gdp4q[i].d <= f.period_date) { g = gdp4q[i].v; break; }
    }
    if (!g) continue;
    out.push({ period_date: f.period_date, value: 100 * (f.value / g) });
  }
  return out;
}

/** Ratio of two 12-month rolling flows, as a percentage. */
function ratio12(num: EvdsRow[], den: EvdsRow[]): Point[] {
  const d = new Map(rollingSum(den, 12).map((p) => [p.period_date, p.value]));
  const out: Point[] = [];
  for (const n of rollingSum(num, 12)) {
    const dv = d.get(n.period_date);
    if (!dv) continue;
    out.push({ period_date: n.period_date, value: 100 * (n.value / dv) });
  }
  return out;
}

/** Trailing moving average over `w` points. */
function movingAvg(pts: Point[], w: number): Point[] {
  const out: Point[] = [];
  for (let i = w - 1; i < pts.length; i++) {
    let acc = 0;
    for (let j = i - w + 1; j <= i; j++) acc += pts[j].value;
    out.push({ period_date: pts[i].period_date, value: acc / w });
  }
  return out;
}

/** Latest vs year-ago monthly value per category, scaled (for grouped bars). */
function catCompare(items: { label: string; rows: EvdsRow[] }[]): BarRow[] {
  return items.map(({ label, rows }) => {
    const now = rows.at(-1);
    const prev = rows.length >= 13 ? rows[rows.length - 13] : undefined;
    const row: BarRow = { x: label };
    if (prev) row.prev = prev.value * BN;
    if (now) row.now = now.value * BN;
    return row;
  });
}

// ---------------------------------------------------------------------------
// Summary table (million TL) — Apr-26 vs Apr-25, monthly + 12m
// ---------------------------------------------------------------------------
export interface TableRow {
  label: string;
  indent?: boolean;
  /** [now monthly, now 12m, year-ago monthly, year-ago 12m] in million TL. */
  cells: [number | null, number | null, number | null, number | null];
}

function tableCells(rows: EvdsRow[]): TableRow["cells"] {
  const n = rows.length;
  if (n < 24) return [null, null, null, null];
  const sum = (end: number) => rows.slice(end - 12, end).reduce((a, r) => a + r.value, 0);
  return [rows[n - 1].value * MN, sum(n) * MN, rows[n - 13].value * MN, sum(n - 12) * MN];
}

// ---------------------------------------------------------------------------
// Loader
// ---------------------------------------------------------------------------
export interface BudgetData {
  asOfLabel: string;
  latestPeriod: string;
  // KPIs (12m, bn TL)
  balance12m: number | null;
  primary12m: number | null;
  tax12m: number | null;
  // figures
  s1: Record<string, Point[]>; // 12m balance + primary (bn TL)
  s5: Record<string, Point[]>; // monthly balance (bn TL)
  s4: Record<string, Point[]>; // revenue y/y % (3m MA)
  s2: BarRow[]; // expenditure category bars
  s3: BarRow[]; // tax category bars
  barLabels: { prev: string; now: string }; // "Apr 2025" / "Apr 2026"
  table: TableRow[];
  // ---- the real twin, and the ratios that need a denominator ----
  /** Revenue and spending growth, CPI-deflated (%). */
  real: Record<string, Point[]>;
  /** Nominal vs real tax revenue growth on one axis (%). */
  taxNominalVsReal: Record<string, Point[]>;
  /** 12m central-government balances as % of trailing-4Q nominal GDP. */
  pctGdp: Record<string, Point[]>;
  /** Interest expenditure as % of tax revenue, 12m rolling. */
  interestShare: Point[];
  balancePctGdpNow: number | null;
  primaryPctGdpNow: number | null;
  interestShareNow: number | null;
  taxRealYoYNow: number | null;
}

export async function getBudgetData(yearsBack = 9): Promise<BudgetData> {
  const s = await evdsMulti([...CODES], yearsBack);
  const g = (code: string) => s[code] ?? [];

  const balance = combine([g(C.rev), g(C.exp)], (v) => v[0] - v[1]);
  const primary = combine([g(C.rev), g(C.primExp)], (v) => v[0] - v[1]);
  const nonTax = combine([g(C.rev), g(C.tax)], (v) => v[0] - v[1]);

  const latest = g(C.rev).at(-1)?.period_date ?? "";
  const last12 = (rows: EvdsRow[]) =>
    rows.length >= 12 ? rows.slice(-12).reduce((a, r) => a + r.value, 0) * BN : null;

  const cpi = g(CPI);
  const gdpQ = g(GDP_CF);
  const taxReal = realYoY(g(C.tax), cpi);
  const balancePctGdp = pctOfGdp(balance, gdpQ);
  const primaryPctGdp = pctOfGdp(primary, gdpQ);
  const interestShare = ratio12(g(C.interestExp), g(C.tax));

  return {
    asOfLabel: latest ? monthLabel(latest) : "",
    latestPeriod: latest ? latest.slice(0, 7) : "",
    balance12m: last12(balance),
    primary12m: last12(primary),
    tax12m: last12(g(C.tax)),

    s1: {
      "Budget balance": roll12Bn(balance),
      "Primary balance": roll12Bn(primary),
    },
    s5: { "Budget balance": monthlyBn(balance) },
    s4: {
      "Tax revenues (y/y)": movingAvg(yoyPct(g(C.tax)), 3),
      "Non-tax revenues (y/y)": movingAvg(yoyPct(nonTax), 3),
    },
    s2: catCompare([
      { label: "Capital transfers", rows: g(C.capTransfers) },
      { label: "Lending", rows: g(C.lending) },
      { label: "Soc. security premium", rows: g(C.socSec) },
      { label: "Goods & services", rows: g(C.goods) },
      { label: "Capital expenditure", rows: g(C.capExp) },
      { label: "Personnel", rows: g(C.personnel) },
      { label: "Current transfers", rows: g(C.currentTransfers) },
    ]),
    s3: catCompare([
      { label: "Petroleum/gas SCT", rows: g(C.otvPetrol) },
      { label: "Stamp duty", rows: g(C.stamp) },
      { label: "Fees", rows: g(C.fees) },
      { label: "Corporate tax", rows: g(C.corpTax) },
      { label: "Domestic VAT", rows: g(C.domVat) },
      { label: "SCT (ÖTV)", rows: g(C.otv) },
      { label: "Income tax", rows: g(C.incomeTax) },
    ]),
    barLabels: {
      prev: latest ? monthLabel(`${Number(latest.slice(0, 4)) - 1}${latest.slice(4)}`) : "year ago",
      now: latest ? monthLabel(latest) : "latest",
    },

    real: {
      "Tax revenues (real y/y)": taxReal,
      "Primary expenditure (real y/y)": realYoY(g(C.primExp), cpi),
      "Interest expenditure (real y/y)": realYoY(g(C.interestExp), cpi),
    },
    taxNominalVsReal: {
      "Nominal": yoyPct(g(C.tax)),
      "Real (CPI-deflated)": taxReal,
    },
    pctGdp: {
      "Budget balance": balancePctGdp,
      "Primary balance": primaryPctGdp,
    },
    interestShare,
    balancePctGdpNow: balancePctGdp.at(-1)?.value ?? null,
    primaryPctGdpNow: primaryPctGdp.at(-1)?.value ?? null,
    interestShareNow: interestShare.at(-1)?.value ?? null,
    taxRealYoYNow: taxReal.at(-1)?.value ?? null,

    table: [
      { label: "Budget revenues", cells: tableCells(g(C.rev)) },
      { label: "Tax revenues", cells: tableCells(g(C.tax)) },
      { label: "Income tax", indent: true, cells: tableCells(g(C.incomeTax)) },
      { label: "Corporate tax", indent: true, cells: tableCells(g(C.corpTax)) },
      { label: "Motor vehicle tax", indent: true, cells: tableCells(g(C.mtv)) },
      { label: "Domestic VAT", indent: true, cells: tableCells(g(C.domVat)) },
      { label: "Special consumption tax (ÖTV)", indent: true, cells: tableCells(g(C.otv)) },
      { label: "VAT on imports", indent: true, cells: tableCells(g(C.impVat)) },
      { label: "Enterprise & property income", cells: tableCells(g(C.enterprise)) },
      { label: "Interest, shares & penalties", cells: tableCells(g(C.interestShares)) },
      { label: "Budget expenditures", cells: tableCells(g(C.exp)) },
      { label: "Primary (non-interest) expenditure", cells: tableCells(g(C.primExp)) },
      { label: "Personnel", indent: true, cells: tableCells(g(C.personnel)) },
      { label: "Current transfers", indent: true, cells: tableCells(g(C.currentTransfers)) },
      { label: "Interest expenditure", cells: tableCells(g(C.interestExp)) },
      { label: "Budget balance", cells: tableCells(balance) },
      { label: "Primary balance", cells: tableCells(primary) },
    ],
  };
}
