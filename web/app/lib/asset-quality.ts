/**
 * Asset-quality transforms — the arithmetic behind the /asset-quality brief.
 *
 * The tab's central problem: the page led with "NPL ratio 2.69%", which is calm,
 * and is the TIP. What the ratio prints is Stage 3. Loans the banks themselves
 * classify as deteriorated are ~4x that, and three-quarters of the problem book
 * is the Stage-2 watchlist the ratio never shows.
 *
 * WHAT THIS MODULE DELIBERATELY DOES NOT DO — the mistake to not re-make:
 *
 *   An NPL ratio is N / L. Deflate BOTH legs by CPI and it is UNCHANGED — a ratio
 *   is deflator-invariant. Inflation therefore does NOT mechanically flatter it,
 *   and there is no "inflation dilution" to claim. Only REAL book growth dilutes,
 *   and that was +3.3% — worth ~0.1pp, not the ~1pp a nominally-frozen-book
 *   counterfactual would suggest. (A real bias does exist: the numerator is stale
 *   — a loan that defaulted two years ago sits at its origination principal —
 *   while the denominator reprices. Sizing it needs origination-vintage data we
 *   do not have, so we put no number on it.) `deflatorInvariance` in the tests
 *   pins this down.
 *
 * TWO NPL RATIOS, NEVER MIXED:
 *   - published  — BDDK `financial_ratios` t15, monthly. The official figure.
 *   - implied    — takipteki 2.0.1 ÷ krediler 1.0.1, weekly. Fresher and denser.
 *   They differ by a STABLE ~0.10pp (definitional, not noise). Quote one per
 *   statement; show the other as labelled context. Never divide across them.
 */
import { baseFor, growthSeries, toMap, type Pt } from "./series";

/**
 * The NPL-stock item ids. These do NOT mirror the `krediler` ids — mapping them
 * positionally is the single easiest way to build a beautiful, wrong page (it
 * gives auto a 1068% NPL ratio and segment shares summing to 204%):
 *
 *   2.0.4  is SME          — NOT housing
 *   2.0.6  is PROVISIONS   — NOT general-purpose
 *   2.0.11 is auto         — NOT SME
 *
 * Verified against `item_name`. The five DISJOINT segments below reconcile to the
 * total (2.0.1) at 100.00% — `nplContributions` returns the sum so callers can
 * print it, and the test asserts it.
 */
export const NPL_ITEMS = {
  TOTAL: "2.0.1",
  PROVISIONS: "2.0.6",
  // disjoint + exhaustive
  HOUSING: "2.0.10",
  AUTO: "2.0.11",
  GPL: "2.0.12",
  CARDS: "2.0.3",
  COMMERCIAL: "2.0.5",
  // memo — a CUT of commercial, never an addend
  SME: "2.0.4",
} as const;

/** The matching loan-book ids in `krediler` (these DO differ from the above). */
export const LOAN_ITEMS = {
  TOTAL: "1.0.1",
  HOUSING: "1.0.4",
  AUTO: "1.0.5",
  GPL: "1.0.6",
  CARDS: "1.0.8",
  COMMERCIAL: "1.0.12",
  SME: "1.0.11",
} as const;

/** NPL ratio implied by the weekly bulletin: stock ÷ book, per week (%). */
export function impliedRatio(stock: Pt[], loans: Pt[]): Pt[] {
  const l = toMap(loans);
  const out: Pt[] = [];
  for (const r of stock) {
    if (r.value == null) continue;
    const book = l.get(r.period);
    if (book == null || book <= 0) continue;
    out.push({ period: r.period, value: (r.value / book) * 100 });
  }
  return out;
}

export interface SegmentRatio {
  key: string;
  label: string;
  /** NPL ratio now and 52w ago (%), and the move. */
  now: number;
  base: number;
  delta: number;
  /** The segment's NPL stock, ₺bn, and its 52w growth (%). */
  stockBn: number;
  stockYoY: number | null;
  /** The segment's loan book, ₺bn. */
  loanBn: number;
  /** Ratio history for a sparkline. */
  series: Pt[];
}

/**
 * Per-segment NPL ratio (stock ÷ its own loan book), plus the history.
 * Source values are TL millions; ₺bn = value / 1_000.
 */
export function segmentRatios(
  segments: Array<{ key: string; label: string; stock: Pt[]; loans: Pt[] }>,
  asOf: string,
): SegmentRatio[] {
  const out: SegmentRatio[] = [];
  for (const s of segments) {
    const sm = toMap(s.stock);
    const lm = toMap(s.loans);
    const stockNow = sm.get(asOf);
    const loanNow = lm.get(asOf);
    const stockBase = baseFor(sm, asOf);
    const loanBase = baseFor(lm, asOf);
    if (stockNow == null || loanNow == null || loanNow <= 0 || !stockBase || !loanBase) continue;
    if (loanBase.value <= 0) continue;

    const now = (stockNow / loanNow) * 100;
    const base = (stockBase.value / loanBase.value) * 100;
    const g = growthSeries(s.stock);

    out.push({
      key: s.key,
      label: s.label,
      now,
      base,
      delta: now - base,
      stockBn: stockNow / 1_000,
      stockYoY: g.at(-1)?.value ?? null,
      loanBn: loanNow / 1_000,
      series: impliedRatio(s.stock, s.loans),
    });
  }
  return out;
}

/**
 * Where the increase in the NPL stock came from: each segment's share of the
 * total ₺ increase over the window. Disjoint segments only — pass SME via `memo`,
 * because it is a CUT of commercial and adding it would double-count.
 */
export function nplStockAttribution(
  total: Pt[],
  parts: Array<{ key: string; label: string; rows: Pt[] }>,
  memo?: { key: string; label: string; rows: Pt[] },
): {
  at: string | null;
  totalDelta: number;
  items: Array<{ key: string; label: string; share: number; delta: number }>;
  sumShare: number;
  memo: { key: string; label: string; share: number; delta: number } | null;
} {
  const tm = toMap(total);
  const last = total.filter((r) => r.value != null).at(-1);
  if (!last) return { at: null, totalDelta: 0, items: [], sumShare: 0, memo: null };
  const tBase = baseFor(tm, last.period);
  const tNow = tm.get(last.period);
  if (!tBase || tNow == null) return { at: last.period, totalDelta: 0, items: [], sumShare: 0, memo: null };

  const totalDelta = tNow - tBase.value;
  const shareOf = (rows: Pt[]) => {
    const m = toMap(rows);
    const now = m.get(last.period);
    const b = baseFor(m, last.period);
    if (now == null || !b || totalDelta === 0) return null;
    const delta = now - b.value;
    return { delta, share: (delta / totalDelta) * 100 };
  };

  const items = parts.flatMap((p) => {
    const s = shareOf(p.rows);
    return s ? [{ key: p.key, label: p.label, share: s.share, delta: s.delta }] : [];
  });

  let memoOut: { key: string; label: string; share: number; delta: number } | null = null;
  if (memo) {
    const s = shareOf(memo.rows);
    if (s) memoOut = { key: memo.key, label: memo.label, share: s.share, delta: s.delta };
  }

  return {
    at: last.period,
    totalDelta,
    items,
    sumShare: items.reduce((a, i) => a + i.share, 0),
    memo: memoOut,
  };
}
