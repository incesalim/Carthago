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
  /** The output has the memo's shape: a `# ` headline and all four sections.
   *  The figure check alone cannot see "this is not a memo" — a leaked
   *  reasoning monologue passed it once, because every number it echoed was
   *  in the data. Form is a claim too. */
  structure_ok: boolean;
  passed: boolean;
}

const REQUIRED_HEADINGS = [
  "## What changed",
  "## What it means",
  "## What to watch",
  "## Comparability caveats",
];

export function memoStructureOk(memo: string): boolean {
  return /^#\s+\S/m.test(memo) && REQUIRED_HEADINGS.every((h) => memo.includes(h));
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

  const structure_ok = memoStructureOk(memo);
  return {
    body: kept.join("\n\n"),
    dropped,
    offending,
    structure_ok,
    passed: dropped.length === 0 && structure_ok,
  };
}
