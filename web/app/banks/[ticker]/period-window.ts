import { ordOf } from "../../lib/period-math";

/** Financials may show year ends; the Desk still reads the latest balance sheet.
 * Input periods are the bank's available filings, newest first.
 */
export function bankPeriodWindow(allPeriods: string[], view: "annual" | "quarterly", count = 4) {
  const periods = (view === "annual" ? allPeriods.filter((p) => p.endsWith("Q4")) : allPeriods).slice(0, count);
  const currentPeriod = allPeriods[0] ?? null;
  // TTM/YoY lenses need eight quarters before the oldest displayed period.
  const displayOrds = periods.map(ordOf).filter((o): o is number => o != null);
  const latestDisplayOrd = displayOrds.length ? Math.max(...displayOrds) : null;
  const floorOrd = (displayOrds.length ? Math.min(...displayOrds) : ordOf(currentPeriod ?? "") ?? 0) - 8;
  const balanceSheetPeriods = allPeriods.filter((p) => {
    const ord = ordOf(p);
    return ord != null && ord >= floorOrd;
  });
  const queryPeriods = balanceSheetPeriods.filter((p) => latestDisplayOrd != null && ordOf(p)! <= latestDisplayOrd);
  return { periods, currentPeriod, queryPeriods, balanceSheetPeriods };
}
