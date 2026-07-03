/**
 * BankNewsSection — the bank-detail "In the News" block: press + Google News
 * items tagged with this bank by the deterministic name→ticker matcher
 * (news_item_banks junction; src/news/bank_tagger.py). Yahoo-Finance-style
 * per-ticker news: compact link-out rows, no cached body — matches the
 * EarningsDisclosures list style.
 */
import Link from "next/link";
import type { NewsItem } from "@/app/lib/news";
import { Card } from "@/app/components/ui/card";

/** ISO date → "14 Apr 2026" (CSS upper-cases it). */
function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

export default function BankNewsSection({ items }: { items: NewsItem[] }) {
  return (
    <Card className="p-5">
      <div className="mb-3 flex items-baseline justify-between gap-2">
        <div className="text-sm font-bold text-foreground">Press coverage</div>
        <Link href="/news" className="text-xs text-muted-foreground hover:text-foreground">
          all sector news →
        </Link>
      </div>
      <ul className="grid grid-cols-1 gap-x-6 gap-y-3 lg:grid-cols-2">
        {items.map((it) => (
          <li key={`${it.source}-${it.external_id}`} className="text-xs">
            <a
              href={it.url}
              target="_blank"
              rel="noopener noreferrer"
              className="-mx-2 block rounded-lg px-2 py-1 transition hover:bg-accent"
            >
              <div className="flex items-center gap-2 text-[10px] uppercase tracking-wide text-muted-foreground">
                <span className="tabular-nums">{fmtDate(it.published_at)}</span>
                <span className="truncate font-medium text-foreground/70">
                  {it.category ?? "Press"}
                </span>
              </div>
              <div className="mt-0.5 leading-snug text-foreground line-clamp-2">
                {it.title}
              </div>
            </a>
          </li>
        ))}
      </ul>
    </Card>
  );
}
