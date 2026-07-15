/**
 * Loans by economic sector — the BDDK monthly bulletin's sector cut (table 5).
 *
 * The ONLY sectoral view of the loan book anywhere in the project. The weekly
 * `krediler` feed splits the book by product (housing/auto/GPL/cards/SME/
 * commercial); this splits it by ~22 NACE economic sectors, with an NPL stock
 * and a non-cash (guarantee/LC) book per sector. The audited
 * `bank_audit_loans_by_sector` table is a Stage-2/3/ECL RISK lens with coverage
 * gaps — this is loan VOLUME, complete, monthly, sector-aggregate.
 *
 * Two gotchas honored here (see docs/PROJECT_STATE.md loans-by-sector note):
 *  1. Table 5 is in THOUSAND TL; the rest of the app is MILLION TL. Every amount
 *     is divided by 1000 on the way out (`toMn`). NPL ratio = npl/book is
 *     unit-free.
 *  2. The clean, non-overlapping partition is the BOLD rows (`is_subtotal=1`)
 *     excluding the `TOPLAM` grand total — they sum EXACTLY to TOPLAM. Their
 *     non-bold drill-down children and the memo row "Bankalara Kullandırılan
 *     Krediler*" (loans to banks, outside TOPLAM) must never be added in.
 *
 * The super-group overlay (SECTOR_GROUPS) is the one authored artifact: it maps
 * each stored Turkish `item_name` to an English label and one of six buckets.
 * Keyed on `item_name` (stable across 2020-01→2026-04 — verified) rather than
 * `item_order`. An unmapped bold sector keeps its raw label and lands in
 * `services`, so the partition still reconciles to TOPLAM.
 */
import { cachedAll } from "./db";
import { deflate, type Pt } from "./series";
import { cpiYoYByMonth } from "./real-terms";

/** Sektör (entire banking sector) bank-type code in the monthly tables. */
export const SECTOR_BANK_TYPE = "10001";

/** Table 5 amounts are in thousand TL; the app convention is million TL. */
const toMn = (v: number | null | undefined): number => (v == null ? 0 : v / 1000);

export type GroupKey =
  | "consumer"
  | "industry"
  | "trade"
  | "services"
  | "construction"
  | "agri";

/** Stack/label order — largest bucket first (renders at the stack's base). */
export const GROUP_ORDER: GroupKey[] = [
  "consumer",
  "industry",
  "services",
  "trade",
  "construction",
  "agri",
];

export const GROUP_LABELS: Record<GroupKey, string> = {
  consumer: "Consumer",
  industry: "Industry",
  trade: "Trade & tourism",
  services: "Services",
  construction: "Construction",
  agri: "Agriculture",
};

/**
 * Exact stored `item_name` → { English label, super-group }. The 22 bold sector
 * lines of table 5 (Sektör). Strings are byte-for-byte from the DB — do not
 * "tidy" the Turkish characters or the "(a+b+c)" formula suffixes.
 */
