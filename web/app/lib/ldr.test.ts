import { describe, expect, it } from "vitest";
import { LDR_AUDITED, LDR_BASES, LDR_PUBLISHED, LDR_WEEKLY_TL, ldrNoteParts } from "./ldr";

/**
 * The bug these pin (2026-07-13 sector-page audit, finding 2): three legitimate
 * loan-to-deposit figures — published TL+FC monthly, computed TL-only weekly,
 * and a bank's own audited quarterly — all printed as a bare "Loan / deposit".
 * A reader saw a comfortable ~91% on /deposits and a flagged ~97% on /liquidity
 * one click later, and had no way to know they were different quantities.
 *
 * So: a label is only correct here if it names its currency scope.
 */
describe("loan-to-deposit bases", () => {
  it("never printed as a bare 'Loan / deposit'", () => {
    for (const b of LDR_BASES) {
      expect(b.label).not.toBe("Loan / deposit");
      expect(b.label).not.toBe("Loan-to-deposit");
      // every label carries a currency scope
      expect(/TL\+FC|^TL /.test(b.label)).toBe(true);
    }
  });

  it("gives each basis a source and a cadence in its note", () => {
    for (const b of LDR_BASES) {
      expect(b.basis.length).toBeGreaterThan(20);
      expect(/monthly|weekly|quarterly/.test(b.basis)).toBe(true);
    }
  });

  it("points the reader at the sibling figure, never at its own page", () => {
    expect(LDR_PUBLISHED.elsewhere.href).toBe("/liquidity");
    expect(LDR_WEEKLY_TL.elsewhere.href).toBe("/deposits");
    expect(LDR_AUDITED.elsewhere.href).toBe("/deposits");
    for (const b of LDR_BASES) {
      expect(b.elsewhere.what.length).toBeGreaterThan(10);
    }
  });

  it("judges the TL book earlier than the TL+FC blend", () => {
    // Not an inconsistency to be unified away: the TL book is where funding
    // pressure shows first, so 95 is its line while 100 is the blend's. Each
    // flag prints its own rule, which is what makes the difference legible.
    expect(LDR_WEEKLY_TL.line).toBeLessThan(LDR_PUBLISHED.line);
    expect(LDR_PUBLISHED.line).toBe(LDR_AUDITED.line);
  });

  it("states the basis in every flag rule", () => {
    for (const b of LDR_BASES) {
      expect(/TL\+FC|tl_ldr/.test(b.rule)).toBe(true);
    }
  });

  it("hands a page the note parts rather than pre-rendered markup", () => {
    const parts = ldrNoteParts(LDR_PUBLISHED);
    expect(parts).toEqual({
      basis: LDR_PUBLISHED.basis,
      href: "/liquidity",
      what: LDR_PUBLISHED.elsewhere.what,
    });
  });
});
