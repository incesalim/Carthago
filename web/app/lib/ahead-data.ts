/**
 * The D1 side of the release schedule. `ahead.ts` stays pure (and unit-tested);
 * this fetches the three facts it needs and hands back the slots.
 *
 * One cached query for the record periods plus the (cached) observed filing lag —
 * cheap enough for the five pages that carry an `Ahead` block.
 */
import { cachedAll } from "./db";
import { filingLagDays } from "./earnings";
import { aheadDates, type AheadKind, type Slot } from "./ahead";

export type AheadSlots = Partial<Record<AheadKind, Slot & { record?: string }>>;

export async function aheadSlots(now: Date = new Date()): Promise<AheadSlots> {
  try {
    const [periods, filingLag] = await Promise.all([
      cachedAll<{ monthly: string | null; audit: string | null }>(
        `SELECT
           (SELECT MAX(year || '-' || PRINTF('%02d', month)) FROM financial_ratios) AS monthly,
           (SELECT MAX(period) FROM bank_audit_balance_sheet) AS audit`,
      ),
      filingLagDays(),
    ]);
    const p = periods[0];
    return aheadDates({
      now,
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