export const SECTOR_GROUPS: Record<string, { en: string; group: GroupKey }> = {
  // Consumer / retail
  "Kredi Kartları**": { en: "Credit cards", group: "consumer" },
  "Ferdi Kredi Diğer": { en: "Consumer — general-purpose", group: "consumer" },
  "Ferdi Kredi Konut": { en: "Consumer — housing", group: "consumer" },
  "Ferdi Kredi Otomobil": { en: "Consumer — auto", group: "consumer" },
  // Industry (manufacturing + mining + utilities)
  "İmalat Sanayi (10+...+22+25)": { en: "Manufacturing", group: "industry" },
  "Elektrik, Gaz ve Su Kaynakları Ürt. Dağt. San.": { en: "Energy & utilities", group: "industry" },
  "Madencilik ve Taşocakçılığı (7+8)": { en: "Mining & quarrying", group: "industry" },
  // Trade & tourism
  "Toptan ve Perakende Ticaret, Motorlu Araçlar Servis Hizm. İle Kişisel ve Hane Halkı Ürünleri (29+30+31)":
    { en: "Wholesale & retail trade", group: "trade" },
  "Otel ve Restoranlar (Turizm) (33+34+35)": { en: "Tourism (hotels & restaurants)", group: "trade" },
  // Construction
  "İnşaat": { en: "Construction", group: "construction" },
  // Agriculture
  "Tarım, Avcılık ve Ormancılık (2+3+4)": { en: "Agriculture & forestry", group: "agri" },
  "Balıkçılık": { en: "Fishing", group: "agri" },
  // Services (transport, financial, real-estate, public, and the small tail)
  "Taşımacılık, Depolama ve Haberleşme (37+38+...+43)": { en: "Transport & communication", group: "services" },
  "Emlak Kom., Kiralama ve İşletmecilik Faal. (51+52+53+54)": { en: "Real estate & business", group: "services" },
  "Finansal Aracılık (45+47+48+49)": { en: "Financial intermediation", group: "services" },
  "Savunma ve Kamu Yönetimi ve Zorunlu Sosyal Güv. Kurumları": { en: "Public administration", group: "services" },
  "Sağlık ve Sosyal Hizmetler": { en: "Health & social work", group: "services" },
  "Diğer Hizmetler (59+60+61+62)": { en: "Other services", group: "services" },
  "Eğitim": { en: "Education", group: "services" },
  "İşçi Çalıştıran Özel Kişiler": { en: "Households w/ employees", group: "services" },
  "Uluslararası Örgüt ve Kuruluşlar": { en: "Extraterritorial orgs", group: "services" },
  "Diğer": { en: "Other", group: "services" },
};

/** Bold parents that are NOT a leaf sector: the grand total. (Memo rows are not
 *  bold, so they never enter the partition.) */
const TOPLAM = "TOPLAM";

/** A sector counts as "material" (drives dispersion / heatmap) above this share. */
export const MATERIAL_SHARE = 1; // %

interface SectorLoanRow {
  year: number;
  month: number;
  item_order: number;
  item_name: string;
  is_subtotal: number;
  total_amount: number | null;
  npl_amount: number | null;
  non_cash_amount: number | null;
}

export interface SectorSnapshot {
  key: string; // stable slug (item_order) — BarByBank category key
  itemName: string;
  label: string;
  group: GroupKey;
  book: number; // million TL
  share: number; // % of TOPLAM
  npl: number; // NPL stock, million TL
  nplRatio: number; // %
  nonCash: number; // million TL
}

export interface GroupSnapshot {
  key: GroupKey;
  label: string;
  book: number; // million TL
  share: number; // %
  npl: number;
  nplRatio: number;
}

export interface SectorMover {
  key: GroupKey;
  label: string;
  shareThen: number | null; // % 12m ago
  shareNow: number | null; // %
}

export interface HeatmapPayload {
  rows: { key: string; label: string; group: GroupKey }[];
  periods: string[]; // quarter labels ascending, e.g. "2024Q2"
  /** NPL ratio (%) per (row.key | period); null where absent. */
  cells: Record<string, number | null>;
}

export interface LoansBySectorData {
  asOf: string; // "YYYY-MM"
  totalBook: number; // million TL
  totalNpl: number; // million TL
  headlineNplRatio: number; // %
  sectors: SectorSnapshot[]; // latest, ~22, sorted by book desc
  groups: GroupSnapshot[]; // latest, GROUP_ORDER
  /** Wide rows for StackedArea: { period, [group]: million-TL book }. */
  groupStack: Record<string, string | number>[]; // all periods, per-group levels
  totalBookSeries: Pt[]; // million TL
  bookYoYNominal: Pt[]; // %
  bookYoYReal: Pt[]; // % (CPI-deflated; may trail by a month)
  nplRatioSeries: Pt[]; // headline NPL ratio %, over time
  consumerShareSeries: Pt[]; // consumer group share %, over time
  movers: SectorMover[]; // 12m group share change
  heatmap: HeatmapPayload;
}

