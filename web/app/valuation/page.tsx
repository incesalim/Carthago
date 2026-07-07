/**
 * /valuation — Scenario projections & intrinsic valuation for the listed banks.
 *
 * Standalone tab (doesn't touch /banks or /cross-bank). The server pre-fetches a
 * compact "seed" for every listed bank (book, TTM ROE, market, equity beta, the
 * TRY risk-free proxy) and hands the whole set to a client component that runs
 * the residual-income / DDM / justified-P/B maths live as the user edits
 * assumptions — no per-keystroke server round-trip. See web/app/lib/valuation.ts.
 */
import type { Metadata } from "next";
import { listedBistTickers } from "@/app/lib/bist";
import { liveQuotes } from "@/app/lib/bist-live";
import { tryRiskFree, valuationSeed, type ValuationSeed } from "@/app/lib/valuation-data";
import { nf } from "@/app/lib/chart-format";
import { PageHeader } from "@/app/components/ui";
import ValuationView from "./ValuationView";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Turkish Bank Stocks — Valuation (BIST)",
  description: "Valuation of listed Turkish banks on Borsa İstanbul — price/book, P/E, dividend yield and performance vs XU100 and XBANK.",
  alternates: { canonical: "/valuation" },
};

// Bank-only basis, consistent with the /cross-bank "Compare" tab.
const KIND = "unconsolidated" as const;

export default async function ValuationPage() {
  const tickers = await listedBistTickers();
  const [live, rf] = await Promise.all([liveQuotes(tickers), tryRiskFree()]);
  const seedsRaw = await Promise.all(tickers.map((t) => valuationSeed(t, KIND, { live, rf })));
  const seeds = seedsRaw.filter((s): s is ValuationSeed => s != null);

  const description =
    `Forward scenarios & intrinsic value for ${seeds.length} listed banks · residual income, DDM, justified P/B · ` +
    `cost of equity via CAPM (nominal TRY) · risk-free ${nf(rf.rf * 100, 1)}% (${rf.source})`;

  return (
    <main className="mx-auto w-full max-w-[1440px] space-y-6 px-4 py-8 sm:px-6 lg:px-8">
      <PageHeader title="Valuation" description={description} />
      {seeds.length > 0 ? (
        <ValuationView seeds={seeds} />
      ) : (
        <p className="text-sm text-muted-foreground">No listed-bank valuation data available yet.</p>
      )}
    </main>
  );
}
