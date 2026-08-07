/**
 * Filing-season tracker — which banks have published the in-window quarter,
 * and in what form. Read-time derivation over lanes we already ingest; no new
 * table, no scraper, no schedule:
 *
 *   - bank_audit_extractions / bank_audit_expected → the BRSA PDF's state per
 *     (bank, kind): extracted, failed, acquired-to-R2, or nothing;
 *   - bank_earnings (kind 'results_filing', source KAP) → independent evidence
 *     that a bank has RELEASED the period's results even though its BRSA PDF
 *     is not on its IR site yet (the İş Bankası 2026Q2 shape: Excel + KAP
 *     filing out, audit report pending).
 *
 * Discipline: "no signal" means exactly that — no evidence either way. Only a
 * KAP results filing may say "published"; absence of evidence never says
 * "not published" (unlisted banks may never produce a KAP signal at all).
 *
 * The window model mirrors refresh-audit.yml's schedule: Q4 files Jan 20–Mar 15
 * (annual consolidated runs late), Q1/Q2/Q3 file the 20th of month+1 through
 * the 20th of month+2. Between windows the tracker keeps showing the most
 * recently opened window so late filers stay visible.
 */
import { getDB } from "./db";

export type KindState = "extracted" | "failed" | "acquired" | "none";
export type BankStatus = "extracted" | "partial" | "acquired" | "results_only" | "none";

export interface FilingWindowInfo {
  /** Period being tracked, e.g. "2026Q2". */
  period: string;
  /** The previous quarter — used as the shape of what each bank normally files. */
  priorPeriod: string;
  opensISO: string;
  closesISO: string;
  open: boolean;
  /** 1-based day inside the window; null when the window has closed. */
  dayOfWindow: number | null;
}

export interface BankFiling {
  ticker: string;
  name: string;
  status: BankStatus;
  /** Per filing kind, in display order (unconsolidated first, like BRSA publication order). */
  kinds: { kind: string; state: KindState }[];
  /** Earliest KAP results-filing date for the period (ISO), or null = no evidence. */
  resultsAt: string | null;
  resultsUrl: string | null;
}

export interface FilingSeasonReport {
  window: FilingWindowInfo;
  banks: BankFiling[];
  counts: Record<BankStatus, number>;
}

const DAY_MS = 86_400_000;
const KIND_ORDER = ["unconsolidated", "consolidated"];

interface WindowSpec {
  period: string;
  opens: number; // UTC ms
  closes: number;
}

/** The four windows whose OPEN date falls in calendar year `y`. */
function windowsOpeningIn(y: number): WindowSpec[] {
  return [
    { period: `${y - 1}Q4`, opens: Date.UTC(y, 0, 20), closes: Date.UTC(y, 2, 15) },
    { period: `${y}Q1`, opens: Date.UTC(y, 3, 20), closes: Date.UTC(y, 4, 20) },
    { period: `${y}Q2`, opens: Date.UTC(y, 6, 20), closes: Date.UTC(y, 7, 20) },
    { period: `${y}Q3`, opens: Date.UTC(y, 9, 20), closes: Date.UTC(y, 10, 20) },
  ];
}

function iso(ms: number): string {
  return new Date(ms).toISOString().slice(0, 10);
}

export function priorPeriod(period: string): string {
  const m = /^(\d{4})Q([1-4])$/.exec(period);
  if (!m) return period;
  const [y, q] = [Number(m[1]), Number(m[2])];
  return q === 1 ? `${y - 1}Q4` : `${y}Q${q - 1}`;
}

/** The window being tracked "now": the most recently OPENED one. */
export function trackingWindow(now: Date): FilingWindowInfo {
  const t = now.getTime();
  const candidates = [...windowsOpeningIn(now.getUTCFullYear() - 1), ...windowsOpeningIn(now.getUTCFullYear())]
    .filter((w) => w.opens <= t)
    .sort((a, b) => a.opens - b.opens);
  const w = candidates[candidates.length - 1];
  const open = t <= w.closes + DAY_MS - 1; // the close date itself still counts
  return {
    period: w.period,
    priorPeriod: priorPeriod(w.period),
    opensISO: iso(w.opens),
    closesISO: iso(w.closes),
    open,
    dayOfWindow: open ? Math.floor((t - w.opens) / DAY_MS) + 1 : null,
  };
}

export interface FilingSignals {
  banks: { ticker: string; name: string }[];
  /** (bank, kind) rows the bank filed in the PRIOR period — its normal shape. */
  priorKinds: { bank_ticker: string; kind: string }[];
  /** Current-period expected rows (exist once the PDF/census knows the period). */
  expected: { bank_ticker: string; kind: string; pdf_present: number }[];
  extractions: { bank_ticker: string; kind: string; success: number }[];
  /** KAP results filings for the period (any order; reduced to first per ticker). */
  results: { ticker: string; event_date: string; url: string }[];
}

