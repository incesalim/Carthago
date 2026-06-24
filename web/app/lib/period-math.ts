/**
 * Quarter-period arithmetic shared across the audit/valuation layer.
 *
 * Periods are stored as "YYYYQN" text (e.g. "2025Q3"). We map each to a
 * chronological ordinal so de-cumulation, trailing-twelve-month sums and
 * year-over-year growth can be expressed as simple integer offsets:
 *
 *     ord = year * 4 + (quarter - 1)      // 2025Q1 → 8100, 2025Q2 → 8101, …
 *
 * P&L and cash-flow amounts in the BRSA audit tables are YTD-cumulative within
 * the year; the balance sheet is point-in-time. `singleQuarter` de-cumulates a
 * YTD series to one quarter, and `ttmEndingAt` sums the trailing four single
 * quarters. The middle quarters telescope, so a trailing-twelve-month figure is
 * robust to the YTD-vs-3-month column quirks in some historical extractions:
 *     TTM(latest) = YTD(latest) + FY(prior) − YTD(same quarter, prior year).
 */

/** "YYYYQN" → chronological ordinal, or null if not a quarter period. */
export function ordOf(period: string): number | null {
  const m = /^(\d{4})Q([1-4])$/.exec(period);
  return m ? Number(m[1]) * 4 + (Number(m[2]) - 1) : null;
}

/** Inverse of {@link ordOf}: chronological ordinal → "YYYYQN". */
export function periodFromOrd(ord: number): string {
  const year = Math.floor(ord / 4);
  const q = (ord % 4) + 1;
  return `${year}Q${q}`;
}

/**
 * De-cumulate a YTD series (keyed by ordinal) to the single quarter at `ord`.
 * Q1's YTD is already one quarter; later quarters subtract the prior quarter's
 * YTD. Returns null if either the current or the needed prior YTD is missing.
 */
export function singleQuarter(
  ytdByOrd: Map<number, number>,
  ord: number,
): number | null {
  const cur = ytdByOrd.get(ord);
  if (cur == null) return null;
  if (ord % 4 === 0) return cur; // Q1 (quarter - 1 === 0) — YTD is one quarter
  const prev = ytdByOrd.get(ord - 1);
  return prev == null ? null : cur - prev;
}

/**
 * Trailing-twelve-month sum ending at `latestOrd` — the four single quarters
 * `[latestOrd-3 .. latestOrd]`. Returns null if any of them can't be derived.
 */
export function ttmEndingAt(
  ytdByOrd: Map<number, number>,
  latestOrd: number,
): number | null {
  let ttm = 0;
  for (let k = 0; k < 4; k++) {
    const sq = singleQuarter(ytdByOrd, latestOrd - k);
    if (sq == null) return null;
    ttm += sq;
  }
  return ttm;
}

/**
 * Year-over-year percentage growth. Magnitude-relative (`/|prior|`) so a swing
 * from a loss to a profit still yields a number, though the sign can read oddly
 * when the prior base is negative. Null when either side is missing or the base
 * is zero (growth undefined).
 */
export function yoyPct(
  curr: number | null | undefined,
  prior: number | null | undefined,
): number | null {
  if (curr == null || prior == null || prior === 0) return null;
  return ((curr - prior) / Math.abs(prior)) * 100;
}
