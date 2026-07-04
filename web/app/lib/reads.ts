/**
 * Per-tab "Read" compute — recomputes each tab's DETERMINISTIC TabTakeaway
 * (the same one each page produces via insights.ts) OUTSIDE the page render, so
 * the headline generator can rewrite it. Consumed by GET /api/reads.
 *
 * Each computer mirrors its page's insight inputs (same metrics calls + helpers).
 * DRIFT SAFETY: if a computer ever diverges from its page, the `det_hash` gate in
 * read-headlines.ts falls that tab back to the deterministic headline — never a
 * wrong number, just no LLM benefit until realigned. So keep these in sync with
 * the pages, but a mismatch can only under-deliver, never mislead. Adding/removing
 * a tab = edit READ_COMPUTERS + wrap (or unwrap) its page's <Takeaway>.
 */
import {
  assetQualityInsights,
  capitalInsights,
  creditInsights,
  depositsInsights,
  liquidityInsights,
  marketRiskInsights,
  overviewInsights,
  profitabilityInsights,
  type TabTakeaway,
} from "./insights";
import {
  BANK_TYPES,
  WEEKLY_BANK_TYPES,
  consumerNplRatios,
  commercialNplRatios,
  equityYoY,
  evdsSeries,
  leverage,
  ratioCar,
  ratioCoverage,
  ratioLdr,
  ratioNim,
  ratioNpl,
  ratioOpex,
  ratioRoa,
  ratioRoe,
  totalAssetsYoY,
  totalDepositsYoY,
  totalLoansYoY,
  weeklyDollarization,
  weeklyGrowth,
  weeklyOwnershipRatio,
  weeklySeries,
  type TimeSeriesRow,
  type WeeklyRow,
} from "./metrics";
import { sectorCapitalRatios, sectorLiquidityRatios } from "./audit-ratios";
import { sectorStageShares } from "./credit-risk";
import { fxNopToCapital, repricingGap1y } from "./market-risk";

// --- helpers copied verbatim from the pages (kept in sync via the det_hash gate) ---

/** FX share = fx / (tl + fx) per period (×100). */
function computeFxShare(tl: WeeklyRow[], fx: WeeklyRow[]): TimeSeriesRow[] {
  const tlMap = new Map(tl.map((r) => [r.period + "|" + r.bank_type_code, r.value]));
  const out: TimeSeriesRow[] = [];
  for (const r of fx) {
    const t = tlMap.get(r.period + "|" + r.bank_type_code);
    if (t == null || r.value == null || t + r.value === 0) continue;
    out.push({ period: r.period, bank_type_code: r.bank_type_code, value: (r.value * 100) / (t + r.value) });
  }
  return out;
}

/** Demand share = demand / total per period (×100). [deposits] */
function demandShare(total: WeeklyRow[], demand: WeeklyRow[]): TimeSeriesRow[] {
  const totalMap = new Map(total.map((r) => [r.period + "|" + r.bank_type_code, r.value]));
  const out: TimeSeriesRow[] = [];
  for (const r of demand) {
    const t = totalMap.get(r.period + "|" + r.bank_type_code);
    if (t == null || r.value == null || t === 0) continue;
    out.push({ period: r.period, bank_type_code: r.bank_type_code, value: (r.value * 100) / t });
  }
  return out;
}

/** Sum several weekly series element-wise by (period, bank_type_code). [deposits] */
function sumWeekly(parts: WeeklyRow[][]): WeeklyRow[] {
  const byKey = new Map<string, WeeklyRow>();
  for (const rows of parts) {
    for (const r of rows) {
      if (r.value == null) continue;
      const k = r.period + "|" + r.bank_type_code;
      const cur = byKey.get(k);
      if (cur) cur.value += r.value;
      else byKey.set(k, { period: r.period, bank_type_code: r.bank_type_code, value: r.value });
    }
  }
  return Array.from(byKey.values());
}

/** Consumer NPL-ratio wide rows → long-form (one synthetic code per segment). [asset-quality] */
function ratiosToTrendRows(
  rows: Array<{ period: string; housing: number | null; auto: number | null; gpl: number | null; cards: number | null }>,
): TimeSeriesRow[] {
  const out: TimeSeriesRow[] = [];
  for (const r of rows) {
    if (r.cards != null) out.push({ period: r.period, bank_type_code: "CARDS", value: r.cards });
  }
  return out;
}

/** Commercial NPL-ratio wide rows → long-form. [asset-quality] */
function commercialToTrendRows(
  rows: Array<{ period: string; sme: number | null; commercial: number | null; non_sme: number | null }>,
): TimeSeriesRow[] {
  const out: TimeSeriesRow[] = [];
  for (const r of rows) {
    if (r.sme != null) out.push({ period: r.period, bank_type_code: "SME", value: r.sme });
  }
  return out;
}

