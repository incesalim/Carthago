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

/**
 * The ₺700-million hole: amounts are stored in THOUSAND TL, so a figure the
 * model writes in millions or billions is numerically small ("₺700 million" →
 * 700) and slips under `unsupportedFigures`' ≥1000 floor — an invented ₺700m
 * passed the second calibration run untouched. Any sub-1000 figure glued to a
 * denomination word must therefore ALSO exist in the data at the thousand-TL
 * scale (million → ×1e3, billion/bn/milyar → ×1e6). The legitimate idiom
 * "7,000,000 thousand TL (₺7.0bn)" passes: 7.0×1e6 is in the data.
 */
const DENOM_RE = /(-?\d+(?:[.,]\d+)?)\s*(bn|billion|milyar|million|milyon|mn)\b/gi;

export function unsupportedDenominatedFigures(answer: string, allowed: number[]): number[] {
  const bad: number[] = [];
  for (const m of answer.matchAll(DENOM_RE)) {
    const v = parseFloat(m[1].replace(",", "."));
    if (!Number.isFinite(v) || Math.abs(v) >= 1000) continue; // the plain check owns those
    const scale = /^(bn|billion|milyar)$/i.test(m[2]) ? 1e6 : 1e3;
    const scaled = v * scale;
    const tol = Math.max(Math.abs(scaled) * 0.005, 1); // the model rounds to ~1 decimal
    if (!allowed.some((a) => Math.abs(Math.abs(a) - Math.abs(scaled)) <= tol)) {
      bad.push(v);
    }
  }
  return bad;
}

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

// The full-report skeleton (prompt.ts STRUCTURE). Requiring the core sections
// keeps the leaked-monologue failure impossible without being brittle about
// the optional ones (a bank with no FX table may fold that section away).
const REQUIRED_HEADINGS = [
  "## First-read scorecard",
  "## What changed",
  "## Asset quality",
  "## Capital",
  "## What the auditor said",
  "## What to watch",
  "## Bottom line",
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

  // Template placeholders ("TL X thousand", "{value}") are never legitimate
  // memo text — a model that could not find a threshold left its scaffolding
  // in. Same treatment as an invented figure: the paragraph goes.
  const PLACEHOLDER_RE = /\bTL\s+X\b|\{[a-z_]+\}|\bXX+%/i;

  for (const para of paragraphsOf(memo)) {
    // Headings and pure-prose paragraphs carry no 4+ digit / percent claims —
    // unsupportedFigures returns [] for them and they pass untouched.
    const bad = [
      ...unsupportedFigures(para, allowed),
      ...unsupportedDenominatedFigures(para, allowed),
    ];
    if (bad.length === 0 && !PLACEHOLDER_RE.test(para)) {
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
