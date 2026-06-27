/**
 * Market-risk tab — data layer (SERVER ONLY). Homes CAMELS "S" (the dashboard
 * audit's P0). Reads the two new per-bank §4 audit tables and aggregates them
 * "of reporting banks" per quarter (the same same-source approach as
 * market-share.ts), plus per-bank rows for drill-downs.
 *
 *   bank_audit_fx_position  — FX net open position by currency (EUR/USD/OTHER/TOTAL)
 *   bank_audit_repricing    — interest-rate repricing gap by bucket
 *
 * Amounts are thousand TRY in the tables → divided to ₺bn for display. Ratios
 * (FX NOP / regulatory capital; cumulative 1y gap / total assets) are returned
 * as percent. Period is `YYYYQN`; we read only period_type='current'.
 *
 * NOTE: securities mark-to-market (the third S-signal) is a documented
 * fast-follow — the AFS/FVOCI revaluation reserve isn't a cleanly-labelled BS
 * line, so it needs an OCI-line mapping before it can be surfaced correctly.
 */
import { cachedAll } from "./db";
import type { TrendPoint } from "@/app/components/TrendChart";

/** Wide row for BopFlowChart (signed stacked bars over an x category). */
type FlowRow = Record<string, number | string | null>;

const DEFAULT_KIND = "unconsolidated";
const TH_TO_BN = 1_000_000; // thousand TRY → ₺bn

// Repricing buckets ≤ 1 year (for the cumulative 1y gap).
const LE_1Y = new Set(["lt_1m", "1_3m", "3_12m"]);
const BUCKET_ORDER = ["lt_1m", "1_3m", "3_12m", "1_5y", "gt_5y", "non_sensitive"];
const BUCKET_LABEL: Record<string, string> = {
  lt_1m: "≤1 month", "1_3m": "1–3 months", "3_12m": "3–12 months",
  "1_5y": "1–5 years", gt_5y: ">5 years", non_sensitive: "Non-rate-sensitive",
};

interface FxRow {
  bank_ticker: string; period: string; currency: string;
  net_position: number | null;
}
interface CapRow { bank_ticker: string; period: string; total_capital: number | null }
interface RpRow {
  bank_ticker: string; period: string; bucket: string;
  gap: number | null; rate_sensitive_assets: number | null;
}

/** Latest quarter with FX-position data from ≥ minBanks banks (for dataThrough). */
export async function marketRiskLatestPeriod(
  minBanks = 5, kind: string = DEFAULT_KIND,
): Promise<string | null> {
  const rows = await cachedAll<{ period: string }>(
    `SELECT period, COUNT(DISTINCT bank_ticker) AS n
       FROM bank_audit_fx_position
      WHERE kind = ? AND period_type = 'current' AND currency = 'TOTAL'
      GROUP BY period HAVING n >= ? ORDER BY period DESC LIMIT 1`,
    [kind, minBanks],
  );
  return rows[0]?.period ?? null;
}

async function fxRows(kind: string) {
  return cachedAll<FxRow>(
    `SELECT bank_ticker, period, currency, net_position
       FROM bank_audit_fx_position
      WHERE kind = ? AND period_type = 'current'`,
    [kind],
  );
}
async function capRows(kind: string) {
  return cachedAll<CapRow>(
    `SELECT bank_ticker, period, total_capital
       FROM bank_audit_capital WHERE kind = ? AND period_type = 'current'`,
    [kind],
  );
}
async function rpRows(kind: string) {
  return cachedAll<RpRow>(
    `SELECT bank_ticker, period, bucket, gap, rate_sensitive_assets
       FROM bank_audit_repricing WHERE kind = ? AND period_type = 'current'`,
    [kind],
  );
}

/**
 * Sector FX net open position ÷ regulatory capital (%), per quarter — the
 * system's net FX tilt against its capital base (Σ net position ÷ Σ capital "of
 * reporting banks"). A small ratio means the sector is well-hedged.
 */
