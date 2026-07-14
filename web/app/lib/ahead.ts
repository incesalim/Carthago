/**
 * ahead — what lands next, derived instead of typed.
 *
 * Five pages carried a hand-typed `Ahead` schedule — about seventeen rows of
 * `{ when: "JUL 23" }` and `{ when: "AUG ~12" }`. They were correct when written
 * and silently wrong a fortnight later: the only forward-looking surface on the
 * site was also the only fully hand-authored one, and nothing derived it.
 *
 * Three of the row kinds are computable from data we already hold:
 *
 *   bddk-monthly   the record month is in D1; a bulletin for month M lands about
 *                  the 12th of M+2 (May's record was in by 12 Jul; June's is due
 *                  ~12 Aug — which is exactly what the hand-typed row said)
 *   brsa-filings   `bank_earnings` holds the KAP filing dates that ALREADY
 *                  happened, so the lag from quarter-end is observed, not guessed
 *   mpc            the one irreducible artefact — see MPC_DATES
 *
 * The purely cadence-based rows ("FRI", "THU", "MONTHLY") never go stale and stay
 * as literals on the pages: a claim that is true every week is not a claim.
 *
 * Every function here is pure and takes `now` as an argument, so the schedule is
 * unit-testable and the pages (all `force-dynamic`) pass the real request time.
 * A kind whose date cannot be established returns nothing and the page OMITS the
 * row — never a date in the past.
 */

export type AheadKind = "mpc" | "bddk-monthly" | "brsa-filings";

/**
 * The only hand-typed forward date left in the app.
 *
 * TCMB publishes its MPC calendar a year or two ahead and nothing scrapes it, so
 * this is transcribed from the source below. `scripts/check_calendar_fresh.py`
 * FAILS CI once the last date here is under 90 days away — it cannot quietly run
 * out the way the `Ahead` blocks did.
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

/** Days of runway left in MPC_DATES — what the CI freshness gate watches. */
export function mpcRunwayDays(now: Date): number {
  const last = MPC_DATES[MPC_DATES.length - 1];
  if (!last) return 0;
  const ms = new Date(`${last}T00:00:00Z`).getTime() - now.getTime();
  return Math.floor(ms / 86_400_000);
}

export interface AheadInput {
  now: Date;
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
  latestMonthly,
  latestAudit,
  filingLag,
}: AheadInput): Partial<Record<AheadKind, Slot & { record?: string }>> {
  const out: Partial<Record<AheadKind, Slot & { record?: string }>> = {};

  const mpc = nextMpc(now);
  if (mpc) {
    out.mpc = {
      when: dayLabel(mpc),
      date: mpc,
      rule: "tcmb published mpc calendar",
    };
  }

  // The next record is the month after the last one we hold; it publishes around
  // the 12th of two months later.
  const m = latestMonthly ? /^(\d{4})-(\d{2})$/.exec(latestMonthly) : null;
  if (m) {
    const year = Number(m[1]);
    const monthIdx = Number(m[2]) - 1; // 0-based, the LAST record we hold
    const recordIdx = monthIdx + 1; // the month we are waiting for
    const pub = utc(year, recordIdx + MONTHLY_PUB_LAG_MONTHS, MONTHLY_PUB_DAY);
    const recordName = LONG_MONTHS[((recordIdx % 12) + 12) % 12];
    out["bddk-monthly"] = {
      when: `${dayLabel(iso(pub))}`.replace(/(\w+) (\d+)/, "$1 ~$2"),
      date: iso(pub),
      record: recordName,
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
