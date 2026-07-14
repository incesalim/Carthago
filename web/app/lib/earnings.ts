/**
 * D1 queries for the earnings lane (bank_earnings table).
 *
 * Two sources, one table:
 *   - kap → results-filing events projected from KAP disclosures
 *           (kind 'results_filing'; the financial-report filing date per quarter)
 *   - ir  → investor/earnings presentation decks from banks' IR sites
 *           (kind 'presentation_deck'; links out to the PDF)
 *
 * Note: Turkish banks do NOT file earnings-call invites or presentation decks on
 * KAP, so the 'call' / 'presentation_filing' / 'webcast_replay' kinds exist in
 * the schema but are not populated today (see src/earnings/classify.py).
 *
 * Pipeline: scripts/sync_news.py (tier 1) + scripts/update_presentations.py
 * (tier 2) → SQLite → push_to_d1.py → here.
 */
import { cachedAll } from "./db";

export type EarningsKind =
  | "results_filing"
  | "presentation_deck"
  | "call"
  | "presentation_filing"
  | "webcast_replay";

export interface EarningsEvent {
  source: "kap" | "ir";
  external_id: string;
  ticker: string;
  period: string | null;
  kind: EarningsKind;
  event_date: string;
  title: string | null;
  url: string;
  language: string | null;
}

const KIND_LABELS: Record<EarningsKind, string> = {
  results_filing: "Results filed",
  presentation_deck: "Presentation",
  call: "Earnings call",
  presentation_filing: "Presentation filing",
  webcast_replay: "Webcast replay",
};

export function kindLabel(k: string): string {
  return KIND_LABELS[k as EarningsKind] ?? k;
}

const _COLS = `source, external_id, ticker, period, kind, event_date, title, url, language`;

/**
 * How long after a quarter-end the results filings actually landed.
 *
 * The /pipeline and Desk "Ahead" blocks used to hand-type "AUG–SEP" for the next
 * BRSA filings. This table records the filings that have ALREADY happened, so the
 * window is observed rather than guessed. Returns null below a handful of
 * filings — a window we cannot support is a window we do not print.
 *
 * Note the basis: `results_filing` rows come from KAP, so this measures the
 * LISTED banks, who file first. It is the lag to the first filings landing, not
 * to the whole 38-bank universe being in.
 */
export async function filingLagDays(): Promise<{
  loDays: number;
  hiDays: number;
  n: number;
} | null> {
  const rows = await cachedAll<{ period: string; event_date: string }>(
    `SELECT period, event_date
       FROM bank_earnings
      WHERE kind = 'results_filing' AND period IS NOT NULL
      ORDER BY event_date DESC
      LIMIT 200`,
  );

  const lags: number[] = [];
  for (const r of rows) {
    const q = /^(\d{4})Q([1-4])$/.exec(r.period);
    if (!q) continue;
    // Day 0 of the month after the quarter = the quarter's last day.
    const qEnd = Date.UTC(Number(q[1]), Number(q[2]) * 3, 0);
    const filed = Date.parse(r.event_date);
    if (Number.isNaN(filed)) continue;
    const days = Math.round((filed - qEnd) / 86_400_000);
    if (days > 0 && days < 200) lags.push(days);
  }
  if (lags.length < 3) return null;

  lags.sort((a, b) => a - b);
  return { loDays: lags[0], hiDays: lags[lags.length - 1], n: lags.length };
}

/** Latest earnings events across all banks, newest first. */
export async function latestEarnings(limit = 250): Promise<EarningsEvent[]> {
  return cachedAll<EarningsEvent>(
    `SELECT ${_COLS}
       FROM bank_earnings
       ORDER BY event_date DESC, ticker
       LIMIT ?`,
    [limit],
  );
}

/** Earnings events for one bank ticker, newest first. */
export async function earningsByTicker(
  ticker: string,
  limit = 40,
): Promise<EarningsEvent[]> {
  return cachedAll<EarningsEvent>(
    `SELECT ${_COLS}
       FROM bank_earnings
       WHERE ticker = ?
       ORDER BY event_date DESC
       LIMIT ?`,
    [ticker.toUpperCase(), limit],
  );
}

/** Per-kind counts + latest event date — used by the /earnings header. */
export async function earningsSummary(): Promise<
  { kind: EarningsKind; total: number; banks: number; latest: string }[]
> {
  return cachedAll<{ kind: EarningsKind; total: number; banks: number; latest: string }>(
    `SELECT kind,
              COUNT(*) AS total,
              COUNT(DISTINCT ticker) AS banks,
              MAX(event_date) AS latest
       FROM bank_earnings
       GROUP BY kind
       ORDER BY total DESC`,
  );
}

/** Group a flat event list by ticker, preserving newest-first order. */
export function groupByTicker(events: EarningsEvent[]): Map<string, EarningsEvent[]> {
  const out = new Map<string, EarningsEvent[]>();
  for (const e of events) {
    const arr = out.get(e.ticker) ?? [];
    arr.push(e);
    out.set(e.ticker, arr);
  }
  return out;
}
