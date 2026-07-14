import { describe, expect, it } from "vitest";
import {
  DOWN_WORDS,
  UP_WORDS,
  VERBS,
  bandsFor,
  claim,
  countOf,
  dec,
  direction,
  everyOf,
  firstClaim,
  runPhrase,
  signed,
  signedPp,
  toneClass,
  type Words,
} from "./prose";
import { deltaByGroup, latestByGroup, leaderOf, type GroupRow } from "./desk";

const DICTS = Object.entries(VERBS as unknown as Record<string, Words>);

describe("direction", () => {
  it("never invents a sign", () => {
    expect(direction(null, VERBS.trend)).toBeNull();
    expect(direction(undefined, VERBS.trend)).toBeNull();
    expect(direction(NaN, VERBS.trend)).toBeNull();
  });

  it("reads zero as flat, not as a fall", () => {
    // The bug shape: `delta > 0 ? "rose" : "fell"` calls a dead-flat series a fall.
    expect(direction(0, VERBS.move)).toBe("held");
  });

  it("bands a move against the scale of the series", () => {
    const b = bandsFor(200); // flat < 2.0, sharp >= 16.0
    expect(direction(1.5, VERBS.move, b)).toBe("held");
    expect(direction(5, VERBS.move, b)).toBe("rose");
    expect(direction(20, VERBS.move, b)).toBe("jumped");
    expect(direction(-20, VERBS.move, b)).toBe("dropped");
  });

  it("falls back to the plain verb when a dictionary has no sharp variant", () => {
    expect(direction(999, VERBS.noun, bandsFor(1))).toBe("appreciation");
    expect(direction(-999, VERBS.noun, bandsFor(1))).toBe("depreciation");
  });

  // THE invariant the whole audit is about: a word that asserts a rise may only
  // appear for a positive delta, and vice versa. Every dictionary, every scale.
  it.each(DICTS)("%s: an up-word implies Δ>0 and a down-word implies Δ<0", (_name, dict) => {
    for (let d = -100; d <= 100; d += 0.5) {
      const w = direction(d, dict, bandsFor(50));
      if (w == null) continue;
      if (UP_WORDS.includes(w)) expect(d).toBeGreaterThan(0);
      if (DOWN_WORDS.includes(w)) expect(d).toBeLessThan(0);
    }
  });

  it("keeps the up and down vocabularies disjoint", () => {
    expect(UP_WORDS.filter((w) => DOWN_WORDS.includes(w))).toEqual([]);
  });
});

describe("claim", () => {
  it("is three-valued — an unknown prints neither branch", () => {
    expect(claim(true, "A", "B")).toBe("A");
    expect(claim(false, "A", "B")).toBe("B");
    expect(claim(false, "A")).toBeNull();
    // The deposits:920 bug: a null guard must NOT fall through to the claim.
    expect(claim(null, "A", "B")).toBeNull();
    expect(claim(undefined, "A", "B")).toBeNull();
  });
});

describe("firstClaim", () => {
  it("takes the strictest rung that holds", () => {
    expect(
      firstClaim([false, "over half, and falling"], [true, "over half"], [true, "falling"]),
    ).toBe("over half");
  });

  it("returns null when no rung holds, so the caller prints the topic", () => {
    expect(firstClaim([false, "a"], [null, "b"], [undefined, "c"])).toBeNull();
    expect(firstClaim()).toBeNull();
  });
});

