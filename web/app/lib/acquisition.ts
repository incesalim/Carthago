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
  /** Digital vs branch, finalised customers per month (thousands). Feed this to
   *  a percent-stacked chart to get the channel share — no separate field needed. */
  byChannel: TrendPoint[];
  /** The individual methods per month (thousands) — composition detail. */
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

/**
 * Load the remote-vs-branch acquisition series for one customer type
 * (default individuals — the headline). Aggregates the per-method rows into
 * digital vs branch totals, a digital/branch percentage split, and keeps the
 * per-method breakdown for a composition chart.
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

  // Group by period → { method: value }.
  const byPeriod = new Map<string, Record<string, number>>();
  for (const r of rows) {
    if (r.value == null) continue;
    if (!byPeriod.has(r.period)) byPeriod.set(r.period, {});
    byPeriod.get(r.period)![r.method] = r.value;
  }

  const byChannel: TrendPoint[] = [];
  const byMethod: TrendPoint[] = [];

  for (const [period, m] of byPeriod) {
    const branch = m["branch"] ?? 0;
    const digital = REMOTE_METHODS.reduce((s, k) => s + (m[k] ?? 0), 0);

    byChannel.push(pt(period, "digital", digital / 1000));
    byChannel.push(pt(period, "branch", branch / 1000));

    for (const k of ["branch", ...REMOTE_METHODS]) {
      if (m[k] != null) byMethod.push(pt(period, k, m[k] / 1000));
    }
  }

  return { byChannel, byMethod };
}
