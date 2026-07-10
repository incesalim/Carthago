/**
 * /news/google — Google News long-tail feed.
 *
 * The same banking-relevance lens as /news, but sourced from topic-scoped
 * Google News search feeds instead of the hand-picked outlet RSS list. This
 * surfaces the long tail of regional / trade outlets that don't publish their
 * own banking RSS feed. Publisher names come from the Google News <source>
 * tag; links resolve to the real article (the news.google.com redirect token
 * is decoded server-side at ingest). Outlets already covered on /news are
 * filtered out so the two tabs don't duplicate each other.
 */
import type { Metadata } from "next";
import Link from "next/link";
import { latestGoogleNews } from "@/app/lib/news";
import { getMarketTicker } from "@/app/lib/market-ticker";
import MarketTicker from "@/app/components/MarketTicker";
import { PageHeader } from "@/app/components/ui";
import PressFeed from "../PressFeed";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Turkish Banking News — Google News",
  description: "Google News coverage of the Turkish banking sector, tagged by bank.",
  alternates: { canonical: "/news/google" },
};

export default async function GoogleNewsPage() {
  const [items, ticker] = await Promise.all([latestGoogleNews(200), getMarketTicker()]);
  const latest = items[0]?.published_at;
  const outletCount = new Set(items.map((it) => it.category ?? "Google News")).size;

  return (
    <main className="mx-auto w-full max-w-[1440px] px-4 py-8 sm:px-6 lg:px-8 space-y-8">
      {ticker.length > 0 && <MarketTicker items={ticker} />}
      <div className="space-y-2">
        <PageHeader
          eyebrow="Long-tail coverage"
          title="Google News"
          description={
            <>
              Banking-sector coverage aggregated from Google News search feeds — the long tail of
              regional and trade outlets beyond the curated{" "}
              <Link href="/news" className="underline hover:text-foreground">
                sector press feed
              </Link>
              . Cards link out to the original article.
            </>
          }
          dataThrough={latest?.slice(0, 10)}
        />
        <div className="flex flex-wrap gap-4 text-xs text-muted-foreground">
          <span>
            <span className="font-semibold text-foreground">{items.length}</span> recent items
            {outletCount > 0 && (
              <span> · <span className="font-semibold text-foreground">{outletCount}</span> outlets</span>
            )}
          </span>
        </div>
      </div>

      {items.length === 0 ? (
        <section className="rounded-[10px] border border-dashed border-border bg-muted p-4 text-sm text-muted-foreground">
          <strong className="font-semibold">No Google News items yet.</strong> The feed populates
          after the next daily news refresh. The curated outlet feed is on{" "}
          <Link href="/news" className="underline hover:text-foreground">
            /news
          </Link>
          .
        </section>
      ) : (
        <PressFeed items={items} />
      )}
    </main>
  );
}
