import { createText } from "../../i18n/text";
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
}, locale = "en"): TabTakeaway {
  const tx = createText(locale);
  const period = asOf(d.npl) ?? asOf(d.assetsYoY);
  const items: Insight[] = [];

  // Size & growth (A — volume)
  const ay = last(d.assetsYoY);
  const ly = last(d.loansYoY);
  const dy = last(d.depositsYoY);
  items.push({
    text: tx("Balance sheet {0} — assets {1} y/y, loans {2}, deposits {3}.", {0: ay != null && ay >= 0 ? "expanding" : "contracting", 1: pct(ay), 2: pct(ly), 3: pct(dy)}),
    tone: "neutral",
    href: "/credit",
  });

  // Asset quality (A)
  const npl = last(d.npl);
  const nplD = deltaPp(d.npl);
  items.push({
    text: tx("NPL ratio {0}{1}.", {0: pct(npl, 2), 1: nplD != null ? tx(" ({0} m/m, {1})", {0: ppStr(nplD), 1: nplD > 0.03 ? "creeping up" : nplD < -0.03 ? "easing" : "broadly stable"}) : ""}),
    tone: nplD != null && nplD > 0.03 ? "warn" : nplD != null && nplD < -0.03 ? "positive" : "neutral",
    href: "/asset-quality",
  });

  // Capital (C)
  const car = last(d.car);
  const carD = deltaPp(d.car);
  const buffer = car != null ? car - CAR_TARGET : null;
  items.push({
    text: tx("Capital adequacy {0}{1}{2}.", {0: pct(car), 1: buffer != null ? tx(" — {0}pp above the {1}% target ratio", {0: buffer.toFixed(1), 1: CAR_TARGET}) : "", 2: carD != null ? tx(" ({0} m/m)", {0: ppStr(carD)}) : ""}),
    tone: buffer != null && buffer < 2 ? "warn" : buffer != null && buffer >= 4 ? "positive" : "neutral",
    href: "/capital",
  });

  // Earnings (E)
  const roe = last(d.roe);
  const roeD = deltaPp(d.roe);
  items.push({
    text: tx("ROE {0} (annualized){1}.", {0: pct(roe), 1: roeD != null ? tx(", {0} {1}pp m/m", {0: roeD >= 0 ? "up" : "down", 1: Math.abs(roeD).toFixed(1)}) : ""}),
    tone: "neutral",
    href: "/profitability",
  });

  // Funding / liquidity (L)
  const ldr = last(d.ldr);
  items.push({
    // TL+FC, because that is what the published ratio measures. The link goes to
    // /liquidity, where the TL-only book is read — a different, hotter number, so
    // the sentence has to say which one it is quoting. See lib/ldr.ts.
    text: tx("Loan-to-deposit (TL+FC) {0} — funding {1}.", {0: pct(ldr), 1: ldr != null && ldr > 110 ? "stretched" : "comfortable"}),
    tone: ldr != null && ldr > 120 ? "warn" : "neutral",
    href: "/liquidity",
  });

  const grow = ay != null && ay >= 0 ? "growing" : "shrinking";
  const earn = roe != null && roe >= 0 ? "profitable" : "loss-making";
  const headline =
    tx("As of {0}: the sector is {1} (assets {2} y/y) and {3} (ROE {4}), ", {0: period ?? "—", 1: grow, 2: pct(ay), 3: earn, 4: pct(roe)}) +
    tx("with NPL at {0} and capital {1} the minimum at {2}.", {0: pct(npl, 2), 1: buffer != null && buffer >= 4 ? "comfortably above" : "above", 2: pct(car)});

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
}, locale = "en"): TabTakeaway {
  const tx = createText(locale);
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
        tx("Nominal credit grows {0} y/y — but strip the lira and the price level and the book ", {0: pct(y)}) +
        tx("{0} {1} in real, constant-FX terms.", {0: real < 0 ? "shrank" : "grew", 1: pct(Math.abs(real))}),
      tone: real < 0 ? "warn" : "neutral",
    });
    if (b?.currencyPp != null && b?.inflationPp != null) {
      items.push({
        text:
          tx("Of that {0} print, {1} is lira depreciation revaluing the FX book ", {0: pct(y), 1: ppStr(b.currencyPp)}) +
          tx("and {0} is inflation. What remains is real volume.", {0: ppStr(b.inflationPp)}),
        tone: "neutral",
      });
    }
  } else if (y != null) {
    items.push({
      text: tx("Loan growth {0} y/y (nominal){1}.", {0: pct(y), 1: m4 != null ? tx("; the 4-week pace ({0}) says the trend is {1}", {0: pct(m4), 1: pace}) : ""}),
      tone: "neutral",
    });
  }

  if (real != null && y != null && m4 != null) {
    items.push({
      text: tx("The 4-week pace ({0}) says the NOMINAL trend is {1} — on a book that is not growing in real terms.", {0: pct(m4), 1: pace}),
      tone: "neutral",
    });
  }

  const st = last(d.yoyState);
  const pr = last(d.yoyPrivate);
  if (st != null && pr != null) {
    items.push({
      text: tx("{0} banks lead the lending cycle — {1} vs {2} y/y ({3} gap).", {0: st >= pr ? "State" : "Private", 1: pct(Math.max(st, pr)), 2: pct(Math.min(st, pr)), 3: ppStr(Math.abs(st - pr))}),
      tone: "neutral",
    });
  }

  const fx = last(d.fxShare);
  const fxD = deltaPp(d.fxShare);
  if (fx != null) {
    items.push({
      text: tx("FX loans are {0} share of the book — {1} of total{2}.", {0: fxD != null && fxD < -0.3 ? "losing" : fxD != null && fxD > 0.3 ? "gaining" : "holding", 1: pct(fx), 2: fxD != null ? ` (${ppStr(fxD)})` : ""}),
      tone: "neutral",
    });
  }

  const cards = last(d.cardsYoY);
  const sme = last(d.smeYoY);
  if (cards != null && sme != null) {
    const tilt = cards > sme + 5 ? "consumer-led (cards)" : sme > cards + 5 ? "SME-led" : "broad-based";
    items.push({
      text: tx("The mix is {0}: retail cards {1} vs SME {2} y/y.", {0: tilt, 1: pct(cards), 2: pct(sme)}),
      tone: cards > sme + 15 ? "warn" : "neutral",
      href: "/asset-quality",
    });
  }

  const headline =
    real != null && y != null
      ? tx("The {0} loan-growth print is mostly lira and inflation: in real, constant-FX terms the book ", {0: pct(y)}) +
        `${real < 0 ? tx("shrank {0}", {0: pct(Math.abs(real))}) : tx("grew {0}", {0: pct(real)})}` +
        `${st != null && pr != null ? tx(", with {0} banks leading the cycle", {0: st >= pr ? "state" : "private"}) : ""}.`
      : tx("Credit is growing {0} y/y and {1}, led by {2} banks; ", {0: pct(y), 1: pace ?? "—", 2: st != null && pr != null && st >= pr ? "state" : "private"}) +
        tx("FX share of the book {0}.", {0: fx != null ? tx("at {0}", {0: pct(fx)}) : "—"});

  return { asOf: period, headline, items };
}

