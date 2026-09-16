import type { Metadata } from "next";
import { notFound } from "next/navigation";
import {
  evdsMulti,
  evdsSeries,
  weeklyDollarization,
  weeklyGrowth,
  weeklyGrowthByOwnership,
  weeklyOwnershipRatio,
  weeklySeries,
  WEEKLY_BANK_TYPES,
  type TimeSeriesRow,
  type WeeklyRow,
} from "@/app/lib/metrics";
import { sectorLiquidityRatios } from "@/app/lib/audit-ratios";
import { cpiYoYByMonth } from "@/app/lib/real-terms";
import {
  contributions,
  creditBridge,
  deflate,
  fxAdjustedGrowth,
  type Pt,
} from "@/app/lib/credit";
import SectorPrototype, {
  type CreditPrototypeData,
  type LiquidityPrototypeData,
  type PrototypeData,
} from "./SectorPrototype";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Sector V2 — local prototype",
  robots: { index: false, follow: false },
};

const CREDIT = "krediler";
const TOTAL_LOANS = "1.0.1";
const HOUSING = "1.0.4";
const AUTO = "1.0.5";
const GPL = "1.0.6";
const CARDS = "1.0.8";
const SME = "1.0.11";
const COMMERCIAL = "1.0.12";

const GROUP_LABELS: Record<string, string> = {
  "10001": "Sektör",
  "10003": "Yerli özel",
  "10004": "Kamu",
  "10005": "Yabancı",
  "10006": "Katılım",
  "10007": "Kalkınma ve yatırım",
};

const trDate = (period: string | null | undefined): string => {
  if (!period) return "—";
  const date = new Date(`${period.slice(0, 10)}T00:00:00Z`);
  if (Number.isNaN(date.valueOf())) return period;
  return new Intl.DateTimeFormat("tr-TR", {
    day: "numeric",
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  }).format(date);
};

const quarterLabel = (period: string | null | undefined): string => {
  if (!period) return "—";
  const compact = /^(\d{4})Q([1-4])$/.exec(period);
  if (compact) return `${compact[1]} ${compact[2]}Ç`;
  const dated = /^(\d{4})-(\d{2})/.exec(period);
  return dated ? `${dated[1]} ${Math.ceil(Number(dated[2]) / 3)}Ç` : period;
};

function lastValue(rows: Array<{ value: number | null }>): number | null {
  return rows.at(-1)?.value ?? null;
}

function toPoint(rows: WeeklyRow[]): Pt[] {
  return rows.map((row) => ({ period: row.period, value: row.value }));
}

function pivotSeries(
  parts: Array<{ key: string; rows: Array<{ period: string; value: number | null }> }>,
): Array<Record<string, string | number | null>> {
  const byPeriod = new Map<string, Record<string, string | number | null>>();
  for (const { key, rows } of parts) {
    for (const row of rows) {
      const current = byPeriod.get(row.period) ?? { period: row.period };
      current[key] = row.value;
      byPeriod.set(row.period, current);
    }
  }
  return [...byPeriod.values()].sort((a, b) => String(a.period).localeCompare(String(b.period)));
}

function groupSnapshots(rows: TimeSeriesRow[], comparisonPeriods = 13) {
  const codes = [...new Set(rows.map((row) => row.bank_type_code))];
  return codes.flatMap((code) => {
    const series = rows
      .filter((row) => row.bank_type_code === code)
      .sort((a, b) => a.period.localeCompare(b.period));
    const current = series.at(-1);
    const prior = series.at(-1 - comparisonPeriods);
    if (!current) return [];
    return [{
      code,
      label: GROUP_LABELS[code] ?? code,
      value: current.value,
      previous: prior?.value ?? null,
      delta: prior ? current.value - prior.value : null,
    }];
  }).sort((a, b) => b.value - a.value);
}

