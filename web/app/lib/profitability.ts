/**
 * Profitability — the arithmetic behind /profitability's brief.
 *
 * TWO THINGS THE PAGE'S OWN DATA HIDES.
 *
 * 1. The BDDK income statement is CUMULATIVE year-to-date (sector net profit runs
 *    0.09 → 0.17 → 0.29 → 0.36 through a year), so every ratio built from it —
 *    ROE, ROA, NIM, OPEX — is a YTD figure annualized. To read a MONTH you must
 *    de-cumulate: month(m) = ytd(m) − ytd(m−1), and January IS the year to date.
 *    De-cumulated, May 2026's net interest income rose ₺98bn y/y and the profit
 *    still FELL — costs and trading took it. A YTD average cannot show that.
 *
 * 2. The margin is not earned on the loan book. It is collected on the deposits
 *    the sector does not pay for: demand deposits are ~37% of the base and pay
 *    nothing, so the blended deposit cost (20.9%) sits far below the rate the
 *    sector actually pays the depositors it does pay (33.1%). Priced at that
 *    rate the demand book is worth ~₺3.2trn a year — around 3× the entire profit
 *    of the banking system.
 *
 * The counterfactual is a SIZING DEVICE, not a forecast (demand deposits carry
 * servicing costs, and a sector that paid for them would not hold the same book).
 * And it is applied as a COST against the published ROE — never as a rival ROE.
 */

/** One month of the sector's cumulative-YTD income statement (₺ thousands). */
export interface PnlRow {
  year: number;
  month: number;
  dep_int: number | null;   // 16 — interest paid to depositors
  nii: number | null;       // 24 — net interest income
  prov: number | null;      // 25 — specific provisions
  fees: number | null;      // 34 — non-interest income
  opex: number | null;      // 45 — non-interest expense
  other: number | null;     // 50 — trading, FX, extraordinary, monetary position
  tax: number | null;       // 52
  net: number | null;       // 53 — reported net profit (the reconciliation anchor)
}

/** One month of the sector's balance sheet (₺ thousands). */
export interface BsRow {
  year: number;
  month: number;
  demand: number | null;
  time_dep: number | null;
  total_dep: number | null;
  equity: number | null;
}

const TRN = 1e6; // ₺ thousands → ₺ trn
export const key = (r: { year: number; month: number }) =>
  `${r.year}-${String(r.month).padStart(2, "0")}`;

/** The month alone, out of a year-to-date series. January IS the YTD. */
export function deCumulate(
  rows: readonly PnlRow[],
  field: keyof Omit<PnlRow, "year" | "month">,
): { period: string; value: number }[] {
  const by = new Map(rows.map((r) => [key(r), r]));
  const out: { period: string; value: number }[] = [];
  for (const r of [...rows].sort((a, b) => key(a).localeCompare(key(b)))) {
    const cur = (r[field] ?? 0) / TRN;
    if (r.month === 1) {
      out.push({ period: key(r), value: cur });
      continue;
    }
    const prev = by.get(`${r.year}-${String(r.month - 1).padStart(2, "0")}`);
    if (!prev) continue; // a hole in the year → no honest month can be formed
    out.push({ period: key(r), value: cur - (prev[field] ?? 0) / TRN });
  }
  return out;
}

/** A YTD figure put on an annual footing: ytd × 12/month. */
export const annualize = (r: PnlRow, field: keyof Omit<PnlRow, "year" | "month">) =>
  ((r[field] ?? 0) / TRN) * (12 / r.month);

/** Trailing average of a balance-sheet stock — the denominator of a return. */
export function avgStock(
  rows: readonly BsRow[],
  upTo: string,
  field: keyof Omit<BsRow, "year" | "month">,
  back = 12,
): number | null {
  const sorted = [...rows].sort((a, b) => key(a).localeCompare(key(b)));
  const i = sorted.findIndex((r) => key(r) === upTo);
  if (i < 0) return null;
  const win = sorted.slice(Math.max(0, i - back), i + 1);
  const vals = win.map((r) => (r[field] ?? 0) / TRN).filter((v) => v > 0);
  return vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
}

