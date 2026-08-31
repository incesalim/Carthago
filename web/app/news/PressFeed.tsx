"use client";

/**
 * Client-side banking-sector press feed: outlet filter chips + a responsive
 * grid of headline cards. Unlike the /regulation raw feeds (which open a
 * drawer with cached body_text), press cards link straight out to the
 * original article — we store only headline + snippet, never the full body.
 */
import { useText } from "@/i18n/use-text";
import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { type NewsItem } from "@/app/lib/news";
import { topicTag, type Tag } from "@/app/lib/news-tags";
import { bankDisplayName } from "@/app/lib/bank_names";

function fmtDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso.slice(0, 10);
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

function Pill({ tag }: { tag: Tag }) {
  const tx = useText();
  return (
    <span className={`inline-block rounded px-1.5 py-0.5 text-[10px] font-medium ${tag.className}`}>
      {tx(tag.label)}
    </span>
  );
}

/** Bank chips from the tagger (news_item_banks → comma-joined `tickers`).
 *  The whole card is an <a>, so chips are spans that router.push instead of
 *  nesting a second anchor. */
function BankChips({ tickers }: { tickers: string }) {
  const tx = useText();
  const router = useRouter();
  const all = tickers.split(",").filter(Boolean);
  const shown = all.slice(0, 3);
  return (
    <>
      {shown.map((t) => (
        <span
          key={t}
          role="link"
          tabIndex={0}
          title={tx(bankDisplayName(t))}
          onClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            router.push(`/banks/${t}`);
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              e.stopPropagation();
              router.push(`/banks/${t}`);
            }
          }}
          className="inline-block rounded bg-primary/10 px-1.5 py-0.5 text-[10px] font-medium text-primary hover:bg-primary/20"
        >
          {tx(t)}
        </span>
      ))}
      {all.length > shown.length && (
        <span className="inline-block px-0.5 py-0.5 text-[10px] text-muted-foreground">
          +{all.length - shown.length}
        </span>
      )}
    </>
  );
}

function PressCard({ item }: { item: NewsItem }) {
  const tx = useText();
  const outlet = item.category ?? "Press";
  return (
    <a
      href={item.url}
      target="_blank"
      rel="noopener noreferrer"
      className="group flex h-full flex-col rounded-[10px] border border-border bg-card p-3 transition hover:bg-accent hover:border-border/80"
    >
      <div className="mb-1 flex items-baseline justify-between gap-2 text-[10px] uppercase tracking-wide text-muted-foreground">
        <span className="font-medium text-foreground/80">{tx(outlet)}</span>
        <span className="tabular-nums">{tx(fmtDate(item.published_at))}</span>
      </div>
      <div className="text-sm font-medium leading-snug text-foreground group-hover:underline underline-offset-2 line-clamp-3">
        <span lang={item.language} translate="no">{item.title}</span>
      </div>
      {item.summary && (
        <p className="mt-1.5 text-xs leading-snug text-muted-foreground line-clamp-2"><span lang={item.language} translate="no">{item.summary}</span></p>
      )}
      <div className="mt-auto flex flex-wrap gap-1 pt-2">
        <Pill tag={topicTag(item.title)} />
        {item.tickers && <BankChips tickers={item.tickers} />}
        <span className="ml-auto text-[10px] text-muted-foreground opacity-0 transition group-hover:opacity-100">{tx("open ↗")}</span>
      </div>
    </a>
  );
}

export default function PressFeed({ items }: { items: NewsItem[] }) {
  const tx = useText();
  const [outlet, setOutlet] = useState<string | null>(null);

  // Outlet chips with counts, ordered by frequency.
  const outlets = useMemo(() => {
    const counts = new Map<string, number>();
    for (const it of items) {
      const o = it.category ?? "Press";
      counts.set(o, (counts.get(o) ?? 0) + 1);
    }
    return [...counts.entries()].sort((a, b) => b[1] - a[1]);
  }, [items]);

  const filtered = useMemo(
    () => (outlet ? items.filter((it) => (it.category ?? "Press") === outlet) : items),
    [items, outlet],
  );

  const chip = (active: boolean) =>
    `rounded-full border px-2.5 py-1 text-xs font-medium transition ${
      active
        ? "border-foreground bg-foreground text-background"
        : "border-border text-muted-foreground hover:bg-accent hover:text-foreground"
    }`;

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center gap-1.5">
        <button type="button" onClick={() => setOutlet(null)} className={chip(outlet === null)}>{tx("All ")}<span className="tabular-nums opacity-70">{tx(items.length)}</span>
        </button>
        {outlets.map(([o, n]) => (
          <button key={o} type="button" onClick={() => setOutlet(o)} className={chip(outlet === o)}>
            {tx(o)} <span className="tabular-nums opacity-70">{tx(n)}</span>
          </button>
        ))}
      </div>

      {filtered.length === 0 ? (
        <p className="text-sm text-muted-foreground italic">{tx("No items.")}</p>
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {filtered.map((it) => (
            <PressCard key={`${it.source}-${it.external_id}`} item={it} />
          ))}
        </div>
      )}
    </section>
  );
}
