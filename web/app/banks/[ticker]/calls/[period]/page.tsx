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
  const { ticker: raw, period: rawPeriod } = await params;
  const ticker = raw.toUpperCase();
  const period = rawPeriod.toUpperCase();
  const name = bankDisplayName(ticker);
  const title = `${name} — ${fmtPeriod(period)} earnings call transcript`;
  return {
    title,
    description: `Full transcript of the ${name} (${ticker}) ${fmtPeriod(period)} earnings call: management remarks and the analyst Q&A.`,
    alternates: { canonical: `/banks/${ticker}/calls/${period}` },
  };
}

export default async function CallTranscriptPage({ params }: Props) {
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
        title={`${name} — ${fmtPeriod(period)} earnings call`}
        record={date ? `Call held ${date}` : "Call date not stated by the source"}
        right={
          <Link href={`/banks/${ticker}`} className="hover:underline">
            ← {ticker}
          </Link>
        }
      />

      <div className="mt-4 flex flex-wrap gap-x-5 gap-y-1 border-y border-border py-2 font-mono text-[11px] uppercase tracking-wide text-muted-foreground">
        {call.turn_count != null && <span>{nf(call.turn_count, 0)} turns</span>}
        {call.word_count != null && <span>{nf(call.word_count, 0)} words</span>}
        {call.speaker_count != null && (
          <span>{nf(call.speaker_count, 0)} speakers</span>
        )}
        {call.analyst_turn_count != null && (
          <span>{nf(call.analyst_turn_count, 0)} analyst turns</span>
        )}
        <a
          href={call.source_url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-primary hover:underline"
        >
          source ↗
        </a>
      </div>

      <p className="mt-3 text-xs leading-relaxed text-muted-foreground">
        Machine transcription of the bank&apos;s own investor call.
        {unresolved > 0 && (
          <>
            {" "}
            The source left {nf(unresolved, 0)} speaker reference
            {unresolved === 1 ? "" : "s"} unresolved in this call, so who asked a
            given question is not reliable here.
          </>
        )}{" "}
        Figures are spoken aloud and transcribed, not extracted — the audited
        numbers are on the{" "}
        <Link href={`/banks/${ticker}`} className="text-primary hover:underline">
          {ticker} financials
        </Link>
        .
      </p>

      <div className="mt-8">
        <SecHead title="Transcript" meta={call.title ?? undefined} />
        {call.turns.length === 0 ? (
          <p className="mt-3 text-xs italic text-muted-foreground">
            The stored transcript for this call has no readable turns. Follow the
            source link above.
          </p>
        ) : (
          <div className="mt-4 space-y-6">
            {call.turns.map((t) => (
              <article key={t.seq}>
                <div className="mb-1 flex items-baseline gap-2">
                  <span className="text-xs font-bold text-foreground">
                    {t.speaker ?? "Unattributed"}
                  </span>
                  {t.role && (
                    <span className="font-mono text-[10px] uppercase tracking-wide text-muted-foreground">
                      {t.role}
                    </span>
                  )}
                </div>
                <p className="whitespace-pre-line text-sm leading-relaxed text-foreground">
                  {t.text}
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