/** Deposits — "where is funding coming from — growing, sticky, dollarizing?" */
export function depositsInsights(d: {
  yoy: SeriesPoint[]; // sector deposit growth
  loansYoY: SeriesPoint[]; // sector loan growth (funding-gap read)
  fxShare: SeriesPoint[]; // dollarization
  demandShare: SeriesPoint[];
  ldr: SeriesPoint[]; // sector, monthly
}, locale = "en"): TabTakeaway {
  const tx = createText(locale);
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
      text: tx("Deposits growing {0} y/y{1}.", {0: pct(dy), 1: gap != null ? tx(" — {0} loans by {1}pp, so the funding gap is {2}", {0: gap >= 0 ? "ahead of" : "behind", 1: Math.abs(gap).toFixed(1), 2: gap >= 0 ? "narrowing" : "widening"}) : ""}),
      tone: gap != null && gap < -5 ? "warn" : gap != null && gap > 0 ? "positive" : "neutral",
    });
  }

  const fx = last(d.fxShare);
  const fxD = deltaOver(d.fxShare, 52);
  if (fx != null) {
    items.push({
      text: tx("Dollarization {0} — FX deposits {1} of total{2}.", {0: fxD != null ? (fxD < -0.5 ? "unwinding" : fxD > 0.5 ? "rebuilding" : "flat") : "", 1: pct(fx), 2: fxD != null ? tx(" ({0} y/y)", {0: ppStr(fxD)}) : ""}),
      tone: fxD != null && fxD < -0.5 ? "positive" : fxD != null && fxD > 1 ? "warn" : "neutral",
    });
  }

  const ds = last(d.demandShare);
  const dsD = deltaOver(d.demandShare, 52);
  if (ds != null) {
    items.push({
      text: tx("Demand deposits — the cheapest funding — are {0} of the base{1}.", {0: pct(ds), 1: dsD != null ? tx(" ({0} y/y)", {0: ppStr(dsD)}) : ""}),
      tone: dsD != null && dsD < -1 ? "warn" : "neutral",
    });
  }

  const l = last(d.ldr);
  if (l != null) {
    items.push({
      text: tx("Loan-to-deposit (TL+FC, published) at {0} — {1}.", {0: pct(l), 1: l > 110 ? "stretched; growth leans on non-deposit funding" : l > 95 ? "fully lent" : "comfortable"}),
      tone: l > 110 ? "warn" : "neutral",
      href: "/liquidity",
    });
  }

  const headline =
    tx("Deposits are growing {0} y/y{1}, ", {0: pct(dy), 1: ly != null && dy != null ? tx(" (loans {0})", {0: pct(ly)}) : ""}) +
    tx("FX share {0}{1}, ", {0: fx != null ? tx("at {0}", {0: pct(fx)}) : "—", 1: fxD != null ? (fxD < -0.5 ? " and unwinding" : fxD > 0.5 ? " and rebuilding" : "") : ""}) +
    tx("and the published TL+FC loan-to-deposit ratio sits at {0}.", {0: pct(l)});

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
}, locale = "en"): TabTakeaway {
  const tx = createText(locale);
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
        tx("The ratio prints Stage 3 — {0} of the book. Loans the banks themselves ", {0: pct(L.stage3Share)}) +
        tx("classify as deteriorated are {0}, {1}× as much ({2}).", {0: pct(L.problemShare), 1: L.multipleOfPrinted.toFixed(1), 2: L.period}),
      tone: L.multipleOfPrinted >= 3 ? "warn" : "neutral",
    });
    items.push({
      text:
        tx("The Stage-2 watchlist is {0} of loans at {1} cover, against ", {0: pct(L.stage2Share), 1: pct(L.cov2)}) +
        tx("Stage 3 at {0} — lower cover is expected on a book that is not impaired, but it is where the next NPLs come from.", {0: pct(L.cov3)}),
      tone: L.cov2 < L.cov3 / 5 ? "warn" : "neutral",
    });
  }

  // The pipeline, and the mechanism — because the obvious suspicion (the ratio is
  // being written off) is FALSE, and saying so is worth an item.
  if (d.roll && d.formationMultiple) {
    const r = d.roll;
    items.push({
      text:
        tx("NPL formation ran {0}× the prior year in {1} ", {0: d.formationMultiple.toFixed(1), 1: r.year}) +
        tx("(net +₺{0}bn), and exits are {1}% collections — ", {0: Math.round(r.net), 1: r.collectionShare.toFixed(0)}) +
        tx("not write-offs or sales. The book is genuinely deteriorating; the ratio is not being managed down."),
      tone: r.net > 0 && d.formationMultiple >= 1.5 ? "warn" : "neutral",
    });
  }

  const g = growthOver(d.grossNpl, 52);
  if (g != null) {
    // "is growing X% y/y" would have read "growing −8.0%" on a shrinking stock.
    const gw = direction(g, VERBS.size, { flat: 1, sharp: Number.POSITIVE_INFINITY });
    items.push({
      text: tx("{0} — the ratio is a slow summary of a fast-moving stock.", {0: gw === VERBS.size.flat
          ? "The NPL stock is flat y/y"
          : tx("The NPL stock {0} {1} y/y", {0: gw, 1: pct(Math.abs(g))})}),
      tone: g > 60 ? "warn" : "neutral",
    });
  }

  if (n != null) {
    // "— rising, but slowly" was typed beside a computed delta, so an EASING NPL
    // read "2.61% (−0.08pp m/m) — rising, but slowly." The band is the nuance:
    // inside it, "rising"; beyond it, "climbing".
    const move = direction(nD, VERBS.trend, { flat: 0.03, sharp: 0.1 });
    items.push({
      text: tx("The published NPL ratio is {0}{1}{2}.", {0: pct(n, 2), 1: nD != null ? tx(" ({0} m/m)", {0: ppStr(nD)}) : "", 2: move ? ` — ${move}` : ""}),
      tone: nD != null && nD > 0.05 ? "warn" : "neutral",
    });
  }

  const c = last(d.coverage);
  const cD = deltaPp(d.coverage);
  if (c != null) {
    items.push({
      text: tx("Provision coverage {0} of gross NPL{1}{2}.", {0: pct(c), 1: cD != null ? tx(" ({0} m/m)", {0: ppStr(cD)}) : "", 2: cD != null && cD < -0.3 ? " — slipping as the book seasons" : ""}),
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
      text: tx("Stress is concentrated in {0} ({1} NPL){2}.", {0: worst.name, 1: pct(worst.v, 2), 2: cards != null && sme != null ? tx(" — vs {0} for {1}", {0: pct(Math.min(cards, sme), 2), 1: cards >= sme ? "SME" : "retail cards"}) : ""}),
      tone: n != null && worst.v > 2 * n ? "warn" : "neutral",
      href: "/credit",
    });
  }

  const headline = L
    ? tx("The {0} NPL ratio is the tip: loans classified as deteriorated are {1}, ", {0: pct(n, 2), 1: pct(L.problemShare)}) +
      tx("{0}× what the headline prints, and {1} of the book sits on a ", {0: L.multipleOfPrinted.toFixed(1), 1: pct(L.stage2Share)}) +
      tx("watchlist carrying {0} cover", {0: pct(L.cov2)}) +
      (d.roll && d.formationMultiple
        ? tx(" — with formation running {0}× and exits that are collections, not write-offs.", {0: d.formationMultiple.toFixed(1)})
        : ".")
    : tx("Headline NPLs at {0} with coverage at {1}{2}; ", {0: pct(n, 2), 1: pct(c), 2: cD != null && cD < -0.3 ? " and slipping" : ""}) +
      tx("the audited staging ladder — where the next NPLs come from — is not yet available.");

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
}, locale = "en"): TabTakeaway {
  const tx = createText(locale);
  const period = asOf(d.car);
  const items: Insight[] = [];

  const car = last(d.car);
  const carD = deltaPp(d.car);
  const buffer = car != null ? car - CAR_TARGET : null;
  if (car != null && buffer != null) {
    items.push({
      text: tx("CAR {0} — a {1}pp buffer over the {2}% target ratio{3}.", {0: pct(car), 1: buffer.toFixed(1), 2: CAR_TARGET, 3: carD != null ? tx(" ({0} m/m)", {0: ppStr(carD)}) : ""}),
      tone: buffer < 2 ? "warn" : buffer >= 4 ? "positive" : "neutral",
    });
  }

  const cet1 = last(d.cet1);
  if (cet1 != null) {
    items.push({
      text: tx("CET1 — the loss-absorbing core — at {0} (audited quarterly); the CAR-to-CET1 spread is AT1/Tier-2 reliance.", {0: pct(cet1)}),
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
          ? tx("Equity is compounding {0} y/y — the generation side of the ratio.", {0: pct(eq)})
          : tx("Equity is compounding {0} y/y — capital generation {1} the {2} nominal balance-sheet cycle.", {0: pct(eq), 1: eq >= bs ? "keeps pace with" : "trails", 2: pct(bs)}),
      tone: bs != null && eq < bs ? "warn" : "neutral",
      href: "/profitability",
    });
  }

  const lev = last(d.leverage);
  const levD = deltaPp(d.leverage);
  if (lev != null) {
    items.push({
      text: tx("Gearing at {0}× equity{1}.", {0: (lev / 100).toFixed(1), 1: levD != null && levD > 10 ? " and rising" : ""}),
      tone: "neutral",
    });
  }

  const headline =
    tx("The sector holds a {0}pp buffer over the {1}% target ratio (CAR {2}", {0: buffer != null ? buffer.toFixed(1) : "—", 1: CAR_TARGET, 2: pct(car)}) +
    tx("{0}); the question is whether {1} equity growth keeps funding the balance sheet.", {0: cet1 != null ? tx(", CET1 {0}", {0: pct(cet1)}) : "", 1: pct(eq)});

  return { asOf: period, headline, items };
}

