/**
 * BDDK capital thresholds — the one place they are defined.
 *
 * There used to be four `CAR_MIN = 12` constants (capital/page.tsx,
 * capital/CapitalByBank.tsx, bank-brief.ts, insights.ts), commented variously as
 * "regulatory minimum total capital", "BDDK regulatory minimum, incl. buffers"
 * and "BDDK regulatory minimum". Two of those readings are wrong and the drift
 * between them is how the page came to test CET1 against 12% and print
 * "18 of 37 banks hold CET1 below the 12% total-capital minimum" — a sentence
 * that names the right instrument and applies it to the wrong one. Every one of
 * those banks clears its actual common-equity requirement.
 *
 * The distinction that matters: **12% is a TARGET, not the legal minimum, and it
 * is a TOTAL-CAPITAL figure that CET1 is not measured against.**
 *
 * - `CAR_LEGAL_MIN` 8% — sermaye yeterliliği standart oranı, the statutory floor.
 *   Breaching it is a regulatory event.
 * - `CAR_TARGET` 12% — BDDK's *hedef rasyo*. Not a breach threshold: it gates
 *   permissions and dividend distribution. This is the number the sector is
 *   normally read against, and the buffer-to-target frame is the right one for
 *   Türkiye — it just has to be labelled a target.
 * - `CET1_MIN` 4.5% — asgari çekirdek sermaye.
 * - `CET1_TARGET` 7% — hedef çekirdek sermaye = 4.5 + the 2.5pp capital
 *   conservation buffer.
 *
 * ⚠️ `CET1_TARGET` is a FLOOR, not a full requirement. Systemically important
 * banks carry an additional D-SIB buffer on top (and a countercyclical buffer
 * where one is set), so a large bank's true CET1 requirement is higher than 7%.
 * **We do not store BDDK's D-SIB designations or buffer rates**, so anything
 * keyed off `CET1_TARGET` is deliberately conservative: it will not flag a
 * systemic bank that sits between 7% and its own requirement. State that where
 * it is used rather than implying 7% is the whole test.
 *
 * Sources: BDDK, asgari %4,5 çekirdek / hedef %7 çekirdek / asgari %8 SYR;
 * the 12% hedef rasyo is BDDK's target ratio for total capital.
 */

/** Statutory minimum total capital ratio (SYR). Breaching this is an event. */
export const CAR_LEGAL_MIN = 8;

/** BDDK's target total-capital ratio — gates permissions/dividends, not a breach. */
export const CAR_TARGET = 12;

/** Minimum common equity tier 1. */
export const CET1_MIN = 4.5;

/** Target CET1 = minimum 4.5 + 2.5pp conservation buffer. A floor: D-SIBs owe more. */
export const CET1_TARGET = 7;
