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
// The five rate-sensitive buckets shown as diverging bars (non-sensitive
// excluded — it isn't a repricing signal), with compact labels.
const RATE_BUCKETS = ["lt_1m", "1_3m", "3_12m", "1_5y", "gt_5y"];
const SHORT_BUCKET_LABEL: Record<string, string> = {
  lt_1m: "0–1M", "1_3m": "1–3M", "3_12m": "3–12M", "1_5y": "1–5Y", gt_5y: "5Y+",
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

/** One repricing bucket for the per-bank diverging-bar view. */
export interface RepricingBucket {
  label: string;
  /** Signed net gap as % of total rate-sensitive assets (null if no denom). */
  pct: number | null;
  /** Signed net gap in ₺bn (for tooltips). */
  gapBn: number;
}
/** One currency line for the per-bank FX net-open-position list. */
export interface FxPositionItem {
  label: string;
  /** Signed net position as % of regulatory capital (null if no denom). */
  pct: number | null;
  /** Signed net position in ₺bn. */
  netBn: number;
}
/** Per-bank §4 market-risk detail for the latest reported quarter. */
export interface MarketRiskDetail {
  period: string | null;
  /** Diverging repricing-gap ladder (5 rate buckets) + cumulative ≤1y gap %. */
  repricing: { buckets: RepricingBucket[]; gap1yPct: number | null };
  /** FX net open position by currency (signed). */
  fx: { items: FxPositionItem[] };
  hasData: boolean;
}

/**
 * Per-bank market-risk detail for the bank-detail "Market Risk" section:
 * the interest-rate repricing gap as a diverging ladder (% of rate-sensitive
 * assets) and the FX net open position by currency (% of regulatory capital).
 * Each block reads its own latest reported quarter. Percentages share the same
 * denominators as the sector ratios so the headline tiles reconcile.
 */
export async function bankMarketRiskDetail(
  kind: string = DEFAULT_KIND,
  ticker?: string,
): Promise<MarketRiskDetail> {
  const [fx, cap, rp] = await Promise.all([fxRows(kind), capRows(kind), rpRows(kind)]);
  const myRp = ticker ? rp.filter((r) => r.bank_ticker === ticker) : rp;
  const myFx = ticker ? fx.filter((r) => r.bank_ticker === ticker) : fx;
  const rpPeriod = [...new Set(myRp.map((r) => r.period))].sort().at(-1) ?? null;
  const fxPeriod = [...new Set(myFx.map((r) => r.period))].sort().at(-1) ?? null;

  // ── Repricing ladder (latest rp quarter) ──
  let rsa = 0;
  const byBucket = new Map<string, number>();
  if (rpPeriod) {
    for (const r of myRp) {
      if (r.period !== rpPeriod) continue;
      if (r.bucket === "total") {
        if (r.rate_sensitive_assets != null) rsa += r.rate_sensitive_assets;
      } else if (r.gap != null) {
        byBucket.set(r.bucket, (byBucket.get(r.bucket) ?? 0) + r.gap);
      }
    }
  }
  const buckets: RepricingBucket[] = RATE_BUCKETS.filter((b) => byBucket.has(b)).map((b) => ({
    label: SHORT_BUCKET_LABEL[b],
    gapBn: byBucket.get(b)! / TH_TO_BN,
    pct: rsa > 0 ? (byBucket.get(b)! / rsa) * 100 : null,
  }));
  let gap1y = 0;
  let gap1yAny = false;
  for (const b of LE_1Y) {
    const v = byBucket.get(b);
    if (v != null) {
      gap1y += v;
      gap1yAny = true;
    }
  }
  const gap1yPct = gap1yAny && rsa > 0 ? (gap1y / rsa) * 100 : null;

  // ── FX net open position by currency (latest fx quarter) ──
  const capV = fxPeriod
    ? (ticker ? cap.filter((r) => r.bank_ticker === ticker) : cap)
        .filter((r) => r.period === fxPeriod)
        .reduce((s, r) => s + (r.total_capital ?? 0), 0)
    : 0;
  const byCcy = new Map<string, number>();
  if (fxPeriod) {
    for (const r of myFx) {
      if (r.period !== fxPeriod || r.currency === "TOTAL" || r.net_position == null) continue;
      const key = r.currency === "EUR" ? "EUR" : r.currency === "USD" ? "USD" : "Other";
      byCcy.set(key, (byCcy.get(key) ?? 0) + r.net_position);
    }
  }
  const items: FxPositionItem[] = ["USD", "EUR", "Other"]
    .filter((k) => byCcy.has(k))
    .map((k) => ({
      label: k === "Other" ? "Other FC" : k,
      netBn: byCcy.get(k)! / TH_TO_BN,
      pct: capV > 0 ? (byCcy.get(k)! / capV) * 100 : null,
    }));

  return {
    period: [rpPeriod, fxPeriod].filter(Boolean).sort().at(-1) ?? null,
    repricing: { buckets, gap1yPct },
    fx: { items },
    hasData: buckets.length > 0 || items.length > 0,
  };
}
