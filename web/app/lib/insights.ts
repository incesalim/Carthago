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
import { seriesFinding } from "./chart-findings";

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

// 12% is BDDK's TARGET ratio, not the statutory minimum (8%) — this was
// `CAR_MIN`, commented "BDDK regulatory minimum". See capital-thresholds.ts.
import { CAR_TARGET } from "./capital-thresholds";

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
  const buffer = car != null ? car - CAR_TARGET : null;
  items.push({
    text: `Capital adequacy ${pct(car)}${buffer != null ? ` — ${buffer.toFixed(1)}pp above the ${CAR_TARGET}% target ratio` : ""}${carD != null ? ` (${ppStr(carD)} m/m)` : ""}.`,
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
    // TL+FC, because that is what the published ratio measures. The link goes to
    // /liquidity, where the TL-only book is read — a different, hotter number, so
    // the sentence has to say which one it is quoting. See lib/ldr.ts.
    text: `Loan-to-deposit (TL+FC) ${pct(ldr)} — funding ${ldr != null && ldr > 110 ? "stretched" : "comfortable"}.`,
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
      // "easing" here meant the GAP, while everywhere else it means a series
      // falling — one word doing two jobs, which makes the direction unreadable
      // (and the regime-flip gate unable to tell a bug from a coincidence).
      // A gap narrows; a rate eases.
      text: `Deposits growing ${pct(dy)} y/y${gap != null ? ` — ${gap >= 0 ? "ahead of" : "behind"} loans by ${Math.abs(gap).toFixed(1)}pp, so the funding gap is ${gap >= 0 ? "narrowing" : "widening"}` : ""}.`,
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
      text: `Loan-to-deposit (TL+FC, published) at ${pct(l)} — ${l > 110 ? "stretched; growth leans on non-deposit funding" : l > 95 ? "fully lent" : "comfortable"}.`,
      tone: l > 110 ? "warn" : "neutral",
      href: "/liquidity",
    });
  }

  const headline =
    `Deposits are growing ${pct(dy)} y/y${ly != null && dy != null ? ` (loans ${pct(ly)})` : ""}, ` +
    `FX share ${fx != null ? `at ${pct(fx)}` : "—"}${fxD != null ? (fxD < -0.5 ? " and unwinding" : fxD > 0.5 ? " and rebuilding" : "") : ""}, ` +
    `and the published TL+FC loan-to-deposit ratio sits at ${pct(l)}.`;

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
  const buffer = car != null ? car - CAR_TARGET : null;
  if (car != null && buffer != null) {
    items.push({
      text: `CAR ${pct(car)} — a ${buffer.toFixed(1)}pp buffer over the ${CAR_TARGET}% target ratio${carD != null ? ` (${ppStr(carD)} m/m)` : ""}.`,
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
    `The sector holds a ${buffer != null ? buffer.toFixed(1) : "—"}pp buffer over the ${CAR_TARGET}% target ratio (CAR ${pct(car)}` +
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

// ───────────────────────────────────────────────────────────── the economy ──

/*
 * The macro builders. Same contract as the sector ones above, and registered in
 * the same regime-flip gate: every directional word arrives from `direction()`
 * or from `seriesFinding()` (which is itself built on it), never typed.
 *
 * Two habits these six keep that the sector builders did not have to:
 *
 *   A GAP GETS NO DIRECTION WORD. Every input in the gate's fixture is the SAME
 *   monotone ramp, so every derived spread is CONSTANT — the fixture cannot give
 *   a gap a direction to contradict, which means a gap sentence is exactly where
 *   an unchecked directional word would survive the gate. Gaps here are phrased
 *   structurally ("sits 4.1pp above"), never as "widening"/"compressing".
 *
 *   A LEVEL READ GOES THROUGH `seriesFinding`. It already owns the sentence
 *   shape, the scale-aware verb bands and the null guard, so a macro level read
 *   and a chart headline for the same series cannot word themselves differently.
 */

/** A level read, or null — `seriesFinding` with the macro defaults. */
const levelRead = (
  s: SeriesPoint[],
  noun: string,
  decimals = 1,
  window = 12,
  windowLabel?: string,
): string | null =>
  seriesFinding(s, { noun, decimals, window, windowLabel });

/** "+4.1pp" / "−4.1pp" — a gap, stated without a direction verb. */
const gapPp = (v: number, d = 1): string =>
  `${Math.abs(v).toFixed(d)}pp ${v >= 0 ? "above" : "below"}`;

/** Economy — "what backdrop are the banks operating in?" */
export function economyInsights(d: {
  cpi: SeriesPoint[]; // headline CPI y/y, monthly
  exp12m: SeriesPoint[]; // market participants' 12m-ahead expectation
  funding: SeriesPoint[]; // CBRT effective cost of funding, monthly avg
  realRate: SeriesPoint[]; // ex-ante real funding rate
  gdp: SeriesPoint[]; // GDP y/y, quarterly
  unemployment: SeriesPoint[]; // SA %
  caPctGdp: SeriesPoint[]; // 12m current account, % of GDP
  usdtry: SeriesPoint[]; // MONTHLY average — a daily array would misread the lag
  budgetPctGdp: SeriesPoint[]; // 12m general-budget balance, % of GDP
  importCover?: number | null; // months of imports gross reserves cover
  ownReserves?: number | null; // net reserves excluding swaps, USD bn
}): TabTakeaway {
  const period = asOf(d.cpi);
  const items: Insight[] = [];

  // Prices — the level read, then where expectations sit against it. The gap is
  // the forward-looking half: a falling print with expectations anchored above
  // it is a different regime from the same print with expectations below.
  const cpiNow = last(d.cpi);
  const expNow = last(d.exp12m);
  const cpiLine = levelRead(d.cpi, "Consumer inflation");
  if (cpiLine) {
    const expClause =
      cpiNow != null && expNow != null
        ? ` — the market's 12m-ahead expectation sits ${gapPp(expNow - cpiNow)} it`
        : "";
    items.push({ text: `${cpiLine}${expClause}.`, tone: "neutral", href: "/economy/inflation" });
  }

  // Policy — the nominal cost of funding, and whether it clears expected prices.
  // The sign of the ex-ante real rate is the single most consequential macro fact
  // for a bank's deposit book, so it gets its own sentence rather than a clause.
  const fundNow = last(d.funding);
  const realNow = last(d.realRate);
  if (fundNow != null) {
    items.push({
      text:
        `CBRT funding costs ${pct(fundNow)}` +
        (realNow != null
          ? ` — ${realNow >= 0 ? "positive" : "negative"} in real terms at ${realNow >= 0 ? "+" : "−"}${Math.abs(realNow).toFixed(1)}% against the 12m expectation.`
          : "."),
      tone: realNow != null && realNow < 0 ? "warn" : "neutral",
      href: "/rates",
    });
  }

  // Activity — output and the labour market in one line; they answer the same
  // question (is there demand for credit) from opposite ends.
  const gdpLine = levelRead(d.gdp, "GDP growth", 1, 4, "4 quarters");
  const unempNow = last(d.unemployment);
  if (gdpLine) {
    items.push({
      text: `${gdpLine}${unempNow != null ? `, with unemployment at ${pct(unempNow)}` : ""}.`,
      tone: "neutral",
      href: "/economy/economic-growth",
    });
  }

  // External — the deficit against the buffer that has to finance it.
  const caNow = last(d.caPctGdp);
  if (caNow != null) {
    const cover = d.importCover;
    items.push({
      text:
        `The current account runs ${Math.abs(caNow).toFixed(1)}% of GDP ${caNow >= 0 ? "in surplus" : "in deficit"}` +
        (cover != null ? `, against gross reserves covering ${cover.toFixed(1)} months of imports` : "") +
        ".",
      tone: caNow < -4 ? "warn" : "neutral",
      href: "/economy/balance-of-payments",
    });
  }

  // The lira — a 12-month move, on the monthly average so one volatile session
  // cannot set the read.
  const fxMove = growthOver(d.usdtry, 12);
  if (fxMove != null) {
    items.push({
      // Not "the lira weakened": the sentence names WHICH way the pair moved and
      // lets the reader hold the sign. A currency verb is where a flipped sign
      // reads as fluent English and passes review.
      text: `USD/TRY is ${Math.abs(fxMove).toFixed(1)}% ${fxMove >= 0 ? "higher" : "lower"} over 12 months — ${fxMove >= 0 ? "each dollar costs more lira" : "each dollar costs less lira"}.`,
      tone: "neutral",
    });
  }

  // Fiscal — the 12m general-budget balance. Named as the general budget because
  // the published headline most readers carry is the central-government one.
  const budNow = last(d.budgetPctGdp);
  if (budNow != null) {
    items.push({
      text: `The general budget runs ${Math.abs(budNow).toFixed(1)}% of GDP ${budNow >= 0 ? "in surplus" : "in deficit"} on a 12-month basis.`,
      tone: budNow < -5 ? "warn" : "neutral",
      href: "/economy/budget",
    });
  }

  const stance =
    realNow == null ? "unscored" : realNow >= 0 ? "restrictive in real terms" : "accommodative in real terms";
  const headline =
    `Policy is ${stance} — funding at ${pct(fundNow)} against ${pct(expNow)} expected inflation` +
    `, with prices at ${pct(cpiNow)} and output ${pct(last(d.gdp))} y/y` +
    `${caNow != null ? `, on a current account of ${Math.abs(caNow).toFixed(1)}% of GDP` : ""}.`;

  return { asOf: period, headline, items };
}

/** Inflation — "what is actually driving the price level, and is it broad?" */
export function inflationInsights(d: {
  cpi: SeriesPoint[]; // headline y/y
  core: SeriesPoint[]; // core-C y/y
  ppi: SeriesPoint[]; // producer prices y/y
  cpiMoM: SeriesPoint[]; // headline m/m
  exp12m: SeriesPoint[]; // 12m-ahead expectation
  /** Share of CPI groups whose m/m print is above the headline's — 0..100. */
  diffusion?: number | null;
  /** How many groups that share was computed over (never print a bare share). */
  diffusionOf?: number | null;
}): TabTakeaway {
  const period = asOf(d.cpi);
  const items: Insight[] = [];

  const cpiLine = levelRead(d.cpi, "Headline CPI");
  if (cpiLine) items.push({ text: `${cpiLine}.`, tone: "neutral" });

  // Core against headline — the underlying read. Structural phrasing, no verb:
  // "core above headline" is a level comparison, not a direction.
  const coreNow = last(d.core);
  const cpiNow = last(d.cpi);
  if (coreNow != null && cpiNow != null) {
    items.push({
      text: `Core-C is ${pct(coreNow)}, ${gapPp(coreNow - cpiNow)} headline — the read with energy, food, alcohol-tobacco and gold stripped out.`,
      tone: coreNow > cpiNow ? "warn" : "neutral",
    });
  }

  // Producer prices — the cost-push pipeline into next year's consumer prints.
  const ppiNow = last(d.ppi);
  if (ppiNow != null && cpiNow != null) {
    items.push({
      text: `Producer prices run ${pct(ppiNow)}, ${gapPp(ppiNow - cpiNow)} consumer prices.`,
      tone: ppiNow > cpiNow + 5 ? "warn" : "neutral",
    });
  }

  // The monthly print — what the annual rate will be built from next.
  const mmLine = levelRead(d.cpiMoM, "The monthly print", 2);
  if (mmLine) items.push({ text: `${mmLine}.`, tone: "neutral" });

  // Breadth. A headline can fall on two or three groups while most of the basket
  // does nothing — the diffusion share is what separates the two cases, and it
  // always prints its denominator.
  if (d.diffusion != null && d.diffusionOf) {
    items.push({
      text: `${Math.round((d.diffusion / 100) * d.diffusionOf)} of ${d.diffusionOf} CPI groups printed a monthly rise above the headline's — the breadth behind the number.`,
      tone: d.diffusion > 60 ? "warn" : "neutral",
    });
  }

  const expNow = last(d.exp12m);
  if (expNow != null && cpiNow != null) {
    items.push({
      text: `The market expects ${pct(expNow)} twelve months out, ${gapPp(expNow - cpiNow)} today's print.`,
      tone: "neutral",
    });
  }

  const headline =
    `Headline CPI is ${pct(cpiNow)} with core-C at ${pct(coreNow)}` +
    `${ppiNow != null ? ` and producer prices at ${pct(ppiNow)}` : ""}` +
    `${expNow != null ? `; the market prices ${pct(expNow)} a year out` : ""}.`;

  return { asOf: period, headline, items };
}

/** Growth — "where is output coming from, and is it demand or net trade?" */
export function growthInsights(d: {
  gdp: SeriesPoint[]; // GDP y/y, quarterly
  ip: SeriesPoint[]; // industrial production y/y, monthly
  consumption: SeriesPoint[]; // household consumption y/y, quarterly
  investment: SeriesPoint[]; // GFCF y/y, quarterly
  exports: SeriesPoint[]; // exports y/y, quarterly
  imports: SeriesPoint[]; // imports y/y, quarterly
}): TabTakeaway {
  const period = asOf(d.gdp);
  const items: Insight[] = [];

  const gdpLine = levelRead(d.gdp, "GDP", 1, 4, "4 quarters");
  if (gdpLine) items.push({ text: `${gdpLine}.`, tone: "neutral" });

  const consLine = levelRead(d.consumption, "Household consumption", 1, 4, "4 quarters");
  if (consLine) items.push({ text: `${consLine} — the largest expenditure component.`, tone: "neutral" });

  const invLine = levelRead(d.investment, "Fixed investment", 1, 4, "4 quarters");
  if (invLine) items.push({ text: `${invLine}.`, tone: "neutral", href: "/credit" });

  // Net trade: exports against imports, as levels of growth. The CONTRIBUTION
  // needs the expenditure weights (the page computes those for its own chart);
  // here the two growth rates are compared without asserting a contribution.
  const ex = last(d.exports);
  const im = last(d.imports);
  if (ex != null && im != null) {
    items.push({
      text: `Exports grow ${pct(ex)} against imports at ${pct(im)} — real trade volumes, not the customs bill.`,
      tone: "neutral",
      href: "/economy/foreign-trade",
    });
  }

  const ipLine = levelRead(d.ip, "Industrial production");
  if (ipLine) items.push({ text: `${ipLine} — the monthly read between quarterly national accounts.`, tone: "neutral" });

  const headline =
    `Output runs ${pct(last(d.gdp))} y/y` +
    `${last(d.consumption) != null ? `, with household consumption at ${pct(last(d.consumption))}` : ""}` +
    `${last(d.investment) != null ? ` and fixed investment at ${pct(last(d.investment))}` : ""}.`;

  return { asOf: period, headline, items };
}

/** Balance of payments — "is the deficit financed, and by what quality of money?" */
export function bopInsights(d: {
  ca12m: SeriesPoint[]; // 12m current account, USD bn
  core12m: SeriesPoint[]; // 12m CA ex gold & energy, USD bn
  neo12m: SeriesPoint[]; // 12m net errors & omissions, USD bn
  fdi12m: SeriesPoint[]; // 12m net FDI liabilities incurred, USD bn
  portfolio12m: SeriesPoint[]; // 12m net portfolio liabilities incurred, USD bn
}): TabTakeaway {
  const period = asOf(d.ca12m);
  const items: Insight[] = [];

  const caNow = last(d.ca12m);
  const coreNow = last(d.core12m);
  if (caNow != null) {
    items.push({
      text:
        `The 12-month current account stands at $${Math.abs(caNow).toFixed(1)}bn ${caNow >= 0 ? "in surplus" : "in deficit"}` +
        (coreNow != null
          ? `; stripping gold and energy leaves $${Math.abs(coreNow).toFixed(1)}bn ${coreNow >= 0 ? "in surplus" : "in deficit"} — the structural read.`
          : "."),
      tone: caNow < -40 ? "warn" : "neutral",
    });
  }

  // Financing quality: FDI is the money that does not leave on a headline;
  // portfolio is the money that can. Both stated as levels, no direction verb.
  const fdi = last(d.fdi12m);
  const port = last(d.portfolio12m);
  if (fdi != null && port != null) {
    items.push({
      text: `Financing over 12 months: $${fdi.toFixed(1)}bn direct investment against $${port.toFixed(1)}bn portfolio — the first is committed capital, the second reprices daily.`,
      tone: "neutral",
    });
  }

  const neo = last(d.neo12m);
  if (neo != null) {
    items.push({
      text: `Net errors and omissions run $${Math.abs(neo).toFixed(1)}bn over 12 months — unidentified flows, ${Math.abs(neo) > 10 ? "large enough to matter to the financing story" : "small against the financing need"}.`,
      tone: Math.abs(neo) > 20 ? "warn" : "neutral",
    });
  }

  const caLine = levelRead(d.ca12m, "The 12-month balance", 1);
  if (caLine) items.push({ text: `${caLine} (USD bn).`, tone: "neutral" });

  const headline =
    `The 12-month current account is $${caNow != null ? Math.abs(caNow).toFixed(1) : "—"}bn ${caNow != null && caNow >= 0 ? "in surplus" : "in deficit"}` +
    `${fdi != null && port != null ? `, financed by $${fdi.toFixed(1)}bn of direct and $${port.toFixed(1)}bn of portfolio investment` : ""}.`;

  return { asOf: period, headline, items };
}

/** Budget — "what does the fiscal stance cost, in real terms?" */
export function budgetInsights(d: {
  balancePctGdp: SeriesPoint[]; // 12m budget balance, % of GDP
  primaryPctGdp: SeriesPoint[]; // 12m primary balance, % of GDP
  taxRealYoY: SeriesPoint[]; // tax revenue y/y, CPI-DEFLATED
  expRealYoY: SeriesPoint[]; // primary expenditure y/y, CPI-DEFLATED
  interestShare: SeriesPoint[]; // interest expenditure as % of tax revenue
}): TabTakeaway {
  const period = asOf(d.balancePctGdp);
  const items: Insight[] = [];

  const bal = last(d.balancePctGdp);
  const prim = last(d.primaryPctGdp);
  if (bal != null) {
    items.push({
      text:
        `The 12-month budget balance is ${Math.abs(bal).toFixed(1)}% of GDP ${bal >= 0 ? "in surplus" : "in deficit"}` +
        (prim != null
          ? `; before interest, ${Math.abs(prim).toFixed(1)}% ${prim >= 0 ? "in surplus" : "in deficit"}.`
          : "."),
      tone: bal < -5 ? "warn" : "neutral",
    });
  }

  // Real, not nominal. At a ~30% price level a nominal revenue line is mostly a
  // chart of the deflator (DESIGN.md: every nominal ₺ level ships with its real
  // twin), and "tax revenues up 28%" is a real CUT nobody would read as one.
  const taxLine = levelRead(d.taxRealYoY, "Real tax revenue", 1);
  if (taxLine) items.push({ text: `${taxLine}, CPI-deflated.`, tone: "neutral" });

  const expLine = levelRead(d.expRealYoY, "Real primary spending", 1);
  if (expLine) items.push({ text: `${expLine}, CPI-deflated.`, tone: "neutral" });

  const int = last(d.interestShare);
  if (int != null) {
    items.push({
      text: `Interest takes ${pct(int)} of tax revenue — the claim on the budget before any policy choice is made.`,
      tone: int > 25 ? "warn" : "neutral",
    });
  }

  const headline =
    `The budget runs ${bal != null ? Math.abs(bal).toFixed(1) : "—"}% of GDP ${bal != null && bal >= 0 ? "in surplus" : "in deficit"} over 12 months` +
    `${int != null ? `, with interest absorbing ${pct(int)} of tax revenue` : ""}.`;

  return { asOf: period, headline, items };
}

/** Foreign trade — "what does the goods gap cost, and how much is energy?" */
export function tradeInsights(d: {
  balance12m: SeriesPoint[]; // 12m trade balance, USD bn
  exEnergy12m: SeriesPoint[]; // 12m balance excluding energy, USD bn
  exports12m: SeriesPoint[]; // 12m exports, USD bn
  imports12m: SeriesPoint[]; // 12m imports, USD bn
  coverage: SeriesPoint[]; // exports ÷ imports, %
  terms: SeriesPoint[]; // terms of trade index
}): TabTakeaway {
  const period = asOf(d.balance12m);
  const items: Insight[] = [];

  const bal = last(d.balance12m);
  const exEn = last(d.exEnergy12m);
  if (bal != null) {
    const energy = exEn != null ? bal - exEn : null;
    items.push({
      text:
        `The 12-month goods balance is $${Math.abs(bal).toFixed(1)}bn ${bal >= 0 ? "in surplus" : "in deficit"}` +
        (energy != null ? `, of which $${Math.abs(energy).toFixed(1)}bn is the energy bill.` : "."),
      tone: "neutral",
    });
  }

  const covLine = levelRead(d.coverage, "Export cover of imports", 1);
  if (covLine) items.push({ text: `${covLine} — how much of the import bill exports pay for.`, tone: "neutral" });

  const exp = last(d.exports12m);
  const imp = last(d.imports12m);
  if (exp != null && imp != null) {
    items.push({
      text: `Exports run $${exp.toFixed(0)}bn against imports of $${imp.toFixed(0)}bn on trailing-12-month sums.`,
      tone: "neutral",
    });
  }

  const termsLine = levelRead(d.terms, "Terms of trade", 1);
  if (termsLine) {
    items.push({
      text: `${termsLine} — export prices against import prices, so a higher index buys more imports per unit exported.`,
      tone: "neutral",
    });
  }

  const headline =
    `The goods gap is $${bal != null ? Math.abs(bal).toFixed(1) : "—"}bn over 12 months` +
    `${exEn != null && bal != null ? `, $${Math.abs(bal - exEn).toFixed(1)}bn of it energy` : ""}` +
    `${last(d.coverage) != null ? `, with exports covering ${pct(last(d.coverage))} of imports` : ""}.`;

  return { asOf: period, headline, items };
}
