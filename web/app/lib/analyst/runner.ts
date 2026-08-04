/**
 * Task 3.3 — the memo generator: sections → prompt → free-model chain → guard,
 * with ONE correction round (the bot's `retriedForNumbers` pattern — a second
 * chance that names the offending figures, then structural drop).
 *
 * This module is environment-agnostic: `env` is a plain string map (the same
 * `StringEnv` shape llm.ts takes), so the CALLER decides where it runs — the
 * CI workflow passes Actions secrets, a Worker route would pass its own env.
 * Production generation runs in CI (workflow `analyst-daily.yml`): batch LLM
 * work belongs in Actions like every other lane, and D1 writes stay inside
 * push_to_d1.py's budget discipline rather than a second Worker-side path.
 */
import { chatComplete } from "../llm";
import { guardMemo } from "./guard";
import { buildMemoMessages, storyGates, type AnalystInput, type StoryGate } from "./prompt";

export interface MemoResult {
  note_id: string;
  bank_ticker: string;
  period: string;
  kind: string;
  title: string;
  body: string;
  signal_ids: string[];
  model: string | null;
  generated_at: string;
  fact_check_passed: boolean;
  dropped_paragraphs: number;
  /** What the guard removed and why — a failed fact-check must be diagnosable
   *  from the artifact alone (the GARAN run's dropped forward-section was
   *  invisible until this existed). Never rendered to a reader. */
  dropped_detail: { paragraph: string; unsupported: number[] }[];
  /** Hash of the BANK-side inputs (sections minus macro/meta + peers +
   *  comparatives). Regeneration is gated on it: same data, same report —
   *  the read-headlines det_hash idea applied to the whole memo. Macro is
   *  excluded so a daily FX tick does not re-roll every bank's prose. */
  data_hash: string;
  /** The editorial rulings the model was bound by — persisted so the scorer
   *  can measure lead-adherence and live-story coverage per report. */
  gates: StoryGate[];
}

/** FNV-1a/32 over a string — the same fingerprint family read-headlines uses. */
function fnv1a(s: string): string {
  let h = 0x811c9dc5;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return (h >>> 0).toString(16).padStart(8, "0");
}

export function computeDataHash(input: AnalystInput): string {
  const { sections } = input;
  const stable = {
    ...sections,
    macro: undefined, // daily market prints must not re-roll bank prose
    meta: undefined, // carries generated_at
  };
  return fnv1a(JSON.stringify({ s: stable, p: input.peers, c: input.comparatives }));
}

const MAX_TOKENS = 10_000; // a 2,500-4,000-word report with tables
const CALL_TIMEOUT_MS = 240_000;
const RUN_BUDGET_MS = 600_000; // CI is patient; the chain's own deadline still bounds retries

function titleOf(body: string): string {
  const m = /^#\s*(.+)$/m.exec(body);
  return (m ? m[1] : body.split("\n")[0] ?? "").trim().slice(0, 300);
}

export async function generateMemo(
  input: AnalystInput,
  env: Record<string, string | undefined>,
  today?: string,
): Promise<MemoResult> {
  const { system, user } = buildMemoMessages(input);
  const deadline = Date.now() + RUN_BUDGET_MS;
  const opts = {
    temperature: 0,
    maxTokens: MAX_TOKENS,
    timeoutMs: CALL_TIMEOUT_MS,
    deadline,
    // The deep-dive chain, explicitly ordered. DeepSeek flash first — PAID,
    // user-authorized 2026-08-04 ("that's cheap"; a full report costs cents),
    // Baidu-pinned + seeded for reproducibility. Cerebras is the free
    // fallback that reliably writes the full report with the tail skeleton.
    // Not nemotron (reasoning leak, see llm.ts).
    providerOrder: [
      "openrouter/deepseek-v4-flash",
      "cerebras/gpt-oss-120b",
      "groq/openai/gpt-oss-120b",
      "cerebras/gemma-4-31b",
    ],
  };

  const first = await chatComplete(
    env,
    [
      { role: "system", content: system },
      { role: "user", content: user },
    ],
    opts,
  );

  let guarded = guardMemo(first.text, user);
  let model = first.model;

  if (!guarded.passed) {
    // One correction round, naming what failed — then the verdict is final.
    const problems: string[] = [];
    if (!guarded.structure_ok) {
      problems.push(
        "Your output was not the memo. Output ONLY the memo, starting with the " +
          '"# " headline line, with exactly the sections "## What changed", ' +
          '"## What it means", "## What to watch", "## Comparability caveats".',
      );
    }
    if (guarded.offending.length) {
      problems.push(
        `These figures are NOT in the DATA block: ${[...new Set(guarded.offending)].join(", ")}. ` +
          `Use ONLY figures that appear in the DATA block verbatim; do not compute new numbers; ` +
          `where a needed figure is not held, say so.`,
      );
    }
    const retry = await chatComplete(
      env,
      [
        { role: "system", content: system },
        { role: "user", content: user },
        { role: "assistant", content: first.text },
        { role: "user", content: problems.join("\n\n") },
      ],
      opts,
    );
    const retried = guardMemo(retry.text, user);
    // Keep whichever survived better; a worse retry must not undo a good first pass.
    const score = (g: typeof guarded) => (g.structure_ok ? 0 : 100) + g.dropped.length;
    if (score(retried) <= score(guarded)) {
      guarded = retried;
      model = retry.model;
    }
  }

  const s = input.sections.meta;
  const day = today ?? new Date().toISOString().slice(0, 10);
  return {
    note_id: `note:${s.bank_ticker}:${s.period}:${day}`,
    bank_ticker: s.bank_ticker,
    period: s.period,
    kind: s.kind,
    title: titleOf(guarded.body),
    body: guarded.body,
    signal_ids: input.sections.comparability.signals_this_period.map((sig) => sig.signal_id),
    model,
    generated_at: new Date().toISOString(),
    fact_check_passed: guarded.passed,
    dropped_paragraphs: guarded.dropped.length,
    dropped_detail: guarded.dropped,
    data_hash: computeDataHash(input),
    gates: storyGates(input),
  };
}