function rollup(kindStates: KindState[], hasResults: boolean): BankStatus {
  const extracted = kindStates.filter((s) => s === "extracted").length;
  if (extracted === kindStates.length && kindStates.length > 0) return "extracted";
  if (extracted > 0) return "partial";
  if (kindStates.some((s) => s === "acquired" || s === "failed")) return "acquired";
  return hasResults ? "results_only" : "none";
}

/** Pure derivation — everything the panel shows, computed from the signals. */
export function deriveFilingSeason(window: FilingWindowInfo, sig: FilingSignals): FilingSeasonReport {
  const priorShape = new Map<string, Set<string>>();
  for (const r of sig.priorKinds) {
    (priorShape.get(r.bank_ticker) ?? priorShape.set(r.bank_ticker, new Set()).get(r.bank_ticker)!).add(r.kind);
  }
  const pdfPresent = new Set(
    sig.expected.filter((r) => r.pdf_present).map((r) => `${r.bank_ticker}|${r.kind}`),
  );
  const currentKinds = new Map<string, Set<string>>();
  for (const r of [...sig.expected, ...sig.extractions]) {
    (currentKinds.get(r.bank_ticker) ?? currentKinds.set(r.bank_ticker, new Set()).get(r.bank_ticker)!).add(r.kind);
  }
  const extraction = new Map<string, number>();
  for (const r of sig.extractions) extraction.set(`${r.bank_ticker}|${r.kind}`, r.success);

  const firstResult = new Map<string, { event_date: string; url: string }>();
  for (const r of sig.results) {
    const seen = firstResult.get(r.ticker);
    if (!seen || r.event_date < seen.event_date) firstResult.set(r.ticker, r);
  }

  const banks: BankFiling[] = sig.banks.map(({ ticker, name }) => {
    // The bank's filing shape: what it filed last quarter; else whatever the
    // current period already knows; else assume both kinds rather than hiding one.
    const shape = priorShape.get(ticker) ?? currentKinds.get(ticker) ?? new Set(KIND_ORDER);
    const kinds = KIND_ORDER.filter((k) => shape.has(k)).map((kind) => {
      const success = extraction.get(`${ticker}|${kind}`);
      const state: KindState =
        success != null
          ? success
            ? "extracted"
            : "failed"
          : pdfPresent.has(`${ticker}|${kind}`)
            ? "acquired"
            : "none";
      return { kind, state };
    });
    const results = firstResult.get(ticker) ?? null;
    return {
      ticker,
      name,
      kinds,
      resultsAt: results?.event_date ?? null,
      resultsUrl: results?.url ?? null,
      status: rollup(kinds.map((k) => k.state), results != null),
    };
  });

  const counts: Record<BankStatus, number> = {
    extracted: 0,
    partial: 0,
    acquired: 0,
    results_only: 0,
    none: 0,
  };
  for (const b of banks) counts[b.status] += 1;
  banks.sort((a, b) => a.ticker.localeCompare(b.ticker));
  return { window, banks, counts };
}

type DB = Awaited<ReturnType<typeof getDB>>;

/** Run a list query, returning [] on any error (missing table degrades quietly). */
async function safeAll<T>(db: DB, sql: string, params: unknown[] = []): Promise<T[]> {
  try {
    const stmt = db.prepare(sql);
    const { results } = await (params.length ? stmt.bind(...params) : stmt).all<T>();
    return results ?? [];
  } catch {
    return [];
  }
}

/** Uncached on purpose: this is the admin control surface, computed on view. */
export async function getFilingSeason(now = new Date()): Promise<FilingSeasonReport> {
  const window = trackingWindow(now);
  const db = await getDB();
  const [banks, priorKinds, expected, extractions, results] = await Promise.all([
    safeAll<{ ticker: string; name: string }>(db, "SELECT ticker, name FROM banks ORDER BY ticker"),
    safeAll<{ bank_ticker: string; kind: string }>(
      db,
      "SELECT bank_ticker, kind FROM bank_audit_expected WHERE period = ?",
      [window.priorPeriod],
    ),
    safeAll<{ bank_ticker: string; kind: string; pdf_present: number }>(
      db,
      "SELECT bank_ticker, kind, pdf_present FROM bank_audit_expected WHERE period = ?",
      [window.period],
    ),
    safeAll<{ bank_ticker: string; kind: string; success: number }>(
      db,
      "SELECT bank_ticker, kind, success FROM bank_audit_extractions WHERE period = ?",
      [window.period],
    ),
    safeAll<{ ticker: string; event_date: string; url: string }>(
      db,
      "SELECT ticker, event_date, url FROM bank_earnings WHERE period = ? AND kind = 'results_filing'",
      [window.period],
    ),
  ]);
  return deriveFilingSeason(window, { banks, priorKinds, expected, extractions, results });
}
