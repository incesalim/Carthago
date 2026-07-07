/**
 * /earnings — per-bank earnings calendar + investor-presentation decks.
 *
 * Two free, deterministic sources (no paid transcript vendor, no LLM):
 *   - KAP results filings (kind 'results_filing') — when each bank filed its
 *     quarterly financial report, derived from the KAP disclosures already in
 *     news_items. Banks do NOT file earnings-call invites on KAP, so there is
 *     no call/webcast lane here.
 *   - IR presentation decks (kind 'presentation_deck') — the quarterly earnings
 *     presentation PDF from each bank's investor-relations site (links out).
 *
 * Pipeline: scripts/sync_news.py + scripts/update_presentations.py → D1 → here.
 */
import type { Metadata } from "next";
import Link from "next/link";
import {
  earningsSummary,
  groupByTicker,
  kindLabel,
  latestEarnings,
  type EarningsEvent,
  type EarningsKind,
} from "@/app/lib/earnings";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Turkish Banks — Earnings Calendar & IR",
  description: "Earnings and results calendar for Türkiye's listed banks (KAP filings) plus investor-relations presentations.",
  alternates: { canonical: "/earnings" },
};

function fmtDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso.slice(0, 10);
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

function fmtPeriod(p: string | null): string {
  if (!p || p.length < 6) return p ?? "";
  return `${p.slice(4)} ${p.slice(0, 4)}`; // 2026Q1 → Q1 2026
}

const KIND_STYLE: Record<EarningsKind, string> = {
  results_filing: "border-l-primary bg-primary/10 text-primary",
  presentation_deck: "border-l-indigo-600 bg-indigo-500/10 text-indigo-700 dark:text-indigo-300",
  call: "border-l-emerald-600 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  presentation_filing: "border-l-indigo-600 bg-indigo-500/10 text-indigo-700 dark:text-indigo-300",
  webcast_replay: "border-l-amber-600 bg-amber-500/10 text-amber-700 dark:text-amber-300",
};

function linkText(kind: string): string {
  if (kind === "presentation_deck") return "Open presentation PDF ↗";
  if (kind === "results_filing") return "View KAP filing ↗";
  return "Open ↗";
}

function EventRow({ e }: { e: EarningsEvent }) {
  const badge = KIND_STYLE[e.kind as EarningsKind] ?? "border-l-border bg-muted text-muted-foreground";
  return (
    <div className={`rounded-md border border-border border-l-4 bg-card p-3 hover:bg-accent transition ${badge.split(" ")[0]}`}>
      <div className="flex flex-wrap items-center gap-2 text-[10px] uppercase tracking-wide mb-1">
        <span className={`rounded px-1.5 py-0.5 font-semibold ${badge}`}>{kindLabel(e.kind)}</span>
        {e.period && <span className="text-foreground font-medium tabular-nums">{fmtPeriod(e.period)}</span>}
        <span className="text-muted-foreground tabular-nums ml-auto">{fmtDate(e.event_date)}</span>
      </div>
      <a
        href={e.url}
        target="_blank"
        rel="noopener noreferrer"
        className="block text-sm text-foreground leading-snug hover:underline"
      >
        {e.title || linkText(e.kind)}
      </a>
      <div className="text-xs text-muted-foreground mt-0.5">{linkText(e.kind)}</div>
    </div>
  );
}

export default async function EarningsPage() {
  const [events, summary] = await Promise.all([latestEarnings(300), earningsSummary()]);
  const byBank = groupByTicker(events);
  // Banks ordered by their most-recent event (events are already newest-first).
  const banks = Array.from(byBank.keys());

  return (
    <main className="mx-auto w-full px-4 py-8 sm:px-6 lg:px-8 space-y-6 max-w-5xl">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Earnings &amp; Presentations</h1>
        <p className="text-sm text-muted-foreground">
          When each BIST-listed bank filed its quarterly results (KAP), plus the quarterly
          investor-presentation decks from their IR sites. Earnings-call transcripts and audio
          are not freely available for Turkish banks, so they are not shown here.
        </p>
        <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground pt-2">
          {summary.map((s) => (
            <span key={s.kind}>
              <span className="font-semibold text-foreground">{kindLabel(s.kind)}</span>
              {" — "}
              {s.total} across {s.banks} bank{s.banks === 1 ? "" : "s"}
              {s.latest && <span> · latest {fmtDate(s.latest)}</span>}
            </span>
          ))}
          <Link href="/disclosures" className="underline hover:text-foreground">
            All KAP disclosures →
          </Link>
        </div>
      </header>

      {banks.length === 0 ? (
        <div className="text-xs text-muted-foreground italic">No earnings data cached yet.</div>
      ) : (
        <div className="space-y-6">
          {banks.map((ticker) => (
            <section key={ticker} className="space-y-2">
              <div className="flex items-baseline gap-3 border-b border-border pb-1">
                <Link
                  href={`/banks/${ticker}`}
                  className="text-lg font-semibold tracking-tight hover:underline"
                >
                  {ticker}
                </Link>
                <span className="text-xs text-muted-foreground">
                  {byBank.get(ticker)!.length} event{byBank.get(ticker)!.length === 1 ? "" : "s"}
                </span>
              </div>
              <div className="grid gap-2 sm:grid-cols-2">
                {byBank.get(ticker)!.map((e) => (
                  <EventRow key={`${e.source}-${e.external_id}`} e={e} />
                ))}
              </div>
            </section>
          ))}
        </div>
      )}
    </main>
  );
}
