/**
 * Data layer for the "Participation banks" sections of the /digital tab —
 * TKBB (Participation Banks Association) digital statistics scraped from the
 * Veri Peteği Turboard dashboards into `tkbb_digital_stats` (quarterly) and
 * `tkbb_acquisition_stats` (monthly rolling window, accumulated). See
 * scripts/update_tkbb_digital.py / update_tkbb_acquisition.py.
 *
 * TKBB values are stored RAW (persons / transaction counts / TRY); scaling to
 * display units happens here. TBB comparison series are stored in thousands —
 * the ×1000 conversion to raw persons is confined to this module.
 *
 * Caveat carried into every cross-association share: a customer of both a
 * deposit bank and a participation bank is counted by both associations, and
 * the two may define "active" differently — the shares are trend-valid, not
 * an exact census.
 */
import { cachedAll } from "./db";
import type { TrendPoint } from "@/app/components/TrendChart";

export interface TkbbSpec {
  /** Series key used by TrendChart (legend order = array order). */
  code: string;
  metric: string;
  breakdown: string;
  dim: string;
}

interface Row {
  period: string;
  metric: string;
  breakdown: string;
  dim_slug: string;
  value: number | null;
}

export const SCALE_PERSONS_TO_M = 1e-6;
export const SCALE_TRY_TO_TRN = 1e-12;

const pt = (period: string, code: string, value: number | null): TrendPoint => ({
  period,
  bank_type_code: code,
  value,
});

/**
 * Fetch pinned TKBB series as TrendChart points, rescaling by `scale`.
 * One cached query covers every series in the chart.
 */
export async function tkbbSeries(specs: TkbbSpec[], scale = 1): Promise<TrendPoint[]> {
  if (specs.length === 0) return [];
  const cond = specs.map(() => "(metric=? AND breakdown=? AND dim_slug=?)").join(" OR ");
  const binds = specs.flatMap((s) => [s.metric, s.breakdown, s.dim]);
  const rows = await cachedAll<Row>(
    `SELECT period, metric, breakdown, dim_slug, value
       FROM tkbb_digital_stats WHERE ${cond} ORDER BY period`,
    binds,
  );
  const codeFor = new Map(specs.map((s) => [`${s.metric}|${s.breakdown}|${s.dim}`, s.code]));
  return rows.map((r) => ({
    period: r.period,
    bank_type_code: codeFor.get(`${r.metric}|${r.breakdown}|${r.dim_slug}`) ?? "?",
    value: r.value == null ? null : r.value * scale,
  }));
}

/** Active digital customers of participation banks (millions) — single series. */
export const ACTIVE_TOTAL: TkbbSpec[] = [
  { code: "participation", metric: "active_customers", breakdown: "total", dim: "total" },
];

// TBB comparison basis: total (individual + corporate) active digital
// customers, stored in thousands. Same natural key the /digital adoption
// charts pin; if TBB ever renames the slug this share simply stops extending.
const TBB_TOTAL_SQL = `
  SELECT period, metric_slug AS metric, 'tbb' AS breakdown, 'tbb' AS dim_slug, value
    FROM tbb_digital_stats
   WHERE channel='digital' AND segment='total' AND section_code='I'
     AND unit='persons_thousands' AND metric_slug=?
   ORDER BY period`;

async function tbbTotalSeries(slug: string): Promise<Map<string, number>> {
  const rows = await cachedAll<Row>(TBB_TOTAL_SQL, [slug]);
  const out = new Map<string, number>();
  for (const r of rows) {
    if (r.value != null) out.set(r.period, r.value * 1000); // thousands → persons
  }
  return out;
}

/**
 * Participation banks' share of all active digital banking customers (%):
 * TKBB total ÷ (TKBB total + TBB total), quarterly, inner-joined on period.
 */
export async function participationShare(): Promise<TrendPoint[]> {
  const [tkbb, tbb] = await Promise.all([
    tkbbSeries(ACTIVE_TOTAL),
    tbbTotalSeries("aktif_dijital_bankacilik_musteri_sayilari_toplam"),
  ]);
  const out: TrendPoint[] = [];
  for (const p of tkbb) {
    const tbbVal = tbb.get(p.period);
    if (p.value == null || tbbVal == null) continue;
    out.push(pt(p.period, "share", (100 * p.value) / (p.value + tbbVal)));
  }
  return out;
}

/**
 * Mobile-only share of active digital customers (%), participation banks vs
 * banks — the direct cross-association behavioral comparison. Both sides use
 * the all-customer (individual + corporate) basis.
 */
