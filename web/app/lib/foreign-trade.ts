/**
 * Foreign-trade data layer — reproduces the Albaraka "Dış Ticaret Dengesi"
 * report from TÜİK customs-trade series in EVDS: the trade balance, exports &
 * imports (level + growth), the export/import coverage ratio, terms of trade,
 * trade by BEC product group, and the energy deficit vs Brent.
 *
 * BEC trade flows are USD **thousand** (÷1e6 → bn$); the energy balance
 * (TP.HARICCARIACIK.K7) is USD **million** (÷1e3 → bn$); unit-value indices are
 * 2015=100; Brent is USD/bbl. "Annualised" panels use a trailing-12-month
 * rolling sum. Verified to the report's Q2-2022 values.
 *
 * Out of scope (flagged in-page): the Şekil 1 "core balance" line (an
 * Albaraka-internal construction that doesn't reproduce from EVDS primitives)
 * and Şekil 9 + the HS-chapter tables (TÜİK's dynamic foreign-trade DB only).
 */
import { evdsMulti, type EvdsRow } from "@/app/lib/metrics";
import { rollingSum, pctChange, type Point } from "@/app/lib/economy";
import { type BarRow } from "@/app/lib/bop";

const KBN = 1 / 1e6; // USD thousand → bn$
const MBN = 1 / 1e3; // USD million → bn$

const C = {
  exp: "TP.IHRACATBEC.9999",
  imp: "TP.ITHALATBEC.9999",
  expInv: "TP.IHRACATBEC.1",
  expInter: "TP.IHRACATBEC.2",
  expCons: "TP.IHRACATBEC.3",
  impInv: "TP.ITHALATBEC.1",
  impInter: "TP.ITHALATBEC.2",
  impCons: "TP.ITHALATBEC.3",
  uvExp: "TP.DT.IH.FIY.D01.2010",
  uvImp: "TP.DT.IT.FIY.D01.2010",
  energy: "TP.HARICCARIACIK.K7",
  brent: "TP.BRENTPETROL.EUBP",
} as const;

const CODES = Object.values(C);
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

// ---------------------------------------------------------------------------
// Pure helpers
// ---------------------------------------------------------------------------
const monthLabel = (d: string) => `${MONTHS[Number(d.slice(5, 7)) - 1]} ${d.slice(2, 4)}`;

/** Element-wise op over two date-aligned Point[] series. */
function zip(a: Point[], b: Point[], fn: (x: number, y: number) => number): Point[] {
  const mb = new Map(b.map((p) => [p.period_date, p.value]));
  const out: Point[] = [];
  for (const p of a) {
    const y = mb.get(p.period_date);
    if (y !== undefined) out.push({ period_date: p.period_date, value: fn(p.value, y) });
  }
  return out;
}

const scaledRows = (rows: EvdsRow[], k: number): Point[] =>
  rows.map((r) => ({ period_date: r.period_date, value: r.value * k }));

/** Pivot Point[] columns into the last `months` wide rows for BopFlowChart. */
function barRows(cols: { key: string; rows: Point[] }[], months: number): BarRow[] {
  const dates = Array.from(new Set(cols.flatMap((c) => c.rows.map((r) => r.period_date)))).sort();
  const window = dates.slice(-months);
  const maps = cols.map((c) => ({ key: c.key, m: new Map(c.rows.map((r) => [r.period_date, r.value])) }));
  return window.map((d) => {
    const row: BarRow = { x: monthLabel(d) };
    for (const { key, m } of maps) {
      const v = m.get(d);
      if (v !== undefined) row[key] = v;
    }
    return row;
  });
}

const latest = (pts: Point[]): number | null => pts.at(-1)?.value ?? null;
const last3 = (rows: EvdsRow[], k: number): number | null =>
  rows.length >= 3 ? rows.slice(-3).reduce((a, r) => a + r.value, 0) * k : null;

// ---------------------------------------------------------------------------
// Loader
// ---------------------------------------------------------------------------
export interface ForeignTradeData {
  asOfLabel: string;
  latestPeriod: string;
  expQ: number | null; // trailing-3-month exports, bn$
  impQ: number | null;
  deficitQ: number | null;
  s1: Record<string, Point[]>; // trade balance + ex-energy (12m bn)
  levels: Record<string, Point[]>; // exports & imports 12m (bn)
  growth: Record<string, Point[]>; // exports & imports y/y %
  coverage: Record<string, Point[]>; // coverage ratio (12m %)
  terms: Record<string, Point[]>; // terms of trade (%)
  becExp: Record<string, Point[]>; // exports by BEC (12m bn)
  becImp: Record<string, Point[]>; // imports by BEC (12m bn)
  energy: BarRow[]; // energy deficit (12m bn) + Brent
}

const QBARS = 150; // ~12.5y of months on the energy/oil bar chart

export async function getForeignTradeData(yearsBack = 16): Promise<ForeignTradeData> {
  const s = await evdsMulti([...CODES], yearsBack);
  const g = (code: string) => s[code] ?? [];

  const exp12 = rollingSum(g(C.exp), 12, KBN);
  const imp12 = rollingSum(g(C.imp), 12, KBN);
  const energy12 = rollingSum(g(C.energy), 12, MBN);
  const tradeBal = zip(exp12, imp12, (e, i) => e - i);
  const exEnergy = zip(tradeBal, energy12, (b, en) => b - en);

  const latestP = g(C.exp).at(-1)?.period_date ?? "";
  const asOfLabel = latestP ? `${MONTHS[Number(latestP.slice(5, 7)) - 1]} ${latestP.slice(0, 4)}` : "";

  const expQ = last3(g(C.exp), KBN);
  const impQ = last3(g(C.imp), KBN);

  return {
    asOfLabel,
    latestPeriod: latestP ? latestP.slice(0, 7) : "",
    expQ,
    impQ,
    deficitQ: expQ != null && impQ != null ? impQ - expQ : null,

    s1: {
      "Trade balance": tradeBal,
      "ex energy": exEnergy,
    },
    levels: {
      Exports: exp12,
      Imports: imp12,
    },
    growth: {
      "Exports (y/y)": pctChange(g(C.exp), 12),
      "Imports (y/y)": pctChange(g(C.imp), 12),
    },
    coverage: {
      "Coverage ratio": zip(exp12, imp12, (e, i) => (i ? (e / i) * 100 : 0)),
    },
    terms: {
      "Terms of trade": zip(scaledRows(g(C.uvExp), 1), scaledRows(g(C.uvImp), 1), (e, i) =>
        i ? (e / i) * 100 : 0,
      ),
    },
    becExp: {
      "Intermediate goods": rollingSum(g(C.expInter), 12, KBN),
      "Consumption goods": rollingSum(g(C.expCons), 12, KBN),
      "Investment goods": rollingSum(g(C.expInv), 12, KBN),
    },
    becImp: {
      "Intermediate goods": rollingSum(g(C.impInter), 12, KBN),
      "Investment goods": rollingSum(g(C.impInv), 12, KBN),
      "Consumption goods": rollingSum(g(C.impCons), 12, KBN),
    },
    energy: barRows(
      [
        { key: "deficit", rows: energy12 },
        { key: "brent", rows: scaledRows(g(C.brent), 1) },
      ],
      QBARS,
    ),
  };
}

/** Latest value of any of the page's derived series — for the data-through badge. */
export function ftLatest(d: ForeignTradeData): number | null {
  return latest(d.s1["Trade balance"] ?? []);
}
