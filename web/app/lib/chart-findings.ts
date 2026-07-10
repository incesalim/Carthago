/**
 * chart-findings — deterministic one-sentence findings for chart headlines
 * (redesign phase E: "the title states the finding, not the topic").
 *
 * `seriesFinding` is recomputed from the EXACT rows the chart renders, so the
 * headline can never go stale — the same guarantee as the Takeaway engine
 * (lib/insights.ts), whose conservative-threshold tone this mirrors. It is a
 * DESCRIPTION of the series' level + direction, not a judgment; returns null
 * on insufficient data so callers fall back to the static metric title.
 *
 * Pure + synchronous — safe in server components and unit tests.
 */

export interface SeriesPointLike {
  period: string;
  value: number | null;
}

export interface FindingOpts {
  /** Subject, capitalized as it should open the sentence ("Loan growth"). */
  noun: string;
  /** Value rendering: "pct" → `38.2%` with pp deltas; "raw" → plain number. */
  format?: "pct" | "raw";
  decimals?: number;
  /** Lookback in points for the direction read (default 12 ≈ a year, monthly). */
  window?: number;
}

/** 'YYYY-MM' → 'Apr 2026'; 'YYYYQN' → 'Q1 2026'; else the raw string. */
const MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
export function prettyPeriod(p: string): string {
  const m = /^(\d{4})-(\d{2})/.exec(p);
  if (m) {
    const mon = MONTHS[Number(m[2]) - 1];
    if (mon) return `${mon} ${m[1]}`;
  }
  const q = /^(\d{4})Q([1-4])$/.exec(p);
  if (q) return `Q${q[2]} ${q[1]}`;
  return p;
}

const fmtNum = (v: number, d: number) =>
  new Intl.NumberFormat("en-US", {
    minimumFractionDigits: d,
    maximumFractionDigits: d,
  }).format(v);

/**
 * One deterministic sentence: level, direction verb, period, and the change
 * over the window. Verb thresholds are conservative (scale-aware) so a flat
 * series reads "holds at", never a manufactured drama.
 */
export function seriesFinding(
  series: ReadonlyArray<SeriesPointLike>,
  { noun, format = "pct", decimals = 1, window = 12 }: FindingOpts,
): string | null {
  const pts = series.filter(
    (r): r is { period: string; value: number } =>
      r.value != null && !Number.isNaN(r.value),
  );
  if (pts.length < 2) return null;

  const last = pts[pts.length - 1];
  const prior = pts[Math.max(0, pts.length - 1 - window)];
  const delta = last.value - prior.value;

  const unit = format === "pct" ? "%" : "";
  const deltaUnit = format === "pct" ? "pp" : "";
  const level = `${fmtNum(last.value, decimals)}${unit}`;

  // Scale-aware flatness: under 0.15 absolute or 1% of the prior level.
  const flatBand = Math.max(0.15, Math.abs(prior.value) * 0.01);
  // "Sharp" band: a move worth a stronger verb.
  const sharpBand = Math.max(1.0, Math.abs(prior.value) * 0.08);

  let verb: string;
  if (Math.abs(delta) < flatBand) verb = "holds at";
  else if (delta > 0) verb = delta >= sharpBand ? "climbed to" : "edged up to";
  else verb = -delta >= sharpBand ? "fell to" : "eased to";

  const when = prettyPeriod(last.period);
  if (Math.abs(delta) < flatBand) {
    return `${noun} ${verb} ${level} in ${when}`;
  }
  const sign = delta > 0 ? "+" : "−";
  const change = `${sign}${fmtNum(Math.abs(delta), decimals)}${deltaUnit}`;
  const span = pts.length - 1 >= window ? ` over ${window}m` : "";
  return `${noun} ${verb} ${level} in ${when} (${change}${span})`;
}
