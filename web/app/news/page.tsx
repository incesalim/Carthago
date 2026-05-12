/**
 * /news — regulatory + central-bank news.
 *
 * Two columns: TCMB (central bank press releases) and BDDK (banking
 * regulator announcements). Per-company disclosures from KAP live on
 * /disclosures so the two pages can be scanned separately by audience
 * (macro / regulatory reader vs. per-bank reader).
 */
import Link from "next/link";
import {
  newsBySource,
  newsSourceSummary,
  sourceLabel,
  type NewsItem,
  type NewsSource,
} from "@/app/lib/news";

export const dynamic = "force-dynamic";

const SOURCE_DESCRIPTIONS: Record<"tcmb" | "bddk", string> = {
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
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
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
        <span className="text-neutral-400">{sourceLabel(item.source)}</span>
      </div>
      <div className="text-sm text-neutral-900 leading-snug line-clamp-3">{item.title}</div>
      {item.summary && (
        <div className="text-xs text-neutral-600 mt-1 line-clamp-2">{item.summary}</div>
      )}
    </a>
  );
}

function SourceColumn({ source, items }: { source: "tcmb" | "bddk"; items: NewsItem[] }) {
  return (
    <section className="space-y-3">
      <header className="space-y-0.5">
        <h2 className="text-base font-semibold text-neutral-900">{sourceLabel(source)}</h2>
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

export default async function NewsPage() {
  const [tcmb, bddk, summary] = await Promise.all([
    newsBySource("tcmb", 50),
    newsBySource("bddk", 50),
    newsSourceSummary(),
  ]);

  const tcmbStats = summary.find((s) => s.source === "tcmb");
  const bddkStats = summary.find((s) => s.source === "bddk");

  return (
    <main className="px-8 py-8 space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Regulatory News</h1>
        <p className="text-sm text-neutral-500">
          Central-bank press releases and banking-regulator announcements — refreshed daily.
        </p>
        <div className="flex flex-wrap gap-4 text-xs text-neutral-500 pt-2">
          {tcmbStats && (
            <div>
              <span className="font-semibold text-neutral-700">TCMB</span>
              {" — "}
              {tcmbStats.total} items
              {tcmbStats.latest && (
                <span className="text-neutral-400"> · latest {fmtDate(tcmbStats.latest)}</span>
              )}
            </div>
          )}
          {bddkStats && (
            <div>
              <span className="font-semibold text-neutral-700">BDDK</span>
              {" — "}
              {bddkStats.total} items
              {bddkStats.latest && (
                <span className="text-neutral-400"> · latest {fmtDate(bddkStats.latest)}</span>
              )}
            </div>
          )}
          <Link
            href="/disclosures"
            className="text-neutral-600 underline hover:text-neutral-900"
          >
            Per-bank KAP disclosures →
          </Link>
        </div>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <SourceColumn source="tcmb" items={tcmb} />
        <SourceColumn source="bddk" items={bddk} />
      </div>
    </main>
  );
}
