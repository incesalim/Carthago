/**
 * Observation cadence and comparison helpers shared by the sector briefings.
 *
 * A calculation window (4w, 13w, YTD, TTM) is not a source cadence. Keeping
 * those two ideas separate prevents a monthly ratio and a weekly pulse from
 * looking directly comparable just because both happen to print a delta.
 */

export type Cadence = "daily" | "weekly" | "monthly" | "quarterly" | "annual";

export type ObservationRole = "current" | "structure" | "audited" | "early-warning";

export interface ObservationMeta {
  cadence: Cadence;
  /** Last observation used by the surface, in the source's own period format. */
  asOf?: string | null;
  /** Calculation window, e.g. "13w annualized", "YTD annualized", "TTM". */
  window?: string;
  /** Population, currency and/or reporting basis. */
  basis?: string;
  /** Source name when the basis alone does not identify it. */
  source?: string;
  /** Whether the figure is current, structural, audited or an early warning. */
  role?: ObservationRole;
}
export interface PeriodValue {
  period: string;
  value: number | null;
}

export interface AlignedLatest {
  /** Latest date that every supplied series had reached. */
  asOf: string;
  /** Latest non-null observation at or before `asOf`, in input order. */
  values: Array<PeriodValue | null>;
}

const CADENCE_ORDER: Record<Cadence, number> = {
  daily: 0,
  weekly: 1,
  monthly: 2,
  quarterly: 3,
  annual: 4,
};

export function cadenceLabel(cadence: Cadence): string {
  return cadence.charAt(0).toUpperCase() + cadence.slice(1);
}

export function mixedCadence(items: ReadonlyArray<Pick<ObservationMeta, "cadence">>): boolean {
  return new Set(items.map((item) => item.cadence)).size > 1;
}

/** Slowest observation frequency in a group; useful for honest section labels. */
export function slowestCadence(items: ReadonlyArray<Pick<ObservationMeta, "cadence">>): Cadence | null {
  if (!items.length) return null;
  return items.reduce((slowest, item) =>
    CADENCE_ORDER[item.cadence] > CADENCE_ORDER[slowest] ? item.cadence : slowest,
  items[0].cadence);
}

/**
 * Align unlike-frequency series before comparing them. The common cutoff is
 * the earliest of their latest dates; each value is then taken at or before
 * that cutoff. This deliberately refuses to pair a fresh weekly print with a
 * monthly value that had not yet been published at that date.
 */
export function alignLatest(series: ReadonlyArray<ReadonlyArray<PeriodValue>>): AlignedLatest | null {
  if (!series.length) return null;

  const cleaned = series.map((rows) =>
    rows
      .filter((row): row is PeriodValue & { value: number } => row.value != null)
      .slice()
      .sort((a, b) => a.period.localeCompare(b.period)),
  );
  if (cleaned.some((rows) => rows.length === 0)) return null;

  const asOf = cleaned
    .map((rows) => rows.at(-1)!.period)
    .sort((a, b) => a.localeCompare(b))[0];

  const values = cleaned.map((rows) => {
    for (let i = rows.length - 1; i >= 0; i -= 1) {
      if (rows[i].period <= asOf) return rows[i];
    }
    return null;
  });
  if (values.some((row) => row == null)) return null;
  return { asOf, values };
}
