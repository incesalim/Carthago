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
import {
  Colophon,
  Depth,
  DeskHeader,
  SecHead,
  Vital,
  Vitals,
} from "@/app/components/desk";
import { monthLabel } from "@/app/lib/desk";

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

const DAY_MS = 86_400_000;

/**
 * Filings published within `days` of `anchor` (skips unparseable dates). The
 * anchor is the feed's own newest filing, not wall-clock: the page reports the
 * record it holds, so a stale feed reads as stale rather than as a quiet month.
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

function DisclosureCard({ item }: { item: NewsItem }) {
  // Outer is a card wrapper; the title link opens KAP, the ticker link
  // goes to the per-bank page. Two anchors instead of one nested in
  // another (which is invalid HTML and breaks Next.js hydration).
  return (
    <div className="rounded-[10px] border border-border border-l-4 border-l-primary bg-card p-3 hover:bg-accent transition">
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
    const latest = items[0]?.published_at;
    const oldest = items.at(-1)?.published_at;

    // ---- the brief's computed vitals — counts and dates from the fetched filings
    const anchor = Date.parse(latest ?? "");
    const base = Number.isFinite(anchor) ? anchor : 0;
    const filings30 = countWithin(items, 30, base);
    const withDocs = items.filter((it) => !!it.url).length;

    return (
      <main className="mx-auto w-full max-w-[1440px] px-4 py-7 sm:px-6 lg:px-9">
        <DeskHeader
          title={`${ticker} disclosures`}
          record={
            <>
              Record <b className="font-normal text-foreground">{monthLabel(latest)}</b> · KAP filings,
              refreshed daily · cards link out
            </>
          }
          right="compiled, not written"
        />

        <div className="mt-2 flex flex-wrap gap-4 font-mono text-[9.5px] uppercase tracking-[0.05em]">
          <Link href={`/banks/${ticker}`} className="font-semibold text-primary">
            ← back to {ticker}
          </Link>
          <Link href="/disclosures" className="font-semibold text-primary">
            ← all disclosures
          </Link>
        </div>

        <SecHead
          title="The vitals"
          meta="volume · recency · span · documents"
          className="mb-2.5 mt-6"
        />
        <Vitals cols={4}>
          <Vital
            label="30 days to the record"
            value={String(filings30)}
            unit="filings"
            note={`of ${items.length} fetched for ${ticker} — counted back from ${shortDate(latest)}`}
          />
          <Vital
            label="Most recent filing"
            value={shortDate(latest)}
            note={
              items[0] ? (
                <>
                  newest of {items.length} fetched ·{" "}
                  <Link href={`/banks/${ticker}`} className="font-semibold text-primary">
                    /banks/{ticker}
                  </Link>
                </>
              ) : (
                "no filings cached yet"
              )
            }
          />
          <Vital
            label="Filings fetched"
            value={String(items.length)}
            note={`newest first, capped at 200 · oldest held ${shortDate(oldest)}`}
          />
          <Vital
            label="Documents"
            value={String(withDocs)}
            note="filings carrying a KAP document link — every card opens the original"
          />
        </Vitals>

        <Depth>
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {items.length === 0 ? (
              <div className="text-xs text-muted-foreground italic">
                No disclosures cached for {ticker} yet.
              </div>
            ) : (
              items.map((it) => <DisclosureCard key={`${it.source}-${it.external_id}`} item={it} />)
            )}
          </div>
        </Depth>

        <Colophon />
      </main>
    );
  }

  // -- Default cross-bank view (all KAP, newest first) -----------------------
  const [items, summary] = await Promise.all([
    newsBySource("kap", 100),
    newsSourceSummary(),
  ]);
  const kapStats = summary.find((s) => s.source === "kap");
  const latest = items[0]?.published_at ?? kapStats?.latest;

  // ---- the brief's computed vitals — counts and dates from the fetched filings
  const anchor = Date.parse(items[0]?.published_at ?? "");
  const base = Number.isFinite(anchor) ? anchor : 0;
  const filings7 = countWithin(items, 7, base);
  const filings30 = countWithin(items, 30, base);

  // Distinct banks filing in the fetched window, and the bank behind the newest row.
  const filers = new Set(items.map((it) => it.ticker).filter((t): t is string => !!t));
  const topFiler = items[0]?.ticker ?? null;
  const withDocs = items.filter((it) => !!it.url).length;

  return (
    <main className="mx-auto w-full max-w-[1440px] px-4 py-7 sm:px-6 lg:px-9">
      <DeskHeader
        title="Bank Disclosures"
        record={
          <>
            Record <b className="font-normal text-foreground">{monthLabel(latest)}</b> · KAP filings,
            refreshed daily · cards link out to KAP
          </>
        }
        right="compiled, not written"
      />

      <div className="mt-2 flex flex-wrap gap-4 font-mono text-[9.5px] uppercase tracking-[0.05em]">
        <Link href="/regulation" className="font-semibold text-primary">
          TCMB &amp; BDDK regulation →
        </Link>
        <Link href="/banks" className="font-semibold text-primary">
          Browse banks →
        </Link>
      </div>

      <SecHead
        title="The vitals"
        meta="volume · recency · filers · documents"
        className="mb-2.5 mt-6"
      />
      <Vitals cols={4}>
        <Vital
          label="7 days to the record"
          value={String(filings7)}
          unit="filings"
          note={`${filings30} in the 30 days to ${shortDate(items[0]?.published_at)} — counted from the fetched window`}
        />
        <Vital
          label="Most recent filing"
          value={shortDate(items[0]?.published_at)}
          note={
            topFiler ? (
              <>
                filed by{" "}
                <Link href={`/banks/${topFiler}`} className="font-semibold text-primary">
                  {topFiler}
                </Link>{" "}
                · newest of {items.length} fetched
              </>
            ) : (
              "no filings in the fetched window"
            )
          }
        />
        <Vital
          label="Banks disclosing"
          value={String(filers.size)}
          note={`distinct tickers across ${items.length} fetched filings`}
        />
        <Vital
          label="Total documents"
          value={kapStats ? String(kapStats.total) : String(withDocs)}
          note={
            kapStats?.latest
              ? `KAP filings held in full — latest ${fmtDate(kapStats.latest)}`
              : "filings carrying a KAP document link in the fetched window"
          }
        />
      </Vitals>

      <Depth>
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {items.length === 0 ? (
            <div className="text-xs text-muted-foreground italic">No disclosures cached yet.</div>
          ) : (
            items.map((it) => <DisclosureCard key={`${it.source}-${it.external_id}`} item={it} />)
          )}
        </div>
      </Depth>

      <Colophon />
    </main>
  );
}
