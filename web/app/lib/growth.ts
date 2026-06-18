/**
 * Economic-growth data layer — reproduces the Albaraka "Ekonomik Büyüme"
 * quarterly GDP report from TÜİK national-accounts series (2021 reference
 * year, chain-linked volume indices) in EVDS.
 *
 * y/y growth is computed from the index level (v[t]/v[t-4] − 1); the Şekil 2
 * growth-contributions use the additive approximation (component Δ over the
 * prior-year real GDP level, imports subtracting, inventories as the
 * residual) — validated against the report's cover-cited contributions
 * (consumption +3.4, investment +0.8, exports −2.9 pp at 2026-Q1).
 *
 * EVDS coverage gaps (NOT wired, would need a TÜİK Excel scraper): the
 * seasonally-adjusted GDP index (q/q line), the expenditure detail
 * (durable/semi/non-durable consumption; construction/machinery/other
 * investment), and the calendar-adjusted variant of the production index
 * (a few sub-sectors differ from the unadjusted figure by up to ~1.5 pp).
 */
import { evdsMulti, type EvdsRow } from "@/app/lib/metrics";
import { type Point } from "@/app/lib/economy";
import { type BarRow } from "@/app/lib/bop";
import { fmtQuarter } from "@/app/lib/chart-format";

const C = {
  gdpZH: "TP.GSYIH26.HY.ZH", // GDP chain-vol index (raw)
  gdpCF: "TP.GSYIH26.HY.CF", // GDP current prices, TL thousand
  // expenditure aggregates (chain vol.)
  cons: "TP.GSYIH20.HY.ZH",
  gov: "TP.GSYIH21.HY.ZH",
  inv: "TP.GSYIH22.HY.ZH",
  exp: "TP.GSYIH24.HY.ZH",
  imp: "TP.GSYIH25.HY.ZH",
  // production / kind of activity (chain vol.)
  agri: "TP.GSYIH01.IFK.ZH",
  industry: "TP.GSYIH02.IFK.ZH",
  manuf: "TP.GSYIH03.IFK.ZH",
  constr: "TP.GSYIH04.IFK.ZH",
  services: "TP.GSYIH05.IFK.ZH",
  ict: "TP.GSYIH06.IFK.ZH",
  finance: "TP.GSYIH07.IFK.ZH",
  realEstate: "TP.GSYIH08.IFK.ZH",
  professional: "TP.GSYIH09.IFK.ZH",
  publicAdmin: "TP.GSYIH10.IFK.ZH",
  otherServ: "TP.GSYIH11.IFK.ZH",
  gva: "TP.GSYIH12.IFK.ZH",
  taxes: "TP.GSYIH13.IFK.ZH",
  // TÜİK detail not in EVDS (ingested into evds_series as TUIK.* by src/tuik)
  consDurable: "TUIK.NA.CONS_DURABLE",
  consSemidur: "TUIK.NA.CONS_SEMIDUR",
  consNondur: "TUIK.NA.CONS_NONDUR",
  consServices: "TUIK.NA.CONS_SERVICES",
  gfcfConstruction: "TUIK.NA.GFCF_CONSTRUCTION",
  gfcfMachinery: "TUIK.NA.GFCF_MACHINERY",
  gfcfOther: "TUIK.NA.GFCF_OTHER",
} as const;

const CODES = Object.values(C);

// ---------------------------------------------------------------------------
// Pure helpers
// ---------------------------------------------------------------------------

/** y/y % change of a quarterly index (lag 4). */
function yoy(rows: EvdsRow[]): Point[] {
  const out: Point[] = [];
  for (let i = 4; i < rows.length; i++) {
    const prev = rows[i - 4].value;
    if (!prev) continue;
    out.push({ period_date: rows[i].period_date, value: 100 * (rows[i].value / prev - 1) });
  }
  return out;
}

