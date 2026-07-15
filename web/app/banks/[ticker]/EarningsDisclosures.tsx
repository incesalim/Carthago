/**
 * EarningsDisclosures — the bank-detail "Earnings & Disclosures" block: a
 * compact results / presentations list next to a recent KAP-disclosures list
 * (matches the "Fresh / Flat" mock). Each is capped to the latest few items;
 * the headers link out to the full /earnings and /disclosures tabs.
 */
import Link from "next/link";
import type { EarningsEvent } from "@/app/lib/earnings";
import type { NewsItem } from "@/app/lib/news";
import { Card } from "@/app/components/ui/card";

/** "2026Q1" → "Q1 2026". */
function fmtPeriod(p: string | null): string {
  if (!p || p.length < 6) return p ?? "";
  return `${p.slice(4)} ${p.slice(0, 4)}`;
}
/** ISO date → "14 Apr 2026" (CSS upper-cases it). */
function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

/** Short uppercase tag per earnings kind (DECK / FILING / CALL / REPLAY). */
function tagOf(kind: string): string {
  if (kind === "presentation_deck") return "DECK";
  if (kind === "call") return "CALL";
  if (kind === "webcast_replay") return "REPLAY";
  return "FILING";
}
function tagClass(kind: string): string {
  if (kind === "presentation_deck") return "text-primary";
  if (kind === "call" || kind === "webcast_replay") return "text-warning";
  return "text-positive";
}

export default function EarningsDisclosures({
  earnings,
  disclosures,
  ticker,
}: {
  earnings: EarningsEvent[];
  disclosures: NewsItem[];
  ticker: string;
}) {
  const results = earnings.slice(0, 6);
  const kap = disclosures.slice(0, 6);

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      <Card className="p-5">
        <div className="mb-3 flex items-baseline justify-between gap-2">
          <div className="text-sm font-bold text-foreground">
            Quarterly results &amp; presentations
          </div>
          <Link href="/actions" className="text-xs text-muted-foreground hover:text-foreground">
            all banks →
          </Link>
        </div>
        {results.length === 0 ? (
          <div className="text-xs italic text-muted-foreground">None cached.</div>
        ) : (
          <ul className="space-y-3">
            {results.map((e) => (
              <li key={`${e.source}-${e.external_id}`} className="text-xs">
                <a
                  href={e.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="-mx-2 block rounded-lg px-2 py-1 transition hover:bg-accent"
                >
                  <div className="flex items-center gap-2 text-[10px] uppercase tracking-wide">
                    <span className={`font-bold ${tagClass(e.kind)}`}>{tagOf(e.kind)}</span>
                    {e.period && (
                      <span className="tabular-nums text-muted-foreground">
                        {fmtPeriod(e.period)}
                      </span>
                    )}
                  </div>
                  <div className="mt-0.5 leading-snug text-foreground line-clamp-2">
                    {e.title ?? "—"}
                  </div>
                </a>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card className="p-5">
        <div className="mb-3 flex items-baseline justify-between gap-2">
          <div className="text-sm font-bold text-foreground">Recent KAP disclosures</div>
          {kap.length > 0 && (
            <Link
              href={`/actions?ticker=${ticker}`}
              className="text-xs text-muted-foreground hover:text-foreground"
            >
              all {ticker} →
            </Link>
          )}
        </div>
        {kap.length === 0 ? (
          <div className="text-xs italic text-muted-foreground">No disclosures cached.</div>
        ) : (
          <ul className="space-y-3">
            {kap.map((it) => (
              <li key={it.external_id} className="text-xs">
                <a
                  href={it.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="-mx-2 block rounded-lg px-2 py-1 transition hover:bg-accent"
                >
                  <div className="text-[10px] uppercase tracking-wide tabular-nums text-muted-foreground">
                    {fmtDate(it.published_at)}
                  </div>
                  <div className="mt-0.5 leading-snug text-foreground line-clamp-2">
                    {it.title}
                  </div>
                </a>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
