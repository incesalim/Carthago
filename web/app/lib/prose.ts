/**
 * prose — the words, computed.
 *
 * The Desk's colophon promises "every figure computed from source series". That
 * was true of the figures and false of the sentences: a 2026-07 audit found 41
 * hand-typed claims asserting a direction, a level or a ranking with nothing
 * checking them — "Every ownership group fell together" off a step detector that
 * picks by |Δ|, "Real appreciation of −4.3", "+₺-42bn" when net NPL formation
 * turned (the *good* case), "rising, but slowly" beside a falling NPL.
 *
 * The root cause was one missing primitive: nothing turned a signed delta into a
 * direction WORD. The only verb logic in the repo was trapped inside
 * `seriesFinding` (chart-findings.ts), which now consumes `direction()` from here.
 *
 * Two rules this module exists to enforce:
 *
 *   1. A claim that the data does not support returns `null`, so the caller's
 *      `?? "Static topic"` prints the TOPIC rather than a finding. Failing closed
 *      is the whole contract — it is what `seriesFinding` already did, and what
 *      `hasOnlyKnownNumbers()` (read-headlines.ts) does to an LLM headline.
 *   2. The directional vocabulary is CLOSED (`VERBS` / `UP_WORDS` / `DOWN_WORDS`).
 *      That is not decoration: prose-regression.test.ts feeds every insight
 *      builder sign-inverted fixtures and asserts no DOWN word survives a rising
 *      series. The gate can only be decisive if the vocabulary is enumerable.
 *
 * `desk.ts` holds the facts (streaks, extremes, group spreads). This holds the
 * words. Pure + synchronous: no D1, no React — safe in server components and
 * unit tests.
 */

// ─────────────────────────────────────────────────────────── direction ──

export interface Bands {
  /** |Δ| under this reads as no move at all. */
  flat: number;
  /** |Δ| at or over this earns the stronger verb. */
  sharp: number;
}

export interface Words {
  up: string;
  down: string;
  flat: string;
  /** Optional stronger verbs; default to `up` / `down`. */
  upSharp?: string;
  downSharp?: string;
}

/**
 * Scale-aware bands, lifted from chart-findings.ts so a 2% series and a 200%
 * series both get an honest "flat". Under 0.15 absolute or 1% of the base reads
 * as flat; 1.0 absolute or 8% of the base earns the stronger verb.
 */
export function bandsFor(
  base: number,
  {
    flatMin = 0.15,
    flatPct = 0.01,
    sharpMin = 1.0,
    sharpPct = 0.08,
  }: { flatMin?: number; flatPct?: number; sharpMin?: number; sharpPct?: number } = {},
): Bands {
  const b = Math.abs(base);
  return {
    flat: Math.max(flatMin, b * flatPct),
    sharp: Math.max(sharpMin, b * sharpPct),
  };
}

/** Every value is its own band: any non-zero move has a direction, none is sharp. */
const EXACT: Bands = { flat: 0, sharp: Number.POSITIVE_INFINITY };

/**
 * A signed delta becomes a word. Never invents a sign: a null/NaN delta returns
 * null (the caller then says nothing rather than guessing).
 */
export function direction(
  delta: number | null | undefined,
  w: Words,
  b: Bands = EXACT,
): string | null {
  if (delta == null || Number.isNaN(delta)) return null;
  if (delta === 0 || Math.abs(delta) < b.flat) return w.flat;
  if (delta > 0) return delta >= b.sharp ? (w.upSharp ?? w.up) : w.up;
  return -delta >= b.sharp ? (w.downSharp ?? w.down) : w.down;
}

/**
 * The closed directional vocabulary. Every directional word the site generates
 * comes from one of these dictionaries — prose-regression.test.ts asserts it.
 * Adding a word here without adding it to a dictionary breaks nothing; typing a
 * directional word straight into a sentence is what the gate catches.
 */
export const VERBS = {
  /** "Capital adequacy eased to 16.4%" — the seriesFinding level read. */
  level: {
    flat: "holds at",
    up: "edged up to",
    upSharp: "climbed to",
    down: "eased to",
    downSharp: "fell to",
  },
  /** "Gearing keeps climbing" — a standing trend. */
  trend: {
    flat: "flat",
    up: "rising",
    upSharp: "climbing",
    down: "falling",
    downSharp: "sliding",
  },
  /** "The ratio rose 2.1pp" — a discrete move. */
  move: {
    flat: "held",
    up: "rose",
    upSharp: "jumped",
    down: "fell",
    downSharp: "dropped",
  },
  /** "Real appreciation of 4.3%" — the move as a noun. */
  noun: {
    flat: "stability",
    up: "appreciation",
    down: "depreciation",
  },
  /** "policy cuts reach deposit pricing first" — the rate cycle, named. */
  cycle: {
    flat: "holds",
    up: "hikes",
    down: "cuts",
  },
} as const satisfies Record<string, Words>;

const flatten = (pick: (w: Words) => (string | undefined)[]): readonly string[] =>
  [...new Set(Object.values(VERBS as Record<string, Words>).flatMap(pick))].filter(
    (s): s is string => !!s,
  );

/** Every word that asserts a rise. The regression gate regexes these. */
export const UP_WORDS: readonly string[] = flatten((w) => [w.up, w.upSharp]);
/** Every word that asserts a fall. */
export const DOWN_WORDS: readonly string[] = flatten((w) => [w.down, w.downSharp]);

