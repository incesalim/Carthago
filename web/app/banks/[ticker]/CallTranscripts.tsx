/**
 * CallTranscripts — the bank-detail "Earnings calls" block: one row per call,
 * newest first, linking into the reader at /banks/[ticker]/calls/[period].
 *
 * Each row carries the call's own shape (turns · words) and, where the source
 * lost speaker names to '[indiscernible]', says so. That marker is not cosmetic:
 * it is why analyst identity on these transcripts cannot be keyed on, and the
 * only honest place to surface it is next to the call it affects.
 */
import Link from "next/link";
import type { CallSummary } from "@/app/lib/transcripts";
import { Card } from "@/app/components/ui/card";
import { nf } from "@/app/lib/chart-format";

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

export default function CallTranscripts({
  calls,
  ticker,
  holdsCalls,
}: {
  calls: CallSummary[];
  ticker: string;
  holdsCalls: boolean;
}) {
  if (calls.length === 0) {
    return (
      <Card className="p-5">
        <div className="text-xs italic text-muted-foreground">
          {holdsCalls
            ? "No transcripts cached yet."
            : "This bank does not hold an English earnings call."}
        </div>
      </Card>
    );
  }

  return (
    <Card className="p-5">
      <ul className="divide-y divide-border">
        {calls.map((c) => {
          const date = fmtDate(c.call_date);
          return (
            <li key={c.period} className="py-2 first:pt-0 last:pb-0">
              <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
                <Link
                  href={`/banks/${ticker}/calls/${c.period}`}
                  className="text-xs font-bold text-primary hover:underline"
                >
                  {fmtPeriod(c.period)} earnings call
                </Link>
                <div className="flex items-baseline gap-3 text-[10px] uppercase tracking-wide text-muted-foreground">
                  {date && <span className="tabular-nums">{date}</span>}
                  {c.word_count != null && (
                    <span className="tabular-nums">{nf(c.word_count, 0)} words</span>
                  )}
                  {c.turn_count != null && (
                    <span className="tabular-nums">{nf(c.turn_count, 0)} turns</span>
                  )}
                </div>
              </div>
              {c.indiscernible_count != null && c.indiscernible_count > 0 && (
                <div className="mt-0.5 text-[10px] text-muted-foreground">
                  {nf(c.indiscernible_count, 0)} unresolved speaker marker
                  {c.indiscernible_count === 1 ? "" : "s"} in this transcript
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </Card>
  );
}
