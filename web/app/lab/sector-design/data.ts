import {
  evdsSeries, weeklyGrowth, weeklyOwnershipRatio, weeklySeries,
  WEEKLY_BANK_TYPES, WEEKLY_BANK_TYPE_LABELS,
} from "@/app/lib/metrics";
import { cpiYoYByMonth } from "@/app/lib/real-terms";
import { contributions, creditBridge, deflate, fxAdjustedGrowth } from "@/app/lib/credit";
import { sectorLiquidityRatios } from "@/app/lib/audit-ratios";

export type PlotRow = { period: string; [key: string]: string | number | null };

function pivot(parts: { key: string; rows: { period: string; value: number | null }[] }[]): PlotRow[] {
  const result = new Map<string, PlotRow>();
  for (const { key, rows } of parts) for (const row of rows) {
    const point = result.get(row.period) ?? { period: row.period };
    point[key] = row.value;
    result.set(row.period, point);
  }
  return [...result.values()].sort((a, b) => a.period.localeCompare(b.period));
}

export async function loadDesignData() {
  const sector = [WEEKLY_BANK_TYPES.SECTOR];
  const segments = [
    { key: "commercial", label: "Ticari", id: "1.0.12" },
    { key: "cards", label: "Bireysel kartlar", id: "1.0.8" },
    { key: "personal", label: "İhtiyaç", id: "1.0.6" },
    { key: "housing", label: "Konut", id: "1.0.4" },
    { key: "auto", label: "Taşıt", id: "1.0.5" },
  ];
  const [nominal, tl, fx, total, cpi, usd, segmentRows, fundingRows, ldr, ratios] = await Promise.all([
    weeklyGrowth("krediler", "1.0.1", "TOTAL", 52, undefined, 156),
    weeklySeries("krediler", "1.0.1", "TL", sector, 210),
    weeklySeries("krediler", "1.0.1", "FX", sector, 210),
    weeklySeries("krediler", "1.0.1", "TOTAL", sector, 210),
    cpiYoYByMonth(), evdsSeries("TP.DK.USD.A", 5),
    Promise.all(segments.map((s) => weeklySeries("krediler", s.id, "TOTAL", sector, 210))),
    evdsSeries("TP.APIFON3", 3),
    weeklyOwnershipRatio("krediler", "1.0.1", "mevduat", "4.0.1", "TL", 156),
    sectorLiquidityRatios(),
  ]);
  const sectorNominal = nominal.filter((r) => r.bank_type_code === WEEKLY_BANK_TYPES.SECTOR);
  const adjusted = fxAdjustedGrowth(tl, fx, usd);
  const real = deflate(adjusted, cpi);
  const bridge = creditBridge(sectorNominal, adjusted, cpi);
  const groups = Object.values(WEEKLY_BANK_TYPES).map((code) => ({
    code, label: WEEKLY_BANK_TYPE_LABELS[code],
    rows: nominal.filter((r) => r.bank_type_code === code),
  }));
  return {
    credit: {
      bridge,
      trend: pivot([{ key: "nominal", rows: sectorNominal }, { key: "adjusted", rows: adjusted }, { key: "real", rows: real }]),
      attribution: contributions(total, segments.map((s, i) => ({ ...s, rows: segmentRows[i] }))),
      groups,
    },
    liquidity: {
      funding: fundingRows.map((r) => ({ period: r.period_date, value: r.value / 1000 })),
      ldr: pivot(["PUBLIC", "PRIVATE"].map((key) => ({ key, rows: ldr.filter((r) => r.bank_type_code === key) }))),
      regulatory: ["LCR", "NSFR"].map((code) => ({ code, row: ratios.filter((r) => r.bank_type_code === code).at(-1) ?? null })),
    },
  };
}

export type DesignData = Awaited<ReturnType<typeof loadDesignData>>;
