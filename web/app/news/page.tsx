/**
 * /news — banking-sector press feed.
 *
 * Journalism about Turkish banks aggregated from financial-media RSS feeds
 * (Bloomberg HT, Dünya, Ekonomim, AA, Hürriyet, NTV …), keyword-filtered to
 * banking-relevant items by src/news/sources/press.py. Distinct from
 * /regulation, which carries the primary regulator feeds (TCMB + BDDK) and
 * per-bank KAP disclosures.
 *
 * We store only headline + link + a short snippet; every card links out to
 * the original article at the source outlet.
 */
import type { Metadata } from "next";
import Link from "next/link";
import { latestPress } from "@/app/lib/news";
import { getMarketTicker } from "@/app/lib/market-ticker";
import MarketTicker from "@/app/components/MarketTicker";
import { PageHeader } from "@/app/components/ui";
import PressFeed from "./PressFeed";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Turkish Banking News",
  description: "Latest news on Türkiye's banking sector and individual banks, aggregated and tagged by bank.",
  alternates: { canonical: "/news" },
};

export default async function NewsPage() {
  const [items, ticker] = await Promise.all([latestPress(160), getMarketTicker()]);
  const latest = items[0]?.published_at;

  return (
    <main className="mx-auto w-full max-w-[1440px] px-4 py-8 sm:px-6 lg:px-8 space-y-8">
      {ticker.length > 0 && <MarketTicker items={ticker} />}
      <div className="space-y-2">
        <PageHeader
          eyebrow="Turkish financial media"
          title="Sector News"
          description="Banking-sector coverage from Turkish financial media, filtered to items that mention banks, regulators, or rates. Cards link out to the original article."
          dataThrough={latest?.slice(0, 10)}
        />
        <div className="flex flex-wrap gap-4 text-xs text-muted-foreground">
          <span>
            <span className="font-semibold text-foreground">{items.length}</span> recent items
          </span>
          <Link href="/regulation" className="text-muted-foreground underline hover:text-foreground">
            Official regulator feeds (TCMB · BDDK) →
          </Link>
        </div>
      </div>

      {items.length === 0 ? (
        <section className="rounded-[10px] border border-dashed border-border bg-muted p-4 text-sm text-muted-foreground">
          <strong className="font-semibold">No press items yet.</strong> The feed populates after the
          next daily news refresh. Until then, the official regulator feeds are on{" "}
          <Link href="/regulation" className="underline hover:text-foreground">
            /regulation
          </Link>
          .
        </section>
      ) : (
        <PressFeed items={items} />
      )}
    </main>
  );
}
