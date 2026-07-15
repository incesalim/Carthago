/**
 * ahead — what lands next, derived instead of typed.
 *
 * Five pages carried a hand-typed `Ahead` schedule — about seventeen rows of
 * `{ when: "JUL 23" }` and `{ when: "AUG ~12" }`. They were correct when written
 * and silently wrong a fortnight later: the only forward-looking surface on the
 * site was also the only fully hand-authored one, and nothing derived it.
 *
 * The row kinds come from two places:
 *
 *   SCRAPED (release_calendar in D1, from TCMB's published calendar):
 *     mpc                the rate decision
 *     mpc-minutes        "Summary of the MPC Meeting"
 *     inflation-report   quarterly
 *     fsr                Financial Stability Report, twice-yearly
 *   DERIVED (from record cadence — no external source needed):
 *     bddk-monthly   the record month is in D1; a bulletin for month M lands about
 *                    the 12th of M+2 (May's record was in by 12 Jul; June's ~12 Aug)
 *     brsa-filings   `bank_earnings` holds the KAP filing dates that ALREADY
 *                    happened, so the lag from quarter-end is observed, not guessed
 *
 * MPC used to be hand-transcribed into MPC_DATES; it is now scraped, and MPC_DATES
 * survives only as the render-time fallback when the scrape is unavailable. The
 * report kinds have no fallback — absent a scrape, their rows are simply omitted.
 *
 * The purely cadence-based rows ("FRI", "THU") never go stale and stay as literals
 * on the pages: a claim that is true every week is not a claim.
 *
 * Every function here is pure and takes `now` (and the scraped events) as
 * arguments, so the schedule is unit-testable and the pages (all `force-dynamic`)
 * pass the real request time. A kind whose date cannot be established returns
 * nothing and the page OMITS the row — never a date in the past.
 */

export type AheadKind =
  | "mpc"
  | "mpc-minutes"
  | "inflation-report"
  | "fsr"
  | "bddk-monthly"
  | "brsa-filings";

/** A scraped release_calendar row (D1 `kind` is snake_case: 'mpc_decision', …). */
export interface CalendarEvent {
  kind: string;
  event_date: string;
}

/** D1 `release_calendar.kind` → the AheadKind it feeds. */
const TCMB_KIND: Record<string, AheadKind> = {
  mpc_decision: "mpc",
  mpc_minutes: "mpc-minutes",
  inflation_report: "inflation-report",
  financial_stability_report: "fsr",
};

/**
 * The MPC fallback list — no longer the source, only the safety net.
 *
 * The dates are scraped into `release_calendar` now (src/release_calendar), so
 * this is used only when the scrape is unavailable at render time. It is still
 * guarded by `scripts/check_calendar_fresh.py` (FAILS CI under 90 days of
 * runway) so the fallback itself can never quietly run out.
 *
 * Transcribed 2026-07-14. TCMB lists no July/August 2027 meeting.
 */
export const MPC_DATES: readonly string[] = [
  "2026-01-22",
  "2026-03-12",
  "2026-04-22",
  "2026-06-11",
  "2026-07-23",
  "2026-09-10",
  "2026-10-22",
  "2026-12-10",
  "2027-01-21",
  "2027-03-18",
  "2027-04-22",
  "2027-06-10",
  "2027-09-09",
  "2027-10-21",
  "2027-12-09",
];

export const MPC_SOURCE =
  "https://www.tcmb.gov.tr/wps/wcm/connect/EN/TCMB+EN/Main+Menu/Announcements/Calendar";

/** BDDK publishes month M's bulletin around the 12th of month M+2. */
const MONTHLY_PUB_LAG_MONTHS = 2;
const MONTHLY_PUB_DAY = 12;

/** Below this many observed filings, we don't claim to know the window. */
const MIN_FILINGS_FOR_WINDOW = 3;

export interface Slot {
  /** The Ahead row's left column — "JUL 23", "AUG ~12", "AUG 4–7". */
  when: string;
  /** ISO date (or the window's start), for sorting and testing. */
  date: string;
  /** How this date was derived — printable, in the Desk's habit. */
  rule: string;
}

/** Observed lag from quarter-end to the KAP results filing. */
export interface FilingLag {
  loDays: number;
  hiDays: number;
  n: number;
}

const MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"];

const iso = (d: Date): string => d.toISOString().slice(0, 10);
const utc = (y: number, m: number, day: number): Date => new Date(Date.UTC(y, m, day));

/** '2026-08-12' → 'AUG 12'. */
export function dayLabel(isoDate: string): string {
  const d = new Date(`${isoDate}T00:00:00Z`);
  return `${MONTHS[d.getUTCMonth()]} ${d.getUTCDate()}`;
}

/** 'AUG 4–7', or 'AUG 30 – SEP 2' when the window straddles a month. */
export function rangeLabel(fromIso: string, toIso: string): string {
  const a = new Date(`${fromIso}T00:00:00Z`);
  const b = new Date(`${toIso}T00:00:00Z`);
  return a.getUTCMonth() === b.getUTCMonth()
    ? `${MONTHS[a.getUTCMonth()]} ${a.getUTCDate()}–${b.getUTCDate()}`
    : `${dayLabel(fromIso)} – ${dayLabel(toIso)}`;
}

/** '2026-05' → 'June' (the month AFTER the last record we hold). */
const LONG_MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

/** The next MPC date on or after `now`; null once the table runs out. */
export function nextMpc(now: Date): string | null {
  const today = iso(now);
  return MPC_DATES.find((d) => d >= today) ?? null;
}

