/**
 * The regime-flip gate.
 *
 * A 2026-07 audit found 41 sentences on the dashboard that asserted a direction
 * and never checked it. The worst of them did not merely go stale — they said the
 * OPPOSITE of the chart beneath them the moment the data turned: "rising, but
 * slowly" beside a falling NPL; "The NPL stock is growing −8.0% y/y".
 *
 * Fixing the 41 is not the same as stopping the 42nd. So: feed every insight
 * builder a fixture in which EVERY series rises, and assert that not one falling
 * word comes out. Then invert it.
 *
 * The test is decisive because it reads the OUTPUT TEXT, not the code path — it
 * does not care whether a word arrived from `direction()` or was typed into a
 * template literal. A directional word that does not move with its data fails
 * here, however it got there.
 *
 * It passes now. It FAILED on the code as it stood before this lane
 * (insights.ts's "— rising, but slowly" survives a falling NPL), which is the
 * evidence that it is a gate and not ceremony.
 */
import { describe, expect, it } from "vitest";
import { DOWN_WORDS, UP_WORDS } from "./prose";
import {
  assetQualityInsights,
  capitalInsights,
  creditInsights,
  depositsInsights,
  liquidityInsights,
  marketRiskInsights,
  overviewInsights,
  profitabilityInsights,
  type SeriesPoint,
  type TabTakeaway,
} from "./insights";

// Directional words the sentences use that are NOT in the closed VERBS vocabulary
// (they come from guarded ternaries). Included on purpose: a guarded word passes,
// an unguarded one fails, and that is exactly the distinction under test.
//
// Every word here must describe the direction of a SERIES. Words about a derived
// gap or spread are out of scope: a uniform ramp leaves every difference at zero,
// so the fixture cannot give them a direction to contradict. (This is why
// "easing" had to stop meaning "the funding gap narrows" in insights.ts — one
// word cannot mean a falling rate in one sentence and a closing gap in another
// and still be checkable.)
const EXTRA_UP = ["creeping up", "accelerating", "gaining", "widening", "deteriorating"];
const EXTRA_DOWN = ["easing", "cooling", "losing", "compressing", "slipping", "receding"];

const UP = [...UP_WORDS, ...EXTRA_UP];
const DOWN = [...DOWN_WORDS, ...EXTRA_DOWN];

/** 24 monthly points, monotone. `sign` = +1 rising, −1 falling. */
function ramp(sign: 1 | -1, { start = 20, step = 0.6 } = {}): SeriesPoint[] {
  return Array.from({ length: 24 }, (_, i) => {
    const m = (i % 12) + 1;
    const y = 2024 + Math.floor(i / 12);
    return {
      period: `${y}-${String(m).padStart(2, "0")}`,
      value: start + sign * step * i,
    };
  });
}

const say = (t: TabTakeaway): string =>
  [t.headline, ...t.items.map((i) => i.text)].join(" · ").toLowerCase();

const hits = (text: string, words: readonly string[]): string[] =>
  words.filter((w) => new RegExp(`\\b${w}\\b`).test(text));

/**
 * Every builder, fed the SAME monotone series on every input. Semantics don't
 * matter — the direction does. A rising world must produce no falling word.
 */
function allTabs(sign: 1 | -1): Array<[string, TabTakeaway]> {
  const s = ramp(sign);
  // Start low so a falling ramp stays positive, and vice-versa — we are testing
  // the words, not the null guards.
  const lo = ramp(sign, { start: 40, step: 0.6 });

  return [
    [
      "overview",
      overviewInsights({
        assetsYoY: s, loansYoY: s, depositsYoY: s, npl: s, car: lo, ldr: s, roe: s,
      }),
    ],
    [
      "credit",
      creditInsights({
        yoy: s, mom4: s, yoyState: s, yoyPrivate: s, fxShare: s, cardsYoY: s, smeYoY: s,
      }),
    ],
    [
      "deposits",
      depositsInsights({ yoy: s, loansYoY: s, fxShare: s, demandShare: s, ldr: s }),
    ],
    [
      "assetQuality",
      assetQualityInsights({
        npl: s, coverage: s, grossNpl: s, cardsNpl: s, smeNpl: s, stage2: s,
      }),
    ],
    [
      "capital",
      capitalInsights({ car: lo, cet1: lo, equityYoY: s, leverage: s, assetsYoY: s }),
    ],
    [
      "profitability",
      profitabilityInsights({ roe: s, roa: s, nim: s, opex: s, cpi: s }),
    ],
    [
      "liquidity",
      liquidityInsights({
        tlLdrPublic: s, tlLdrPrivate: s, dollarization: s, netCbrtFunding: s, lcr: lo,
      }),
    ],
    ["marketRisk", marketRiskInsights({ nop: s, gap1y: s })],
  ];
}

describe("regime flip — no sentence may contradict its data", () => {
  it.each(allTabs(1))("%s: says nothing about falling when everything RISES", (_name, t) => {
    expect(hits(say(t), DOWN)).toEqual([]);
  });

  it.each(allTabs(-1))("%s: says nothing about rising when everything FALLS", (_name, t) => {
    expect(hits(say(t), UP)).toEqual([]);
  });

  it("actually produces sentences — a silent builder would pass vacuously", () => {
    for (const [name, t] of allTabs(1)) {
      expect(t.items.length, `${name} produced no items`).toBeGreaterThan(0);
      expect(t.headline.length, `${name} produced no headline`).toBeGreaterThan(10);
    }
  });

  it("has a vocabulary to check — an empty word list would pass vacuously", () => {
    expect(UP.length).toBeGreaterThan(5);
    expect(DOWN.length).toBeGreaterThan(5);
    expect(UP.filter((w) => DOWN.includes(w))).toEqual([]);
  });
});
