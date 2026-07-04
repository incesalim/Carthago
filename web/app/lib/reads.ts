/**
 * Per-tab "Read" compute — recomputes each tab's DETERMINISTIC TabTakeaway
 * (the same one `web/app/lib/insights.ts` produces on the page) outside of the
 * page render, so the headline generator can rewrite it.
 *
 * Used by GET /api/reads (the collector the CI generator reads). Each computer
 * MUST reproduce its page's insight inputs exactly; if it ever drifts, the
 * `det_hash` gate in read-headlines.ts simply falls back to the deterministic
 * headline on that tab (safe — never a wrong number, just no LLM benefit until
 * realigned). Adding a tab = add its computer here + wrap its page's <Takeaway>
 * with `withLlmHeadline`.
 */
import { overviewInsights, type TabTakeaway } from "./insights";
import {
  BANK_TYPES,
  ratioCar,
  ratioLdr,
  ratioNpl,
  ratioRoe,
  totalAssetsYoY,
  totalDepositsYoY,
  totalLoansYoY,
} from "./metrics";

/** Overview "Sector Pulse" — mirrors web/app/page.tsx (always sector aggregate). */
export async function overviewRead(): Promise<TabTakeaway> {
  const sector = [BANK_TYPES.SECTOR];
  const [assetsYoY, loansYoY, depositsYoY, npl, car, ldr, roe] = await Promise.all([
    totalAssetsYoY(sector),
    totalLoansYoY(sector),
    totalDepositsYoY(sector),
    ratioNpl(sector),
    ratioCar(sector),
    ratioLdr(sector),
    ratioRoe(sector),
  ]);
  return overviewInsights({ assetsYoY, loansYoY, depositsYoY, npl, car, ldr, roe });
}

/**
 * Registry of the tabs whose headline the generator rewrites. Keyed by the tab
 * slug used in read_headlines.tab and in each page's `withLlmHeadline(tab, …)`.
 * Extend one tab at a time as each page's compute is mirrored above.
 */
export const READ_COMPUTERS: Record<string, () => Promise<TabTakeaway>> = {
  overview: overviewRead,
};

export async function computeReads(): Promise<{ tab: string; takeaway: TabTakeaway }[]> {
  const tabs = Object.keys(READ_COMPUTERS);
  const takeaways = await Promise.all(tabs.map((t) => READ_COMPUTERS[t]()));
  return tabs.map((tab, i) => ({ tab, takeaway: takeaways[i] }));
}