async function loadCredit(): Promise<CreditPrototypeData> {
  const sector = [WEEKLY_BANK_TYPES.SECTOR];
  const allGroups = Object.values(WEEKLY_BANK_TYPES);
  const [
    loans,
    tlLoans,
    fxLoans,
    growthByGroup,
    commercial,
    cards,
    generalPurpose,
    housing,
    auto,
    sme,
    cpi,
    usdTry,
  ] = await Promise.all([
    weeklySeries(CREDIT, TOTAL_LOANS, "TOTAL", sector, 156),
    weeklySeries(CREDIT, TOTAL_LOANS, "TL", sector, 156),
    weeklySeries(CREDIT, TOTAL_LOANS, "FX", sector, 156),
    weeklyGrowth(CREDIT, TOTAL_LOANS, "TOTAL", 52, allGroups, 104),
    weeklySeries(CREDIT, COMMERCIAL, "TOTAL", sector, 156),
    weeklySeries(CREDIT, CARDS, "TOTAL", sector, 156),
    weeklySeries(CREDIT, GPL, "TOTAL", sector, 156),
    weeklySeries(CREDIT, HOUSING, "TOTAL", sector, 156),
    weeklySeries(CREDIT, AUTO, "TOTAL", sector, 156),
    weeklySeries(CREDIT, SME, "TOTAL", sector, 156),
    cpiYoYByMonth(),
    evdsSeries("TP.DK.USD.A", 4),
  ]);

  const sectorGrowth = growthByGroup.filter(
    (row) => row.bank_type_code === WEEKLY_BANK_TYPES.SECTOR,
  );
  const fxAdjusted = fxAdjustedGrowth(toPoint(tlLoans), toPoint(fxLoans), usdTry);
  const realFxAdjusted = deflate(fxAdjusted, cpi);
  const bridge = creditBridge(sectorGrowth, fxAdjusted, cpi);
  const attribution = contributions(toPoint(loans), [
    { key: "commercial", label: "Ticari", rows: toPoint(commercial) },
    { key: "cards", label: "Bireysel kartlar", rows: toPoint(cards) },
    { key: "gpl", label: "İhtiyaç", rows: toPoint(generalPurpose) },
    { key: "housing", label: "Konut", rows: toPoint(housing) },
    { key: "auto", label: "Taşıt", rows: toPoint(auto) },
  ]);
  const smeCut = contributions(toPoint(loans), [
    { key: "sme", label: "KOBİ", rows: toPoint(sme) },
  ]).items[0] ?? null;

  const tlNow = lastValue(tlLoans);
  const fxNow = lastValue(fxLoans);
  const fxShare = tlNow != null && fxNow != null && tlNow + fxNow > 0
    ? (fxNow / (tlNow + fxNow)) * 100
    : null;

  const headline = bridge.realFxAdj == null
    ? "Reel kredi görünümü için ortak veri kesimi oluşmadı."
    : bridge.realFxAdj < 0
      ? "Nominal büyüme güçlü; kur ve fiyat etkileri çıkarıldığında kredi hacmi daralıyor."
      : "Kredi büyümesi kur ve fiyat etkileri çıkarıldıktan sonra da reel hacim üretiyor.";

  return {
    kind: "credit",
    title: "Krediler",
    question: "Kredi büyümesinin ne kadarı gerçek hacim artışı?",
    cadence: "Haftalık görünüm",
    asOf: trDate(bridge.asOfNominal),
    commonCutoff: trDate(bridge.asOfReal),
    headline,
    summary: [
      { label: "Nominal, 52 hafta", value: bridge.nominal, format: "pct" },
      { label: "Reel ve sabit kur", value: bridge.realFxAdj, format: "pct" },
      { label: "Kredilerde YP payı", value: fxShare, format: "pct" },
    ],
    bridge: [
      { label: "Nominal", value: bridge.nominalAtReal, kind: "total" },
      { label: "Kur etkisi", value: bridge.currencyPp == null ? null : -bridge.currencyPp, kind: "delta" },
      { label: "Sabit kur", value: bridge.fxAdj, kind: "subtotal" },
      { label: "Enflasyon", value: bridge.inflationPp == null ? null : -bridge.inflationPp, kind: "delta" },
      { label: "Reel, sabit kur", value: bridge.realFxAdj, kind: "total" },
    ],
    trend: pivotSeries([
      { key: "nominal", rows: sectorGrowth },
      { key: "fxAdjusted", rows: fxAdjusted },
      { key: "realFxAdjusted", rows: realFxAdjusted },
    ]).slice(-104),
    contributions: attribution.items.map((item) => ({
      key: item.key,
      label: item.label,
      value: item.pp,
      growth: item.growth,
      level: item.level,
      nested: item.key === "commercial" && smeCut
        ? { label: "Bunun içinde KOBİ", value: smeCut.pp }
        : null,
    })),
    groups: groupSnapshots(growthByGroup, 13),
    sourceNote: "BDDK haftalık bülteni · TCMB USD/TRY · TÜİK TÜFE. Reel seri, yayımlanmış son TÜFE ayındaki ortak haftada kesilir.",
  };
}

