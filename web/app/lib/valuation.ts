/**
 * Bank equity valuation & scenario projection — PURE MATH (no React, no D1).
 *
 * Why a standalone module: the /valuation page recomputes a bank's fair value
 * live in the browser as the user drags assumption sliders, so the maths must be
 * a synchronous pure function with no I/O. It is also unit-tested in isolation
 * (valuation.test.ts) and shared by the server (peer ranking) and the client.
 *
 * Conventions
 *  • All rates/ratios are FRACTIONS (0.30 = 30%), never percentage points.
 *  • Book/income amounts are THOUSAND TL — the unit the audit tables and
 *    bankFundamentals use. Convert to a per-share TL figure only at the edge
 *    (× 1000 ÷ shares), mirroring bist.ts (equityTL = equity × 1000).
 *  • Everything is NOMINAL TRY. DCF/FCF is inappropriate for banks (leverage is
 *    regulated, not a policy choice), so we use equity-side models: the residual
 *    (excess-return) income model, a two-stage dividend discount model, and the
 *    warranted price-to-book identity. The value driver throughout is the spread
 *    of return over the cost of equity (ROE − COE), which is broadly invariant
 *    to the nominal inflation level — the relevant caveat for Turkish banks is
 *    TAS-29 hyperinflation restatement of the book itself, surfaced in the UI.
 */

// ---------------------------------------------------------------------------
// Inputs
// ---------------------------------------------------------------------------

/** CAPM build-up for the cost of equity, nominal TRY. */
export interface CoeInputs {
  /** Risk-free rate (TRY proxy — CBRT funding / gov bond), fraction. */
  rf: number;
  /** Equity risk premium, fraction. */
  erp: number;
  /** Levered equity beta vs the local index (XU100). */
  beta: number;
  /** Optional extra country / idiosyncratic premium on top of β·ERP, fraction. */
  crp?: number;
}

/** A full, serializable scenario the client can build from a preset + edits. */
export interface Assumptions {
  // --- seeded starting state (from the audited filing + market) -------------
  /** Current period-end book equity, thousand TL. */
  b0: number;
  /** Starting return on equity (TTM), fraction. */
  roe0: number;
  /** Shares outstanding (count) — for per-share conversion. */
  shares: number;

  // --- cost of equity -------------------------------------------------------
  coe: CoeInputs;

  // --- payout / growth ------------------------------------------------------
  /** Dividend payout ratio, fraction. Drives sustainable growth + DDM. */
  payout: number;

  // --- residual income (multi-stage) ---------------------------------------
  /** Explicit forecast horizon, whole years. */
  horizon: number;
  /** Terminal (steady-state) ROE the explicit path fades to, fraction. */
  roeFadeTo: number;
  /** Terminal perpetual growth g_T, fraction. */
  terminalGrowth: number;
  /**
   * Ohlson abnormal-earnings persistence ω ∈ [0,1].
   *  ω = 0 → terminal residual income is a Gordon growing perpetuity at g_T.
   *  ω > 0 → residual income decays geometrically (AR(1)): the steady spread
   *          earns less each year, a conservative alternative to perpetual g_T.
   */
  persistence: number;

  // --- dividend discount model ---------------------------------------------
  /** DDM stage-1 length, whole years. */
  ddmStage1Years: number;
  /** DDM stage-1 dividend growth g1, fraction (stage 2 reverts to terminalGrowth). */
  ddmStage1Growth: number;
}

// ---------------------------------------------------------------------------
// Outputs
// ---------------------------------------------------------------------------

/** One projected year of the residual-income roll-forward. */
export interface ProjectionYear {
  year: number;
  /** Book equity at the start of the year, thousand TL. */
  beginBook: number;
  roe: number;
  /** Net income = ROE × beginBook, thousand TL. */
  netIncome: number;
  dividend: number;
  retained: number;
  endBook: number;
  /** Residual income = (ROE − COE) × beginBook, thousand TL. */
  residualIncome: number;
  discountFactor: number;
  pvResidualIncome: number;
}

