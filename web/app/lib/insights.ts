/**
 * Deterministic insight engine (SERVER-safe, pure). Turns the series a page
 * already fetches into ranked plain-language takeaways — no LLM, recomputed live
 * from D1 each render, so it can never drift from the charts. Each tab's
 * takeaway is framed by its rationale.json guiding question (the "perspective"
 * layer, gated by the spine rather than piled on).
 *
 * Tone rules are conservative: a metric only reads positive/warn when its
 * move/level clears a threshold; otherwise neutral. All thresholds are explicit.
 */
import type { TimeSeriesRow } from "./metrics";

export type Tone = "positive" | "warn" | "neutral";

export interface Insight {
  text: string;
  tone: Tone;
  href?: string;
}

export interface TabTakeaway {
  asOf: string | null;
  headline: string;
  items: Insight[];
}

const last = (s: TimeSeriesRow[]): number | null => s.at(-1)?.value ?? null;
const prev = (s: TimeSeriesRow[]): number | null => s.at(-2)?.value ?? null;
const asOf = (s: TimeSeriesRow[]): string | null => s.at(-1)?.period ?? null;
const pct = (v: number | null, d = 1): string => (v == null ? "—" : `${v.toFixed(d)}%`);
const ppStr = (v: number): string => `${v >= 0 ? "+" : ""}${v.toFixed(2)}pp`;

/** Period-over-period change in percentage points (for ratio series). */
function deltaPp(s: TimeSeriesRow[]): number | null {
  const c = last(s);
  const p = prev(s);
  return c != null && p != null ? c - p : null;
}

const CAR_MIN = 12; // BDDK regulatory minimum (incl. buffers)

/**
 * Overview "Sector Pulse" — one takeaway per CAMELS vital, in spine order
 * (growth → asset quality → capital → earnings → funding), each linking to the
 * tab that proves it. Answers the Overview guiding question: "how is the sector
 * doing right now?"
 */
export function overviewInsights(d: {
  assetsYoY: TimeSeriesRow[];
  loansYoY: TimeSeriesRow[];
  depositsYoY: TimeSeriesRow[];
  npl: TimeSeriesRow[];
  car: TimeSeriesRow[];
  ldr: TimeSeriesRow[];
  roe: TimeSeriesRow[];
}): TabTakeaway {
  const period = asOf(d.npl) ?? asOf(d.assetsYoY);
  const items: Insight[] = [];

  // Size & growth (A — volume)
  const ay = last(d.assetsYoY);
  const ly = last(d.loansYoY);
  const dy = last(d.depositsYoY);
  items.push({
    text: `Balance sheet ${ay != null && ay >= 0 ? "expanding" : "contracting"} — assets ${pct(ay)} y/y, loans ${pct(ly)}, deposits ${pct(dy)}.`,
    tone: "neutral",
    href: "/credit",
  });

  // Asset quality (A)
  const npl = last(d.npl);
  const nplD = deltaPp(d.npl);
  items.push({
    text: `NPL ratio ${pct(npl, 2)}${nplD != null ? ` (${ppStr(nplD)} m/m, ${nplD > 0.03 ? "creeping up" : nplD < -0.03 ? "easing" : "broadly stable"})` : ""}.`,
    tone: nplD != null && nplD > 0.03 ? "warn" : nplD != null && nplD < -0.03 ? "positive" : "neutral",
    href: "/asset-quality",
  });

  // Capital (C)
  const car = last(d.car);
  const carD = deltaPp(d.car);
  const buffer = car != null ? car - CAR_MIN : null;
  items.push({
    text: `Capital adequacy ${pct(car)}${buffer != null ? ` — ${buffer.toFixed(1)}pp above the ${CAR_MIN}% minimum` : ""}${carD != null ? ` (${ppStr(carD)} m/m)` : ""}.`,
    tone: buffer != null && buffer < 2 ? "warn" : buffer != null && buffer >= 4 ? "positive" : "neutral",
    href: "/capital",
  });

  // Earnings (E)
  const roe = last(d.roe);
  const roeD = deltaPp(d.roe);
  items.push({
    text: `ROE ${pct(roe)} (annualized)${roeD != null ? `, ${roeD >= 0 ? "up" : "down"} ${Math.abs(roeD).toFixed(1)}pp m/m` : ""}.`,
    tone: "neutral",
    href: "/profitability",
  });

  // Funding / liquidity (L)
  const ldr = last(d.ldr);
  items.push({
    text: `Loan-to-deposit ${pct(ldr)} — funding ${ldr != null && ldr > 110 ? "stretched" : "comfortable"}.`,
    tone: ldr != null && ldr > 120 ? "warn" : "neutral",
    href: "/liquidity",
  });

  const grow = ay != null && ay >= 0 ? "growing" : "shrinking";
  const earn = roe != null && roe >= 0 ? "profitable" : "loss-making";
  const headline =
    `As of ${period ?? "—"}: the sector is ${grow} (assets ${pct(ay)} y/y) and ${earn} (ROE ${pct(roe)}), ` +
    `with NPL at ${pct(npl, 2)} and capital ${buffer != null && buffer >= 4 ? "comfortably above" : "above"} the minimum at ${pct(car)}.`;

  return { asOf: period, headline, items };
}