/** Pivot y/y series into the last `n` quarterly wide rows keyed by x. */
function barRowsQ(cols: { key: string; rows: Point[] }[], n: number): BarRow[] {
  const dates = Array.from(
    new Set(cols.flatMap((c) => c.rows.map((r) => r.period_date))),
  ).sort();
  const window = dates.slice(-n);
  const maps = cols.map((c) => ({ key: c.key, m: new Map(c.rows.map((r) => [r.period_date, r.value])) }));
  return window.map((d) => {
    const row: BarRow = { x: fmtQuarter(d) };
    for (const { key, m } of maps) {
      const v = m.get(d);
      if (v !== undefined) row[key] = v;
    }
    return row;
  });
}

const round1 = (v: number) => Math.round(v * 10) / 10;

// Growth contributions (pp): component real Δ over prior-year real GDP level.
function contributions(s: Record<string, EvdsRow[]>, n: number): BarRow[] {
  const m = (code: string) => new Map((s[code] ?? []).map((r) => [r.period_date, r.value]));
  const G = m(C.gdpZH), Co = m(C.cons), Go = m(C.gov), In = m(C.inv), Ex = m(C.exp), Im = m(C.imp);
  const dates = (s[C.gdpZH] ?? []).map((r) => r.period_date);
  const out: BarRow[] = [];
  for (let i = 4; i < dates.length; i++) {
    const d = dates[i], p = dates[i - 4];
    const g0 = G.get(p);
    const all = [Co, Go, In, Ex, Im, G].map((x) => x.get(d) && x.get(p));
    if (!g0 || all.some((v) => v === undefined)) continue;
    const c = ((Co.get(d)! - Co.get(p)!) / g0) * 100;
    const gg = ((Go.get(d)! - Go.get(p)!) / g0) * 100;
    const ii = ((In.get(d)! - In.get(p)!) / g0) * 100;
    const xx = ((Ex.get(d)! - Ex.get(p)!) / g0) * 100;
    const mm = (-(Im.get(d)! - Im.get(p)!) / g0) * 100; // imports subtract
    const gyoy = (G.get(d)! / g0 - 1) * 100;
    const res = gyoy - (c + gg + ii + xx + mm); // inventories ≈ residual
    out.push({
      x: fmtQuarter(d),
      consumption: c, government: gg, investment: ii,
      inventories: res, exports: xx, imports: mm, gdp: gyoy,
    });
  }
  return out.slice(-n);
}

// ---------------------------------------------------------------------------
// y/y tables (last `nq` quarters) — mirror the report's two grids
// ---------------------------------------------------------------------------
export interface GrowthTableRow { label: string; values: (number | null)[]; indent?: boolean }
export interface GrowthTable { quarters: string[]; rows: GrowthTableRow[] }

function buildTable(
  s: Record<string, EvdsRow[]>,
  defs: { label: string; code: string; indent?: boolean }[],
  nq: number,
): GrowthTable {
  const dates = (s[C.gdpZH] ?? []).map((r) => r.period_date);
  const quarters = dates.slice(-nq);
  const rows = defs.map(({ label, code, indent }) => {
    const y = new Map(yoy(s[code] ?? []).map((p) => [p.period_date, p.value]));
    return {
      label,
      indent,
      values: quarters.map((q) => (y.has(q) ? round1(y.get(q)!) : null)),
    };
  });
  return { quarters: quarters.map(fmtQuarter), rows };
}

// ---------------------------------------------------------------------------
// Loader
// ---------------------------------------------------------------------------
export interface GrowthData {
  asOfLabel: string; // "2026-Q1"
  latestPeriod: string; // "2026-01" for the data-through badge
  gdpYoY: number | null;
  nominalQ: number | null; // ₺ trillion, this quarter
  nominalAnnual: number | null; // ₺ trillion, trailing 4Q
  s1: Record<string, Point[]>; // GDP y/y line
  s2: BarRow[]; // contributions (stacked) + gdp line
  s3: BarRow[]; // sectoral grouped bars
  s4inv: BarRow[]; // investment detail (TÜİK) grouped bars
  s5cons: BarRow[]; // consumption detail (TÜİK) grouped bars
  s6: BarRow[]; // government grouped bars
  hasTuik: boolean; // TÜİK detail present in D1
  expTable: GrowthTable;
  prodTable: GrowthTable;
}

