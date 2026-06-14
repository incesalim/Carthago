/**
 * Data layer for the "Customer acquisition: digital vs branch" section of the
 * /digital tab — TBB's monthly **Uzaktan ve Şubeden Müşteri Edinim
 * İstatistikleri** (`tbb_acquisition_stats`, populated by
 * scripts/update_tbb_acquisition.py).
 *
 * This is a separate publication from the quarterly digital/internet/mobile
 * report: it reports, per month, how many customers banks acquired remotely
 * (without a branch visit) vs at a branch. We treat the three branch-free
 * finalisation methods — a video call with a rep, courier ID confirmation, and
 * bulk onboarding (payroll/corporate) — as "digital", and `branch` as
 * non-digital. `remote_application` is intake (a funnel count, not a finalised
 * customer) and is excluded from these channel/share figures.
 *
 * Counts are sector-wide and stored as raw persons; series here are rescaled to
 * thousands for display.
 */
import { cachedAll } from "./db";
import type { TrendPoint } from "@/app/components/TrendChart";

interface Row {
  period: string;
  method: string;
  value: number | null;
}

// Branch-free finalisation methods we count as "digital".
const REMOTE_METHODS = ["remote_rep", "remote_courier", "bulk"] as const;

export interface AcquisitionData {
  /** Digital vs branch, finalised customers per quarter (thousands). Feed this to
   *  a percent-stacked chart to get the channel share — no separate field needed. */
  byChannel: TrendPoint[];
  /** The individual methods per quarter (thousands) — composition detail. */
  byMethod: TrendPoint[];
}

export const CHANNEL_LABELS: Record<string, string> = {
  digital: "Acquired remotely (digital)",
  branch: "Acquired at branch",
};

export const METHOD_LABELS: Record<string, string> = {
  branch: "Branch",
  remote_rep: "Remote — video call with rep",
  remote_courier: "Remote — courier ID check",
  bulk: "Bulk (payroll / corporate)",
};

const pt = (period: string, code: string, value: number | null): TrendPoint => ({
  period,
  bank_type_code: code,
  value,
});

// Monthly "YYYY-MM" → its quarter-end month label ("YYYY-03|06|09|12"), so the
// axis matches the rest of the tab's quarterly periods.
function quarterEnd(period: string): string {
  const [y, mm] = period.split("-").map(Number);
  const end = Math.ceil(mm / 3) * 3;
  return `${y}-${String(end).padStart(2, "0")}`;
}

/**
 * Load the remote-vs-branch acquisition series for one customer type
 * (default individuals — the headline). The source is monthly and noisy, so the
 * rows are **aggregated to calendar quarters** (each channel/method summed over
 * the quarter's months). Returns digital-vs-branch totals (feed a percent-stack
 * for the channel share) and the per-method breakdown.
 */
export async function acquisitionData(
  entity: "individual" | "merchant" | "legal" = "individual",
): Promise<AcquisitionData> {
  const rows = await cachedAll<Row>(
    `SELECT period, method, value FROM tbb_acquisition_stats
       WHERE entity_type = ? AND method != 'remote_application'
       ORDER BY period`,
    [entity],
  );

  // Sum each method over each calendar quarter, tracking which months landed in
  // it. Only complete (3-month) quarters are emitted, so the partial leading
  // quarter (data starts May 2021) and the in-progress trailing quarter don't
  // show an artificially low total.
  const byQuarter = new Map<string, { months: Set<string>; sums: Record<string, number> }>();
  for (const r of rows) {
    if (r.value == null) continue;
    const q = quarterEnd(r.period);
    let e = byQuarter.get(q);
    if (!e) {
      e = { months: new Set(), sums: {} };
      byQuarter.set(q, e);
    }
    e.months.add(r.period);
    e.sums[r.method] = (e.sums[r.method] ?? 0) + r.value;
  }

  const byChannel: TrendPoint[] = [];
  const byMethod: TrendPoint[] = [];
  const quarters = Array.from(byQuarter.entries())
    .filter(([, e]) => e.months.size === 3)
    .sort((a, b) => a[0].localeCompare(b[0]));

  for (const [q, e] of quarters) {
    const m = e.sums;
    const branch = m["branch"] ?? 0;
    const digital = REMOTE_METHODS.reduce((s, k) => s + (m[k] ?? 0), 0);

    byChannel.push(pt(q, "digital", digital / 1000));
    byChannel.push(pt(q, "branch", branch / 1000));

    for (const k of ["branch", ...REMOTE_METHODS]) {
      if (m[k] != null) byMethod.push(pt(q, k, m[k] / 1000));
    }
  }

  return { byChannel, byMethod };
}
