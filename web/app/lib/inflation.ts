/**
 * Inflation data layer — reproduces the Albaraka "Enflasyon" monthly report
 * from TÜİK CPI/PPI series in EVDS: headline & core inflation, the CPI
 * special-scope core indices (A/B/C/D), and the CPI-group / PPI-sector mix.
 *
 * All series are monthly index levels; everything here is a scale-invariant
 * derivation (m/m, y/y, cumulative-since-December, 12-month-average y/y as the
 * ratio of trailing-12m index averages — the exact TÜİK convention).
 *
 * Coverage note: Şekil 2/3 in the report plot weighted *contributions* (pp),
 * which need TÜİK group weights not published in EVDS — here we show **m/m %
 * change per group** instead (relabeled). The PPI Main-Industrial-Groupings
 * table (Table 2-left) is TÜİK-Excel-only and not wired.
 */
import { evdsMulti, type EvdsRow } from "@/app/lib/metrics";
import { pctChange, type Point } from "@/app/lib/economy";
import { type BarRow } from "@/app/lib/bop";

const C = {
  cpi: "TP.TUKFIY2025.GENEL",
  coreA: "TP.FE25.OKTG02",
  coreB: "TP.FE25.OKTG03",
  coreC: "TP.FE25.OKTG04",
  coreD: "TP.FE25.OKTG05",
  ppi: "TP.TUFE1YI.T1",
  ppiElec: "TP.TUFE1YI.T118",
} as const;

const CPI_GROUPS = [
  { code: "TP.TUKFIY2025.01", label: "Food & non-alc. bev." },
  { code: "TP.TUKFIY2025.02", label: "Alcohol & tobacco" },
  { code: "TP.TUKFIY2025.03", label: "Clothing & footwear" },
  { code: "TP.TUKFIY2025.04", label: "Housing & utilities" },
  { code: "TP.TUKFIY2025.05", label: "Furnishings" },
  { code: "TP.TUKFIY2025.06", label: "Health" },
  { code: "TP.TUKFIY2025.07", label: "Transport" },
  { code: "TP.TUKFIY2025.08", label: "Communication" },
  { code: "TP.TUKFIY2025.09", label: "Recreation & culture" },
  { code: "TP.TUKFIY2025.10", label: "Education" },
  { code: "TP.TUKFIY2025.11", label: "Restaurants & hotels" },
  { code: "TP.TUKFIY2025.13", label: "Personal care & misc" },
];

const PPI_SECTORS = [
  { code: "TP.TUFE1YI.T118", label: "Electricity & gas" },
  { code: "TP.TUFE1YI.T16", label: "Food products" },
  { code: "TP.TUFE1YI.T61", label: "Rubber & plastic" },
  { code: "TP.TUFE1YI.T52", label: "Chemicals" },
  { code: "TP.TUFE1YI.T73", label: "Base metals" },
  { code: "TP.TUFE1YI.T30", label: "Textiles" },
  { code: "TP.TUFE1YI.T79", label: "Fabricated metal" },
  { code: "TP.TUFE1YI.T64", label: "Non-metallic minerals" },
  { code: "TP.TUFE1YI.T93", label: "Electrical equipment" },
  { code: "TP.TUFE1YI.T6", label: "Crude oil & gas" },
  { code: "TP.TUFE1YI.T114", label: "Other manufactured" },
  { code: "TP.TUFE1YI.T28", label: "Tobacco" },
  { code: "TP.TUFE1YI.T49", label: "Coke & petroleum" },
];

// PPI Main Industrial Groupings — TÜİK detail not in EVDS (ingested as TUIK.* by src/tuik).
const PPI_MIG = [
  { code: "TUIK.PPI.MIG_INTERMEDIATE", label: "Intermediate goods" },
  { code: "TUIK.PPI.MIG_DURABLE", label: "Durable consumer goods" },
  { code: "TUIK.PPI.MIG_NONDUR", label: "Non-durable consumer goods" },
  { code: "TUIK.PPI.MIG_ENERGY", label: "Energy" },
  { code: "TUIK.PPI.MIG_CAPITAL", label: "Capital goods" },
];

const CODES = [
  ...Object.values(C),
  ...CPI_GROUPS.map((g) => g.code),
  ...PPI_SECTORS.map((g) => g.code),
  ...PPI_MIG.map((g) => g.code),
];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

// ---------------------------------------------------------------------------
// Pure helpers
// ---------------------------------------------------------------------------

/** "2026-05-01" → "May 26". */
const monthLabel = (d: string) => `${MONTHS[Number(d.slice(5, 7)) - 1]} ${d.slice(2, 4)}`;

const yoy = (rows: EvdsRow[]): Point[] => pctChange(rows, 12);
const mom = (rows: EvdsRow[]): Point[] => pctChange(rows, 1);
const latest = (pts: Point[]): number | null => pts.at(-1)?.value ?? null;

/** Cumulative % since the prior December (year-to-date inflation). */
function cumSinceDec(rows: EvdsRow[]): number | null {
  const last = rows.at(-1);
  if (!last) return null;
  const dec = rows.find((r) => r.period_date === `${Number(last.period_date.slice(0, 4)) - 1}-12-01`);
  return dec ? 100 * (last.value / dec.value - 1) : null;
}