async function loadLiquidity(): Promise<LiquidityPrototypeData> {
  const loans = { category: "krediler", itemId: "1.0.1" };
  const deposits = { category: "mevduat", itemId: "4.0.1" };
  const [tlLdr, tlDepositGrowth, dollarization, evds, ratios] = await Promise.all([
    weeklyOwnershipRatio(
      loans.category,
      loans.itemId,
      deposits.category,
      deposits.itemId,
      "TL",
      156,
    ),
    weeklyGrowthByOwnership(deposits.category, deposits.itemId, "TL", 13, 104),
    weeklyDollarization(156),
    evdsMulti(["TP.APIFON3"], 3),
    sectorLiquidityRatios(),
  ]);

  const publicLdr = tlLdr.filter((row) => row.bank_type_code === "PUBLIC");
  const privateLdr = tlLdr.filter((row) => row.bank_type_code === "PRIVATE");
  const funding = (evds["TP.APIFON3"] ?? []).map((row) => ({
    period: row.period_date,
    value: row.value / 1000,
  }));
  const fundingNow = funding.at(-1)?.value ?? null;
  const publicNow = publicLdr.at(-1)?.value ?? null;
  const privateNow = privateLdr.at(-1)?.value ?? null;
  const dollarSector = dollarization.filter((row) => row.bank_type_code === "SECTOR");
  const dollarNow = dollarSector.at(-1)?.value ?? null;
  const ratioPeriod = ratios.at(-1)?.period ?? null;
  const latestRatio = (code: string) => ratios.filter((row) => row.bank_type_code === code).at(-1)?.value ?? null;

  const headline = fundingNow == null
    ? "Günlük sistem likiditesi için güncel gözlem bulunamadı."
    : fundingNow < 0
      ? "Bankacılık sistemi lirada açık veriyor; fonlama baskısı TCMB bilançosunda doğrudan görülüyor."
      : "Bankacılık sistemi lirada fazla veriyor; fazla likidite TCMB’ye geri dönüyor.";

  const growthSnapshots = ["PUBLIC", "PRIVATE"].flatMap((code) => {
    const rows = tlDepositGrowth.filter((row) => row.bank_type_code === code);
    const current = rows.at(-1);
    if (!current) return [];
    return [{
      code,
      label: code === "PUBLIC" ? "Kamu" : "Özel",
      value: current.value,
      previous: rows.at(-14)?.value ?? null,
      delta: rows.at(-14) ? current.value - (rows.at(-14)?.value ?? current.value) : null,
    }];
  });

  return {
    kind: "liquidity",
    title: "Likidite",
    question: "Günlük likidite açığı ile düzenleyici tamponlar birlikte ne söylüyor?",
    cadence: "Günlük görünüm",
    asOf: trDate(funding.at(-1)?.period),
    weeklyAsOf: trDate(tlLdr.at(-1)?.period),
    quarterlyAsOf: quarterLabel(ratioPeriod),
    headline,
    summary: [
      { label: "Net TCMB fonlaması", value: fundingNow, format: "bn" },
      { label: "Özel TL kredi/mevduat", value: privateNow, format: "pct" },
      { label: "Mevduatta YP payı", value: dollarNow, format: "pct" },
    ],
    funding: funding.slice(-400),
    ldr: pivotSeries([
      { key: "public", rows: publicLdr },
      { key: "private", rows: privateLdr },
    ]).slice(-104),
    ownershipGrowth: growthSnapshots,
    regulatory: [
      { label: "Likidite karşılama oranı", short: "LCR", value: latestRatio("LCR"), floor: 100 },
      { label: "Net istikrarlı fonlama oranı", short: "NSFR", value: latestRatio("NSFR"), floor: 100 },
    ],
    publicLdr: publicNow,
    privateLdr: privateNow,
    sourceNote: "TCMB günlük sistem likiditesi · BDDK haftalık TL kredi ve mevduat · BRSA çeyreklik denetimli LCR/NSFR.",
  };
}

export default async function SectorV2Prototype({
  searchParams,
}: {
  searchParams: Promise<{ page?: string }>;
}) {
  // Design studies are local artifacts, never a public product route.
  if (process.env.NODE_ENV !== "development") notFound();
  const { page } = await searchParams;
  const data: PrototypeData = page === "liquidity"
    ? await loadLiquidity()
    : await loadCredit();

  return <SectorPrototype data={data} />;
}