describe("signed", () => {
  it("puts one sign in front of the magnitude", () => {
    expect(signed(4.2)).toBe("+4.2");
    expect(signed(-4.2)).toBe("−4.2");
    expect(signed(null)).toBe("—");
  });

  it("keeps the minus outside the currency symbol", () => {
    const fmtBn = (v: number) => `₺${Math.round(v)}bn`;
    // The /asset-quality bug rendered `+{fmtBn(-42)}` → "+₺-42bn".
    expect(signed(-42, fmtBn)).toBe("−₺42bn");
    expect(signed(42, fmtBn)).toBe("+₺42bn");
  });

  it("never emits a double sign, for any value or formatter", () => {
    const fmts = [dec(0), dec(2), (v: number) => `₺${v.toFixed(1)}bn`, (v: number) => `${v}%`];
    for (const fmt of fmts) {
      for (const v of [-1e6, -42.5, -0.001, 0, 0.001, 42.5, 1e6]) {
        expect(signed(v, fmt)).not.toMatch(/[+−]\s*[-−+]/);
      }
    }
  });

  it("signedPp is unchanged from the desk.ts original", () => {
    const original = (v: number, d = 2) => `${v >= 0 ? "+" : "−"}${Math.abs(v).toFixed(d)}pp`;
    for (const v of [-12.345, -0.5, 0, 0.5, 12.345]) {
      expect(signedPp(v)).toBe(original(v));
      expect(signedPp(v, 1)).toBe(original(v, 1));
    }
  });
});

describe("everyOf", () => {
  it("is FALSE on an empty list — a universal needs members", () => {
    // Array.every([]) is true; that vacuous truth is how "Every ownership group
    // is below the line" would survive the groups failing to load.
    expect([].every(() => false)).toBe(true);
    expect(everyOf([], () => true)).toBe(false);
  });

  it("otherwise behaves like every", () => {
    expect(everyOf([1, 2, 3], (n) => n < 4)).toBe(true);
    expect(everyOf([1, 2, 9], (n) => n < 4)).toBe(false);
  });
});

describe("countOf", () => {
  it("counts the honest fallback when a universal fails", () => {
    expect(countOf([1, 2, 9, 10], (n) => n < 4)).toEqual({ n: 2, of: 4 });
  });
});

describe("runPhrase", () => {
  it("disappears when the run is over", () => {
    // "negative for 0 consecutive weeks" — /credit, the moment real growth turned.
    expect(runPhrase(0, "negative")).toBeNull();
    expect(runPhrase(-1, "negative")).toBeNull();
    expect(runPhrase(7, "negative")).toBe("negative for 7w running");
  });
});

describe("toneClass", () => {
  it("follows the sign, so the colour cannot contradict the number", () => {
    expect(toneClass(5, "up")).toBe("text-positive");
    expect(toneClass(-5, "up")).toBe("text-negative");
    // Net NPL formation going negative is the GOOD case.
    expect(toneClass(-5, "down")).toBe("text-positive");
    expect(toneClass(5, "down")).toBe("text-negative");
    expect(toneClass(null, "up")).toBe("text-foreground");
    expect(toneClass(0, "up")).toBe("text-foreground");
  });
});

describe("group primitives", () => {
  const rows: GroupRow[] = [
    { period: "2026-04", bank_type_code: "state", value: 10 },
    { period: "2026-05", bank_type_code: "state", value: 14 },
    { period: "2026-04", bank_type_code: "private", value: 20 },
    { period: "2026-05", bank_type_code: "private", value: 18 },
    { period: "2026-05", bank_type_code: "sector", value: 16 },
    { period: "2026-05", bank_type_code: "foreign", value: null },
  ];

  it("takes the latest non-null observation per group", () => {
    const m = latestByGroup(rows);
    expect(m.get("state")).toEqual({ period: "2026-05", value: 14 });
    expect(m.get("private")).toEqual({ period: "2026-05", value: 18 });
    expect(m.has("foreign")).toBe(false);
  });

  it("computes each group's own delta, not a cross-group one", () => {
    const d = deltaByGroup(rows, 1);
    expect(d.get("state")).toBe(4);
    expect(d.get("private")).toBe(-2);
    expect(d.has("sector")).toBe(false); // one point — no delta, no claim
  });

  it("names the leader, excluding the sector aggregate", () => {
    expect(leaderOf(rows, { exclude: ["sector"] })).toEqual({ code: "private", value: 18 });
    expect(leaderOf(rows, { exclude: ["sector"], dir: "min" })).toEqual({
      code: "state",
      value: 14,
    });
    expect(leaderOf([], {})).toBeNull();
  });
});
