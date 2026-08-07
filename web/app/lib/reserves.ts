/**
 * The reserve buffer — one module owns the three levels, so two surfaces cannot
 * print rival numbers for the same quantity.
 *
 * TCMB publishes NO net-reserves headline: only gross (TP.AB.TOPLAM) and the IMF
 * reserve-template components. Net international reserves are therefore DERIVED
 * from the analytical balance sheet, and a derivation that lives inline in a page
 * is a derivation the next page re-implements slightly differently — the exact
 * shape of the loan-to-deposit bug that had `/deposits` showing 91% while
 * `/liquidity`, one click away, showed 97% (DESIGN.md, "one metric, one number").
 * `/liquidity` derived this inline first; `/economy` needs the same figure, so the
 * arithmetic moved here and both import it.
 *
 * The three levels, widest first:
 *
 *   gross    TP.AB.TOPLAM — published, USD m, weekly.
 *   net      (TP.BL054 − TP.BL122) ÷ USD/TRY. Both legs are the analytical
 *            balance sheet's FX assets and liabilities in TL thousand, so the
 *            quotient is USD and ÷1e6 lands in USD bn. The swap SPOT leg sits
 *            inside BL054 (verified: the net position moves with it), so this
 *            level INCLUDES swap FX.
 *   exSwaps  net − |TP.DOVVARNC.K15|. K15 is the forward/swap short position
 *            from the IMF reserve template (§2.2.1, monthly, USD m, published
 *            negative) — the off-balance-sheet FX owed forward, dominated by
 *            swaps. This is the CBRT's own money.
 *
 * Cadence: gross/net are WEEKLY, K15 is MONTHLY. K15 is stepped onto the weekly
 * dates (nearest-earlier month) rather than interpolated — a reserve template is
 * a month-end stock, not a path.
 *
 * `exSwaps` goes NEGATIVE for long stretches (42 of 150 weeks when /liquidity's
 * buffer chart was built), which is why the three levels are drawn as lines with
 * shaded gaps and never as a stack: a stacked area silently misstates the total
 * the moment a component crosses zero (DESIGN.md, "the mark has to fit the data").
 *
 * Pure + synchronous over rows the caller already fetched — no D1 here, so this
 * is unit-testable and safe in server components.
 */
import { type EvdsRow } from "@/app/lib/metrics";

/** The EVDS codes this module needs; spread into the caller's `evdsMulti`. */
export const RESERVE_CODES = [
  "TP.AB.TOPLAM",
  "TP.BL054",
  "TP.BL122",
  "TP.DK.USD.A",
  "TP.DOVVARNC.K15",
] as const;

/**
 * The forward/swap leg (K15) is MONTHLY while the buffer is WEEKLY, so the first
 * few weeks of any window can precede its first monthly row — on a 3-year fetch,
 * the balance sheet starts 2023-08-11 and the reserve template's first row in
 * that window is 2023-09-01. Those weeks are unscorable, and the page that
 * derived this inline used to score them anyway by treating "no row" as "no
 * swaps", printing the CBRT's own FX as larger than it was by the entire swap
 * book. Callers with a short window pass K15 fetched this much deeper as `fwd`,
 * which resolves the step instead of dropping the weeks.
 */
export const FWD_YEARS_BACK = 8;

/** One weekly observation of the buffer, all three levels in USD bn. */
export interface BufferPoint {
  period: string;
  /** Published gross reserves. */
  gross: number;
  /** Derived net international reserves (includes swap FX). */
  net: number;
  /** Net excluding the forward/swap book — the CBRT's own FX. May be negative. */
  own: number;
  /** Index signature so a row satisfies the chart helpers' `Row` shape. */
  [k: string]: string | number;
}

export interface ReserveBuffer {
  /** Weekly points carrying all three levels (only dates where all three exist). */
  points: BufferPoint[];
  /** Latest observation, or null when the series can't be assembled. */
  latest: BufferPoint | null;
  /** net − own: the swap stock standing inside net reserves, USD bn. */
  swapStock: number | null;
  /** gross − net: the banks' own FX held at the CBRT (required reserves), USD bn. */
  banksFx: number | null;
  /** How many weeks in the window the CBRT's own net FX sat below zero. */
  weeksOwnNegative: number;
}

/** Latest value at or before `date` in an ascending series — a stepped read. */
function stepAt(rows: EvdsRow[], date: string): number | null {
  for (let i = rows.length - 1; i >= 0; i--) {
    if (rows[i].period_date <= date) return rows[i].value;
  }
  return null;
}

/**
 * Assemble the buffer from an `evdsMulti` result.
 *
 * Returns only dates where every level is derivable: a week with no FX rate, or
 * before the reserve template starts, drops out rather than carrying a zero. A
 * missing K15 is NOT treated as "no swaps" — that would print the CBRT's own FX
 * as larger than it is, which is the direction that flatters.
 */
export function reserveBuffer(
  s: Record<string, EvdsRow[]>,
  /** K15 fetched over a longer window — see FWD_YEARS_BACK. */
  fwdOverride?: EvdsRow[],
): ReserveBuffer {
  const g = (code: string) => s[code] ?? [];
  const usd = new Map(g("TP.DK.USD.A").map((r) => [r.period_date, r.value]));
  const liab = new Map(g("TP.BL122").map((r) => [r.period_date, r.value]));
  const gross = new Map(g("TP.AB.TOPLAM").map((r) => [r.period_date, r.value / 1000]));
  const fwd = fwdOverride?.length ? fwdOverride : g("TP.DOVVARNC.K15");

  const points: BufferPoint[] = [];
  for (const r of g("TP.BL054")) {
    const d = r.period_date;
    const fx = usd.get(d);
    const l = liab.get(d);
    const gr = gross.get(d);
    if (!fx || l === undefined || gr === undefined) continue;
    const net = (r.value - l) / fx / 1e6;
    const k15 = stepAt(fwd, d);
    if (k15 == null) continue;
    points.push({ period: d, gross: gr, net, own: net - Math.abs(k15) / 1000 });
  }

  const latest = points.at(-1) ?? null;
  return {
    points,
    latest,
    swapStock: latest ? latest.net - latest.own : null,
    banksFx: latest ? latest.gross - latest.net : null,
    weeksOwnNegative: points.filter((p) => p.own < 0).length,
  };
}

/**
 * Months of the goods import bill that gross reserves cover — the standard
 * external-adequacy read (the IMF's 3-month rule of thumb).
 *
 * `imports12m` is the trailing-12-month customs import bill in USD bn, so the
 * monthly bill is that ÷ 12. Returns null rather than a ratio against a partial
 * year: a coverage figure computed off nine months of imports overstates cover
 * by a third, and the number looks entirely plausible.
 */
export function importCoverMonths(
  grossBn: number | null,
  imports12mBn: number | null,
): number | null {
  if (grossBn == null || imports12mBn == null || imports12mBn <= 0) return null;
  return grossBn / (imports12mBn / 12);
}
