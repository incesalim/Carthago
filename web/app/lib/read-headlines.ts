/**
 * "The Read" headline resolution (Option 1 of the perspective layer).
 *
 * On render, a page computes its deterministic TabTakeaway (from insights.ts)
 * and calls `withLlmHeadline(tab, takeaway)`. This reads the LLM-rewritten
 * headline cached in D1 (read_headlines, written by the weekly generator) and
 * substitutes it ONLY when both gates pass:
 *   1. `det_hash` still matches the live deterministic takeaway (headline +
 *      bullets) — so a rewrite from an older period is never shown; and
 *   2. the rewrite invents no number not present in the deterministic facts
 *      (defense-in-depth; the generator already validated this).
 * Otherwise the deterministic headline is returned unchanged. The result: the
 * LLM headline can never drift from the charts or go stale — worst case it
 * silently falls back to the sentence the engine would have written anyway.
 *
 * The read is intentionally UNCACHED (a single indexed lookup on an ~8-row
 * table) so a freshly generated headline appears without a KV-cache purge.
 */
import { getDB } from "./db";
import type { TabTakeaway } from "./insights";

// ascii + unicode hyphens/dashes (gpt-oss emits U+2011/U+2013)
const DASHES = "-‐‑‒–—";

function numberMatches(text: string): { value: number; start: number; end: number }[] {
  const re = /-?\d+(?:\.\d+)?/g;
  const out: { value: number; start: number; end: number }[] = [];
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    out.push({ value: parseFloat(m[0]), start: m.index, end: m.index + m[0].length });
  }
  return out;
}

/** Stable fingerprint of a deterministic takeaway (headline + bullet text).
 *  FNV-1a/32; any change to any fact flips it, which flips the gate. */
export function takeawayHash(t: TabTakeaway): string {
  const s = t.headline + "\n" + t.items.map((i) => i.text).join("\n");
  let h = 0x811c9dc5;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return (h >>> 0).toString(16);
}

/** True iff every numeric CLAIM in `text` is a number present in the takeaway.
 *  Digits bound to a label (Stage-2, CET1, 1-year) are not claims — skipped. */
export function hasOnlyKnownNumbers(text: string, t: TabTakeaway): boolean {
  const factText = t.headline + " " + t.items.map((i) => i.text).join(" ");
  const allowed = numberMatches(factText).map((n) => n.value);
  for (const { value, start, end } of numberMatches(text)) {
    // glued to a label on the LEFT (Stage-2, CET1)
    let j = start - 1;
    while (j >= 0 && DASHES.includes(text[j])) j--;
    if (j >= 0 && /[a-zA-Z]/.test(text[j])) continue;
    // glued to a label on the RIGHT via a hyphen (1-year, 3-month)
    if (end < text.length && DASHES.includes(text[end]) && end + 1 < text.length && /[a-zA-Z]/.test(text[end + 1])) continue;
    // Match on MAGNITUDE: a fact printed negative that the rewrite phrases positive
    // (e.g. "-7.3pp real" → "7.3pp below inflation") is the same figure, not an
    // invention — the deterministic bullets still carry the sign. Must stay in sync
    // with unknown_numbers() in src/news/free_llm.py.
    if (!allowed.some((a) => Math.abs(Math.abs(value) - Math.abs(a)) < 0.01)) {
      return false;
    }
  }
  return true;
}

interface HeadlineRow {
  det_hash: string;
  headline: string;
  model: string | null;
}

/** Swap in the cached LLM headline when it matches this render's facts; else
 *  return the deterministic takeaway unchanged. Never throws. */
export async function withLlmHeadline(tab: string, takeaway: TabTakeaway): Promise<TabTakeaway> {
  let row: HeadlineRow | null = null;
  try {
    const db = await getDB();
    row = await db
      .prepare("SELECT det_hash, headline, model FROM read_headlines WHERE tab = ?")
      .bind(tab)
      .first<HeadlineRow>();
  } catch {
    return takeaway; // table missing / no CF context (local dev) → deterministic
  }
  if (!row) return takeaway;
  if (row.det_hash !== takeawayHash(takeaway)) return takeaway; // facts moved on
  if (!hasOnlyKnownNumbers(row.headline, takeaway)) return takeaway; // belt & suspenders
  return { ...takeaway, headline: row.headline };
}