/** Long-form rows → TrendChart points. [liquidity] */
function toTrend(rows: (TimeSeriesRow | WeeklyRow)[]): { period: string; bank_type_code: string; value: number }[] {
  return rows.map((r) => ({ period: r.period, bank_type_code: r.bank_type_code, value: r.value }));
}

// --- per-tab computers ---

/** Overview "Sector Pulse" — always sector aggregate. [web/app/page.tsx] */
export async function overviewRead(): Promise<TabTakeaway> {
  const s = [BANK_TYPES.SECTOR];
  const [assetsYoY, loansYoY, depositsYoY, npl, car, ldr, roe] = await Promise.all([
    totalAssetsYoY(s), totalLoansYoY(s), totalDepositsYoY(s),
    ratioNpl(s), ratioCar(s), ratioLdr(s), ratioRoe(s),
  ]);
  return overviewInsights({ assetsYoY, loansYoY, depositsYoY, npl, car, ldr, roe });
}

/** Credit. [web/app/credit/page.tsx] */
export async function creditRead(): Promise<TabTakeaway> {
  const KREDI = "krediler", TOTAL = "1.0.1", CARDS = "1.0.8", SME = "1.0.11";
  const sector = [WEEKLY_BANK_TYPES.SECTOR];
  const pubPriv = [WEEKLY_BANK_TYPES.PRIVATE, WEEKLY_BANK_TYPES.STATE];
  const smeGroups = [WEEKLY_BANK_TYPES.SECTOR, ...pubPriv];
  const [tlSec, fxSec, yoySec, mom4, yoyPubPriv, consCards, smeRaw] = await Promise.all([
    weeklySeries(KREDI, TOTAL, "TL", sector, 156),
    weeklySeries(KREDI, TOTAL, "FX", sector, 156),
    weeklyGrowth(KREDI, TOTAL, "TOTAL", 52, sector, 104),
    weeklyGrowth(KREDI, TOTAL, "TOTAL", 4, sector, 104),
    weeklyGrowth(KREDI, TOTAL, "TOTAL", 52, pubPriv, 104),
    weeklyGrowth(KREDI, CARDS, "TOTAL", 52, sector, 104),
    weeklyGrowth(KREDI, SME, "TOTAL", 52, smeGroups, 104),
  ]);
  return creditInsights({
    yoy: yoySec,
    mom4,
    yoyState: yoyPubPriv.filter((r) => r.bank_type_code === WEEKLY_BANK_TYPES.STATE),
    yoyPrivate: yoyPubPriv.filter((r) => r.bank_type_code === WEEKLY_BANK_TYPES.PRIVATE),
    fxShare: computeFxShare(tlSec, fxSec),
    cardsYoY: consCards,
    smeYoY: smeRaw.filter((r) => r.bank_type_code === WEEKLY_BANK_TYPES.SECTOR),
  });
}

/** Deposits. [web/app/deposits/page.tsx] */
export async function depositsRead(): Promise<TabTakeaway> {
  const MEVDUAT = "mevduat", TOTAL = "4.0.1";
  const DEMAND_PARTS = ["4.0.3", "4.0.6", "4.0.9"];
  const sector = [WEEKLY_BANK_TYPES.SECTOR];
  const [depSector, yoySec, tlSec, fxSec, demandParts, ldr, loansYoY] = await Promise.all([
    weeklySeries(MEVDUAT, TOTAL, "TOTAL", sector, 156),
    weeklyGrowth(MEVDUAT, TOTAL, "TOTAL", 52, sector, 104),
    weeklySeries(MEVDUAT, TOTAL, "TL", sector, 156),
    weeklySeries(MEVDUAT, TOTAL, "FX", sector, 156),
    Promise.all(DEMAND_PARTS.map((id) => weeklySeries(MEVDUAT, id, "TOTAL", sector, 156))),
    ratioLdr([BANK_TYPES.SECTOR]),
    weeklyGrowth("krediler", "1.0.1", "TOTAL", 52, sector, 104),
  ]);
  return depositsInsights({
    yoy: yoySec,
    loansYoY,
    fxShare: computeFxShare(tlSec, fxSec),
    demandShare: demandShare(depSector, sumWeekly(demandParts)),
    ldr: ldr.filter((r) => r.bank_type_code === BANK_TYPES.SECTOR),
  });
}

/** Asset Quality. [web/app/asset-quality/page.tsx] */
export async function assetQualityRead(): Promise<TabTakeaway> {
  const SECTOR = "10001";
  const [npl, coverage, gross, cRatios, commRatios, stageShares] = await Promise.all([
    ratioNpl([SECTOR]),
    ratioCoverage([SECTOR]),
    weeklySeries("takipteki_alacaklar", "2.0.1", "TOTAL", [WEEKLY_BANK_TYPES.SECTOR], 156),
    consumerNplRatios(),
    commercialNplRatios(),
    sectorStageShares(),
  ]);
  return assetQualityInsights({
    npl,
    coverage,
    grossNpl: gross,
    cardsNpl: ratiosToTrendRows(cRatios).filter((r) => r.bank_type_code === "CARDS"),
    smeNpl: commercialToTrendRows(commRatios).filter((r) => r.bank_type_code === "SME"),
    stage2: stageShares.filter((r) => r.bank_type_code === "STAGE2"),
  });
}

