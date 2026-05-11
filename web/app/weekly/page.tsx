/**
 * Weekly Trends tab — BDDK weekly bulletin.
 *
 * Loans + Deposits + NPL with annualized 4-week and 13-week growth rates
 * across the 5 bank groups + sector.
 */
import {
  weeklySeries,
  weeklyGrowth,
  WEEKLY_BANK_TYPES,
  WEEKLY_BANK_TYPE_LABELS,
} from "@/app/lib/metrics";
import TrendChart from "@/app/components/TrendChart";

export const dynamic = "force-dynamic";

export default async function WeeklyPage() {
  // weekly_series item ids
  const TOPLAM_KREDILER = { category: "krediler", item_id: "1.0.1" };
  const TOPLAM_MEVDUAT = { category: "mevduat", item_id: "4.0.1" };
  const NPL = { category: "takipteki_alacaklar", item_id: "2.0.1" };

  const all = Object.values(WEEKLY_BANK_TYPES);

  const [
    loansLevel, loans4w, loans13w,
    depsLevel, deps4w, deps13w,
    nplLevel, nplYoY,
  ] = await Promise.all([
    weeklySeries(TOPLAM_KREDILER.category, TOPLAM_KREDILER.item_id, "TOTAL", all, 156),
    weeklyGrowth(TOPLAM_KREDILER.category, TOPLAM_KREDILER.item_id, "TOTAL", 4, all, 104),
    weeklyGrowth(TOPLAM_KREDILER.category, TOPLAM_KREDILER.item_id, "TOTAL", 13, all, 104),
    weeklySeries(TOPLAM_MEVDUAT.category, TOPLAM_MEVDUAT.item_id, "TOTAL", all, 156),
    weeklyGrowth(TOPLAM_MEVDUAT.category, TOPLAM_MEVDUAT.item_id, "TOTAL", 4, all, 104),
    weeklyGrowth(TOPLAM_MEVDUAT.category, TOPLAM_MEVDUAT.item_id, "TOTAL", 13, all, 104),
    weeklySeries(NPL.category, NPL.item_id, "TOTAL", all, 156),
    weeklyGrowth(NPL.category, NPL.item_id, "TOTAL", 52, all, 104),
  ]);

  return (
    <main className="px-8 py-8 space-y-6">
      <h1 className="text-3xl font-bold mb-2">Weekly Trends</h1>
      <p className="text-sm text-neutral-500 mb-6">
        BDDK weekly bulletin · loans, deposits, NPL · annualized 4-week and 13-week growth
      </p>

      <h2 className="text-lg font-semibold mb-3">Loans</h2>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
        <TrendChart
          data={loansLevel}
          seriesLabels={WEEKLY_BANK_TYPE_LABELS}
          title="Total Loans — Level (TL bn)"
          yFormat="bn"
          decimals={0}
        />
        <TrendChart
          data={loans4w}
          seriesLabels={WEEKLY_BANK_TYPE_LABELS}
          title="Loan Growth 4w (annualized %)"
          yFormat="pct"
          decimals={1}
          zeroLine
        />
        <TrendChart
          data={loans13w}
          seriesLabels={WEEKLY_BANK_TYPE_LABELS}
          title="Loan Growth 13w (annualized %)"
          yFormat="pct"
          decimals={1}
          zeroLine
        />
      </div>

      <h2 className="text-lg font-semibold mb-3">Deposits</h2>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
        <TrendChart
          data={depsLevel}
          seriesLabels={WEEKLY_BANK_TYPE_LABELS}
          title="Total Deposits — Level (TL bn)"
          yFormat="bn"
          decimals={0}
        />
        <TrendChart
          data={deps4w}
          seriesLabels={WEEKLY_BANK_TYPE_LABELS}
          title="Deposit Growth 4w (annualized %)"
          yFormat="pct"
          decimals={1}
          zeroLine
        />
        <TrendChart
          data={deps13w}
          seriesLabels={WEEKLY_BANK_TYPE_LABELS}
          title="Deposit Growth 13w (annualized %)"
          yFormat="pct"
          decimals={1}
          zeroLine
        />
      </div>

      <h2 className="text-lg font-semibold mb-3">Asset quality</h2>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <TrendChart
          data={nplLevel}
          seriesLabels={WEEKLY_BANK_TYPE_LABELS}
          title="NPL Stock — Level (TL bn)"
          yFormat="bn"
          decimals={0}
        />
        <TrendChart
          data={nplYoY}
          seriesLabels={WEEKLY_BANK_TYPE_LABELS}
          title="NPL Growth YoY (%)"
          yFormat="pct"
          decimals={1}
          zeroLine
        />
      </div>
    </main>
  );
}
