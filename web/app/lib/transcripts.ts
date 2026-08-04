/**
 * D1 queries for the earnings-call transcript lane (bank_call_transcripts).
 *
 * One row per call; the speaker turns are a JSON array in `transcript_json`,
 * parsed here rather than stored per-row (a call is only read whole, and D1
 * bills rows written).
 *
 * Coverage is bounded by the source, not by us: of the listed banks only
 * AKBNK / GARAN / ISCTR / YKBNK / HALKB / VAKBN / TSKB / ALBRK hold an English
 * call at all. SKBNK and ICBCT hold none and QNBFB is delisted, so an empty
 * result for those three is the correct answer and the UI says so rather than
 * implying a fetch failed.
 *
 * Pipeline: scripts/update_transcripts.py → SQLite → push_to_d1.py → here.
 */
import { cachedAll } from "./db";

/** Banks the source publishes calls for. Anything else has none to show. */
export const TRANSCRIPT_BANKS = new Set([
  "AKBNK", "GARAN", "ISCTR", "YKBNK", "HALKB", "VAKBN", "TSKB", "ALBRK",
]);

export interface CallTurn {
  seq: number;
  speaker: string | null;
  role: string | null;
  text: string;
}

export interface CallSummary {
  bank_ticker: string;
  period: string;
  call_date: string | null;
  source_url: string;
  title: string | null;
  turn_count: number | null;
  word_count: number | null;
  speaker_count: number | null;
  analyst_turn_count: number | null;
  indiscernible_count: number | null;
}

export interface CallDetail extends CallSummary {
  turns: CallTurn[];
}

const _COLS = `bank_ticker, period, call_date, source_url, title, turn_count,
               word_count, speaker_count, analyst_turn_count, indiscernible_count`;

/** Calls for one bank, newest quarter first. */
export async function callsByTicker(
  ticker: string,
  limit = 40,
): Promise<CallSummary[]> {
  return cachedAll<CallSummary>(
    `SELECT ${_COLS}
       FROM bank_call_transcripts
      WHERE bank_ticker = ?
      ORDER BY period DESC
      LIMIT ?`,
    [ticker.toUpperCase(), limit],
  );
}

/** One call, with its turns parsed out of transcript_json. */
export async function callDetail(
  ticker: string,
  period: string,
): Promise<CallDetail | null> {
  const rows = await cachedAll<CallSummary & { transcript_json: string }>(
    `SELECT ${_COLS}, transcript_json
       FROM bank_call_transcripts
      WHERE bank_ticker = ? AND period = ?
      LIMIT 1`,
    [ticker.toUpperCase(), period.toUpperCase()],
  );
  const row = rows[0];
  if (!row) return null;

  // A malformed blob must degrade to "no turns", not to a 500 on the route:
  // the row's metadata is still worth rendering with a link out to the source.
  let turns: CallTurn[] = [];
  try {
    const parsed: unknown = JSON.parse(row.transcript_json);
    if (Array.isArray(parsed)) turns = parsed as CallTurn[];
  } catch {
    turns = [];
  }

  const { transcript_json: _drop, ...rest } = row;
  void _drop;
  return { ...rest, turns };
}

/** Most recent calls across all banks — the results-season view. */
export async function latestCalls(limit = 40): Promise<CallSummary[]> {
  return cachedAll<CallSummary>(
    `SELECT ${_COLS}
       FROM bank_call_transcripts
      ORDER BY call_date DESC, bank_ticker
      LIMIT ?`,
    [limit],
  );
}
