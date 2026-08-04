/**
 * Task 3.2 — the grounding guard, reusing the bot's machinery (bot-sql.ts),
 * not reimplementing it. The allowed-number set is `numbersIn(dataBlock)` —
 * the EXACT text the model received — so "what the model saw" and "what the
 * guard permits" cannot drift apart.
 *
 * Verdicts are structural, mirroring bot.ts's sequence: a paragraph whose
 * figures are not all in the data is DROPPED (the guard never edits a figure);
 * the memo passes fact-check only if nothing was dropped. The measured reality
 * this defends against: three confidently wrong figures in 80 calls, every one
 * `found=true` — there is no confidence signal to gate on, so abstention has
 * to be structural.
 */
import { numbersIn, unsupportedFigures } from "../bot-sql";

export interface GuardResult {
  body: string;
  dropped: { paragraph: string; unsupported: number[] }[];
  /** Unsupported figures across the WHOLE memo before dropping (for the retry prompt). */
  offending: number[];
  passed: boolean;
}

/** Split on blank lines, keeping headings attached to their following text. */
function paragraphsOf(memo: string): string[] {
  return memo
    .split(/\n{2,}/)
    .map((p) => p.trim())
    .filter(Boolean);
}

export function guardMemo(memo: string, dataBlock: string): GuardResult {
  const allowed = numbersIn(dataBlock);
  const kept: string[] = [];
  const dropped: GuardResult["dropped"] = [];
  const offending: number[] = [];

  for (const para of paragraphsOf(memo)) {
    // Headings and pure-prose paragraphs carry no 4+ digit / percent claims —
    // unsupportedFigures returns [] for them and they pass untouched.
    const bad = unsupportedFigures(para, allowed);
    if (bad.length === 0) {
      kept.push(para);
    } else {
      dropped.push({ paragraph: para, unsupported: bad });
      offending.push(...bad);
    }
  }

  return {
    body: kept.join("\n\n"),
    dropped,
    offending,
    passed: dropped.length === 0,
  };
}