/** Profitability — "is the sector earning its cost of capital — and what drives it?" */
export function profitabilityInsights(d: {
  roe: SeriesPoint[]; // sector, annualized
  roa: SeriesPoint[];
  nim: SeriesPoint[];
  opex: SeriesPoint[]; // OPEX / avg assets
  cpi: SeriesPoint[]; // CPI YoY 12m avg (may be empty)
}, locale = "en"): TabTakeaway {
  const tx = createText(locale);
  const period = asOf(d.roe);
  const items: Insight[] = [];

  const roe = last(d.roe);
  const cpi = last(d.cpi);
  const real = roe != null && cpi != null ? roe - cpi : null;
  if (roe != null) {
    items.push({
      text: tx("ROE {0} nominal{1}.", {0: pct(roe), 1: real != null ? tx(" — {0}{1}pp vs 12m-avg CPI, so {2} in real terms", {0: real >= 0 ? "+" : "", 1: real.toFixed(1), 2: real > 5 ? "solidly positive" : real > 0 ? "barely positive" : "negative"}) : ""}),
      tone: real != null && real < 0 ? "warn" : real != null && real > 5 ? "positive" : "neutral",
    });
  }

  const nim = last(d.nim);
  const nimD = deltaPp(d.nim);
  if (nim != null) {
    items.push({
      text: tx("NIM {0}{1}.", {0: pct(nim, 2), 1: nimD != null ? tx(" ({0} m/m — margins {1})", {0: ppStr(nimD), 1: nimD > 0.05 ? "widening as funding reprices down" : nimD < -0.05 ? "compressing" : "flat"}) : ""}),
      tone: nimD != null && nimD > 0.05 ? "positive" : nimD != null && nimD < -0.05 ? "warn" : "neutral",
      href: "/rates",
    });
  }

  const roa = last(d.roa);
  if (roa != null) {
    items.push({ text: tx("ROA {0} — the leverage-free read on the same earnings.", {0: pct(roa, 2)}), tone: "neutral" });
  }

  const opex = last(d.opex);
  const opexD = deltaPp(d.opex);
  if (opex != null) {
    items.push({
      text: tx("Operating cost {0} of assets{1} — inflation passes through wages with a lag.", {0: pct(opex, 2), 1: opexD != null ? tx(" ({0} {1} m/m)", {0: opexD <= 0 ? "improving" : "deteriorating", 1: ppStr(opexD)}) : ""}),
      tone: opexD != null && opexD > 0.05 ? "warn" : "neutral",
    });
  }

  const headline =
    tx("The sector earns {0} on equity — {1} inflation", {0: pct(roe), 1: real != null ? (real > 5 ? "comfortably above" : real > 0 ? "roughly at" : "below") : "vs"}) +
    `${real != null ? tx(" ({0}{1}pp real)", {0: real >= 0 ? "+" : "", 1: real.toFixed(1)}) : ""} — ` +
    tx("with NIM at {0}{1}.", {0: pct(nim, 2), 1: nimD != null && nimD > 0.05 ? " and widening" : nimD != null && nimD < -0.05 ? " and compressing" : ""});

  return { asOf: period, headline, items };
}

