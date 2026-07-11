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
import {
  Colophon,
  Depth,
  DeskHeader,
  SecHead,
  Vital,
  Vitals,
} from "@/app/components/desk";
import { monthLabel } from "@/app/lib/desk";
import PressFeed from "../PressFeed";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Turkish Banking News — Google News",
  description: "Google News coverage of the Turkish banking sector, tagged by bank.",
  alternates: { canonical: "/news/google" },
};

const DAY_MS = 86_400_000;

/**
 * Items published within `days` of `anchor` (skips unparseable dates). The
 * anchor is the feed's own newest item, not wall-clock: the page reports the
 * record it holds, so a stale feed reads as stale rather than as a quiet week.
 */
function countWithin(items: { published_at: string }[], days: number, anchor: number): number {
  return items.filter((it) => {
    const t = Date.parse(it.published_at);
    return Number.isFinite(t) && anchor - t <= days * DAY_MS;
  }).length;
}

/** 'YYYY-MM-DD…' → 'Jul 10'. */
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
function shortDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!m) return iso.slice(0, 10);
  return `${MONTHS[Number(m[2]) - 1] ?? m[2]} ${Number(m[3])}`;
}

export default async function GoogleNewsPage() {
  const [items, ticker] = await Promise.all([latestGoogleNews(200), getMarketTicker()]);
  const latest = items[0]?.published_at;
  const outletCount = new Set(items.map((it) => it.category ?? "Google News")).size;

  // ---- the brief's computed vitals — counts and dates from the fetched feed
  const anchor = Date.parse(latest ?? "");
  const base = Number.isFinite(anchor) ? anchor : 0;
  const items7 = countWithin(items, 7, base);
  const items30 = countWithin(items, 30, base);

  // Most-tagged bank across the fetched window (news_item_banks → `tickers`).
  const bankCounts = new Map<string, number>();
  for (const it of items) {
    for (const t of (it.tickers ?? "").split(",")) {
      if (t) bankCounts.set(t, (bankCounts.get(t) ?? 0) + 1);
    }
  }
  const topBank = [...bankCounts.entries()].sort((a, b) => b[1] - a[1])[0];

  return (
    <main className="mx-auto w-full max-w-[1440px] px-4 py-7 sm:px-6 lg:px-9">
      <DeskHeader
        title="Google News"
        record={
          <>
            Record <b className="font-normal text-foreground">{monthLabel(latest)}</b> · Google News
            search feeds, refreshed daily · cards link out
          </>
        }
        right="compiled, not written"
      />

      {ticker.length > 0 && (
        <div className="mt-3">
          <MarketTicker items={ticker} />
        </div>
      )}

      <SecHead
        title="The vitals"
        meta="volume · tagging · outlets · recency"
        className="mb-2.5 mt-6"
      />
      <Vitals cols={4}>
        <Vital
          label="7 days to the record"
          value={String(items7)}
          unit="items"
          note={`${items30} in the 30 days to ${shortDate(latest)} — counted from the fetched window`}
        />
        <Vital
          label="Most-mentioned bank"
          value={topBank ? topBank[0] : "—"}
          note={
            topBank ? (
              <>
                tagged in {topBank[1]} of {items.length} fetched items ·{" "}
                <Link href={`/banks/${topBank[0]}`} className="font-semibold text-primary">
                  /banks/{topBank[0]}
                </Link>
              </>
            ) : (
              "no bank tags in the fetched window"
            )
          }
        />
        <Vital
          label="Outlets"
          value={String(outletCount)}
          note={`distinct publishers across ${items.length} fetched items — the long tail beyond the curated feed`}
        />
        <Vital
          label="Latest item"
          value={shortDate(latest)}
          note={
            <>
              the curated outlet feed is on{" "}
              <Link href="/news" className="font-semibold text-primary">
                /news
              </Link>
            </>
          }
        />
      </Vitals>

      <Depth>
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
      </Depth>

      <Colophon />
    </main>
  );
}