export interface ValuationResult {
  coe: number;
  /** Sustainable growth from the STARTING ROE, g = roe0 × (1 − payout). */
  sustainableGrowth: number;
  /** Warranted P/B from the steady-state inputs (terminal ROE & g_T). */
  justifiedPB: number | null;
  /** Warranted P/B if the CURRENT ROE were sustainable (roe0 & its g). */
  justifiedPBCurrent: number | null;

  /** Residual-income intrinsic equity value, thousand TL. */
  fairValueRI: number;
  /** Sum of PV of explicit-horizon residual income, thousand TL. */
  sumPvExplicit: number;
  /** Terminal value at the horizon, thousand TL. */
  terminalValueRI: number;
  /** PV of the terminal value, thousand TL. */
  pvTerminalRI: number;
  /** RI intrinsic value ÷ current book — the fade-aware implied P/B. */
  impliedPB: number | null;

  /** Two-stage DDM intrinsic equity value, thousand TL. */
  fairValueDDM: number;

  /** Per-share fair values, TL (null when shares ≤ 0). */
  perShareRI: number | null;
  perShareDDM: number | null;

  path: ProjectionYear[];
  warnings: string[];
}

// ---------------------------------------------------------------------------
// Core formulas
// ---------------------------------------------------------------------------

/** CAPM cost of equity, nominal TRY: COE = rf + β·ERP + CRP. */
export function costOfEquity(c: CoeInputs): number {
  return c.rf + c.beta * c.erp + (c.crp ?? 0);
}

/** Sustainable growth g = ROE × retention = ROE × (1 − payout). */
export function sustainableGrowth(roe: number, payout: number): number {
  return roe * (1 - payout);
}

/**
 * Warranted price-to-book from the Gordon residual-income identity:
 *   P/B = (ROE − g) / (COE − g).
 * Returns null when COE ≤ g (the perpetuity diverges — value is unbounded);
 * the caller surfaces "n/a" with the reason.
 */
export function justifiedPB(roe: number, g: number, coe: number): number | null {
  if (!(coe > g)) return null;
  return (roe - g) / (coe - g);
}

/**
 * Linear ROE fade: a straight glide from roe0 (t=0 baseline) to roeFadeTo at
 * t = horizon. Returns the ROE earned in year t (1-based), so year `horizon`
 * earns exactly roeFadeTo.
 */
export function fadedRoe(roe0: number, roeFadeTo: number, t: number, horizon: number): number {
  if (horizon <= 0) return roeFadeTo;
  return roe0 + (roeFadeTo - roe0) * (t / horizon);
}

/**
 * Clean-surplus book roll-forward over the explicit horizon. Net income accrues
 * at the faded ROE on opening book; dividends pay out `payout`; the rest is
 * retained (B_t = B_{t-1} + retained). Residual income (ROE − COE)·B_{t-1} is
 * discounted at COE.
 */
export function projectPath(a: Assumptions, coe: number): ProjectionYear[] {
  const path: ProjectionYear[] = [];
  let beginBook = a.b0;
  for (let t = 1; t <= a.horizon; t++) {
    const roe = fadedRoe(a.roe0, a.roeFadeTo, t, a.horizon);
    const netIncome = roe * beginBook;
    const dividend = a.payout * netIncome;
    const retained = netIncome - dividend;
    const endBook = beginBook + retained;
    const residualIncome = (roe - coe) * beginBook;
    const discountFactor = 1 / Math.pow(1 + coe, t);
    path.push({
      year: t,
      beginBook,
      roe,
      netIncome,
      dividend,
      retained,
      endBook,
      residualIncome,
      discountFactor,
      pvResidualIncome: residualIncome * discountFactor,
    });
    beginBook = endBook;
  }
  return path;
}

