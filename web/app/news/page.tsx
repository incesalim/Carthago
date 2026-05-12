/**
 * /news — qualitative feed.
 *
 * Default view: three columns (KAP / TCMB / BDDK), latest ~30 items each.
 * Filtered view (?ticker=AKBNK): all KAP disclosures for one bank in a
 * single tall column. Click any item to open the original source.
 */
import Link from "next/link";
import {
  latestNews,
  newsBySource,
  newsByTicker,
  newsSourceSummary,
  sourceLabel,
  type NewsItem,
  type NewsSource,
} from "@/app/lib/news";

export const dynamic = "force-dynamic";

interface Props {
  searchParams: Promise<{ ticker?: string }>;
}

const SOURCE_DESCRIPTIONS: Record<NewsSource, string> = {
  kap: "Public Disclosure Platform — regulator-mandated filings from BIST-listed banks.",
  tcmb: "Central Bank of Türkiye — monetary policy + market operations press releases (English).",
  bddk: "Banking Regulation and Supervision Agency — official announcements (Turkish).",
};

const SOURCE_COLOR: Record<NewsSource, string> = {
  kap: "border-l-[#7a0d2e]",
  tcmb: "border-l-[#1f4068]",
  bddk: "border-l-[#0f7b6c]",
};

function fmtDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso.slice(0, 10);
  return d.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function NewsCard({ item }: { item: NewsItem }) {
  return (
    <a
      href={item.url}
      target="_blank"
      rel="noopener noreferrer"
      className={`block rounded-md border border-neutral-200 border-l-4 ${SOURCE_COLOR[item.source as NewsSource]} bg-white p-3 hover:bg-neutral-50 transition`}
    >
      <div className="flex items-baseline justify-between gap-2 text-[10px] text-neutral-500 uppercase tracking-wide mb-1">
        <span className="tabular-nums">{fmtDate(item.published_at)}</span>
        {item.ticker ? (
          <span className="font-semibold text-neutral-700">{item.ticker}</span>
        ) : (
          <span className="text-neutral-400">{sourceLabel(item.source)}</span>
        )}
      </div>
      <div className="text-sm text-neutral-900 leading-snug line-clamp-3">
        {item.title}
      </div>
      {item.summary && (
        <div className="text-xs text-neutral-600 mt-1 line-clamp-2">
          {item.summary}
        </div>
      )}
    </a>
  );
}

function SourceColumn({ source, items }: { source: NewsSource; items: NewsItem[] }) {
  return (
    <section className="space-y-3">
      <header className="space-y-0.5">
        <h2 className="text-base font-semibold text-neutral-900">
          {sourceLabel(source)}
        </h2>
        <p className="text-xs text-neutral-500">{SOURCE_DESCRIPTIONS[source]}</p>
      </header>
      <div className="space-y-2">
        {items.length === 0 ? (
          <div className="text-xs text-neutral-500 italic">No items yet.</div>
        ) : (
          items.map((it) => <NewsCard key={`${it.source}-${it.external_id}`} item={it} />)
        )}
      </div>
    </section>
  );
}

export default async function NewsPage({ searchParams }: Props) {
  const sp = await searchParams;
  const ticker = sp.ticker?.toUpperCase();

  // -- Per-ticker focused view -----------------------------------------------
  if (ticker) {
    const items = await newsByTicker(ticker, 200);
    return (
      <main className="px-8 py-8 space-y-6 max-w-3xl">
        <header className="space-y-1">
          <div className="flex items-baseline gap-3">
            <h1 className="text-2xl font-semibold tracking-tight">{ticker}</h1>
            <span className="text-sm text-neutral-500">disclosures</span>
          </div>
          <p className="text-sm text-neutral-500">
            All KAP disclosures filed by {ticker}, newest first.
          </p>
          <div className="flex flex-wrap gap-4 text-xs text-neutral-500 pt-2">
            <span>{items.length} items</span>
            <Link
              href={`/banks/${ticker}`}
              className="text-neutral-600 underline hover:text-neutral-900"
            >
              ← back to {ticker}
            </Link>
            <Link
              href="/news"
              className="text-neutral-600 underline hover:text-neutral-900"
            >
              ← all news
            </Link>
          </div>
        </header>
        <div className="space-y-2">
          {items.length === 0 ? (
            <div className="text-xs text-neutral-500 italic">
              No disclosures cached for {ticker} yet.
            </div>
          ) : (
            items.map((it) => <NewsCard key={`${it.source}-${it.external_id}`} item={it} />)
          )}
        </div>
      </main>
    );
  }

  // -- Default three-column feed --------------------------------------------
  const [kap, tcmb, bddk, summary] = await Promise.all([
    newsBySource("kap", 30),
    newsBySource("tcmb", 30),
    newsBySource("bddk", 30),
    newsSourceSummary(),
  ]);

  return (
    <main className="px-8 py-8 space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">News & Disclosures</h1>
        <p className="text-sm text-neutral-500">
          Regulator-mandated filings + central-bank press releases — refreshed daily.
        </p>
        <div className="flex flex-wrap gap-4 text-xs text-neutral-500 pt-2">
          {summary.map((s) => (
            <div key={s.source}>
              <span className="font-semibold text-neutral-700">{sourceLabel(s.source)}</span>
              {" — "}
              {s.total} items
              {s.latest && (
                <span className="text-neutral-400">
                  {" · latest "}
                  {fmtDate(s.latest)}
                </span>
              )}
            </div>
          ))}
          <Link
            href="/banks"
            className="text-neutral-600 underline hover:text-neutral-900"
          >
            Per-bank disclosures →
          </Link>
        </div>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <SourceColumn source="kap" items={kap} />
        <SourceColumn source="tcmb" items={tcmb} />
        <SourceColumn source="bddk" items={bddk} />
      </div>
    </main>
  );
}

// Silence ts-unused for the import — `latestNews` is exported for callers
// outside this file (and may be used here later).
void latestNews;