// ─────────────────────────────────────────────────────────────── claim ──

/**
 * A sentence that only prints if the data supports it.
 *
 * THREE-valued on purpose. `holds === null` means "we don't know", and an unknown
 * must not print the false branch either — that is how `deposits:920` came to
 * claim "Every deposit-taking group funds its loan book below the 100% line" off
 * a guard that only ever tested the sector.
 */
export function claim(
  holds: boolean | null | undefined,
  then: string,
  otherwise?: string,
): string | null {
  if (holds == null) return null;
  return holds ? then : (otherwise ?? null);
}

/**
 * The claim ladder: the first rung whose test holds wins, strictest first. The
 * fix for a guard that tests one quantity and asserts another — every rung tests
 * exactly the fact its sentence states.
 *
 *   firstClaim(
 *     [ci > 50 && falling, "Costs still eat more than half of income — but less than they did"],
 *     [ci > 50,            `Costs eat ${pct(ci)} of income — more than half`],
 *   ) ?? "Cost / income"
 */
export function firstClaim(
  ...cs: Array<readonly [boolean | null | undefined, string]>
): string | null {
  for (const [holds, text] of cs) if (holds === true) return text;
  return null;
}

/**
 * A claim that carries the test that chose it, so a chart can print WHY it says
 * what it says — the `Flag.rule` idiom (desk.tsx), applied to a headline. Use on
 * the few titles where the call is close enough that the reader deserves the rule.
 */
export interface Ruled {
  title: string;
  rule: string;
}
export function ruled(
  holds: boolean | null | undefined,
  rule: string,
  then: string,
  otherwise: string,
): Ruled {
  return { title: holds === true ? then : otherwise, rule };
}

// ───────────────────────────────────────────────────────────── signed ──

export type NumFmt = (v: number) => string;

/** `dec(0)` → "42"; `dec(1)` → "42.0". */
export const dec =
  (d = 1): NumFmt =>
  (v) =>
    v.toFixed(d);

/**
 * The sign, once, in front of the MAGNITUDE.
 *
 * `fmt` receives `Math.abs(v)`, so an existing `fmtBn = (v) => \`₺${v}bn\`` composes
 * unchanged — and the minus lands OUTSIDE the currency symbol (−₺42bn, not the
 * ₺-42bn that `Intl.NumberFormat` produces). This is the fix for the whole
 * `+{fmtBn(x)}` bug class: four sites on /asset-quality rendered "+₺-42bn" the
 * moment net NPL formation went negative.
 *
 * Zero prints "+0.0" — when zero is meaningful, band it through `direction()`.
 */
export function signed(
  v: number | null | undefined,
  fmt: NumFmt = dec(1),
  dash = "—",
): string {
  if (v == null || Number.isNaN(v)) return dash;
  return `${v >= 0 ? "+" : "−"}${fmt(Math.abs(v))}`;
}

/** "+1.20pp" / "−0.34pp". Moved here from desk.ts — same output, one sign rule. */
export const signedPp = (v: number, d = 2): string => signed(v, (x) => `${x.toFixed(d)}pp`);

// ───────────────────────────────────────────────────────── universals ──

/**
 * UNLIKE `Array.prototype.every`, this is FALSE on an empty list.
 *
 * "Every ownership group is below the line" must not be *vacuously* true when the
 * groups failed to load — a universal claim with no members behind it is exactly
 * the silent lie this module exists to stop.
 */
export function everyOf<T>(xs: readonly T[], test: (x: T) => boolean): boolean {
  return xs.length > 0 && xs.every(test);
}

/** "6 of 8" — the honest fallback when a universal doesn't hold. */
export function countOf<T>(
  xs: readonly T[],
  test: (x: T) => boolean,
): { n: number; of: number } {
  return { n: xs.filter(test).length, of: xs.length };
}

// ─────────────────────────────────────────────────────────────── runs ──

/**
 * A run clause that disappears when the run is over — null at n <= 0.
 *
 * `/credit` printed "What remains is real volume — negative for 0 consecutive
 * weeks" the moment real growth turned positive, because the count was computed
 * and the word "negative" was typed.
 */
export function runPhrase(n: number, what: string, unit = "w"): string | null {
  if (!Number.isFinite(n) || n <= 0) return null;
  return `${what} for ${n}${unit} running`;
}

// ─────────────────────────────────────────────────────────────── tone ──

/** Which way is good — the same axis `MoverRow.good` already uses (desk.tsx). */
export type Good = "up" | "down" | "neutral";

/**
 * The colour follows the sign, so a class can never contradict the number beside
 * it. `/credit` branched its verb on the sign but hardcoded `text-negative`, so a
 * *growing* real loan book rendered "the book grew" in red.
 *
 * Mirrors the tone rule in `Movers` (desk.tsx) — one convention, not two.
 */
export function toneClass(
  v: number | null | undefined,
  good: Good = "up",
  flat = 1e-9,
): "text-positive" | "text-negative" | "text-foreground" {
  if (v == null || Number.isNaN(v) || good === "neutral" || Math.abs(v) < flat) {
    return "text-foreground";
  }
  return (good === "down" ? -v : v) >= 0 ? "text-positive" : "text-negative";
}