// ---------------------------------------------------------------------------
// Orchestrator
// ---------------------------------------------------------------------------

/**
 * Full valuation for one scenario. Computes the cost of equity once, rolls the
 * book forward over the explicit horizon, then values the terminal phase two
 * ways (residual income + DDM) and the warranted P/B. Every divergent case
 * (COE ≤ g, no shares, non-positive book) degrades to null + a warning rather
 * than a misleading number.
 */
export function runValuation(a: Assumptions): ValuationResult {
  const warnings: string[] = [];
  const coe = costOfEquity(a.coe);
  const gT = a.terminalGrowth;

  if (!(a.b0 > 0)) warnings.push("Book equity is not positive — valuation is undefined.");
  if (coe <= 0) warnings.push("Cost of equity is not positive — check the CAPM inputs.");

  // --- Residual income ------------------------------------------------------
  const path = projectPath(a, coe);
  const sumPvExplicit = path.reduce((s, y) => s + y.pvResidualIncome, 0);
  const last = path[path.length - 1];
  const bookH = last ? last.endBook : a.b0;
  const dfH = last ? 1 / Math.pow(1 + coe, a.horizon) : 1;

  let terminalValueRI = 0;
  // First terminal-phase residual income, earned on the end-of-horizon book at
  // the steady-state spread (roeFadeTo − COE).
  const riTerminal = (a.roeFadeTo - coe) * bookH;
  if (a.persistence > 0) {
    // Ohlson AR(1): RI_{H+k} = ω^k · RI_{H+1}. Continuing value at H is the
    // geometric sum Σ_{k≥1} ω^{k-1}·RI_{H+1}/(1+COE)^k = RI_{H+1} / (1 + COE − ω).
    terminalValueRI = riTerminal / (1 + coe - a.persistence);
  } else if (coe > gT) {
    // Gordon growing perpetuity of residual income at g_T.
    terminalValueRI = riTerminal / (coe - gT);
  } else {
    warnings.push("Residual income: cost of equity ≤ terminal growth — terminal value omitted (would be unbounded).");
  }
  const pvTerminalRI = terminalValueRI * dfH;
  const fairValueRI = a.b0 + sumPvExplicit + pvTerminalRI;

  // --- Two-stage DDM --------------------------------------------------------
  const d0 = a.roe0 * a.b0 * a.payout; // last actual dividend, thousand TL
  let pvDiv = 0;
  let dN = d0;
  for (let t = 1; t <= a.ddmStage1Years; t++) {
    dN = d0 * Math.pow(1 + a.ddmStage1Growth, t);
    pvDiv += dN / Math.pow(1 + coe, t);
  }
  let fairValueDDM = pvDiv;
  if (coe > gT) {
    const tvN = (dN * (1 + gT)) / (coe - gT); // terminal value at year N
    fairValueDDM += tvN / Math.pow(1 + coe, a.ddmStage1Years);
  } else {
    warnings.push("DDM: cost of equity ≤ terminal growth — terminal value omitted (would be unbounded).");
  }

  // --- Warranted P/B --------------------------------------------------------
  const gCurrent = sustainableGrowth(a.roe0, a.payout);
  const justifiedPBCurrent = justifiedPB(a.roe0, gCurrent, coe);
  const justifiedPBTerminal = justifiedPB(a.roeFadeTo, gT, coe);

  // --- Per share ------------------------------------------------------------
  const perShare = (valueThousandTL: number): number | null =>
    a.shares > 0 ? (valueThousandTL * 1000) / a.shares : null;

  return {
    coe,
    sustainableGrowth: gCurrent,
    justifiedPB: justifiedPBTerminal,
    justifiedPBCurrent,
    fairValueRI,
    sumPvExplicit,
    terminalValueRI,
    pvTerminalRI,
    impliedPB: a.b0 > 0 ? fairValueRI / a.b0 : null,
    fairValueDDM,
    perShareRI: perShare(fairValueRI),
    perShareDDM: perShare(fairValueDDM),
    path,
    warnings,
  };
}

