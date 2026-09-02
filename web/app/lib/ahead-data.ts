/**
 * The D1 side of the release schedule. `ahead.ts` stays pure (and unit-tested);
 * this fetches the facts the app overview API needs and hands back the slots.
 *
 * Two cached queries — the record periods and the scraped TCMB calendar
 * (release_calendar) — plus the (cached) observed filing lag. Cheap enough for
 * the app overview response that carries upcoming releases.
 */
import { cachedAll } from "./db";
import { filingLagDays } from "./earnings";
import { aheadDates, type AheadKind, type CalendarEvent, type Slot } from "./ahead";

export type AheadSlots = Partial<Record<AheadKind, Slot & { record?: string }>>;

export async function aheadSlots(now: Date = new Date()): Promise<AheadSlots> {
  try {
    const nowIso = now.toISOString().slice(0, 10);
    const [periods, events, filingLag] = await Promise.all([
      // `audit` = the last quarter the FLEET has filed, not the last quarter any
      // single bank has. `ahead.ts` reads it as "the last quarter we hold" and
      // predicts the NEXT quarter's filing window, so one early filer (TEB
      // opened 2026Q2 alone) would make the strip announce the Q3 window while
      // the Q2 season was still running. Quorum of 10, as in `latestCommonPeriod`.
      cachedAll<{ monthly: string | null; audit: string | null }>(
        `SELECT
           (SELECT MAX(year || '-' || PRINTF('%02d', month)) FROM financial_ratios) AS monthly,
           (SELECT period FROM bank_audit_balance_sheet
             WHERE statement = 'assets'
             GROUP BY period HAVING COUNT(DISTINCT bank_ticker) >= 10
             ORDER BY period DESC LIMIT 1) AS audit`,
      ),
      // The scraped TCMB calendar — future rows only; ahead.ts picks next-of-kind.
      cachedAll<CalendarEvent>(
        `SELECT kind, event_date FROM release_calendar
          WHERE source = 'tcmb' AND event_date >= ?
          ORDER BY event_date`,
        [nowIso],
      ).catch(() => [] as CalendarEvent[]),
      filingLagDays(),
    ]);
    const p = periods[0];
    return aheadDates({
      now,
      events,
      latestMonthly: p?.monthly ?? null,
      latestAudit: p?.audit ?? null,
      filingLag,
    });
  } catch {
    // A schedule we cannot derive is a schedule we do not print — the pages drop
    // the rows rather than fall back to a date typed in months ago.
    return {};
  }
}