const period = (y: number, m: number): string => `${y}-${String(m).padStart(2, "0")}`;
const prevYearKey = (p: string): string => `${Number(p.slice(0, 4)) - 1}${p.slice(4)}`;
const groupOf = (name: string): GroupKey => SECTOR_GROUPS[name]?.group ?? "services";
const labelOf = (name: string): string => SECTOR_GROUPS[name]?.en ?? name;

/** Pure: fold the raw table-5 rows into the page's typed struct. */
export function buildLoansBySector(
  rows: SectorLoanRow[],
  cpiYoY: Map<string, number>,
): LoansBySectorData {
  // Bucket rows by period, splitting the grand total from the sector partition.
  const byPeriod = new Map<string, { toplam: SectorLoanRow | null; sectors: SectorLoanRow[] }>();
  for (const r of rows) {
    const p = period(r.year, r.month);
    const slot = byPeriod.get(p) ?? { toplam: null, sectors: [] };
    if (Number(r.is_subtotal) === 1) {
      if (r.item_name.trim().toUpperCase().startsWith(TOPLAM)) slot.toplam = r;
      else slot.sectors.push(r);
    }
    byPeriod.set(p, slot);
  }
  const periods = [...byPeriod.keys()].sort();
  const asOf = periods.at(-1) ?? "";

  // ---- per-period group levels (million TL) + total, for the stack & series --
  const groupStack: Record<string, string | number>[] = [];
  const totalBookSeries: Pt[] = [];
  const nplRatioSeries: Pt[] = [];
  const consumerShareSeries: Pt[] = [];
  const groupShareByPeriod = new Map<string, Map<GroupKey, number>>();

  for (const p of periods) {
    const { toplam, sectors } = byPeriod.get(p)!;
    const total = toMn(toplam?.total_amount) || sectors.reduce((a, s) => a + toMn(s.total_amount), 0);
    const totalNplP = sectors.reduce((a, s) => a + toMn(s.npl_amount), 0);

    const gBook = Object.fromEntries(GROUP_ORDER.map((g) => [g, 0])) as Record<GroupKey, number>;
    for (const s of sectors) gBook[groupOf(s.item_name)] += toMn(s.total_amount);

    groupStack.push({ period: p, ...gBook });
    totalBookSeries.push({ period: p, value: total });
    nplRatioSeries.push({ period: p, value: total > 0 ? (totalNplP / total) * 100 : null });

    const shares = new Map<GroupKey, number>();
    for (const g of GROUP_ORDER) shares.set(g, total > 0 ? (gBook[g] / total) * 100 : 0);
    groupShareByPeriod.set(p, shares);
    consumerShareSeries.push({ period: p, value: total > 0 ? (gBook.consumer / total) * 100 : null });
  }

  // ---- whole-book growth: nominal YoY (month-key paired) then CPI-deflated ----
  const bookMap = new Map(totalBookSeries.map((r) => [r.period, r.value]));
  const bookYoYNominal: Pt[] = [];
  for (const { period: p, value } of totalBookSeries) {
    const base = bookMap.get(prevYearKey(p));
    if (value != null && base != null && base > 0) {
      bookYoYNominal.push({ period: p, value: (value / base - 1) * 100 });
    }
  }
  const bookYoYReal = deflate(bookYoYNominal, cpiYoY);

  // ---- latest snapshot: the 22 sectors + the 6 groups ------------------------
  const latest = byPeriod.get(asOf) ?? { toplam: null, sectors: [] };
  const totalBook =
    toMn(latest.toplam?.total_amount) || latest.sectors.reduce((a, s) => a + toMn(s.total_amount), 0);
  const totalNpl = latest.sectors.reduce((a, s) => a + toMn(s.npl_amount), 0);

  const sectors: SectorSnapshot[] = latest.sectors
    .map((s): SectorSnapshot => {
      const book = toMn(s.total_amount);
      const npl = toMn(s.npl_amount);
      return {
        key: `s${s.item_order}`,
        itemName: s.item_name,
        label: labelOf(s.item_name),
        group: groupOf(s.item_name),
        book,
        share: totalBook > 0 ? (book / totalBook) * 100 : 0,
        npl,
        nplRatio: book > 0 ? (npl / book) * 100 : 0,
        nonCash: toMn(s.non_cash_amount),
      };
    })
    .sort((a, b) => b.book - a.book);

  const groups: GroupSnapshot[] = GROUP_ORDER.map((key): GroupSnapshot => {
    const members = sectors.filter((s) => s.group === key);
    const book = members.reduce((a, s) => a + s.book, 0);
    const npl = members.reduce((a, s) => a + s.npl, 0);
    return {
      key,
      label: GROUP_LABELS[key],
      book,
      share: totalBook > 0 ? (book / totalBook) * 100 : 0,
      npl,
      nplRatio: book > 0 ? (npl / book) * 100 : 0,
    };
  });

  // ---- 12m group share movers -----------------------------------------------
  const nowShares = groupShareByPeriod.get(asOf);
  const thenShares = groupShareByPeriod.get(prevYearKey(asOf));
  const movers: SectorMover[] = GROUP_ORDER.map((key) => ({
    key,
    label: GROUP_LABELS[key],
    shareThen: thenShares?.get(key) ?? null,
    shareNow: nowShares?.get(key) ?? null,
  }));

  // ---- heatmap: material sectors × quarter-end months, coloured by NPL ratio --
  const material = sectors.filter((s) => s.share >= MATERIAL_SHARE).slice(0, 14);
  const quarterPeriods = periods.filter((p) => [3, 6, 9, 12].includes(Number(p.slice(5, 7)))).slice(-10);
  const nplByKeyPeriod = new Map<string, number | null>();
  for (const p of quarterPeriods) {
    const slot = byPeriod.get(p);
    if (!slot) continue;
    for (const s of slot.sectors) {
      const book = toMn(s.total_amount);
      nplByKeyPeriod.set(`s${s.item_order}|${p}`, book > 0 ? (toMn(s.npl_amount) / book) * 100 : null);
    }
  }
  const qLabel = (p: string) => `${p.slice(0, 4)}Q${Math.ceil(Number(p.slice(5, 7)) / 3)}`;
  const heatmap: HeatmapPayload = {
    rows: material.map((s) => ({ key: s.key, label: s.label, group: s.group })),
    periods: quarterPeriods.map(qLabel),
    cells: Object.fromEntries(
      material.flatMap((s) =>
        quarterPeriods.map((p) => [`${s.key}|${qLabel(p)}`, nplByKeyPeriod.get(`${s.key}|${p}`) ?? null]),
      ),
    ),
  };

  return {
    asOf,
    totalBook,
    totalNpl,
    headlineNplRatio: totalBook > 0 ? (totalNpl / totalBook) * 100 : 0,
    sectors,
    groups,
    groupStack,
    totalBookSeries,
    bookYoYNominal,
    bookYoYReal,
    nplRatioSeries,
    consumerShareSeries,
    movers,
    heatmap,
  };
}

/** Fetch table-5 (Sektör) + CPI and fold into the page struct. */
export async function loansBySector(): Promise<LoansBySectorData> {
  const [rows, cpiYoY] = await Promise.all([
    cachedAll<SectorLoanRow>(
      `SELECT year, month, item_order, item_name, is_subtotal,
              total_amount, npl_amount, non_cash_amount
         FROM loans
        WHERE table_number = 5 AND currency = 'TL' AND bank_type_code = ?
        ORDER BY year, month, item_order`,
      [SECTOR_BANK_TYPE],
    ),
    cpiYoYByMonth(),
  ]);
  return buildLoansBySector(rows, cpiYoY);
}