/** Liquidity — "can the sector fund itself — TL/FC pressure, CBRT backdrop, Basel buffers?" */
export function liquidityInsights(d: {
  tlLdrPublic: SeriesPoint[];
  tlLdrPrivate: SeriesPoint[];
  dollarization: SeriesPoint[]; // sector FC share of deposits
  netCbrtFunding: SeriesPoint[]; // million TL; + = excess per page convention
  lcr: SeriesPoint[]; // audited quarterly sector LCR (may lag)
}, locale = "en"): TabTakeaway {
  const tx = createText(locale);
  const period = asOf(d.tlLdrPublic) ?? asOf(d.dollarization);
  const items: Insight[] = [];

  const pub = last(d.tlLdrPublic);
  const priv = last(d.tlLdrPrivate);
  if (pub != null && priv != null) {
    const worst = Math.max(pub, priv);
    items.push({
      text: tx("TL loan-to-deposit: public {0} vs private {1} — {2}.", {0: pct(pub, 0), 1: pct(priv, 0), 2: worst > 100 ? "the TL book is more than fully lent" : "the TL book is fully funded by deposits"}),
      tone: worst > 110 ? "warn" : "neutral",
    });
  }

  const doll = last(d.dollarization);
  const dollD = deltaOver(d.dollarization, 52);
  if (doll != null) {
    items.push({
      text: tx("FC deposits {0} of the base{1} — dollarization is the system's structural funding risk.", {0: pct(doll), 1: dollD != null ? tx(" ({0} y/y)", {0: ppStr(dollD)}) : ""}),
      tone: dollD != null && dollD > 1 ? "warn" : dollD != null && dollD < -1 ? "positive" : "neutral",
      href: "/deposits",
    });
  }

  const lcr = last(d.lcr);
  if (lcr != null) {
    items.push({
      text: tx("LCR {0} (audited quarterly) — {1} cushion over the 100% floor.", {0: pct(lcr, 0), 1: lcr >= 150 ? "a wide" : lcr >= 110 ? "an adequate" : "a thin"}),
      tone: lcr < 110 ? "warn" : lcr >= 150 ? "positive" : "neutral",
    });
  }

  const fund = last(d.netCbrtFunding);
  if (fund != null) {
    items.push({
      text: tx("Net CBRT funding ₺{0}bn {1}.", {0: Math.abs(fund / 1000).toFixed(0), 1: fund >= 0 ? "surplus — the system parks TL at the central bank" : "shortfall — the system leans on CBRT for TL"}),
      tone: "neutral",
      href: "/rates",
    });
  }

  const headline =
    tx("Funding is {0}: TL loan-to-deposit {1} (private) / {2} (public), ", {0: pub != null && priv != null && Math.max(pub, priv) > 110 ? "tight" : "manageable", 1: pct(priv, 0), 2: pct(pub, 0)}) +
    tx("FC deposits {0} of the base{1}.", {0: pct(doll), 1: lcr != null ? tx(", and LCR at {0}", {0: pct(lcr, 0)}) : ""});

  return { asOf: period, headline, items };
}

