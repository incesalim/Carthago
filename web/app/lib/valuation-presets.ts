/**
 * Base / Bull / Bear scenario presets for the /valuation tool.
 *
 * A preset patches a *scenario* (cost-of-equity shape, payout, ROE fade,
 * terminal growth) onto a bank's *seeded* starting state (current book, TTM ROE,
 * shares). The starting point is fixed reality; scenarios differ in where the
 * franchise fades to and how it is discounted. Defaults are anchored to Turkish
 * listed-bank reality circa 2026 — nominal TTM ROE ~28–30%, payouts 30–40% under
 * BRSA caps, a CBRT funding-rate-driven cost of equity in the low 30s%, terminal
 * nominal growth in the high teens/low 20s tracking the disinflation path. The
 * base case anchors the risk-free leg to the LIVE seeded rate (CBRT funding);
 * bull/bear shift it by plausible policy deltas.
 */
import type { Assumptions } from "./valuation";

export type ScenarioKey = "base" | "bull" | "bear";

/** The minimum seeded state a preset needs (resolved, non-null). */
export interface PresetSeed {
  /** Current book equity, thousand TL. */
  b0: number;
  /** Starting TTM ROE, fraction. */
  roe0: number;
  /** Shares outstanding (count). */
  shares: number;
  /** Resolved equity beta (sector default already substituted if estimation failed). */
  beta: number;
  /** Live TRY risk-free proxy, fraction. */
  rf: number;
  /** Observed trailing payout (fraction) to seed the base case, when available. */
  payout?: number | null;
}

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

export const SCENARIO_LABELS: Record<ScenarioKey, string> = {
  base: "Base",
  bull: "Bull",
  bear: "Bear",
};

/** Build all three preset scenarios for a seeded bank. */
export function buildPresets(seed: PresetSeed): Record<ScenarioKey, Assumptions> {
  const core = { b0: seed.b0, roe0: seed.roe0, shares: seed.shares };
  const basePayout = clamp(seed.payout ?? 0.35, 0.1, 0.6);

  return {
    base: {
      ...core,
      coe: { rf: seed.rf, erp: 0.055, beta: seed.beta, crp: 0 },
      payout: basePayout,
      horizon: 5,
      roeFadeTo: 0.22,
      terminalGrowth: 0.2,
      persistence: 0,
      ddmStage1Years: 5,
      ddmStage1Growth: 0.24,
    },
    bull: {
      ...core,
      coe: { rf: Math.max(0.05, seed.rf - 0.06), erp: 0.05, beta: seed.beta, crp: 0 },
      payout: 0.3,
      horizon: 5,
      roeFadeTo: 0.26,
      terminalGrowth: 0.22,
      persistence: 0,
      ddmStage1Years: 5,
      ddmStage1Growth: 0.27,
    },
    bear: {
      ...core,
      coe: { rf: seed.rf + 0.07, erp: 0.07, beta: seed.beta, crp: 0.03 },
      payout: 0.4,
      horizon: 5,
      roeFadeTo: 0.16,
      terminalGrowth: 0.18,
      persistence: 0.2,
      ddmStage1Years: 5,
      ddmStage1Growth: 0.16,
    },
  };
}