/**
 * When the NEXT BDDK monthly bulletin is expected, given the latest month held.
 *
 * BDDK publishes no forward calendar; this is the OBSERVED cadence — month M's
 * bulletin lands ~the 12th of month M+2. Grounded in the ingest history (Apr
 * 2026 was in by 5 Jun, May by 29 Jun; the lag runs ~28–75 days, so day-12-of-M+2
 * sits at the generous end and rarely cries wolf).
 *
 * Used both to schedule the "Ahead" derivation AND to judge monthly freshness
 * (admin-health / healthcheck): while `now` is before this date, holding month M
 * is FRESH — the next month simply isn't out yet, so age-of-last-write says
 * nothing. `record` is the month we're waiting for.
 */
export function nextMonthlyBulletinDue(
  latestMonthly: string,
): { date: string; record: string } | null {
  const m = /^(\d{4})-(\d{2})$/.exec(latestMonthly);
  if (!m) return null;
  const year = Number(m[1]);
  const monthIdx = Number(m[2]) - 1; // 0-based month of the LATEST record we hold
  const recordIdx = monthIdx + 1; // the month we are waiting for (may be 12)
  const pub = utc(year, recordIdx + MONTHLY_PUB_LAG_MONTHS, MONTHLY_PUB_DAY);
  return { date: iso(pub), record: LONG_MONTHS[((recordIdx % 12) + 12) % 12] };
}

/** Days of runway left in MPC_DATES — what the CI freshness gate watches. */
export function mpcRunwayDays(now: Date): number {
  const last = MPC_DATES[MPC_DATES.length - 1];
  if (!last) return 0;
  const ms = new Date(`${last}T00:00:00Z`).getTime() - now.getTime();
  return Math.floor(ms / 86_400_000);
}

export interface AheadInput {
  now: Date;
  /** Scraped TCMB events (release_calendar); feeds mpc + the report kinds. */
  events?: CalendarEvent[];
  /** Latest BDDK monthly record in D1, 'YYYY-MM'. */
  latestMonthly?: string | null;
  /** Latest audited quarter in D1, 'YYYYQn'. */
  latestAudit?: string | null;
  /** Observed KAP filing lag; null (or too few filings) omits the row. */
  filingLag?: FilingLag | null;
}

/**
 * The dates. A kind is absent when it cannot be established — the caller then
 * drops the row rather than printing something stale.
 */
export function aheadDates({
  now,
  events,
  latestMonthly,
  latestAudit,
  filingLag,
}: AheadInput): Partial<Record<AheadKind, Slot & { record?: string }>> {
  const out: Partial<Record<AheadKind, Slot & { record?: string }>> = {};
  const today = iso(now);

  /** The next scraped event (on or after today) that feeds `kind`. */
  const nextEvent = (kind: AheadKind): string | null => {
    const dates = (events ?? [])
      .filter((e) => TCMB_KIND[e.kind] === kind && e.event_date >= today)
      .map((e) => e.event_date)
      .sort();
    return dates[0] ?? null;
  };

  // MPC decision — the scraped calendar, falling back to the hand-typed list so a
  // scrape outage degrades to the previous behaviour, never to a blank.
  const scrapedMpc = nextEvent("mpc");
  const mpc = scrapedMpc ?? nextMpc(now);
  if (mpc) {
    out.mpc = {
      when: dayLabel(mpc),
      date: mpc,
      rule: scrapedMpc ? "tcmb published calendar" : "tcmb calendar (fallback list)",
    };
  }

  // The other TCMB events come only from the scrape — no fallback, so a missing
  // one just omits its row.
  for (const kind of ["mpc-minutes", "inflation-report", "fsr"] as const) {
    const d = nextEvent(kind);
    if (d) out[kind] = { when: dayLabel(d), date: d, rule: "tcmb published calendar" };
  }

  // The next record is the month after the last one we hold; it publishes around
  // the 12th of two months later (see nextMonthlyBulletinDue).
  const monthly = latestMonthly ? nextMonthlyBulletinDue(latestMonthly) : null;
  if (monthly) {
    out["bddk-monthly"] = {
      when: dayLabel(monthly.date).replace(/(\w+) (\d+)/, "$1 ~$2"),
      date: monthly.date,
      record: monthly.record,
      rule: `bddk monthly lands ~day ${MONTHLY_PUB_DAY} of record + ${MONTHLY_PUB_LAG_MONTHS}m`,
    };
  }

  // The filing window comes from the filings that have already happened.
  const q = latestAudit ? /^(\d{4})Q([1-4])$/.exec(latestAudit) : null;
  if (q && filingLag && filingLag.n >= MIN_FILINGS_FOR_WINDOW) {
    const year = Number(q[1]);
    const quarter = Number(q[2]); // the LAST quarter we hold
    const nextQ = quarter + 1; // 5 → rolls into next year via Date arithmetic
    const qEnd = utc(year, nextQ * 3, 0); // day 0 of the month after the quarter
    const from = new Date(qEnd.getTime() + filingLag.loDays * 86_400_000);
    const to = new Date(qEnd.getTime() + filingLag.hiDays * 86_400_000);
    const qLabel = `Q${((nextQ - 1) % 4) + 1}`;
    out["brsa-filings"] = {
      when: rangeLabel(iso(from), iso(to)),
      date: iso(from),
      record: qLabel,
      rule: `observed kap filing lag ${filingLag.loDays}–${filingLag.hiDays}d after quarter-end (n=${filingLag.n})`,
    };
  }

  return out;
}