/** The engine: what the deposits the sector does not pay for are worth. */
export interface EnginePt {
  period: string;
  demandShare: number;  // % of the deposit base that pays nothing
  paidOnTime: number;   // the rate paid on the deposits that DO earn interest
  blended: number;      // what the sector pays across the whole base
  free: number;         // paidOnTime − blended, in pp
  worth: number;        // the demand book priced at paidOnTime, ₺ trn/yr
  profit: number;       // sector net profit, annualized, ₺ trn
  ratio: number;        // worth ÷ profit
  equity: number;       // average equity, ₺ trn
  roeCost: number;      // what paying for the demand book would cost, in pp of ROE
}

export function engine(pnl: readonly PnlRow[], bs: readonly BsRow[]): EnginePt[] {
  const out: EnginePt[] = [];
  for (const r of [...pnl].sort((a, b) => key(a).localeCompare(key(b)))) {
    const k = key(r);
    const dem = avgStock(bs, k, "demand");
    const tim = avgStock(bs, k, "time_dep");
    const tot = avgStock(bs, k, "total_dep");
    const eq = avgStock(bs, k, "equity");
    if (!dem || !tim || !tot || !eq) continue;

    const depInt = annualize(r, "dep_int");
    const profit = annualize(r, "net");
    if (!(profit > 0)) continue;

    const paidOnTime = (depInt / tim) * 100;
    const blended = (depInt / tot) * 100;
    const worth = (paidOnTime / 100) * dem;
    out.push({
      period: k,
      demandShare: (dem / tot) * 100,
      paidOnTime,
      blended,
      free: paidOnTime - blended,
      worth,
      profit,
      ratio: worth / profit,
      equity: eq,
      roeCost: (worth / eq) * 100,
    });
  }
  return out;
}

/** The month's P&L, de-cumulated — and whether it reconciles to the reported line. */
export interface Bridge {
  period: string;
  nii: number;
  prov: number;   // negative
  fees: number;
  opex: number;   // negative
  other: number;
  tax: number;    // negative
  net: number;    // the REPORTED line, not the sum
  computed: number;
  gap: number;    // computed − reported
  reconciles: boolean;
}

/**
 * The bridge is assembled from FIXED item_order positions. If BDDK renumbers a
 * line the sum drifts silently — so it is checked against the statement's own
 * net-profit line, and the page prints a data-quality flag instead of the chart
 * when it fails. A page that must survive a cron cannot fail quietly.
 */
export const RECONCILE_TOLERANCE = 0.001; // ₺ trn

export function bridge(pnl: readonly PnlRow[], period?: string): Bridge | null {
  const sorted = [...pnl].sort((a, b) => key(a).localeCompare(key(b)));
  const target = period ?? (sorted.length ? key(sorted[sorted.length - 1]) : null);
  if (!target) return null;

  const pick = (f: keyof Omit<PnlRow, "year" | "month">) =>
    deCumulate(sorted, f).find((p) => p.period === target)?.value;

  const nii = pick("nii"), prov = pick("prov"), fees = pick("fees");
  const opex = pick("opex"), other = pick("other"), tax = pick("tax"), net = pick("net");
  if ([nii, prov, fees, opex, other, tax, net].some((v) => v == null)) return null;

  const computed = nii! - prov! + fees! - opex! + other! - tax!;
  const gap = computed - net!;
  return {
    period: target,
    nii: nii!,
    prov: -prov!,
    fees: fees!,
    opex: -opex!,
    other: other!,
    tax: -tax!,
    net: net!,
    computed,
    gap,
    reconciles: Math.abs(gap) <= RECONCILE_TOLERANCE,
  };
}

/** Cost ÷ income — the efficiency ratio the page never printed. */
export function costIncome(pnl: readonly PnlRow[]): { period: string; value: number }[] {
  return [...pnl]
    .sort((a, b) => key(a).localeCompare(key(b)))
    .map((r) => {
      const income = annualize(r, "nii") + annualize(r, "fees");
      return income > 0
        ? { period: key(r), value: (annualize(r, "opex") / income) * 100 }
        : null;
    })
    .filter((p): p is { period: string; value: number } => p != null);
}
