/**
 * Pure helpers for "The Desk" briefing layer — streak counting, window
 * extremes and the CPI y/y ⁄ 12m-average transforms the brief's computed
 * notes and rule-based flags are built from. Server-safe, no I/O.
 */

export interface Pt {
  period: string;
  value: number | null;
}

export const lastVal = (s: Pt[]): number | null => s.at(-1)?.value ?? null;
export const prevVal = (s: Pt[]): number | null => s.at(-2)?.value ?? null;
export const lastPeriod = (s: Pt[]): string | null => s.at(-1)?.period ?? null;

/** Value n periods before the latest (n=12 on monthly ≈ a year ago). */
export const valAgo = (s: Pt[], n: number): number | null => s.at(-1 - n)?.value ?? null;

/**
 * Length of the terminal run of strictly rising (dir="up") or falling
 * (dir="down") period-over-period moves. `tol` ignores sub-threshold wiggles.
 */
export function streak(s: Pt[], dir: "up" | "down", tol = 0): number {
  let n = 0;
  for (let i = s.length - 1; i > 0; i--) {
    const c = s[i]?.value;
    const p = s[i - 1]?.value;
    if (c == null || p == null) break;
    const d = c - p;
    if (dir === "up" ? d > tol : d < -tol) n++;
    else break;
  }
  return n;
}

/** Min/max over the trailing n points (skips nulls). */
export function windowExtremes(
  s: Pt[],
  n: number,
): { min: number; minPeriod: string; max: number; maxPeriod: string } | null {
  const w = s.slice(-n).filter((r) => r.value != null) as { period: string; value: number }[];
  if (!w.length) return null;
  let min = w[0], max = w[0];
  for (const r of w) {
    if (r.value < min.value) min = r;
    if (r.value > max.value) max = r;
  }
  return { min: min.value, minPeriod: min.period, max: max.value, maxPeriod: max.period };
}

/** 'YYYY-MM…' → 'May 2026' / 'May' (short). */
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
export function monthLabel(p: string | null | undefined, withYear = true): string {
  if (!p) return "—";
  const m = /^(\d{4})-(\d{2})/.exec(p);
  if (!m) return p;
  const mon = MONTHS[Number(m[2]) - 1] ?? p;
  return withYear ? `${mon} ${m[1]}` : mon;
}

export const signedPp = (v: number, d = 2): string =>
  `${v >= 0 ? "+" : "−"}${Math.abs(v).toFixed(d)}pp`;

/**
 * Latest value of each bank-type group in a long-form `{period, bank_type_code,
 * value}` series — the spread the scorecard's peer bar scales against, so a
 * group's cell reads against the league it belongs to and not an arbitrary axis.
 */
export function groupSpread(
  rows: ReadonlyArray<{ period: string; bank_type_code: string; value: number | null }>,
): { lo: number; hi: number } | null {
  const latest = new Map<string, { period: string; value: number }>();
  for (const r of rows) {
    if (r.value == null) continue;
    const cur = latest.get(r.bank_type_code);
    if (!cur || r.period > cur.period) latest.set(r.bank_type_code, { period: r.period, value: r.value });
  }
  const vals = [...latest.values()].map((v) => v.value);
  if (!vals.length) return null;
  return { lo: Math.min(...vals), hi: Math.max(...vals) };
}

/**
 * Monthly CPI index levels (EVDS `TP.TUKFIY2025.GENEL`, `period_date` rows) →
 * y/y % and the 12-month rolling average of y/y (the deflator used for every
 * "real terms" read; same arithmetic as /profitability and /economy).
 */
export function cpiFromIndex(raw: { period_date: string; value: number }[]): {
  yoy: Pt[];
  avg12: Pt[];
} {
  const levels = raw
    .slice()
    .sort((a, b) => (a.period_date < b.period_date ? -1 : 1));
  const yoy: Pt[] = [];
  for (let i = 12; i < levels.length; i++) {
    const cur = levels[i].value;
    const prev = levels[i - 12].value;
    if (prev > 0)
      yoy.push({ period: levels[i].period_date.slice(0, 7), value: (cur / prev - 1) * 100 });
  }
  const avg12: Pt[] = [];
  for (let i = 11; i < yoy.length; i++) {
    let sum = 0;
    for (let j = i - 11; j <= i; j++) sum += yoy[j].value as number;
    avg12.push({ period: yoy[i].period, value: sum / 12 });
  }
  return { yoy, avg12 };
}
