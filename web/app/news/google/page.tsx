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
import Link from "next/link";
import { latestGoogleNews } from "@/app/lib/news";
import { getMarketTicker } from "@/app/lib/market-ticker";
import MarketTicker from "@/app/components/MarketTicker";
import PressFeed from "../PressFeed";

export const dynamic = "force-dynamic";

function fmtDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso.slice(0, 10);
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

export default async function GoogleNewsPage() {
  const [items, ticker] = await Promise.all([latestGoogleNews(200), getMarketTicker()]);
  const latest = items[0]?.published_at;
  const outletCount = new Set(items.map((it) => it.category ?? "Google News")).size;

  return (
    <main className="mx-auto w-full max-w-[1440px] px-4 py-8 sm:px-6 lg:px-8 space-y-6">
      {ticker.length > 0 && <MarketTicker items={ticker} />}
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Google News</h1>
        <p className="text-sm text-muted-foreground">
          Banking-sector coverage aggregated from Google News search feeds, filtered to items that
          mention banks, regulators, or rates. Captures the long tail of regional and trade outlets
          beyond the curated{" "}
          <Link href="/news" className="underline hover:text-foreground">
            sector press feed
          </Link>
          . Cards link out to the original article.
        </p>
        <div className="flex flex-wrap gap-4 pt-2 text-xs text-muted-foreground">
          <div>
            <span className="font-semibold text-foreground">{items.length}</span> recent items
            {outletCount > 0 && (
              <span> · <span className="font-semibold text-foreground">{outletCount}</span> outlets</span>
            )}
            {latest && <span> · latest {fmtDate(latest)}</span>}
          </div>
        </div>
      </header>

      {items.length === 0 ? (
        <section className="rounded-lg border border-dashed border-border bg-muted p-4 text-sm text-muted-foreground">
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