/** Market Risk — "how exposed is the sector to rate and FX shocks?" */
export function marketRiskInsights(d: {
  nop: SeriesPoint[]; // FX net open position / capital, %
  gap1y: SeriesPoint[]; // cumulative ≤1y repricing gap / assets, %
}, locale = "en"): TabTakeaway {
  const tx = createText(locale);
  const period = asOf(d.nop) ?? asOf(d.gap1y);
  const items: Insight[] = [];

  const nop = last(d.nop);
  if (nop != null) {
    items.push({
      text: tx("FX net open position {0}{1}% of capital — {2} (net {3}).", {0: nop >= 0 ? "+" : "", 1: nop.toFixed(1), 2: Math.abs(nop) < 5 ? "small and well inside the ±20% limit; direct FX risk is hedged" : "a live currency exposure", 3: nop >= 0 ? "long" : "short"}),
      tone: Math.abs(nop) > 10 ? "warn" : "neutral",
    });
  }

  const gap = last(d.gap1y);
  if (gap != null) {
    items.push({
      text:
        gap < 0
          ? tx("The ≤1y repricing gap is {0}% of assets — liabilities reprice first, so falling rates lift NII; the exposure is an easing-cycle stall.", {0: gap.toFixed(1)})
          : tx("The ≤1y repricing gap is +{0}% of assets — assets reprice first, so NII compresses as rates fall.", {0: gap.toFixed(1)}),
      tone: "neutral",
      href: "/rates",
    });
  }

  const headline =
    tx("Direct FX risk is {0} (NOP {1} of capital); ", {0: nop != null && Math.abs(nop) < 5 ? "small" : "material", 1: nop != null ? `${nop >= 0 ? "+" : ""}${nop.toFixed(1)}%` : "—"}) +
    tx("the real sensitivity is rates — {0}.", {0: gap != null && gap < 0 ? "a negative repricing gap gears earnings to the easing cycle continuing" : "an asset-sensitive book"});

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
  locale = "en",
): string | null =>
  seriesFinding(s, { noun, decimals, window, windowLabel }, locale);