export async function fxNopToCapital(kind: string = DEFAULT_KIND): Promise<TrendPoint[]> {
  const [fx, cap] = await Promise.all([fxRows(kind), capRows(kind)]);
  const nop = new Map<string, number>();   // period → Σ net_position (TOTAL)
  for (const r of fx) {
    if (r.currency !== "TOTAL" || r.net_position == null) continue;
    nop.set(r.period, (nop.get(r.period) ?? 0) + r.net_position);
  }
  const capByPeriod = new Map<string, number>();
  for (const r of cap) {
    if (r.total_capital == null) continue;
    capByPeriod.set(r.period, (capByPeriod.get(r.period) ?? 0) + r.total_capital);
  }
  return [...nop.keys()].sort()
    .filter((p) => (capByPeriod.get(p) ?? 0) > 0)
    .map((period) => ({
      period, bank_type_code: "SECTOR",
      value: (nop.get(period)! / capByPeriod.get(period)!) * 100,
    }));
}

/** Sector FX net position by currency (₺bn), per quarter — which currency the
 *  system is net long (+) / short (−). Signed stacked bars (EUR/USD/Other incl.
 *  GBP); x = period. */
export async function fxByCurrency(kind: string = DEFAULT_KIND, ticker?: string): Promise<FlowRow[]> {
  const fx = await fxRows(kind);
  const byPeriod = new Map<string, { EUR: number; USD: number; Other: number }>();
  for (const r of fx) {
    if (ticker && r.bank_ticker !== ticker) continue;
    if (r.currency === "TOTAL" || r.net_position == null) continue;
    const slot = byPeriod.get(r.period) ?? { EUR: 0, USD: 0, Other: 0 };
    const key = r.currency === "EUR" ? "EUR" : r.currency === "USD" ? "USD" : "Other";
    slot[key] += r.net_position / TH_TO_BN;
    byPeriod.set(r.period, slot);
  }
  return [...byPeriod.keys()].sort().map((period) => ({
    x: period, EUR: byPeriod.get(period)!.EUR, USD: byPeriod.get(period)!.USD,
    Other: byPeriod.get(period)!.Other,
  }));
}

export const FX_CURRENCY_BARS = [
  { key: "EUR", label: "EUR" }, { key: "USD", label: "USD" }, { key: "Other", label: "Other FC" },
];

/** Sector cumulative repricing gap ≤ 1y ÷ total assets (%), per quarter — how
 *  much of the book reprices within a year, net (assets − liabilities). A large
 *  |value| means NIM is sensitive to a rate move. */
export async function repricingGap1y(kind: string = DEFAULT_KIND): Promise<TrendPoint[]> {
  const rp = await rpRows(kind);
  const gap = new Map<string, number>();    // period → Σ gap over ≤1y buckets
  const assets = new Map<string, number>();  // period → Σ total RSA
  for (const r of rp) {
    if (r.bucket === "total") {
      if (r.rate_sensitive_assets != null)
        assets.set(r.period, (assets.get(r.period) ?? 0) + r.rate_sensitive_assets);
    } else if (LE_1Y.has(r.bucket) && r.gap != null) {
      gap.set(r.period, (gap.get(r.period) ?? 0) + r.gap);
    }
  }
  return [...gap.keys()].sort()
    .filter((p) => (assets.get(p) ?? 0) > 0)
    .map((period) => ({
      period, bank_type_code: "SECTOR",
      value: (gap.get(period)! / assets.get(period)!) * 100,
    }));
}

/** Sector repricing-gap ladder for the latest quarter — Σ gap per bucket (₺bn),
 *  signed. Wide rows for BopFlowChart: { x: bucketLabel, gap: ₺bn }. */
export async function repricingLadder(
  kind: string = DEFAULT_KIND,
  ticker?: string,
): Promise<{ data: Array<Record<string, number | string | null>>; period: string | null }> {
  const all = await rpRows(kind);
  const rp = ticker ? all.filter((r) => r.bank_ticker === ticker) : all;
  const periods = [...new Set(rp.map((r) => r.period))].sort();
  const period = periods.at(-1) ?? null;
  if (!period) return { data: [], period: null };
  const byBucket = new Map<string, number>();
  for (const r of rp) {
    if (r.period !== period || r.bucket === "total" || r.gap == null) continue;
    byBucket.set(r.bucket, (byBucket.get(r.bucket) ?? 0) + r.gap / TH_TO_BN);
  }
  const data = BUCKET_ORDER.filter((b) => byBucket.has(b)).map((b) => ({
    x: BUCKET_LABEL[b], gap: byBucket.get(b)!,
  }));
  return { data, period };
}
