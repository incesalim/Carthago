/**
 * Deterministic insight engine (SERVER-safe, pure). Turns the series a page
 * already fetches into ranked plain-language takeaways — no LLM, recomputed live
 * from D1 each render, so it can never drift from the charts. Each tab's
 * takeaway is framed by its rationale.json guiding question (the "perspective"
 * layer, gated by the spine rather than piled on).
 *
 * Tone rules are conservative: a metric only reads positive/warn when its
 * move/level clears a threshold; otherwise neutral. All thresholds are explicit.
 *
 * Every DIRECTIONAL word comes from `direction()` + the closed `VERBS` vocabulary
 * (lib/prose.ts) rather than being typed into the template. That is what lets
 * prose-regression.test.ts feed these builders sign-inverted fixtures and assert
 * that no falling word survives a rising series — the gate can only be decisive
 * if the vocabulary is enumerable.
 */

import { VERBS, direction } from "./prose";

/**
 * Minimal series shape the engine needs — structurally satisfied by
 * `TimeSeriesRow` (metrics) and `TrendPoint` (audit-ratios / market-risk),
 * so pages can feed either without adapters.
 */
export interface SeriesPoint {
  period: string;
  value: number | null;
}

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

const last = (s: SeriesPoint[]): number | null => s.at(-1)?.value ?? null;
const prev = (s: SeriesPoint[]): number | null => s.at(-2)?.value ?? null;
const asOf = (s: SeriesPoint[]): string | null => s.at(-1)?.period ?? null;
const pct = (v: number | null, d = 1): string => (v == null ? "—" : `${v.toFixed(d)}%`);
const ppStr = (v: number): string => `${v >= 0 ? "+" : ""}${v.toFixed(2)}pp`;

/** Period-over-period change in percentage points (for ratio series). */
function deltaPp(s: SeriesPoint[]): number | null {
  const c = last(s);
  const p = prev(s);
  return c != null && p != null ? c - p : null;
}

/** Change over the trailing n periods, in pp (e.g. n=52 on weekly ≈ YoY). */
function deltaOver(s: SeriesPoint[], n: number): number | null {
  const c = last(s);
  const p = s.at(-1 - n)?.value ?? null;
  return c != null && p != null ? c - p : null;
}

/** % growth over the trailing n periods (for level series). */
function growthOver(s: SeriesPoint[], n: number): number | null {
  const c = last(s);
  const p = s.at(-1 - n)?.value ?? null;
  return c != null && p != null && p !== 0 ? ((c - p) / Math.abs(p)) * 100 : null;
}

const CAR_MIN = 12; // BDDK regulatory minimum (incl. buffers)

/**
 * Overview "Sector Pulse" — one takeaway per CAMELS vital, in spine order
 * (growth → asset quality → capital → earnings → funding), each linking to the
 * tab that proves it. Answers the Overview guiding question: "how is the sector
 * doing right now?"
 */