/** "+4.1pp" / "−4.1pp" — a gap, stated without a direction verb. */
const gapPp = (v: number, d = 1, locale = "en"): string =>
  locale === "tr"
    ? `${Math.abs(v).toFixed(d)} yüzde puan ${v >= 0 ? "üzerinde" : "altında"}`
    : `${Math.abs(v).toFixed(d)}pp ${v >= 0 ? "above" : "below"}`;

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
}, locale = "en"): TabTakeaway {
  const tx = createText(locale);
  const period = asOf(d.cpi);
  const items: Insight[] = [];

  // Prices — the level read, then where expectations sit against it. The gap is
  // the forward-looking half: a falling print with expectations anchored above
  // it is a different regime from the same print with expectations below.
  const cpiNow = last(d.cpi);
  const expNow = last(d.exp12m);
  const cpiLine = levelRead(d.cpi, "Consumer inflation", undefined, undefined, undefined, locale);
  if (cpiLine) {
    const expClause =
      cpiNow != null && expNow != null
        ? tx(" — the market's 12m-ahead expectation sits {0} it", {0: gapPp(expNow - cpiNow, undefined, locale)})
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
        tx("CBRT funding costs {0}", {0: pct(fundNow)}) +
        (realNow != null
          ? tx(" — {0} in real terms at {1}{2}% against the 12m expectation.", {0: realNow >= 0 ? "positive" : "negative", 1: realNow >= 0 ? "+" : "−", 2: Math.abs(realNow).toFixed(1)})
          : "."),
      tone: realNow != null && realNow < 0 ? "warn" : "neutral",
      href: "/rates",
    });
  }

  // Activity — output and the labour market in one line; they answer the same
  // question (is there demand for credit) from opposite ends.
  const gdpLine = levelRead(d.gdp, "GDP growth", 1, 4, "4 quarters", locale);
  const unempNow = last(d.unemployment);
  if (gdpLine) {
    items.push({
      text: `${gdpLine}${unempNow != null ? tx(", with unemployment at {0}", {0: pct(unempNow)}) : ""}.`,
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
        tx("The current account runs {0}% of GDP {1}", {0: Math.abs(caNow).toFixed(1), 1: caNow >= 0 ? "in surplus" : "in deficit"}) +
        (cover != null ? tx(", against gross reserves covering {0} months of imports", {0: cover.toFixed(1)}) : "") +
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
      text: tx("USD/TRY is {0}% {1} over 12 months — {2}.", {0: Math.abs(fxMove).toFixed(1), 1: fxMove >= 0 ? "higher" : "lower", 2: fxMove >= 0 ? "each dollar costs more lira" : "each dollar costs less lira"}),
      tone: "neutral",
    });
  }

  // Fiscal — the 12m general-budget balance. Named as the general budget because
  // the published headline most readers carry is the central-government one.
  const budNow = last(d.budgetPctGdp);
  if (budNow != null) {
    items.push({
      text: tx("The general budget runs {0}% of GDP {1} on a 12-month basis.", {0: Math.abs(budNow).toFixed(1), 1: budNow >= 0 ? "in surplus" : "in deficit"}),
      tone: budNow < -5 ? "warn" : "neutral",
      href: "/economy/budget",
    });
  }

  const stance =
    realNow == null ? "unscored" : realNow >= 0 ? "restrictive in real terms" : "accommodative in real terms";
  const headline =
    tx("Policy is {0} — funding at {1} against {2} expected inflation", {0: stance, 1: pct(fundNow), 2: pct(expNow)}) +
    tx(", with prices at {0} and output {1} y/y", {0: pct(cpiNow), 1: pct(last(d.gdp))}) +
    `${caNow != null ? tx(", on a current account of {0}% of GDP", {0: Math.abs(caNow).toFixed(1)}) : ""}.`;

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
}, locale = "en"): TabTakeaway {
  const tx = createText(locale);
  const period = asOf(d.cpi);
  const items: Insight[] = [];

  const cpiLine = levelRead(d.cpi, "Headline CPI", undefined, undefined, undefined, locale);
  if (cpiLine) items.push({ text: `${cpiLine}.`, tone: "neutral" });

  // Core against headline — the underlying read. Structural phrasing, no verb:
  // "core above headline" is a level comparison, not a direction.
  const coreNow = last(d.core);
  const cpiNow = last(d.cpi);
  if (coreNow != null && cpiNow != null) {
    items.push({
      text: tx("Core-C is {0}, {1} headline — the read with energy, food, alcohol-tobacco and gold stripped out.", {0: pct(coreNow), 1: gapPp(coreNow - cpiNow, undefined, locale)}),
      tone: coreNow > cpiNow ? "warn" : "neutral",
    });
  }

  // Producer prices — the cost-push pipeline into next year's consumer prints.
  const ppiNow = last(d.ppi);
  if (ppiNow != null && cpiNow != null) {
    items.push({
      text: tx("Producer prices run {0}, {1} consumer prices.", {0: pct(ppiNow), 1: gapPp(ppiNow - cpiNow, undefined, locale)}),
      tone: ppiNow > cpiNow + 5 ? "warn" : "neutral",
    });
  }

  // The monthly print — what the annual rate will be built from next.
  const mmLine = levelRead(d.cpiMoM, "The monthly print", 2, undefined, undefined, locale);
  if (mmLine) items.push({ text: `${mmLine}.`, tone: "neutral" });

  // Breadth. A headline can fall on two or three groups while most of the basket
  // does nothing — the diffusion share is what separates the two cases, and it
  // always prints its denominator.
  if (d.diffusion != null && d.diffusionOf) {
    items.push({
      text: tx("{0} of {1} CPI groups printed a monthly rise above the headline's — the breadth behind the number.", {0: Math.round((d.diffusion / 100) * d.diffusionOf), 1: d.diffusionOf}),
      tone: d.diffusion > 60 ? "warn" : "neutral",
    });
  }

  const expNow = last(d.exp12m);
  if (expNow != null && cpiNow != null) {
    items.push({
      text: tx("The market expects {0} twelve months out, {1} today's print.", {0: pct(expNow), 1: gapPp(expNow - cpiNow, undefined, locale)}),
      tone: "neutral",
    });
  }

  const headline =
    tx("Headline CPI is {0} with core-C at {1}", {0: pct(cpiNow), 1: pct(coreNow)}) +
    `${ppiNow != null ? tx(" and producer prices at {0}", {0: pct(ppiNow)}) : ""}` +
    `${expNow != null ? tx("; the market prices {0} a year out", {0: pct(expNow)}) : ""}.`;

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
}, locale = "en"): TabTakeaway {
  const tx = createText(locale);
  const period = asOf(d.gdp);
  const items: Insight[] = [];

  const gdpLine = levelRead(d.gdp, "GDP", 1, 4, "4 quarters", locale);
  if (gdpLine) items.push({ text: `${gdpLine}.`, tone: "neutral" });

  const consLine = levelRead(d.consumption, "Household consumption", 1, 4, "4 quarters", locale);
  if (consLine) items.push({ text: tx("{0} — the largest expenditure component.", {0: consLine}), tone: "neutral" });

  const invLine = levelRead(d.investment, "Fixed investment", 1, 4, "4 quarters", locale);
  if (invLine) items.push({ text: `${invLine}.`, tone: "neutral", href: "/credit" });

  // Net trade: exports against imports, as levels of growth. The CONTRIBUTION
  // needs the expenditure weights (the page computes those for its own chart);
  // here the two growth rates are compared without asserting a contribution.
  const ex = last(d.exports);
  const im = last(d.imports);
  if (ex != null && im != null) {
    items.push({
      text: tx("Exports grow {0} against imports at {1} — real trade volumes, not the customs bill.", {0: pct(ex), 1: pct(im)}),
      tone: "neutral",
      href: "/economy/foreign-trade",
    });
  }

  const ipLine = levelRead(d.ip, "Industrial production", undefined, undefined, undefined, locale);
  if (ipLine) items.push({ text: tx("{0} — the monthly read between quarterly national accounts.", {0: ipLine}), tone: "neutral" });

  const headline =
    tx("Output runs {0} y/y", {0: pct(last(d.gdp))}) +
    `${last(d.consumption) != null ? tx(", with household consumption at {0}", {0: pct(last(d.consumption))}) : ""}` +
    `${last(d.investment) != null ? tx(" and fixed investment at {0}", {0: pct(last(d.investment))}) : ""}.`;

  return { asOf: period, headline, items };
}