/** 12-month-average y/y: ratio of trailing-12m index averages (TÜİK exact). */
function avg12Yoy(rows: EvdsRow[]): number | null {
  if (rows.length < 24) return null;
  const mean = (a: EvdsRow[]) => a.reduce((s, r) => s + r.value, 0) / a.length;
  return 100 * (mean(rows.slice(-12)) / mean(rows.slice(-24, -12)) - 1);
}

/** Latest-month m/m per group, sorted descending — for the Şekil 2/3 bars. */
function momBars(groups: { code: string; label: string }[], s: Record<string, EvdsRow[]>): BarRow[] {
  return groups
    .map((g) => ({ label: g.label, value: latest(mom(s[g.code] ?? [])) }))
    .filter((r): r is { label: string; value: number } => r.value != null)
    .sort((a, b) => b.value - a.value)
    .map((r) => ({ x: r.label, mm: r.value }));
}

// ---------------------------------------------------------------------------
// Tables
// ---------------------------------------------------------------------------
export interface Table1Row {
  month: string;
  cpiMM: number | null;
  cpiYY: number | null;
  ppiMM: number | null;
  ppiYY: number | null;
}

export interface CoreRow {
  label: string;
  mm: number | null;
  cum: number | null;
  yy: number | null;
  avg12: number | null;
}

export interface MigRow {
  label: string;
  mm: number | null;
  yy: number | null;
}

// ---------------------------------------------------------------------------
// Loader
// ---------------------------------------------------------------------------
export interface InflationData {
  asOfLabel: string; // "May 2026"
  latestPeriod: string;
  cpiYoY: number | null;
  ppiYoY: number | null;
  coreYoY: number | null;
  s1: Record<string, Point[]>; // CPI / Core C / PPI y/y
  s6: Record<string, Point[]>; // Core C m/m + y/y
  s4: Record<string, Point[]>; // clothing m/m
  s5: Record<string, Point[]>; // electricity & gas m/m
  s2: BarRow[]; // CPI group m/m
  s3: BarRow[]; // PPI sector m/m
  table1: Table1Row[];
  core: CoreRow[];
  mig: MigRow[]; // PPI Main Industrial Groupings (TÜİK detail)
  hasMig: boolean;
}

const T1_MONTHS = 17;

export async function getInflationData(yearsBack = 9): Promise<InflationData> {
  const s = await evdsMulti([...CODES], yearsBack);
  const g = (code: string) => s[code] ?? [];

  const cpiY = yoy(g(C.cpi));
  const last = cpiY.at(-1)?.period_date ?? "";
  const asOfLabel = last ? `${MONTHS[Number(last.slice(5, 7)) - 1]} ${last.slice(0, 4)}` : "";

  // Table 1 — CPI & PPI m/m + y/y, most recent T1_MONTHS, newest first
  const map = (pts: Point[]) => new Map(pts.map((p) => [p.period_date, p.value]));
  const cpiMM = map(mom(g(C.cpi))), cpiYY = map(cpiY);
  const ppiMM = map(mom(g(C.ppi))), ppiYY = map(yoy(g(C.ppi)));
  const dates = g(C.cpi).map((r) => r.period_date).filter((d) => cpiYY.has(d)).slice(-T1_MONTHS).reverse();
  const table1: Table1Row[] = dates.map((d) => ({
    month: monthLabel(d),
    cpiMM: cpiMM.get(d) ?? null,
    cpiYY: cpiYY.get(d) ?? null,
    ppiMM: ppiMM.get(d) ?? null,
    ppiYY: ppiYY.get(d) ?? null,
  }));

  const coreRow = (label: string, code: string): CoreRow => ({
    label,
    mm: latest(mom(g(code))),
    cum: cumSinceDec(g(code)),
    yy: latest(yoy(g(code))),
    avg12: avg12Yoy(g(code)),
  });

  return {
    asOfLabel,
    latestPeriod: last ? last.slice(0, 7) : "",
    cpiYoY: latest(cpiY),
    ppiYoY: latest(yoy(g(C.ppi))),
    coreYoY: latest(yoy(g(C.coreC))),
    s1: {
      "CPI (y/y)": cpiY,
      "Core C (y/y)": yoy(g(C.coreC)),
      "PPI / Yİ-ÜFE (y/y)": yoy(g(C.ppi)),
    },
    s6: {
      "Core C (y/y)": yoy(g(C.coreC)),
      "Core C (m/m)": mom(g(C.coreC)),
    },
    s4: { "Clothing & footwear (m/m)": mom(g("TP.TUKFIY2025.03")) },
    s5: { "Electricity & gas (m/m)": mom(g(C.ppiElec)) },
    s2: momBars(CPI_GROUPS, s),
    s3: momBars(PPI_SECTORS, s),
    table1,
    core: [
      coreRow("A — excl. seasonal", C.coreA),
      coreRow("B — excl. food, energy, gold", C.coreB),
      coreRow("C — core (headline)", C.coreC),
      coreRow("D — excl. unproc. food", C.coreD),
    ],
    mig: PPI_MIG.map((m) => ({
      label: m.label,
      mm: latest(mom(g(m.code))),
      yy: latest(yoy(g(m.code))),
    })),
    hasMig: (g("TUIK.PPI.MIG_ENERGY")?.length ?? 0) > 0,
  };
}