const QBARS = 24; // quarters shown on the time-series bar charts
const QTABLE = 6; // columns on the y/y tables (matches the report)

export async function getGrowthData(yearsBack = 10): Promise<GrowthData> {
  const s = await evdsMulti([...CODES], yearsBack);
  const gdpY = yoy(s[C.gdpZH] ?? []);
  const cf = s[C.gdpCF] ?? [];
  const latest = gdpY.at(-1)?.period_date ?? "";

  const nominalQ = cf.at(-1) ? cf.at(-1)!.value / 1e9 : null;
  const nominalAnnual =
    cf.length >= 4 ? cf.slice(-4).reduce((a, r) => a + r.value, 0) / 1e9 : null;

  return {
    asOfLabel: latest ? fmtQuarter(latest) : "",
    latestPeriod: latest ? latest.slice(0, 7) : "",
    gdpYoY: gdpY.at(-1)?.value ?? null,
    nominalQ,
    nominalAnnual,

    s1: { "GDP (y/y)": gdpY },
    s2: contributions(s, QBARS),
    s3: barRowsQ(
      [
        { key: "agri", rows: yoy(s[C.agri] ?? []) },
        { key: "industry", rows: yoy(s[C.industry] ?? []) },
        { key: "constr", rows: yoy(s[C.constr] ?? []) },
        { key: "services", rows: yoy(s[C.services] ?? []) },
      ],
      QBARS,
    ),
    s4inv: barRowsQ(
      [
        { key: "construction", rows: yoy(s[C.gfcfConstruction] ?? []) },
        { key: "machinery", rows: yoy(s[C.gfcfMachinery] ?? []) },
        { key: "other", rows: yoy(s[C.gfcfOther] ?? []) },
      ],
      QBARS,
    ),
    s5cons: barRowsQ(
      [
        { key: "durable", rows: yoy(s[C.consDurable] ?? []) },
        { key: "semidur", rows: yoy(s[C.consSemidur] ?? []) },
        { key: "nondur", rows: yoy(s[C.consNondur] ?? []) },
        { key: "services", rows: yoy(s[C.consServices] ?? []) },
      ],
      QBARS,
    ),
    s6: barRowsQ([{ key: "gov", rows: yoy(s[C.gov] ?? []) }], QBARS),
    hasTuik: (s[C.consDurable]?.length ?? 0) > 0,

    expTable: buildTable(
      s,
      [
        { label: "Household consumption", code: C.cons },
        { label: "Government consumption", code: C.gov },
        { label: "Gross fixed capital formation", code: C.inv },
        { label: "Exports", code: C.exp },
        { label: "Imports", code: C.imp },
        { label: "GDP", code: C.gdpZH },
      ],
      QTABLE,
    ),
    prodTable: buildTable(
      s,
      [
        { label: "Agriculture", code: C.agri },
        { label: "Industry", code: C.industry },
        { label: "Manufacturing", code: C.manuf, indent: true },
        { label: "Construction", code: C.constr },
        { label: "Services", code: C.services },
        { label: "Information & communication", code: C.ict, indent: true },
        { label: "Finance & insurance", code: C.finance, indent: true },
        { label: "Real estate", code: C.realEstate, indent: true },
        { label: "Professional, admin & support", code: C.professional, indent: true },
        { label: "Public admin, education & health", code: C.publicAdmin, indent: true },
        { label: "Other services", code: C.otherServ, indent: true },
        { label: "Gross value added (sectoral total)", code: C.gva },
        { label: "Taxes less subsidies", code: C.taxes },
        { label: "GDP", code: C.gdpZH },
      ],
      QTABLE,
    ),
  };
}
