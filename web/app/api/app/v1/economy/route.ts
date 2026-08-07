/**
 * GET /api/app/v1/economy — the macro backdrop.
 *
 * `getEconomyData()` fans out to ~35 EVDS series in one round trip and returns
 * them chart-ready (y/y computed, 12m rolling summed, GDP-scaled). The website's
 * /economy tab renders exactly this object, so the derivations — the CPI rebase
 * handling, the ex-ante real rate, the %-of-GDP bases — are shared rather than
 * re-derived against the raw codes.
 *
 * The loader grew past what this endpoint exposes (the transmission chain, the
 * reserve buffer, households' FX, EUR/TRY, the CA as % of GDP). Those are NOT
 * served here on purpose: the wire format is private but the app ships against a
 * pinned shape, so a new field lands when the app has a screen for it — not
 * because the website gained one.
 *
 * Series are trimmed on the way out. The tab plots eight years because a laptop
 * can show it; a phone chart resolves maybe three, and the untrimmed payload is
 * roughly ten times the size for pixels nobody can see.
 */
import { getEconomyData, type Point } from "@/app/lib/economy";
import { appApiDisabled, disabledResponse, jsonResponse } from "../_shared";

export { OPTIONS } from "../_shared";
export const dynamic = "force-dynamic";

/** Points kept per series, by cadence. Daily USD/TRY needs far more rows to
 *  cover the same span than a quarterly GDP print does. */
const KEEP_DAILY = 260;   // ≈ 1 trading year
const KEEP_MONTHLY = 48;  // 4 years
const KEEP_QUARTERLY = 20; // 5 years

const trim = (rows: Point[], n: number) =>
  rows.slice(-n).map((r) => ({ t: r.period_date, v: r.value }));

export async function GET() {
  if (await appApiDisabled()) return disabledResponse();

  const d = await getEconomyData();

  const latest = (rows: Point[]) => rows.at(-1)?.value ?? null;

  return jsonResponse({
    // The band at the top of the screen — one figure each, no chart.
    headline: {
      gdpGrowth: latest(d.gdpGrowth),
      cpiYoY: latest(d.cpiYoY),
      unemployment: latest(d.unemployment),
      fundingCost: latest(d.fundingMonthly),
      realRate: latest(d.realRate),
      usdtry: latest(d.usdtry),
      ca12m: latest(d.ca12m),
      budgetPctGdp: latest(d.budgetPctGdp),
    },
    series: {
      gdpGrowth: trim(d.gdpGrowth, KEEP_QUARTERLY),
      ipGrowth: trim(d.ipGrowth, KEEP_MONTHLY),
      unemployment: trim(d.unemployment, KEEP_MONTHLY),
      cpiYoY: trim(d.cpiYoY, KEEP_MONTHLY),
      cpiMoM: trim(d.cpiMoM, KEEP_MONTHLY),
      exp12m: trim(d.exp12m, KEEP_MONTHLY),
      fundingMonthly: trim(d.fundingMonthly, KEEP_MONTHLY),
      realRate: trim(d.realRate, KEEP_MONTHLY),
      usdtry: trim(d.usdtry, KEEP_DAILY),
      reer: trim(d.reer, KEEP_MONTHLY),
      ca12m: trim(d.ca12m, KEEP_MONTHLY),
      budgetPctGdp: trim(d.budgetPctGdp, KEEP_MONTHLY),
    },
    units: {
      gdpGrowth: "% y/y", ipGrowth: "% y/y", unemployment: "%",
      cpiYoY: "% y/y", cpiMoM: "% m/m", exp12m: "%",
      fundingMonthly: "%", realRate: "%", usdtry: "TRY",
      reer: "index", ca12m: "USD bn, 12m", budgetPctGdp: "% GDP, 12m",
    },
    source: "TCMB EVDS · TÜİK",
  });
}
