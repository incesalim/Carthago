/**
 * Non-bank financial sector data layer — "how much of banking business is done
 * by non-banks?" (financial disintermediation).
 *
 * Compares the BDDK non-bank monthly bulletin (`nonbank_balance_sheet`:
 * financial leasing / factoring / financing companies) against the in-D1
 * banking-sector aggregate (`balance_sheet`, bank_type_code = 10001). Both
 * bulletins are published in Million TL, so the two sides are directly
 * comparable and same-source — the clean apples-to-apples denominator.
 *
 * Scope: the three credit-substitution sectors (they compete with bank
 * lending). VYŞ asset-management is a COMPLEMENT (buys NPLs from banks) and
 * savings-finance isn't in this bulletin — both are out of scope here.
 *
 * All money values stay in Million TL end-to-end; chart formatters (`bn`/`trn`)
 * rescale at render. Shares are returned already in percent (e.g. 2.87).
 */
import { cachedAll } from "@/app/lib/db";
import type { StackPoint } from "@/app/components/StackedArea";

export const SECTORS = [
  { code: "leasing", label: "Financial leasing" },
  { code: "factoring", label: "Factoring" },
  { code: "financing", label: "Financing cos." },
] as const;

export interface Point {
  period_date: string;
  value: number;
}

interface NbAgg {
  sector_code: string;
  year: number;
  month: number;
  assets: number | null; // VARLIK TOPLAMI
  credit: number | null; // roman-V amortized-cost financial assets (the lending book)
  equity: number | null; // XIV. ÖZKAYNAKLAR
}

interface BankAgg {
  year: number;
  month: number;
  assets: number | null; // TOPLAM AKTİFLER
  credit: number | null; // Krediler (net loans)
}

const pd = (y: number, m: number) => `${y}-${String(m).padStart(2, "0")}-01`;
const pkey = (y: number, m: number) => y * 100 + m;

const MONTHS_EN = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

/** One aggregate row per (sector, period): assets, lending book, equity. */
function nbfiRows() {
  return cachedAll<NbAgg>(
    `SELECT sector_code, year, month,
        MAX(CASE WHEN item_name = 'VARLIK TOPLAMI' THEN amount_total END) AS assets,
        MAX(CASE WHEN item_name LIKE 'V. İTFA EDİLMİŞ MALİYETİ%' THEN amount_total END) AS credit,
        MAX(CASE WHEN item_name LIKE 'XIV. ÖZKAYNAKLAR%' THEN amount_total END) AS equity
     FROM nonbank_balance_sheet
     WHERE source = 'bddk'
     GROUP BY sector_code, year, month
     ORDER BY year, month`,
  );
}

/** Banking-sector aggregate (bank_type_code 10001): total assets + net loans. */
function bankRows() {
  return cachedAll<BankAgg>(
    `SELECT year, month,
        MAX(CASE WHEN item_name = 'TOPLAM AKTİFLER' THEN amount_total END) AS assets,
        MAX(CASE WHEN item_name LIKE 'Krediler%' THEN amount_total END) AS credit
     FROM balance_sheet
     WHERE bank_type_code = '10001' AND currency = 'TL'
     GROUP BY year, month
     ORDER BY year, month`,
  );
}

export interface SectorLatest {
  code: string;
  label: string;
  assets: number; // Million TL
  credit: number; // Million TL
  equity: number | null; // Million TL
  growthYoY: number | null; // % change in assets vs 12m earlier
  shareOfBankLoans: number | null; // sector lending book ÷ bank loans, %
}

export interface NonBankData {
  hasData: boolean;
  asOfLabel: string; // "April 2026"
  asOfPeriod: string; // "2026-04"
  // KPIs at the latest common period (Million TL / %)
  nbfiAssets: number;
  nbfiCredit: number;
  bankAssets: number;
  bankCredit: number;
  assetSharePct: number | null;
  creditSharePct: number | null;
  // Trends (share %, for TimeSeriesChart)
  shareTrend: Record<string, Point[]>;
  // Sector assets composition over time (Million TL, for StackedArea)
  sectorAssetsStack: StackPoint[];
  // Per-sector snapshot at the latest period
  sectors: SectorLatest[];
}