/** Balance of payments — "is the deficit financed, and by what quality of money?" */
export function bopInsights(d: {
  ca12m: SeriesPoint[]; // 12m current account, USD bn
  core12m: SeriesPoint[]; // 12m CA ex gold & energy, USD bn
  neo12m: SeriesPoint[]; // 12m net errors & omissions, USD bn
  fdi12m: SeriesPoint[]; // 12m net FDI liabilities incurred, USD bn
  portfolio12m: SeriesPoint[]; // 12m net portfolio liabilities incurred, USD bn
}, locale = "en"): TabTakeaway {
  const tx = createText(locale);
  const period = asOf(d.ca12m);
  const items: Insight[] = [];

  const caNow = last(d.ca12m);
  const coreNow = last(d.core12m);
  if (caNow != null) {
    items.push({
      text:
        tx("The 12-month current account stands at ${0}bn {1}", {0: Math.abs(caNow).toFixed(1), 1: caNow >= 0 ? "in surplus" : "in deficit"}) +
        (coreNow != null
          ? tx("; stripping gold and energy leaves ${0}bn {1} — the structural read.", {0: Math.abs(coreNow).toFixed(1), 1: coreNow >= 0 ? "in surplus" : "in deficit"})
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
      text: tx("Financing over 12 months: ${0}bn direct investment against ${1}bn portfolio — the first is committed capital, the second reprices daily.", {0: fdi.toFixed(1), 1: port.toFixed(1)}),
      tone: "neutral",
    });
  }

  const neo = last(d.neo12m);
  if (neo != null) {
    items.push({
      text: tx("Net errors and omissions run ${0}bn over 12 months — unidentified flows, {1}.", {0: Math.abs(neo).toFixed(1), 1: Math.abs(neo) > 10 ? "large enough to matter to the financing story" : "small against the financing need"}),
      tone: Math.abs(neo) > 20 ? "warn" : "neutral",
    });
  }

  const caLine = levelRead(d.ca12m, "The 12-month balance", 1, undefined, undefined, locale);
  if (caLine) items.push({ text: tx("{0} (USD bn).", {0: caLine}), tone: "neutral" });

  const headline =
    tx("The 12-month current account is ${0}bn {1}", {0: caNow != null ? Math.abs(caNow).toFixed(1) : "—", 1: caNow != null && caNow >= 0 ? "in surplus" : "in deficit"}) +
    `${fdi != null && port != null ? tx(", financed by ${0}bn of direct and ${1}bn of portfolio investment", {0: fdi.toFixed(1), 1: port.toFixed(1)}) : ""}.`;

  return { asOf: period, headline, items };
}

/** Budget — "what does the fiscal stance cost, in real terms?" */
export function budgetInsights(d: {
  balancePctGdp: SeriesPoint[]; // 12m budget balance, % of GDP
  primaryPctGdp: SeriesPoint[]; // 12m primary balance, % of GDP
  taxRealYoY: SeriesPoint[]; // tax revenue y/y, CPI-DEFLATED
  expRealYoY: SeriesPoint[]; // primary expenditure y/y, CPI-DEFLATED
  interestShare: SeriesPoint[]; // interest expenditure as % of tax revenue
}, locale = "en"): TabTakeaway {
  const tx = createText(locale);
  const period = asOf(d.balancePctGdp);
  const items: Insight[] = [];

  const bal = last(d.balancePctGdp);
  const prim = last(d.primaryPctGdp);
  if (bal != null) {
    items.push({
      text:
        tx("The 12-month budget balance is {0}% of GDP {1}", {0: Math.abs(bal).toFixed(1), 1: bal >= 0 ? "in surplus" : "in deficit"}) +
        (prim != null
          ? tx("; before interest, {0}% {1}.", {0: Math.abs(prim).toFixed(1), 1: prim >= 0 ? "in surplus" : "in deficit"})
          : "."),
      tone: bal < -5 ? "warn" : "neutral",
    });
  }

  // Real, not nominal. At a ~30% price level a nominal revenue line is mostly a
  // chart of the deflator (DESIGN.md: every nominal ₺ level ships with its real
  // twin), and "tax revenues up 28%" is a real CUT nobody would read as one.
  const taxLine = levelRead(d.taxRealYoY, "Real tax revenue", 1, undefined, undefined, locale);
  if (taxLine) items.push({ text: tx("{0}, CPI-deflated.", {0: taxLine}), tone: "neutral" });

  const expLine = levelRead(d.expRealYoY, "Real primary spending", 1, undefined, undefined, locale);
  if (expLine) items.push({ text: tx("{0}, CPI-deflated.", {0: expLine}), tone: "neutral" });

  const int = last(d.interestShare);
  if (int != null) {
    items.push({
      text: tx("Interest takes {0} of tax revenue — the claim on the budget before any policy choice is made.", {0: pct(int)}),
      tone: int > 25 ? "warn" : "neutral",
    });
  }

  const headline =
    tx("The budget runs {0}% of GDP {1} over 12 months", {0: bal != null ? Math.abs(bal).toFixed(1) : "—", 1: bal != null && bal >= 0 ? "in surplus" : "in deficit"}) +
    `${int != null ? tx(", with interest absorbing {0} of tax revenue", {0: pct(int)}) : ""}.`;

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
}, locale = "en"): TabTakeaway {
  const tx = createText(locale);
  const period = asOf(d.balance12m);
  const items: Insight[] = [];

  const bal = last(d.balance12m);
  const exEn = last(d.exEnergy12m);
  if (bal != null) {
    const energy = exEn != null ? bal - exEn : null;
    items.push({
      text:
        tx("The 12-month goods balance is ${0}bn {1}", {0: Math.abs(bal).toFixed(1), 1: bal >= 0 ? "in surplus" : "in deficit"}) +
        (energy != null ? tx(", of which ${0}bn is the energy bill.", {0: Math.abs(energy).toFixed(1)}) : "."),
      tone: "neutral",
    });
  }

  const covLine = levelRead(d.coverage, "Export cover of imports", 1, undefined, undefined, locale);
  if (covLine) items.push({ text: tx("{0} — how much of the import bill exports pay for.", {0: covLine}), tone: "neutral" });

  const exp = last(d.exports12m);
  const imp = last(d.imports12m);
  if (exp != null && imp != null) {
    items.push({
      text: tx("Exports run ${0}bn against imports of ${1}bn on trailing-12-month sums.", {0: exp.toFixed(0), 1: imp.toFixed(0)}),
      tone: "neutral",
    });
  }

  const termsLine = levelRead(d.terms, "Terms of trade", 1, undefined, undefined, locale);
  if (termsLine) {
    items.push({
      text: tx("{0} — export prices against import prices, so a higher index buys more imports per unit exported.", {0: termsLine}),
      tone: "neutral",
    });
  }

  const headline =
    tx("The goods gap is ${0}bn over 12 months", {0: bal != null ? Math.abs(bal).toFixed(1) : "—"}) +
    `${exEn != null && bal != null ? tx(", ${0}bn of it energy", {0: Math.abs(bal - exEn).toFixed(1)}) : ""}` +
    `${last(d.coverage) != null ? tx(", with exports covering {0} of imports", {0: pct(last(d.coverage))}) : ""}.`;

  return { asOf: period, headline, items };
}