export async function mobileOnlyShare(): Promise<TrendPoint[]> {
  const [mix, tbbMobile, tbbTotal] = await Promise.all([
    tkbbSeries([
      { code: "mobile_only", metric: "active_customers_mix", breakdown: "channel_mix", dim: "mobile_only" },
      { code: "internet_only", metric: "active_customers_mix", breakdown: "channel_mix", dim: "internet_only" },
      { code: "both", metric: "active_customers_mix", breakdown: "channel_mix", dim: "both" },
    ]),
    tbbTotalSeries("aktif_dijital_bankacilik_musteri_sayilari_sadece_mobil_bankacilik_kullanan"),
    tbbTotalSeries("aktif_dijital_bankacilik_musteri_sayilari_toplam"),
  ]);

  const out: TrendPoint[] = [];
  const byPeriod = new Map<string, Record<string, number>>();
  for (const p of mix) {
    if (p.value == null) continue;
    let e = byPeriod.get(p.period);
    if (!e) byPeriod.set(p.period, (e = {}));
    e[p.bank_type_code] = p.value;
  }
  for (const [period, e] of Array.from(byPeriod.entries()).sort()) {
    const total = (e.mobile_only ?? 0) + (e.internet_only ?? 0) + (e.both ?? 0);
    if (total > 0 && e.mobile_only != null) {
      out.push(pt(period, "participation", (100 * e.mobile_only) / total));
    }
  }
  for (const [period, mobile] of tbbMobile) {
    const total = tbbTotal.get(period);
    if (total) out.push(pt(period, "banks", (100 * mobile) / total));
  }
  return out;
}

export const COMPARISON_LABELS: Record<string, string> = {
  participation: "Participation banks",
  banks: "Banks (TBB)",
};

/**
 * Participation banks' digital transaction volume by channel (₺ trillion),
 * quarterly stack. Codes match the page-wide mobile/internet entity colors.
 */
export async function tkbbVolumeByChannel(): Promise<TrendPoint[]> {
  return tkbbSeries(
    [
      { code: "mobile", metric: "txn_volume_channel", breakdown: "channel", dim: "mobil_bankacilik" },
      { code: "internet", metric: "txn_volume_channel", breakdown: "channel", dim: "internet_bankaciligi" },
    ],
    SCALE_TRY_TO_TRN,
  );
}

// ── Monthly acquisition (rolling window, accumulated) ───────────────────────

export const ACQ_SERIES_LABELS: Record<string, string> = {
  remote: "Acquired remotely (digital)",
  branch: "Acquired at branch",
};

// Shift a "YYYY-MM" period by `delta` months.
function addMonths(period: string, delta: number): string {
  const [y, mm] = period.split("-").map(Number);
  const idx = y * 12 + (mm - 1) + delta;
  return `${Math.floor(idx / 12)}-${String((idx % 12) + 1).padStart(2, "0")}`;
}

/**
 * Finalised-customer acquisition per month as trailing 3-month sums keyed
 * remote/branch (raw persons). Shared base for the level and share charts;
 * months without a complete trailing window are dropped.
 */
async function acquisitionWindows(): Promise<Map<string, Record<string, number>>> {
  const rows = await cachedAll<{ period: string; series: string; value: number | null }>(
    `SELECT period, series, value FROM tkbb_acquisition_stats
      WHERE measure='customers' ORDER BY period`,
  );
  const byMonth = new Map<string, Record<string, number>>();
  for (const r of rows) {
    if (r.value == null) continue;
    let e = byMonth.get(r.period);
    if (!e) byMonth.set(r.period, (e = {}));
    e[r.series] = (e[r.series] ?? 0) + r.value;
  }
  const out = new Map<string, Record<string, number>>();
  for (const period of Array.from(byMonth.keys()).sort()) {
    const window = [addMonths(period, -2), addMonths(period, -1), period];
    if (!window.every((mp) => byMonth.has(mp))) continue;
    const sums: Record<string, number> = {};
    for (const mp of window) {
      const e = byMonth.get(mp)!;
      for (const k in e) sums[k] = (sums[k] ?? 0) + e[k];
    }
    out.set(period, sums);
  }
  return out;
}

/** Remote vs branch new customers of participation banks (thousands, trailing 3M). */
export async function tkbbAcquisitionLevels(): Promise<TrendPoint[]> {
  const windows = await acquisitionWindows();
  const out: TrendPoint[] = [];
  for (const [period, sums] of windows) {
    out.push(pt(period, "remote", (sums.remote ?? 0) / 1000));
    out.push(pt(period, "branch", (sums.branch ?? 0) / 1000));
  }
  return out;
}

/**
 * Remote share of new customers (%), participation banks vs banks. The TBB
 * side comes from `acquisitionData("individual").byChannel` (already trailing
 * 3-month sums) — pass it in so this module doesn't re-query it.
 */
export async function remoteShareComparison(
  tbbByChannel: TrendPoint[],
): Promise<TrendPoint[]> {
  const windows = await acquisitionWindows();
  const out: TrendPoint[] = [];
  for (const [period, sums] of windows) {
    const total = (sums.remote ?? 0) + (sums.branch ?? 0);
    if (total > 0) out.push(pt(period, "participation", (100 * (sums.remote ?? 0)) / total));
  }
  const tbbByPeriod = new Map<string, Record<string, number>>();
  for (const p of tbbByChannel) {
    if (p.value == null) continue;
    let e = tbbByPeriod.get(p.period);
    if (!e) tbbByPeriod.set(p.period, (e = {}));
    e[p.bank_type_code] = p.value;
  }
  for (const [period, e] of Array.from(tbbByPeriod.entries()).sort()) {
    const total = (e.digital ?? 0) + (e.branch ?? 0);
    if (total > 0) out.push(pt(period, "banks", (100 * (e.digital ?? 0)) / total));
  }
  return out;
}
