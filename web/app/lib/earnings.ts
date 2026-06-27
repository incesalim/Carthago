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