export function overviewInsights(d: {
  assetsYoY: SeriesPoint[];
  loansYoY: SeriesPoint[];
  depositsYoY: SeriesPoint[];
  npl: SeriesPoint[];
  car: SeriesPoint[];
  ldr: SeriesPoint[];
  roe: SeriesPoint[];
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

/*
 * Per-tab Reads. Every input is a SINGLE pre-filtered series (the page filters
 * by its own bank_type_code convention before calling), so these stay agnostic
 * to weekly vs monthly code schemes.
 */

/** Credit — "how fast is credit growing, in what currency, to whom?" */
export function creditInsights(d: {
  yoy: SeriesPoint[]; // sector loan growth, 52w NOMINAL
  mom4: SeriesPoint[]; // 4w annualized momentum
  yoyState: SeriesPoint[];
  yoyPrivate: SeriesPoint[];
  fxShare: SeriesPoint[]; // weekly
  cardsYoY: SeriesPoint[];
  smeYoY: SeriesPoint[];
  /**
   * The bridge: nominal -> minus lira -> minus inflation -> real, constant FX.
   * Without it this engine opened with "Credit expands 36.6% y/y ... confirming
   * acceleration", which flatly CONTRADICTS the brief above it: the same book
   * SHRANK 2.1% once the lira and the price level are stripped. The Read must not
   * argue with the page it sits on.
   */
  bridge?: {
    nominal: number | null;
    realFxAdj: number | null;
    currencyPp: number | null;
    inflationPp: number | null;
  } | null;
}): TabTakeaway {
  const period = asOf(d.yoy);
  const items: Insight[] = [];

  const y = last(d.yoy);
  const m4 = last(d.mom4);
  const b = d.bridge ?? null;
  const real = b?.realFxAdj ?? null;
  const pace =
    y != null && m4 != null ? (m4 > y + 2 ? "accelerating" : m4 < y - 2 ? "cooling" : "steady") : null;

  // Lead with what the book actually did, not with the nominal print.
  if (real != null && y != null) {
    items.push({
      text:
        `Nominal credit grows ${pct(y)} y/y — but strip the lira and the price level and the book ` +
        `${real < 0 ? "shrank" : "grew"} ${pct(Math.abs(real))} in real, constant-FX terms.`,
      tone: real < 0 ? "warn" : "neutral",
    });
    if (b?.currencyPp != null && b?.inflationPp != null) {
      items.push({
        text:
          `Of that ${pct(y)} print, ${ppStr(b.currencyPp)} is lira depreciation revaluing the FX book ` +
          `and ${ppStr(b.inflationPp)} is inflation. What remains is real volume.`,
        tone: "neutral",
      });
    }
  } else if (y != null) {
    items.push({
      text: `Loan growth ${pct(y)} y/y (nominal)${m4 != null ? `; the 4-week pace (${pct(m4)}) says the trend is ${pace}` : ""}.`,
      tone: "neutral",
    });
  }

  if (real != null && y != null && m4 != null) {
    items.push({
      text: `The 4-week pace (${pct(m4)}) says the NOMINAL trend is ${pace} — on a book that is not growing in real terms.`,
      tone: "neutral",
    });
  }

  const st = last(d.yoyState);
  const pr = last(d.yoyPrivate);
  if (st != null && pr != null) {
    items.push({
      text: `${st >= pr ? "State" : "Private"} banks lead the lending cycle — ${pct(Math.max(st, pr))} vs ${pct(Math.min(st, pr))} y/y (${ppStr(Math.abs(st - pr))} gap).`,
      tone: "neutral",
    });
  }

  const fx = last(d.fxShare);
  const fxD = deltaPp(d.fxShare);
  if (fx != null) {
    items.push({
      text: `FX loans are ${fxD != null && fxD < -0.3 ? "losing" : fxD != null && fxD > 0.3 ? "gaining" : "holding"} share of the book — ${pct(fx)} of total${fxD != null ? ` (${ppStr(fxD)})` : ""}.`,
      tone: "neutral",
    });
  }

  const cards = last(d.cardsYoY);
  const sme = last(d.smeYoY);
  if (cards != null && sme != null) {
    const tilt = cards > sme + 5 ? "consumer-led (cards)" : sme > cards + 5 ? "SME-led" : "broad-based";
    items.push({
      text: `The mix is ${tilt}: retail cards ${pct(cards)} vs SME ${pct(sme)} y/y.`,
      tone: cards > sme + 15 ? "warn" : "neutral",
      href: "/asset-quality",
    });
  }

  const headline =
    real != null && y != null
      ? `The ${pct(y)} loan-growth print is mostly lira and inflation: in real, constant-FX terms the book ` +
        `${real < 0 ? `shrank ${pct(Math.abs(real))}` : `grew ${pct(real)}`}` +
        `${st != null && pr != null ? `, with ${st >= pr ? "state" : "private"} banks leading the cycle` : ""}.`
      : `Credit is growing ${pct(y)} y/y and ${pace ?? "—"}, led by ${st != null && pr != null && st >= pr ? "state" : "private"} banks; ` +
        `FX share of the book ${fx != null ? `at ${pct(fx)}` : "—"}.`;

  return { asOf: period, headline, items };
}

/** Deposits — "where is funding coming from — growing, sticky, dollarizing?" */
export function depositsInsights(d: {
  yoy: SeriesPoint[]; // sector deposit growth
  loansYoY: SeriesPoint[]; // sector loan growth (funding-gap read)
  fxShare: SeriesPoint[]; // dollarization
  demandShare: SeriesPoint[];
  ldr: SeriesPoint[]; // sector, monthly
}): TabTakeaway {
  const period = asOf(d.yoy);
  const items: Insight[] = [];

  const dy = last(d.yoy);
  const ly = last(d.loansYoY);
  if (dy != null) {
    const gap = ly != null ? dy - ly : null;
    items.push({
      text: `Deposits growing ${pct(dy)} y/y${gap != null ? ` — ${gap >= 0 ? "ahead of" : "behind"} loans by ${Math.abs(gap).toFixed(1)}pp, so the funding gap is ${gap >= 0 ? "easing" : "widening"}` : ""}.`,
      tone: gap != null && gap < -5 ? "warn" : gap != null && gap > 0 ? "positive" : "neutral",
    });
  }

  const fx = last(d.fxShare);
  const fxD = deltaOver(d.fxShare, 52);
  if (fx != null) {
    items.push({
      text: `Dollarization ${fxD != null ? (fxD < -0.5 ? "unwinding" : fxD > 0.5 ? "rebuilding" : "flat") : ""} — FX deposits ${pct(fx)} of total${fxD != null ? ` (${ppStr(fxD)} y/y)` : ""}.`,
      tone: fxD != null && fxD < -0.5 ? "positive" : fxD != null && fxD > 1 ? "warn" : "neutral",
    });
  }

  const ds = last(d.demandShare);
  const dsD = deltaOver(d.demandShare, 52);
  if (ds != null) {
    items.push({
      text: `Demand deposits — the cheapest funding — are ${pct(ds)} of the base${dsD != null ? ` (${ppStr(dsD)} y/y)` : ""}.`,
      tone: dsD != null && dsD < -1 ? "warn" : "neutral",
    });
  }

  const l = last(d.ldr);
  if (l != null) {
    items.push({
      text: `Loan-to-deposit at ${pct(l)} — ${l > 110 ? "stretched; growth leans on non-deposit funding" : l > 95 ? "fully lent" : "comfortable"}.`,
      tone: l > 110 ? "warn" : "neutral",
      href: "/liquidity",
    });
  }

  const headline =
    `Deposits are growing ${pct(dy)} y/y${ly != null && dy != null ? ` (loans ${pct(ly)})` : ""}, ` +
    `FX share ${fx != null ? `at ${pct(fx)}` : "—"}${fxD != null ? (fxD < -0.5 ? " and unwinding" : fxD > 0.5 ? " and rebuilding" : "") : ""}, ` +
    `and the loan-to-deposit ratio sits at ${pct(l)}.`;

  return { asOf: period, headline, items };
}

/** Asset Quality — "is the credit good — where is deterioration concentrated?" */
export function assetQualityInsights(d: {
  npl: SeriesPoint[]; // sector NPL ratio, monthly (BDDK published basis)
  coverage: SeriesPoint[]; // provisions / gross NPL
  grossNpl: SeriesPoint[]; // weekly NPL stock level
  cardsNpl: SeriesPoint[]; // consumer cards NPL ratio
  smeNpl: SeriesPoint[]; // SME NPL ratio
  stage2?: SeriesPoint[]; // sector Stage-2 share of gross loans (audited quarterly)
  /** The audited staging ladder — the iceberg the ratio does not print. */
  ladder?: {
    stage2Share: number;
    stage3Share: number;
    problemShare: number;
    cov2: number;
    cov3: number;
    multipleOfPrinted: number;
    period: string;
  } | null;
  /** The latest audited NPL roll-forward year. */
  roll?: { additions: number; exits: number; net: number; collectionShare: number; year: string } | null;
  formationMultiple?: number | null;
}): TabTakeaway {
  const period = asOf(d.npl);
  const items: Insight[] = [];

  const n = last(d.npl);
  const nD = deltaPp(d.npl);
  const L = d.ladder ?? null;

  // Lead with the iceberg: what the ratio prints is the tip. NOT with the ratio's
  // level, which reads "benign" and is the misreading this tab exists to prevent.
  if (L) {
    items.push({
      text:
        `The ratio prints Stage 3 — ${pct(L.stage3Share)} of the book. Loans the banks themselves ` +
        `classify as deteriorated are ${pct(L.problemShare)}, ${L.multipleOfPrinted.toFixed(1)}× as much (${L.period}).`,
      tone: L.multipleOfPrinted >= 3 ? "warn" : "neutral",
    });
    items.push({
      text:
        `The Stage-2 watchlist is ${pct(L.stage2Share)} of loans at ${pct(L.cov2)} cover, against ` +
        `Stage 3 at ${pct(L.cov3)} — lower cover is expected on a book that is not impaired, but it is where the next NPLs come from.`,
      tone: L.cov2 < L.cov3 / 5 ? "warn" : "neutral",
    });
  }

  // The pipeline, and the mechanism — because the obvious suspicion (the ratio is
  // being written off) is FALSE, and saying so is worth an item.
  if (d.roll && d.formationMultiple) {
    const r = d.roll;
    items.push({
      text:
        `NPL formation ran ${d.formationMultiple.toFixed(1)}× the prior year in ${r.year} ` +
        `(net +₺${Math.round(r.net)}bn), and exits are ${r.collectionShare.toFixed(0)}% collections — ` +
        `not write-offs or sales. The book is genuinely deteriorating; the ratio is not being managed down.`,
      tone: r.net > 0 && d.formationMultiple >= 1.5 ? "warn" : "neutral",
    });
  }

  const g = growthOver(d.grossNpl, 52);
  if (g != null) {
    // "is growing X% y/y" would have read "growing −8.0%" on a shrinking stock.
    const gw = direction(g, VERBS.size, { flat: 1, sharp: Number.POSITIVE_INFINITY });
    items.push({
      text: `${
        gw === VERBS.size.flat
          ? "The NPL stock is flat y/y"
          : `The NPL stock ${gw} ${pct(Math.abs(g))} y/y`
      } — the ratio is a slow summary of a fast-moving stock.`,
      tone: g > 60 ? "warn" : "neutral",
    });
  }

  if (n != null) {
    // "— rising, but slowly" was typed beside a computed delta, so an EASING NPL
    // read "2.61% (−0.08pp m/m) — rising, but slowly." The band is the nuance:
    // inside it, "rising"; beyond it, "climbing".
    const move = direction(nD, VERBS.trend, { flat: 0.03, sharp: 0.1 });
    items.push({
      text: `The published NPL ratio is ${pct(n, 2)}${nD != null ? ` (${ppStr(nD)} m/m)` : ""}${
        move ? ` — ${move}` : ""
      }.`,
      tone: nD != null && nD > 0.05 ? "warn" : "neutral",
    });
  }

  const c = last(d.coverage);
  const cD = deltaPp(d.coverage);
  if (c != null) {
    items.push({
      text: `Provision coverage ${pct(c)} of gross NPL${cD != null ? ` (${ppStr(cD)} m/m)` : ""}${cD != null && cD < -0.3 ? " — slipping as the book seasons" : ""}.`,
      tone: cD != null && cD < -0.3 ? "warn" : "neutral",
    });
  }

  const cards = last(d.cardsNpl);
  const sme = last(d.smeNpl);
  if (cards != null || sme != null) {
    const worst =
      cards != null && (sme == null || cards >= sme)
        ? { name: "retail cards", v: cards }
        : { name: "SME", v: sme as number };
    items.push({
      text: `Stress is concentrated in ${worst.name} (${pct(worst.v, 2)} NPL)${cards != null && sme != null ? ` — vs ${pct(Math.min(cards, sme), 2)} for ${cards >= sme ? "SME" : "retail cards"}` : ""}.`,
      tone: n != null && worst.v > 2 * n ? "warn" : "neutral",
      href: "/credit",
    });
  }

  const headline = L
    ? `The ${pct(n, 2)} NPL ratio is the tip: loans classified as deteriorated are ${pct(L.problemShare)}, ` +
      `${L.multipleOfPrinted.toFixed(1)}× what the headline prints, and ${pct(L.stage2Share)} of the book sits on a ` +
      `watchlist carrying ${pct(L.cov2)} cover` +
      (d.roll && d.formationMultiple
        ? ` — with formation running ${d.formationMultiple.toFixed(1)}× and exits that are collections, not write-offs.`
        : ".")
    : `Headline NPLs at ${pct(n, 2)} with coverage at ${pct(c)}${cD != null && cD < -0.3 ? " and slipping" : ""}; ` +
      `the audited staging ladder — where the next NPLs come from — is not yet available.`;

  return { asOf: period, headline, items };
}

/** Capital — "can the sector absorb losses — buffer over the minimum, and why moving?" */
export function capitalInsights(d: {
  car: SeriesPoint[]; // sector CAR, monthly
  cet1: SeriesPoint[]; // audited quarterly sector CET1 (may lag)
  equityYoY: SeriesPoint[];
  leverage: SeriesPoint[]; // liabilities / equity, sector
  /** Sector asset growth y/y — the cycle equity has to keep pace WITH. */
  assetsYoY?: SeriesPoint[];
}): TabTakeaway {
  const period = asOf(d.car);
  const items: Insight[] = [];

  const car = last(d.car);
  const carD = deltaPp(d.car);
  const buffer = car != null ? car - CAR_MIN : null;
  if (car != null && buffer != null) {
    items.push({
      text: `CAR ${pct(car)} — a ${buffer.toFixed(1)}pp buffer over the ${CAR_MIN}% minimum${carD != null ? ` (${ppStr(carD)} m/m)` : ""}.`,
      tone: buffer < 2 ? "warn" : buffer >= 4 ? "positive" : "neutral",
    });
  }

  const cet1 = last(d.cet1);
  if (cet1 != null) {
    items.push({
      text: `CET1 — the loss-absorbing core — at ${pct(cet1)} (audited quarterly); the CAR-to-CET1 spread is AT1/Tier-2 reliance.`,
      tone: "neutral",
    });
  }

  // The balance-sheet cycle was a TYPED constant ("a ~40% nominal cycle") with the
  // thresholds 30 and 25 pinned to it. It is a series we already hold: as nominal
  // growth cools with CPI, the hardcoded version drifts into nonsense ("equity
  // compounding 28% keeps pace with a ~40% cycle"). Compare against the cycle
  // itself and all three magic numbers go away.
  const eq = last(d.equityYoY);
  const bs = d.assetsYoY ? last(d.assetsYoY) : null;
  if (eq != null) {
    items.push({
      text:
        bs == null
          ? `Equity is compounding ${pct(eq)} y/y — the generation side of the ratio.`
          : `Equity is compounding ${pct(eq)} y/y — capital generation ${
              eq >= bs ? "keeps pace with" : "trails"
            } the ${pct(bs)} nominal balance-sheet cycle.`,
      tone: bs != null && eq < bs ? "warn" : "neutral",
      href: "/profitability",
    });
  }

  const lev = last(d.leverage);
  const levD = deltaPp(d.leverage);
  if (lev != null) {
    items.push({
      text: `Gearing at ${(lev / 100).toFixed(1)}× equity${levD != null && levD > 10 ? " and rising" : ""}.`,
      tone: "neutral",
    });
  }

  const headline =
    `The sector holds a ${buffer != null ? buffer.toFixed(1) : "—"}pp buffer over the ${CAR_MIN}% minimum (CAR ${pct(car)}` +
    `${cet1 != null ? `, CET1 ${pct(cet1)}` : ""}); the question is whether ${pct(eq)} equity growth keeps funding the balance sheet.`;

  return { asOf: period, headline, items };
}

/** Profitability — "is the sector earning its cost of capital — and what drives it?" */
export function profitabilityInsights(d: {
  roe: SeriesPoint[]; // sector, annualized
  roa: SeriesPoint[];
  nim: SeriesPoint[];
  opex: SeriesPoint[]; // OPEX / avg assets
  cpi: SeriesPoint[]; // CPI YoY 12m avg (may be empty)
}): TabTakeaway {
  const period = asOf(d.roe);
  const items: Insight[] = [];

  const roe = last(d.roe);
  const cpi = last(d.cpi);
  const real = roe != null && cpi != null ? roe - cpi : null;
  if (roe != null) {
    items.push({
      text: `ROE ${pct(roe)} nominal${real != null ? ` — ${real >= 0 ? "+" : ""}${real.toFixed(1)}pp vs 12m-avg CPI, so ${real > 5 ? "solidly positive" : real > 0 ? "barely positive" : "negative"} in real terms` : ""}.`,
      tone: real != null && real < 0 ? "warn" : real != null && real > 5 ? "positive" : "neutral",
    });
  }

  const nim = last(d.nim);
  const nimD = deltaPp(d.nim);
  if (nim != null) {
    items.push({
      text: `NIM ${pct(nim, 2)}${nimD != null ? ` (${ppStr(nimD)} m/m — margins ${nimD > 0.05 ? "widening as funding reprices down" : nimD < -0.05 ? "compressing" : "flat"})` : ""}.`,
      tone: nimD != null && nimD > 0.05 ? "positive" : nimD != null && nimD < -0.05 ? "warn" : "neutral",
      href: "/rates",
    });
  }

  const roa = last(d.roa);
  if (roa != null) {
    items.push({ text: `ROA ${pct(roa, 2)} — the leverage-free read on the same earnings.`, tone: "neutral" });
  }

  const opex = last(d.opex);
  const opexD = deltaPp(d.opex);
  if (opex != null) {
    items.push({
      text: `Operating cost ${pct(opex, 2)} of assets${opexD != null ? ` (${opexD <= 0 ? "improving" : "deteriorating"} ${ppStr(opexD)} m/m)` : ""} — inflation passes through wages with a lag.`,
      tone: opexD != null && opexD > 0.05 ? "warn" : "neutral",
    });
  }

  const headline =
    `The sector earns ${pct(roe)} on equity — ${real != null ? (real > 5 ? "comfortably above" : real > 0 ? "roughly at" : "below") : "vs"} inflation` +
    `${real != null ? ` (${real >= 0 ? "+" : ""}${real.toFixed(1)}pp real)` : ""} — ` +
    `with NIM at ${pct(nim, 2)}${nimD != null && nimD > 0.05 ? " and widening" : nimD != null && nimD < -0.05 ? " and compressing" : ""}.`;

  return { asOf: period, headline, items };
}

/** Liquidity — "can the sector fund itself — TL/FC pressure, CBRT backdrop, Basel buffers?" */
export function liquidityInsights(d: {
  tlLdrPublic: SeriesPoint[];
  tlLdrPrivate: SeriesPoint[];
  dollarization: SeriesPoint[]; // sector FC share of deposits
  netCbrtFunding: SeriesPoint[]; // million TL; + = excess per page convention
  lcr: SeriesPoint[]; // audited quarterly sector LCR (may lag)
}): TabTakeaway {
  const period = asOf(d.tlLdrPublic) ?? asOf(d.dollarization);
  const items: Insight[] = [];

  const pub = last(d.tlLdrPublic);
  const priv = last(d.tlLdrPrivate);
  if (pub != null && priv != null) {
    const worst = Math.max(pub, priv);
    items.push({
      text: `TL loan-to-deposit: public ${pct(pub, 0)} vs private ${pct(priv, 0)} — ${worst > 100 ? "the TL book is more than fully lent" : "the TL book is fully funded by deposits"}.`,
      tone: worst > 110 ? "warn" : "neutral",
    });
  }

  const doll = last(d.dollarization);
  const dollD = deltaOver(d.dollarization, 52);
  if (doll != null) {
    items.push({
      text: `FC deposits ${pct(doll)} of the base${dollD != null ? ` (${ppStr(dollD)} y/y)` : ""} — dollarization is the system's structural funding risk.`,
      tone: dollD != null && dollD > 1 ? "warn" : dollD != null && dollD < -1 ? "positive" : "neutral",
      href: "/deposits",
    });
  }

  const lcr = last(d.lcr);
  if (lcr != null) {
    items.push({
      text: `LCR ${pct(lcr, 0)} (audited quarterly) — ${lcr >= 150 ? "a wide" : lcr >= 110 ? "an adequate" : "a thin"} cushion over the 100% floor.`,
      tone: lcr < 110 ? "warn" : lcr >= 150 ? "positive" : "neutral",
    });
  }

  const fund = last(d.netCbrtFunding);
  if (fund != null) {
    items.push({
      text: `Net CBRT funding ₺${Math.abs(fund / 1000).toFixed(0)}bn ${fund >= 0 ? "surplus — the system parks TL at the central bank" : "shortfall — the system leans on CBRT for TL"}.`,
      tone: "neutral",
      href: "/rates",
    });
  }

  const headline =
    `Funding is ${pub != null && priv != null && Math.max(pub, priv) > 110 ? "tight" : "manageable"}: TL loan-to-deposit ${pct(priv, 0)} (private) / ${pct(pub, 0)} (public), ` +
    `FC deposits ${pct(doll)} of the base${lcr != null ? `, and LCR at ${pct(lcr, 0)}` : ""}.`;

  return { asOf: period, headline, items };
}

/** Market Risk — "how exposed is the sector to rate and FX shocks?" */
export function marketRiskInsights(d: {
  nop: SeriesPoint[]; // FX net open position / capital, %
  gap1y: SeriesPoint[]; // cumulative ≤1y repricing gap / assets, %
}): TabTakeaway {
  const period = asOf(d.nop) ?? asOf(d.gap1y);
  const items: Insight[] = [];

  const nop = last(d.nop);
  if (nop != null) {
    items.push({
      text: `FX net open position ${nop >= 0 ? "+" : ""}${nop.toFixed(1)}% of capital — ${Math.abs(nop) < 5 ? "small and well inside the ±20% limit; direct FX risk is hedged" : "a live currency exposure"} (net ${nop >= 0 ? "long" : "short"}).`,
      tone: Math.abs(nop) > 10 ? "warn" : "neutral",
    });
  }

  const gap = last(d.gap1y);
  if (gap != null) {
    items.push({
      text:
        gap < 0
          ? `The ≤1y repricing gap is ${gap.toFixed(1)}% of assets — liabilities reprice first, so falling rates lift NII; the exposure is an easing-cycle stall.`
          : `The ≤1y repricing gap is +${gap.toFixed(1)}% of assets — assets reprice first, so NII compresses as rates fall.`,
      tone: "neutral",
      href: "/rates",
    });
  }

  const headline =
    `Direct FX risk is ${nop != null && Math.abs(nop) < 5 ? "small" : "material"} (NOP ${nop != null ? `${nop >= 0 ? "+" : ""}${nop.toFixed(1)}%` : "—"} of capital); ` +
    `the real sensitivity is rates — ${gap != null && gap < 0 ? "a negative repricing gap gears earnings to the easing cycle continuing" : "an asset-sensitive book"}.`;

  return { asOf: period, headline, items };
}
