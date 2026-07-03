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
  yoy: SeriesPoint[]; // sector loan growth, 52w
  mom4: SeriesPoint[]; // 4w annualized momentum
  yoyState: SeriesPoint[];
  yoyPrivate: SeriesPoint[];
  fxShare: SeriesPoint[]; // weekly
  cardsYoY: SeriesPoint[];
  smeYoY: SeriesPoint[];
}): TabTakeaway {
  const period = asOf(d.yoy);
  const items: Insight[] = [];

  const y = last(d.yoy);
  const m4 = last(d.mom4);
  const pace =
    y != null && m4 != null ? (m4 > y + 2 ? "accelerating" : m4 < y - 2 ? "cooling" : "steady") : null;
  if (y != null) {
    items.push({
      text: `Loan growth ${pct(y)} y/y${m4 != null ? `; the 4-week pace (${pct(m4)}) says the trend is ${pace}` : ""}.`,
      tone: "neutral",
    });
  }

  const st = last(d.yoyState);
  const pr = last(d.yoyPrivate);
  if (st != null && pr != null) {
    const gap = st - pr;
    const leader = gap >= 0 ? "State" : "Private";
    items.push({
      text: `${leader} banks lead the lending cycle — ${pct(Math.max(st, pr))} vs ${pct(Math.min(st, pr))} y/y (${ppStr(Math.abs(gap))} gap).`,
      tone: Math.abs(gap) > 10 ? "warn" : "neutral",
    });
  }

  const fx = last(d.fxShare);
  const fxD = deltaOver(d.fxShare, 52);
  if (fx != null) {
    items.push({
      text: `FX loans are ${fxD != null && fxD > 0.3 ? "regaining" : fxD != null && fxD < -0.3 ? "losing" : "holding"} share of the book — ${pct(fx)} of total${fxD != null ? ` (${ppStr(fxD)} y/y)` : ""}.`,
      tone: fxD != null && fxD > 1 ? "warn" : "neutral",
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
    `Credit is growing ${pct(y)} y/y and ${pace ?? "—"}, led by ${st != null && pr != null && st >= pr ? "state" : "private"} banks; ` +
    `FX share of the book ${fx != null ? `at ${pct(fx)}` : "—"}${fxD != null ? (fxD < -0.3 ? " and falling" : fxD > 0.3 ? " and rising" : ", flat") : ""}.`;

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
  npl: SeriesPoint[]; // sector NPL ratio, monthly
  coverage: SeriesPoint[]; // provisions / gross NPL
  grossNpl: SeriesPoint[]; // weekly level
  cardsNpl: SeriesPoint[]; // consumer cards NPL ratio
  smeNpl: SeriesPoint[]; // SME NPL ratio
  stage2?: SeriesPoint[]; // sector Stage-2 share of gross loans (audited quarterly)
}): TabTakeaway {
  const period = asOf(d.npl);
  const items: Insight[] = [];

  const n = last(d.npl);
  const nD = deltaPp(d.npl);
  if (n != null) {
    items.push({
      text: `NPL ratio ${pct(n, 2)}${nD != null ? ` (${ppStr(nD)} m/m)` : ""} — ${n < 3 ? "low by Turkish cycle standards" : n < 5 ? "mid-cycle" : "elevated"}.`,
      tone: nD != null && nD > 0.05 ? "warn" : nD != null && nD < -0.05 ? "positive" : "neutral",
    });
  }

  const s2 = d.stage2 ? last(d.stage2) : null;
  const s2D = d.stage2 ? deltaPp(d.stage2) : null;
  if (s2 != null) {
    items.push({
      text: `Stage-2 loans — the pre-NPL watchlist — are ${pct(s2)} of the book${s2D != null ? ` (${ppStr(s2D)} q/q, ${s2D > 0.2 ? "migrating up" : s2D < -0.2 ? "easing" : "stable"})` : ""}.`,
      tone: s2D != null && s2D > 0.2 ? "warn" : s2D != null && s2D < -0.2 ? "positive" : "neutral",
    });
  }

  const g = growthOver(d.grossNpl, 52);
  if (g != null) {
    items.push({
      text: `The NPL stock is growing ${pct(g)} y/y — ${g > 40 ? "formation is running well ahead of the book" : "broadly with the book"} (ratios can stay flat while stock builds under 30%+ nominal loan growth).`,
      tone: g > 60 ? "warn" : "neutral",
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

  const headline =
    `Headline asset quality is ${n != null && n < 3 ? "still benign" : "under pressure"} — NPLs at ${pct(n, 2)} — ` +
    `with coverage at ${pct(c)}${cD != null && cD < -0.3 ? " and slipping" : ""}; ` +
    `the pockets to watch are ${cards != null && sme != null && cards >= sme ? "consumer cards" : "SME"} books.`;

  return { asOf: period, headline, items };
}

/** Capital — "can the sector absorb losses — buffer over the minimum, and why moving?" */
export function capitalInsights(d: {
  car: SeriesPoint[]; // sector CAR, monthly
  cet1: SeriesPoint[]; // audited quarterly sector CET1 (may lag)
  equityYoY: SeriesPoint[];
  leverage: SeriesPoint[]; // liabilities / equity, sector
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

  const eq = last(d.equityYoY);
  if (eq != null) {
    items.push({
      text: `Equity is compounding ${pct(eq)} y/y — capital generation ${eq > 30 ? "keeps pace with" : "trails"} a ~40% nominal balance-sheet cycle.`,
      tone: eq < 25 ? "warn" : "neutral",
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
