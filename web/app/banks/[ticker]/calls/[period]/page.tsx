/**
 * /banks/[ticker]/calls/[period] — the earnings-call transcript reader.
 *
 * One call, rendered turn by turn with the speaker and the role the source
 * tagged them with. Deliberately plain: this is a document to read, so the page
 * is a column of prose with a mono meta band above it, not a dashboard.
 *
 * Two honesty notes are rendered from the row's own counters rather than
 * asserted in prose:
 *   - unresolved speaker markers ('[indiscernible]'), which is why analyst
 *     identity on these transcripts is not something to key on;
 *   - that the figures spoken aloud are transcription, not extraction — the
 *     audited numbers live in the bank_audit_* lanes and on the bank page.
 */
import { getText } from "@/i18n/server";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { callDetail, TRANSCRIPT_BANKS } from "@/app/lib/transcripts";
import { bankDisplayName } from "@/app/lib/bank_names";
import { Colophon, DeskHeader, SecHead } from "@/app/components/desk";
import { nf } from "@/app/lib/chart-format";

export const dynamic = "force-dynamic";

interface Props {
  params: Promise<{ ticker: string; period: string }>;
}

/** "2026Q1" → "Q1 2026". */
function fmtPeriod(p: string): string {
  return p.length < 6 ? p : `${p.slice(4)} ${p.slice(0, 4)}`;
}

/** ISO date → "28 Apr 2026". */
function fmtDate(iso: string | null): string | null {
  if (!iso) return null;
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return null;
  return new Date(t).toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const tx = await getText();
  const { ticker: raw, period: rawPeriod } = await params;
  const ticker = raw.toUpperCase();
  const period = rawPeriod.toUpperCase();
  const name = bankDisplayName(ticker);
  const title = tx("{0} — {1} earnings call transcript", {0: name, 1: fmtPeriod(period)});
  return {
    title,
    description: tx("Full transcript of the {0} ({1}) {2} earnings call: management remarks and the analyst Q&A.", {0: name, 1: ticker, 2: fmtPeriod(period)}),
    alternates: { canonical: `/banks/${ticker}/calls/${period}` },
  };
}

export default async function CallTranscriptPage({ params }: Props) {
  const tx = await getText();
  const { ticker: raw, period: rawPeriod } = await params;
  const ticker = raw.toUpperCase();
  const period = rawPeriod.toUpperCase();

  if (!TRANSCRIPT_BANKS.has(ticker)) notFound();
  const call = await callDetail(ticker, period);
  if (!call) notFound();

  const name = bankDisplayName(ticker);
  const date = fmtDate(call.call_date);
  const unresolved = call.indiscernible_count ?? 0;

  return (
    <main className="mx-auto max-w-3xl px-4 py-8 sm:px-6 lg:px-8">
      <DeskHeader
        title={tx("{0} — {1} earnings call", {0: name, 1: fmtPeriod(period)})}
        record={tx(date ? tx("Call held {0}", {0: date}) : "Call date not stated by the source")}
        right={
          <Link href={`/banks/${ticker}`} className="hover:underline">
            ← {tx(ticker)}
          </Link>
        }
      />

      <div className="mt-4 flex flex-wrap gap-x-5 gap-y-1 border-y border-border py-2 font-mono text-[11px] uppercase tracking-wide text-muted-foreground">
        {call.turn_count != null && <span>{tx(nf(call.turn_count, 0))}{tx(" turns")}</span>}
        {call.word_count != null && <span>{tx(nf(call.word_count, 0))}{tx(" words")}</span>}
        {call.speaker_count != null && (
          <span>{tx(nf(call.speaker_count, 0))}{tx(" speakers")}</span>
        )}
        {call.analyst_turn_count != null && (
          <span>{tx(nf(call.analyst_turn_count, 0))}{tx(" analyst turns")}</span>
        )}
        <a
          href={call.source_url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-primary hover:underline"
        >{tx("source ↗")}</a>
      </div>

      <p className="mt-3 text-xs leading-relaxed text-muted-foreground">{tx("Machine transcription of the bank's own investor call.")}{unresolved > 0 && (
          <>
            {" "}{tx("The source left ")}{tx(nf(unresolved, 0))}{tx(" speaker reference")}{tx(unresolved === 1 ? "" : "s")}{tx(" unresolved in this call, so who asked a given question is not reliable here.")}</>
        )}{" "}{tx("Figures are spoken aloud and transcribed, not extracted — the audited numbers are on the")}{" "}
        <Link href={`/banks/${ticker}`} className="text-primary hover:underline">
          {tx(ticker)}{tx(" financials")}</Link>
        .
      </p>

      <div className="mt-8">
        <SecHead title={tx("Transcript")} meta={tx(call.title ?? undefined)} />
        {call.turns.length === 0 ? (
          <p className="mt-3 text-xs italic text-muted-foreground">{tx("The stored transcript for this call has no readable turns. Follow the source link above.")}</p>
        ) : (
          <div className="mt-4 space-y-6">
            {call.turns.map((t) => (
              <article key={t.seq}>
                <div className="mb-1 flex items-baseline gap-2">
                  <span className="text-xs font-bold text-foreground">
                    {tx(t.speaker ?? "Unattributed")}
                  </span>
                  {t.role && (
                    <span className="font-mono text-[10px] uppercase tracking-wide text-muted-foreground">
                      {tx(t.role)}
                    </span>
                  )}
                </div>
                <p className="whitespace-pre-line text-sm leading-relaxed text-foreground">
                  {tx(t.text)}
                </p>
              </article>
            ))}
          </div>
        )}
      </div>

      <Colophon />
    </main>
  );
}
