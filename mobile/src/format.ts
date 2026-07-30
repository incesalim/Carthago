/**
 * Number formatting. Mirrors web/app/lib/chart-format.ts.
 *
 * Two rules carried over verbatim, because both have already caused real wrong
 * numbers on the website:
 *
 *   • null is an em dash, NEVER 0. A missing disclosure and a disclosed zero
 *     are different facts, and only one of them is the bank's fault.
 *   • A metric's `unit` decides its scaling. "pct" arrives as a FRACTION
 *     (0.155 → 15.5%); "pts" arrives already in percentage POINTS (15.5 →
 *     15.5%), which is how the audited §4 capital and liquidity ratios come
 *     out of the filings. Treating one as the other is a silent 100× error that
 *     still looks like a plausible ratio.
 */
import type { MetricUnit } from "./api/types";

export const DASH = "—";

/** Turkish locale grouping, matching the website's figures. */
const grouped = (v: number, decimals: number) =>
  v.toLocaleString("tr-TR", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });

export function num(v: number | null | undefined, decimals = 2): string {
  return v == null || !Number.isFinite(v) ? DASH : grouped(v, decimals);
}

export function pct(v: number | null | undefined, decimals = 2): string {
  return v == null || !Number.isFinite(v) ? DASH : `${grouped(v, decimals)}%`;
}

/** Signed, for a change: "+1,2pp" / "−0,4pp". */
export function pp(v: number | null | undefined, decimals = 1): string {
  if (v == null || !Number.isFinite(v)) return DASH;
  // U+2212 MINUS, not a hyphen — it aligns with digits in the mono face.
  const sign = v > 0 ? "+" : v < 0 ? "−" : "";
  return `${sign}${grouped(Math.abs(v), decimals)}pp`;
}

export function signedPct(v: number | null | undefined, decimals = 1): string {
  if (v == null || !Number.isFinite(v)) return DASH;
  const sign = v > 0 ? "+" : v < 0 ? "−" : "";
  return `${sign}${grouped(Math.abs(v), decimals)}%`;
}

/**
 * Thousand-TL (how every audit amount is stored) → a readable ₺ figure.
 * Thresholds are on the STORED scale: 1e9 thousand-TL = ₺1trn.
 */
export function tl(thousands: number | null | undefined): string {
  if (thousands == null || !Number.isFinite(thousands)) return DASH;
  const abs = Math.abs(thousands);
  if (abs >= 1e9) return `₺${grouped(thousands / 1e9, 2)} trn`;
  if (abs >= 1e6) return `₺${grouped(thousands / 1e6, 1)} bn`;
  if (abs >= 1e3) return `₺${grouped(thousands / 1e3, 0)} mn`;
  return `₺${grouped(thousands, 0)}k`;
}

/** Format a scorecard metric by its declared unit. */
export function metric(
  v: number | null | undefined,
  unit: MetricUnit,
  decimals: number,
): string {
  if (v == null || !Number.isFinite(v)) return DASH;
  switch (unit) {
    case "pct":
      return pct(v * 100, decimals);
    case "pts":
      return pct(v, decimals);
    case "trn":
      return `₺${grouped(v / 1e9, decimals)} trn`;
    case "bn":
      return `₺${grouped(v / 1e6, decimals)} bn`;
    case "mult":
      return `${grouped(v, decimals)}×`;
    default:
      return grouped(v, decimals);
  }
}

/** '2026Q1' → 'Q1 2026'; '2026-03-31' → 'Mar 2026'. Anything else passes through. */
export function periodLabel(p: string | null | undefined): string {
  if (!p) return DASH;
  const q = /^(\d{4})Q([1-4])$/.exec(p);
  if (q) return `Q${q[2]} ${q[1]}`;
  const m = /^(\d{4})-(\d{2})/.exec(p);
  if (!m) return p;
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return `${months[Number(m[2]) - 1] ?? m[2]} ${m[1]}`;
}

/** "2h ago", "3d ago" — for a news timestamp and the cache age note. */
export function ago(iso: string | number): string {
  const then = typeof iso === "number" ? iso : Date.parse(iso);
  if (!Number.isFinite(then)) return DASH;
  const mins = Math.max(0, Math.round((Date.now() - then) / 60000));
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}
