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
  /** Digital vs branch, finalised customers — trailing 3-month sum (thousands).
   *  Feed this to a percent-stacked chart to get the channel share. */
  byChannel: TrendPoint[];
  /** The individual methods, trailing 3-month sum (thousands) — composition detail. */
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

// Shift a "YYYY-MM" period by `delta` months.
function addMonths(period: string, delta: number): string {
  const [y, mm] = period.split("-").map(Number);
  const idx = y * 12 + (mm - 1) + delta;
  return `${Math.floor(idx / 12)}-${String((idx % 12) + 1).padStart(2, "0")}`;
}

/**
 * Load the remote-vs-branch acquisition series for one customer type
 * (default individuals — the headline). The source is monthly and noisy, so each
 * point is a **trailing 3-month sum** (the month plus the prior two) — smoothing
 * the jitter while keeping monthly cadence and the latest month. Returns
 * digital-vs-branch totals (feed a percent-stack for the channel share) and the
 * per-method breakdown.
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

  // Monthly map: period → { method: value }.
  const byMonth = new Map<string, Record<string, number>>();
  for (const r of rows) {
    if (r.value == null) continue;
    let e = byMonth.get(r.period);
    if (!e) {
      e = {};
      byMonth.set(r.period, e);
    }
    e[r.method] = (e[r.method] ?? 0) + r.value;
  }

  const byChannel: TrendPoint[] = [];
  const byMethod: TrendPoint[] = [];
  for (const period of Array.from(byMonth.keys()).sort()) {
    // Trailing 3-month window ending at `period`; skip until it's complete (the
    // first two months, May–Jun 2021, have no full window).
    const window = [addMonths(period, -2), addMonths(period, -1), period];
    if (!window.every((mp) => byMonth.has(mp))) continue;

    const sums: Record<string, number> = {};
    for (const mp of window) {
      const e = byMonth.get(mp)!;
      for (const k in e) sums[k] = (sums[k] ?? 0) + e[k];
    }
    const branch = sums["branch"] ?? 0;
    const digital = REMOTE_METHODS.reduce((s, k) => s + (sums[k] ?? 0), 0);

    byChannel.push(pt(period, "digital", digital / 1000));
    byChannel.push(pt(period, "branch", branch / 1000));

    for (const k of ["branch", ...REMOTE_METHODS]) {
      if (sums[k] != null) byMethod.push(pt(period, k, sums[k] / 1000));
    }
  }

  return { byChannel, byMethod };
}
