/**
 * Capital — the pure arithmetic behind /capital's brief.
 *
 * The page's central problem: capital adequacy did not drift down, it STEPPED.
 * CAR went 19.69% → 16.77% between Dec 2025 and Jan 2026 — a −2.92pp move in a
 * single month, the largest in 76 months of record, and every ownership group
 * fell together. A twelve-month "drift" that straddles a discontinuity is not a
 * trend, and extrapolating it (as the old Headroom device did) sizes a buffer
 * against an average of a step and a non-step.
 *
 * So: detect the break from the series itself, split the year into the step and
 * everything else, and measure the drift only AFTER the break.
 */

export interface Pt {
  period: string;
  value: number | null;
}

const clean = (s: readonly Pt[]) =>
  s.filter((r): r is { period: string; value: number } => r.value != null);

/**
 * The largest single-period move in the trailing `window`, and whether it is a
 * structural break: a move `k`× larger than the typical move over the same
 * window. Rule-based, printable, no hand-picked date.
 */
export function detectStep(
  series: readonly Pt[],
  { window = 13, k = 3 }: { window?: number; k?: number } = {},
): { period: string; delta: number; typical: number; isBreak: boolean } | null {
  const s = clean(series).slice(-window);
  if (s.length < 3) return null;

  const moves = s.slice(1).map((p, i) => ({ period: p.period, delta: p.value - s[i].value }));
  const typical = moves.reduce((a, m) => a + Math.abs(m.delta), 0) / moves.length;
  const biggest = moves.reduce((a, m) => (Math.abs(m.delta) > Math.abs(a.delta) ? m : a));
  // Compare the biggest move against the typical move of the OTHER months, so a
  // single huge step can't inflate the bar it has to clear.
  const others = moves.filter((m) => m.period !== biggest.period);
  const base = others.length
    ? others.reduce((a, m) => a + Math.abs(m.delta), 0) / others.length
    : typical;
  return {
    period: biggest.period,
    delta: biggest.delta,
    typical: base,
    isBreak: base > 0 && Math.abs(biggest.delta) > k * base,
  };
}

/**
 * The 12-month change, split into the step and everything else. `rest` is what
 * the year did apart from the one-off — the number the old page averaged away.
 */
export function decompose12m(
  series: readonly Pt[],
  stepPeriod: string | null,
  months = 12,
): { from: number; to: number; total: number; step: number; rest: number } | null {
  const s = clean(series);
  if (s.length < months + 1) return null;
  const to = s[s.length - 1].value;
  const from = s[s.length - 1 - months].value;
  const total = to - from;
  let step = 0;
  if (stepPeriod) {
    const i = s.findIndex((p) => p.period === stepPeriod);
    // only count the step if it falls INSIDE the window being decomposed
    if (i > 0 && i >= s.length - months) step = s[i].value - s[i - 1].value;
  }
  return { from, to, total, step, rest: total - step };
}

/**
 * Drift measured only AFTER the break, annualized from the months since. The
 * honest slope to size a buffer against — and it names the window it used.
 */
export function postStepDrift(
  series: readonly Pt[],
  stepPeriod: string | null,
): { months: number; change: number; perYear: number } | null {
  const s = clean(series);
  if (!stepPeriod || s.length < 2) return null;
  const i = s.findIndex((p) => p.period === stepPeriod);
  if (i < 0 || i === s.length - 1) return null;
  const months = s.length - 1 - i;
  const change = s[s.length - 1].value - s[i].value;
  return { months, change, perYear: (change / months) * 12 };
}

/**
 * Quarters until the buffer over `min` is used up at `perYear` — a sizing
 * device, not a forecast. Null when the buffer is not eroding.
 */
export function quartersToFloor(
  car: number | null,
  perYear: number | null,
  min = 12,
): number | null {
  if (car == null || perYear == null || perYear >= 0) return null;
  const buffer = car - min;
  if (buffer <= 0) return 0;
  return (buffer / -perYear) * 4;
}

/**
 * The capital stack from the audited CET1 / Tier-1 / CAR ratios: AT1 is the gap
 * between Tier-1 and CET1, Tier-2 the gap between CAR and Tier-1. All three
 * components are POSITIVE and sum to total capital by construction — which is
 * why this one legitimately draws as a stacked area (unlike /liquidity's
 * reserve buffer, where a component goes negative and a stack would lie).
 */
export interface StackPt {
  period: string;
  cet1: number;
  at1: number;
  t2: number;
  car: number;
}

export function capitalStack(
  rows: readonly { period: string; bank_type_code: string; value: number | null }[],
): StackPt[] {
  const by = new Map<string, Record<string, number>>();
  for (const r of rows) {
    if (r.value == null) continue;
    const p = by.get(r.period) ?? {};
    p[r.bank_type_code] = r.value;
    by.set(r.period, p);
  }
  const out: StackPt[] = [];
  for (const period of [...by.keys()].sort()) {
    const p = by.get(period)!;
    const cet1 = p.CET1, tier1 = p.TIER1, car = p.CAR;
    if (cet1 == null || tier1 == null || car == null) continue;
    out.push({
      period,
      cet1,
      at1: Math.max(0, tier1 - cet1),
      t2: Math.max(0, car - tier1),
      car,
    });
  }
  return out;
}
