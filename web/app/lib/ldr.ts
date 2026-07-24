/**
 * Loan-to-deposit — one name, three legitimate bases (strings only; safe on the
 * client). This module exists so no surface can print a bare "Loan / deposit"
 * again.
 *
 * The bug it closes (2026-07-13 sector-page audit, finding 2): `/deposits`
 * showed a comfortable ~91% with no flag, and one click later `/liquidity`
 * flagged ~97% as stretched. Both figures were right. Neither label said what it
 * was, so they read as one metric disagreeing with itself — and the pages link
 * to each other, so a reader meets both in seconds.
 *
 * They are not the same quantity:
 *
 *   published  BDDK's own published ratio, monthly, sector, TL+FC. Per DESIGN.md
 *              ("one metric, one number — never print a home-made version of a
 *              published one") this IS the sector's loan/deposit ratio.
 *   weeklyTl   computed from the weekly bulletin: TL loans ÷ TL deposits, split
 *              public vs private. Not published at this granularity, and the one
 *              that shows funding pressure first — the TL book is where a
 *              deposit war is fought, and it runs hotter than the TL+FC blend.
 *   audited    one bank's own BRSA balance sheet, quarterly, TL+FC.
 *
 * Each carries its own line for the same reason: 100% is "fully lent" on a TL+FC
 * book; on the private TL book, 95% is already the pressure point.
 *
 * Rule for a new surface: take the label from here, print `basis` in the note,
 * and point at `elsewhere` so the reader meets the sibling figure knowingly.
 */

export interface LdrBasis {
  /**
   * Label as printed. Always names the currency scope: "Loan / deposit" alone is
   * exactly the ambiguity this module exists to prevent.
   */
  label: string;
  /** Source + cadence + population — belongs in the note under the figure. */
  basis: string;
  /** The sibling figure the reader will meet on another page. */
  elsewhere: { href: string; what: string };
  /** The line this basis is judged against, and the phrase for its flag rule. */
  line: number;
  rule: string;
}

/** `/deposits` — BDDK's published sector ratio (`financial_ratios`, monthly). */
export const LDR_PUBLISHED: LdrBasis = {
  label: "Loan / deposit — TL+FC",
  basis: "BDDK published sector ratio, monthly, all currencies",
  elsewhere: { href: "/liquidity", what: "TL-only, weekly, public vs private" },
  line: 100,
  rule: "published TL+FC loan/deposit > 100%",
};

/** `/liquidity` — computed from the weekly bulletin, TL legs only, by group. */
export const LDR_WEEKLY_TL: LdrBasis = {
  label: "TL loan / deposit",
  basis: "TL loans ÷ TL deposits from the weekly bulletin, by ownership group",
  elsewhere: { href: "/deposits", what: "the published TL+FC sector ratio, monthly" },
  // The TL book carries the funding pressure first, so it is judged earlier than
  // the TL+FC blend — a private TL ratio at 95 is already at the line.
  line: 95,
  rule: "tl_ldr_private > 95%",
};

/** `/banks/[ticker]` — that bank's audited BRSA balance sheet, quarterly. */
export const LDR_AUDITED: LdrBasis = {
  label: "Loan / deposit — TL+FC",
  basis: "this bank's audited balance sheet: loans (2.1) ÷ deposits (I.), quarterly",
  elsewhere: { href: "/deposits", what: "the sector's published ratio" },
  line: 100,
  rule: "audited TL+FC loan/deposit > 100%",
};

export const LDR_BASES = [LDR_PUBLISHED, LDR_WEEKLY_TL, LDR_AUDITED] as const;

/**
 * The note that goes under a printed figure: what this one is, and where its
 * sibling lives. Kept as parts so a page can render the link with its own
 * component rather than raw HTML.
 */
export function ldrNoteParts(b: LdrBasis): { basis: string; href: string; what: string } {
  return { basis: b.basis, href: b.elsewhere.href, what: b.elsewhere.what };
}