// ---------------------------------------------------------------------------
// Peer regression (P/B on ROE) — the analyst "relative value" workhorse
// ---------------------------------------------------------------------------

export interface PeerPoint {
  ticker: string;
  /** Forecast / current ROE, fraction. */
  roe: number;
  /** Observed price-to-book, multiple. */
  pb: number;
}

export interface PbRoeRegression {
  slope: number;
  intercept: number;
  /** Coefficient of determination, 0..1. */
  r2: number;
  n: number;
  /** Fitted P/B for a given ROE. */
  predict: (roe: number) => number;
}

/**
 * Ordinary-least-squares fit of P/B on ROE across a peer set. The residual
 * (actual − fitted) ranks a bank rich/cheap vs how its ROE "should" price.
 * Returns null when fewer than two points or ROE has no spread.
 */
export function regressPbOnRoe(points: PeerPoint[]): PbRoeRegression | null {
  const n = points.length;
  if (n < 2) return null;
  const xs = points.map((p) => p.roe);
  const ys = points.map((p) => p.pb);
  const mx = mean(xs);
  const my = mean(ys);
  let sxx = 0;
  let sxy = 0;
  let syy = 0;
  for (let i = 0; i < n; i++) {
    const dx = xs[i] - mx;
    const dy = ys[i] - my;
    sxx += dx * dx;
    sxy += dx * dy;
    syy += dy * dy;
  }
  if (sxx === 0) return null;
  const slope = sxy / sxx;
  const intercept = my - slope * mx;
  const r2 = syy === 0 ? 1 : (sxy * sxy) / (sxx * syy);
  return { slope, intercept, r2, n, predict: (roe: number) => intercept + slope * roe };
}

// ---------------------------------------------------------------------------
// Stats helpers (also drive the equity-beta computation in valuation-data.ts)
// ---------------------------------------------------------------------------

export function mean(xs: number[]): number {
  if (xs.length === 0) return 0;
  return xs.reduce((s, x) => s + x, 0) / xs.length;
}

/** Sample variance (÷ n−1). */
export function variance(xs: number[]): number {
  const n = xs.length;
  if (n < 2) return 0;
  const m = mean(xs);
  return xs.reduce((s, x) => s + (x - m) * (x - m), 0) / (n - 1);
}

/** Sample covariance (÷ n−1). x and y must be the same length. */
export function covariance(xs: number[], ys: number[]): number {
  const n = Math.min(xs.length, ys.length);
  if (n < 2) return 0;
  const mx = mean(xs.slice(0, n));
  const my = mean(ys.slice(0, n));
  let s = 0;
  for (let i = 0; i < n; i++) s += (xs[i] - mx) * (ys[i] - my);
  return s / (n - 1);
}

export interface BetaFit {
  /** Slope of y on x — the beta. */
  beta: number;
  alpha: number;
  r2: number;
  n: number;
}

/**
 * OLS regression of y on x → beta = cov(y,x)/var(x). For an equity beta pass
 * y = bank returns, x = index (XU100) returns. The n−1 in cov and var cancels.
 * Returns null with fewer than two paired observations or no variance in x.
 */
export function linregBeta(y: number[], x: number[]): BetaFit | null {
  const n = Math.min(x.length, y.length);
  if (n < 2) return null;
  const vx = variance(x.slice(0, n));
  if (vx === 0) return null;
  const beta = covariance(y.slice(0, n), x.slice(0, n)) / vx;
  const alpha = mean(y.slice(0, n)) - beta * mean(x.slice(0, n));
  const vy = variance(y.slice(0, n));
  const corr = vy === 0 ? 0 : covariance(y.slice(0, n), x.slice(0, n)) / Math.sqrt(vx * vy);
  return { beta, alpha, r2: corr * corr, n };
}