/** Capital. [web/app/capital/page.tsx] */
export async function capitalRead(): Promise<TabTakeaway> {
  const s = [BANK_TYPES.SECTOR];
  const [car, capRatios, equity, lev] = await Promise.all([
    ratioCar(s),
    sectorCapitalRatios(),
    equityYoY(s),
    leverage(s),
  ]);
  return capitalInsights({
    car,
    cet1: capRatios.filter((r) => r.bank_type_code === "CET1"),
    equityYoY: equity,
    leverage: lev,
  });
}

/** Profitability. [web/app/profitability/page.tsx] */
export async function profitabilityRead(): Promise<TabTakeaway> {
  const s = [BANK_TYPES.SECTOR];
  const [roe, roa, nim, opex, cpiRaw] = await Promise.all([
    ratioRoe(s), ratioRoa(s), ratioNim(s), ratioOpex(s),
    evdsSeries("TP.TUKFIY2025.GENEL", 10),
  ]);
  // CPI 12m-rolling-average YoY from monthly CPI levels (mirrors the page).
  type Cpi = { period_date: string; value: number };
  const cpi = (cpiRaw as Cpi[]).slice().sort((a, b) => a.period_date.localeCompare(b.period_date));
  const cpiYoY: { period: string; value: number }[] = [];
  for (let i = 12; i < cpi.length; i++) {
    const prev = cpi[i - 12].value;
    if (prev > 0) cpiYoY.push({ period: cpi[i].period_date.slice(0, 7), value: (cpi[i].value / prev - 1) * 100 });
  }
  const cpiAvg: { period: string; value: number }[] = [];
  for (let i = 11; i < cpiYoY.length; i++) {
    let sum = 0;
    for (let j = i - 11; j <= i; j++) sum += cpiYoY[j].value;
    cpiAvg.push({ period: cpiYoY[i].period, value: sum / 12 });
  }
  return profitabilityInsights({
    roe, roa, nim, opex,
    cpi: cpiAvg.map((c) => ({ period: c.period, bank_type_code: "CPI", value: c.value })),
  });
}

/** Liquidity. [web/app/liquidity/page.tsx] */
export async function liquidityRead(): Promise<TabTakeaway> {
  const [tlLtd, dollarization, apifon, liqRatios] = await Promise.all([
    weeklyOwnershipRatio("krediler", "1.0.1", "mevduat", "4.0.1", "TL"),
    weeklyDollarization(),
    evdsSeries("TP.APIFON3", 3),
    sectorLiquidityRatios(),
  ]);
  const netFunding = (apifon as { period_date: string; value: number }[]).map((r) => ({
    period: r.period_date, bank_type_code: "NETFUND", value: r.value,
  }));
  return liquidityInsights({
    tlLdrPublic: toTrend(tlLtd).filter((r) => r.bank_type_code === "PUBLIC"),
    tlLdrPrivate: toTrend(tlLtd).filter((r) => r.bank_type_code === "PRIVATE"),
    dollarization: toTrend(dollarization).filter((r) => r.bank_type_code === "SECTOR"),
    netCbrtFunding: netFunding,
    lcr: liqRatios.filter((r) => r.bank_type_code === "LCR"),
  });
}

/** Market Risk. [web/app/market-risk/page.tsx] */
export async function marketRiskRead(): Promise<TabTakeaway> {
  const [nop, gap1y] = await Promise.all([fxNopToCapital(), repricingGap1y()]);
  return marketRiskInsights({ nop, gap1y });
}

/**
 * Registry — keyed by the tab slug in read_headlines.tab and each page's
 * `withLlmHeadline(tab, …)`.
 */
export const READ_COMPUTERS: Record<string, () => Promise<TabTakeaway>> = {
  overview: overviewRead,
  credit: creditRead,
  deposits: depositsRead,
  "asset-quality": assetQualityRead,
  capital: capitalRead,
  profitability: profitabilityRead,
  liquidity: liquidityRead,
  "market-risk": marketRiskRead,
};

export async function computeReads(): Promise<{ tab: string; takeaway: TabTakeaway }[]> {
  const tabs = Object.keys(READ_COMPUTERS);
  const takeaways = await Promise.all(
    tabs.map((t) => READ_COMPUTERS[t]().catch(() => null)),
  );
  return tabs
    .map((tab, i) => ({ tab, takeaway: takeaways[i] }))
    .filter((r): r is { tab: string; takeaway: TabTakeaway } => r.takeaway !== null);
}
