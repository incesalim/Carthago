/**
 * /disclosures — KAP (Public Disclosure Platform) bank filings.
 *
 * Default view: all KAP rows, newest first, with ticker shown on each card.
 * Filtered view (?ticker=AKBNK): one bank's disclosures, with back-link
 * to that bank's drill-down page.
 *
 * Why separate from /news: KAP rows are bank-level operational filings;
 * TCMB + BDDK are macro / regulatory announcements. Two audiences,
 * two pages.
 */
import type { Metadata } from "next";
import Link from "next/link";
import {
  newsBySource,
  newsByTicker,
  newsSourceSummary,
  type NewsItem,
} from "@/app/lib/news";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Turkish Banks — KAP Disclosures",
  description: "Latest KAP public disclosures from Turkish banks — material events, filings and financial reports.",
  alternates: { canonical: "/disclosures" },
};

interface Props {
  searchParams: Promise<{ ticker?: string }>;
}

function fmtDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso.slice(0, 10);
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

function DisclosureCard({ item }: { item: NewsItem }) {
  // Outer is a card wrapper; the title link opens KAP, the ticker link
  // goes to the per-bank page. Two anchors instead of one nested in
  // another (which is invalid HTML and breaks Next.js hydration).
  return (
    <div className="rounded-xl border border-border border-l-4 border-l-primary bg-card p-3 hover:bg-accent transition">
      <div className="flex items-baseline justify-between gap-2 text-[10px] text-muted-foreground uppercase tracking-wide mb-1">
        <span className="tabular-nums">{fmtDate(item.published_at)}</span>
        {item.ticker && (
          <Link
            href={`/banks/${item.ticker}`}
            className="font-semibold text-foreground hover:underline"
          >
            {item.ticker}
          </Link>
        )}
      </div>
      <a
        href={item.url}
        target="_blank"
        rel="noopener noreferrer"
        className="block text-sm text-foreground leading-snug line-clamp-3 hover:underline"
      >
        {item.title}
      </a>
      {item.summary && (
        <div className="text-xs text-muted-foreground mt-1 line-clamp-2">{item.summary}</div>
      )}
    </div>
  );
}

export default async function DisclosuresPage({ searchParams }: Props) {
  const sp = await searchParams;
  const ticker = sp.ticker?.toUpperCase();

  // -- Per-ticker focused view -----------------------------------------------
  if (ticker) {
    const items = await newsByTicker(ticker, 200);
    return (
      <main className="mx-auto w-full px-4 py-8 sm:px-6 lg:px-8 space-y-6 max-w-3xl">
        <header className="space-y-1">
          <div className="flex items-baseline gap-3">
            <h1 className="text-2xl font-semibold tracking-tight">{ticker}</h1>
            <span className="text-sm text-muted-foreground">disclosures</span>
          </div>
          <p className="text-sm text-muted-foreground">
            All KAP disclosures filed by {ticker}, newest first.
          </p>
          <div className="flex flex-wrap gap-4 text-xs text-muted-foreground pt-2">
            <span>{items.length} items</span>
            <Link
              href={`/banks/${ticker}`}
              className="text-muted-foreground underline hover:text-foreground"
            >
              ← back to {ticker}
            </Link>
            <Link
              href="/disclosures"
              className="text-muted-foreground underline hover:text-foreground"
            >
              ← all disclosures
            </Link>
          </div>
        </header>
        <div className="space-y-2">
          {items.length === 0 ? (
            <div className="text-xs text-muted-foreground italic">
              No disclosures cached for {ticker} yet.
            </div>
          ) : (
            items.map((it) => <DisclosureCard key={`${it.source}-${it.external_id}`} item={it} />)
          )}
        </div>
      </main>
    );
  }

  // -- Default cross-bank view (all KAP, newest first) -----------------------
  const [items, summary] = await Promise.all([
    newsBySource("kap", 100),
    newsSourceSummary(),
  ]);
  const kapStats = summary.find((s) => s.source === "kap");

  return (
    <main className="mx-auto w-full px-4 py-8 sm:px-6 lg:px-8 space-y-6 max-w-4xl">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Bank Disclosures</h1>
        <p className="text-sm text-muted-foreground">
          BIST-listed banks&apos; filings on KAP (Kamuyu Aydınlatma Platformu) — refreshed daily.
        </p>
        <div className="flex flex-wrap gap-4 text-xs text-muted-foreground pt-2">
          {kapStats && (
            <div>
              <span className="font-semibold text-foreground">KAP</span>
              {" — "}
              {kapStats.total} items
              {kapStats.latest && (
                <span className="text-muted-foreground"> · latest {fmtDate(kapStats.latest)}</span>
              )}
            </div>
          )}
          <Link
            href="/regulation"
            className="text-muted-foreground underline hover:text-foreground"
          >
            TCMB &amp; BDDK regulation →
          </Link>
          <Link
            href="/banks"
            className="text-muted-foreground underline hover:text-foreground"
          >
            Browse banks →
          </Link>
        </div>
      </header>
      <div className="space-y-2">
        {items.length === 0 ? (
          <div className="text-xs text-muted-foreground italic">No disclosures cached yet.</div>
        ) : (
          items.map((it) => <DisclosureCard key={`${it.source}-${it.external_id}`} item={it} />)
        )}
      </div>
    </main>
  );
}