const EMPTY: NonBankData = {
  hasData: false,
  asOfLabel: "—",
  asOfPeriod: "",
  nbfiAssets: 0,
  nbfiCredit: 0,
  bankAssets: 0,
  bankCredit: 0,
  assetSharePct: null,
  creditSharePct: null,
  shareTrend: {},
  sectorAssetsStack: [],
  sectors: [],
};

export async function getNonBankData(): Promise<NonBankData> {
  const [nb, bk] = await Promise.all([nbfiRows(), bankRows()]);
  if (nb.length === 0) return EMPTY;

  const bank = new Map<number, BankAgg>();
  for (const r of bk) bank.set(pkey(r.year, r.month), r);

  // Group non-bank rows by period → sector map.
  const periods = new Map<number, { y: number; m: number; bySector: Map<string, NbAgg> }>();
  for (const r of nb) {
    const k = pkey(r.year, r.month);
    let p = periods.get(k);
    if (!p) {
      p = { y: r.year, m: r.month, bySector: new Map() };
      periods.set(k, p);
    }
    p.bySector.set(r.sector_code, r);
  }

  const keys = [...periods.keys()].sort((a, b) => a - b);
  const fullCoverage = (k: number) =>
    SECTORS.every((s) => periods.get(k)?.bySector.get(s.code)?.assets != null);

  const assetShare: Point[] = [];
  const creditShare: Point[] = [];
  const stack: StackPoint[] = [];

  for (const k of keys) {
    if (!fullCoverage(k)) continue; // only periods with all 3 sectors on the charts
    const p = periods.get(k)!;
    const b = bank.get(k);
    let aSum = 0;
    let cSum = 0;
    const row: StackPoint = { period: pd(p.y, p.m) };
    for (const s of SECTORS) {
      const r = p.bySector.get(s.code)!;
      aSum += r.assets ?? 0;
      cSum += r.credit ?? 0;
      row[s.code] = r.assets ?? 0;
    }
    stack.push(row);
    if (b?.assets != null) {
      assetShare.push({ period_date: pd(p.y, p.m), value: (100 * aSum) / (b.assets + aSum) });
    }
    if (b?.credit != null && cSum > 0) {
      creditShare.push({ period_date: pd(p.y, p.m), value: (100 * cSum) / (b.credit + cSum) });
    }
  }

  // Latest period with full sector coverage AND a banking figure.
  const latestK = [...keys].reverse().find((k) => fullCoverage(k) && bank.get(k)?.assets != null);
  if (latestK === undefined) return { ...EMPTY, shareTrend: {}, sectorAssetsStack: stack };

  const lp = periods.get(latestK)!;
  const b = bank.get(latestK)!;
  const prev = periods.get(latestK - 100); // same month, prior year

  let nbfiAssets = 0;
  let nbfiCredit = 0;
  const sectors: SectorLatest[] = SECTORS.map((s) => {
    const r = lp.bySector.get(s.code)!;
    const assets = r.assets ?? 0;
    const credit = r.credit ?? 0;
    nbfiAssets += assets;
    nbfiCredit += credit;
    const prevAssets = prev?.bySector.get(s.code)?.assets ?? null;
    return {
      code: s.code,
      label: s.label,
      assets,
      credit,
      equity: r.equity,
      growthYoY: prevAssets && prevAssets > 0 ? (100 * (assets - prevAssets)) / prevAssets : null,
      shareOfBankLoans: b.credit ? (100 * credit) / b.credit : null,
    };
  });

  return {
    hasData: true,
    asOfLabel: `${MONTHS_EN[lp.m - 1]} ${lp.y}`,
    asOfPeriod: `${lp.y}-${String(lp.m).padStart(2, "0")}`,
    nbfiAssets,
    nbfiCredit,
    bankAssets: b.assets ?? 0,
    bankCredit: b.credit ?? 0,
    assetSharePct: b.assets ? (100 * nbfiAssets) / (b.assets + nbfiAssets) : null,
    creditSharePct: b.credit ? (100 * nbfiCredit) / (b.credit + nbfiCredit) : null,
    shareTrend: {
      "Share of sector assets": assetShare,
      "Share of sector credit": creditShare,
    },
    sectorAssetsStack: stack,
    sectors,
  };
}
