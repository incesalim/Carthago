/**
 * Analyst V2 — the bounded, hypothesis-driven research loop.
 *
 * The model decides what to examine next; the harness decides what is true.
 * A validated JSON action protocol (no provider function-calling assumed):
 * each turn the model returns exactly one action — call a tool, update the
 * hypothesis ledger, emit a structured finding, abstain, or conclude.
 * Protocol violations get ONE repair message and count as spent turns; three
 * consecutive violations abort into abstention. Everything is traced.
 *
 * Abstention is a first-class success outcome: "nothing material, and here is
 * what was checked" beats a manufactured story every time.
 */
import { chatComplete } from "../../llm";
import type { EvidenceRecord } from "./evidence";
import { FINDING_SCHEMA_PROMPT, findingProblems, type Finding } from "./findings";
import { STATEMENTS } from "./registry";
import type { ScoutResult } from "./scout";
import { runTool, toolCatalog, ToolError, type ToolContext } from "./tools";
import { verifyFindings } from "./verifier";

export interface Hypothesis {
  hypothesis_id: string;
  statement: string;
  status: "open" | "supported" | "rejected" | "unresolved";
  materiality: "high" | "medium" | "low";
  confidence: "high" | "medium" | "low";
  supporting_evidence_ids: string[];
  counterevidence_ids: string[];
  open_questions: string[];
}

export interface ResearchResult {
  findings: Finding[];
  hypotheses: Hypothesis[];
  abstained: boolean;
  abstain_reason: string | null;
  metrics: {
    turns: number;
    tool_calls: number;
    protocol_errors: number;
    duration_ms: number;
    model: string | null;
    aborted: string | null;
  };
  traceJsonl: string;
}

// Raised 22→32 after the ALBRK round-3 run: with the case file in place the
// model spent every turn productively (18 distinct queries, zero repeats)
// and hit the budget mid-synthesis — turns, not discipline, were binding.
const MAX_TURNS = 32;
const WALL_MS = 14 * 60_000;
const RESULT_CHARS = 9_000;
const MAX_CONSECUTIVE_PROTOCOL = 3;
/**
 * Total byte budget for the evidence-on-file digest. Every delivered record
 * stays visible in the prompt — a memoryless last-result-only loop was
 * measured (ALBRK head-to-head) driving models to re-fetch the same table
 * 16 turns straight, because data vanished the turn after delivery. Oldest
 * non-seed records are evicted to a stub when over budget; a re-call after
 * eviction re-delivers.
 *
 * Sized so a full 32-turn run NEVER evicts in practice: at 45KB, 8KB pages
 * overflowed the file mid-run and the model spent 9 turns re-delivering its
 * own evicted evidence (measured, round 6). 150KB ≈ 40k tokens still fits
 * the smallest fallback model's context with ample headroom.
 */
const DIGEST_BUDGET = 150_000;

const SYSTEM = `You are a bank research analyst investigating ONE bank, ONE quarter, ONE
consolidation basis, over audited-filing data that has already been extracted
into structured tables. You work in turns. Each turn you output EXACTLY ONE
JSON object (no markdown fences, no prose outside it) — one of:

{"action":"tool","tool":"<name>","args":{...}}
{"action":"hypotheses","set":[{"hypothesis_id":"H1","statement":"...","status":"open|supported|rejected|unresolved","materiality":"high|medium|low","confidence":"high|medium|low","supporting_evidence_ids":[],"counterevidence_ids":[],"open_questions":["..."]}]}
{"action":"finding","finding":{...FINDING object...}}
{"action":"abstain","reason":"nothing material — and what was checked"}
{"action":"conclude","reason":"investigation complete"}

TOOLS (read-only; args validated; results carry evidence_id, warnings and the
partition's validation status):
__TOOL_CATALOG__

__FINDING_SCHEMA__

METHOD — this is an investigation, not a report:
0. Everything you have retrieved stays ON FILE in the EVIDENCE ON FILE
   section of each turn — you NEVER need to re-fetch anything. A repeated
   identical call returns only a pointer to the file. If an entry was
   evicted for space, re-calling the tool re-delivers it.
1. Start from the scout candidates, but they are LEADS, not conclusions.
   Work BREADTH-FIRST: a real economic event leaves matching fingerprints in
   MORE THAN ONE statement (P&L ↔ balance sheet ↔ equity ↔ notes), so before
   going deep on any single line, rank movements on the major statements and
   look for its counterparts. A large number whose counterpart trail you
   cannot find is more likely an extraction or presentation artifact than a
   story. If a hypothesis resists confirmation after several probes, mark it
   unresolved and test the NEXT lead — do not tunnel.
2. Keep the hypothesis ledger current ("hypotheses" action) — every idea you
   are working on, with status and open questions.
3. For your preferred explanation, actively SEEK COUNTEREVIDENCE before
   emitting a finding: check the other statements, the filing text, the
   validation status. An extraction defect and a real event look identical
   until reconciled.
4. Numbers: only ever cite numbers you have SEEN in a tool result, and cite
   the evidence_id that contains them (the id is shown WITH the result — note
   which id held which number as you go). In tables, ∅ means null =
   not-disclosed, never zero.
5. A validation-failing partition can still carry a story — but say so.
6. Emit at most 3 findings, most material first. Each finding is verified
   deterministically AT EMISSION: if a cited number is not in the cited
   evidence, you get the failing checks back and ONE chance to repair that
   finding. If nothing clears the bar, abstain — a documented "ordinary
   quarter" is a correct result.
7. Budget: you have a limited number of turns (shown each turn). Repeating an
   identical tool call returns a short notice, never new data — results are
   cached and complete. Spend turns broadening the investigation instead.`;

interface TraceLine {
  turn: number;
  raw_reply_head: string;
  action: string | null;
  detail: string;
  evidence_id?: string;
  error?: string;
}

function extractJson(text: string): unknown | null {
  const start = text.indexOf("{");
  if (start < 0) return null;
  let depth = 0;
  let inStr = false;
  let esc = false;
  for (let i = start; i < text.length; i++) {
    const ch = text[i];
    if (esc) { esc = false; continue; }
    if (ch === "\\") { esc = true; continue; }
    if (ch === '"') inStr = !inStr;
    if (inStr) continue;
    if (ch === "{") depth++;
    if (ch === "}") {
      depth--;
      if (depth === 0) {
        try {
          return JSON.parse(text.slice(start, i + 1));
        } catch {
          return null;
        }
      }
    }
  }
  return null;
}

type Primitive = string | number | boolean | null;

function isPrimitive(v: unknown): v is Primitive {
  return v == null || ["string", "number", "boolean"].includes(typeof v);
}

function cell(v: unknown): string {
  if (v == null) return "∅";
  return String(v).replace(/\|/g, "¦").replace(/\s+/g, " ");
}

/**
 * Render an array of row-objects as a pipe-table instead of verbose JSON —
 * one nesting level of plain objects is flattened into dotted columns. The
 * stored EvidenceRecord keeps full JSON; this only compresses what the model
 * SEES, so a 14-column statement matrix fits the result window whole.
 * `∅` marks null (not-disclosed — never zero).
 */
export function tablify(rows: unknown[]): string | null {
  if (rows.length < 3) return null;
  const flat: Record<string, Primitive>[] = [];
  for (const r of rows) {
    if (typeof r !== "object" || r == null || Array.isArray(r)) return null;
    const out: Record<string, Primitive> = {};
    for (const [k, v] of Object.entries(r as Record<string, unknown>)) {
      if (isPrimitive(v)) out[k] = v;
      else if (typeof v === "object" && !Array.isArray(v) && Object.values(v as object).every(isPrimitive)) {
        for (const [k2, v2] of Object.entries(v as Record<string, Primitive>)) out[`${k}.${k2}`] = v2;
      } else return null;
    }
    flat.push(out);
  }
  const cols: string[] = [];
  for (const r of flat) for (const k of Object.keys(r)) if (!cols.includes(k)) cols.push(k);
  const lines = [`TABLE ${flat.length} rows · cols: ${cols.join("|")} · ∅=null(not disclosed)`];
  for (const r of flat) lines.push(cols.map((c) => cell(c in r ? r[c] : null)).join("|"));
  return lines.join("\n");
}

function renderData(data: unknown): string {
  if (Array.isArray(data)) {
    const t = tablify(data);
    if (t) return t;
  }
  if (data != null && typeof data === "object" && !Array.isArray(data)) {
    const parts: string[] = [];
    for (const [k, v] of Object.entries(data as Record<string, unknown>)) {
      const t = Array.isArray(v) ? tablify(v) : null;
      parts.push(t ? `${k}:\n${t}` : `${k}: ${JSON.stringify(v)}`);
    }
    return parts.join("\n");
  }
  return JSON.stringify(data);
}

function compactEvidence(rec: EvidenceRecord): string {
  const head = JSON.stringify({
    evidence_id: rec.evidence_id,
    tool: rec.tool,
    args: rec.args,
    warnings: rec.warnings,
    validation_warnings: rec.validation_warnings,
    rows_returned: rec.rows_returned,
  });
  const s = `${head}\nDATA:\n${renderData(rec.data)}`;
  return s.length > RESULT_CHARS ? s.slice(0, RESULT_CHARS) + `…(truncated of ${s.length} chars — narrow the query)` : s;
}

export async function runResearch(
  ctx: ToolContext,
  scout: ScoutResult,
  env: Record<string, string | undefined>,
): Promise<ResearchResult> {
  const t0 = Date.now();
  const deadlineAt = t0 + WALL_MS;
  const trace: TraceLine[] = [];
  const findings: Finding[] = [];
  let hypotheses: Hypothesis[] = [];
  let abstained = false;
  let abstainReason: string | null = null;
  let aborted: string | null = null;
  let toolCalls = 0;
  let protocolErrors = 0;
  let consecutiveProtocol = 0;
  let model: string | null = null;

  // Seed evidence, delivered into the persistent case file.
  const seedAvail = await runTool(ctx, "list_available_data", {});
  const seedValidation = await runTool(ctx, "get_validation_status", {});
  toolCalls += 2;
  const examinedStatements = new Set<string>();
  const findingRepairs = new Map<string, number>();
  let verifierBounces = 0;
  // Tunnel-vision detector: consecutive tool calls probing one area (a
  // statement, or the filing text) earn a breadth nudge — measured round 4
  // spending 8 straight turns on one line's filing-text trail.
  const recentFocus: string[] = [];
  const FOCUS_WINDOW = 6;

  // The case file: every delivered record stays visible each turn. The model
  // never has to re-fetch; only over-budget entries fall back to a stub.
  const digest = new Map<string, string>();
  const stubOf = new Map<string, string>();
  const evictedStubs = new Map<string, string>();
  const seedIds = new Set([seedAvail.evidence_id, seedValidation.evidence_id]);
  const deliver = (rec: EvidenceRecord) => {
    digest.set(rec.evidence_id, compactEvidence(rec));
    stubOf.set(rec.evidence_id, `${rec.evidence_id} ${rec.tool}(${JSON.stringify(rec.args)})`);
    evictedStubs.delete(rec.evidence_id);
    let size = [...digest.values()].reduce((s, v) => s + v.length, 0);
    for (const [id, v] of digest) {
      if (size <= DIGEST_BUDGET) break;
      if (seedIds.has(id) || id === rec.evidence_id) continue;
      evictedStubs.set(id, stubOf.get(id) ?? id);
      digest.delete(id);
      size -= v.length;
    }
  };
  deliver(seedAvail);
  deliver(seedValidation);

  const system = SYSTEM.replace("__TOOL_CATALOG__", toolCatalog()).replace("__FINDING_SCHEMA__", FINDING_SCHEMA_PROMPT);
  const briefing =
    `INVESTIGATION: ${ctx.defaults.bank} ${ctx.defaults.period} ${ctx.defaults.kind} · snapshot ${ctx.snapshot.id}\n\n` +
    `SCOUT — ranked movements (leads, not conclusions; scores are surprise-weighted):\n` +
    scout.candidates.slice(0, 28).map((c) => `  [${c.score}] ${c.source} ${c.statement ?? ""} ${c.row ?? c.metric ?? ""} — ${c.description} :: ${JSON.stringify(c.values)}`).join("\n");

  let lastResult = "(seed evidence is on file above — begin the investigation)";
  let turn = 0;

  while (turn < MAX_TURNS) {
    if (Date.now() > deadlineAt) { aborted = "wall_clock"; break; }
    turn++;
    const user =
      `${briefing}\n\n` +
      `EVIDENCE ON FILE (your case file — everything retrieved so far; cite these evidence_ids):\n` +
      [...digest.values()].join("\n---\n") +
      (evictedStubs.size ? `\n[evicted for space — re-call to re-deliver: ${[...evictedStubs.values()].join(" · ")}]` : "") +
      `\n\nHYPOTHESIS LEDGER (yours to maintain):\n${JSON.stringify(hypotheses)}\n\n` +
      `FINDINGS EMITTED SO FAR: ${findings.length}\n` +
      `LAST ACTION RESULT:\n${lastResult}\n\n` +
      `Turns remaining: ${MAX_TURNS - turn}. Output exactly one action JSON object.`;

    let reply: { text: string; model: string };
    try {
      reply = await chatComplete(env, [
        { role: "system", content: system },
        { role: "user", content: user },
      ], {
        temperature: 0,
        maxTokens: 1700,
        timeoutMs: 120_000,
        deadline: deadlineAt,
        // Luna-pro leads the RESEARCH loop (user-authorized): multi-turn
        // investigation is where model capability binds, and its 1M context
        // absorbs long tool results without truncation pressure.
        providerOrder: [
          "openrouter/gpt-5.6-luna-pro",
          "openrouter/deepseek-v4-flash",
          "cerebras/gpt-oss-120b",
          "groq/openai/gpt-oss-120b",
        ],
      });
    } catch (e) {
      aborted = `llm_error: ${e instanceof Error ? e.message.slice(0, 200) : String(e)}`;
      break;
    }
    model = reply.model;

    const parsed = extractJson(reply.text) as { action?: string } | null;
    const head = reply.text.slice(0, 220).replace(/\s+/g, " ");

    if (!parsed || typeof parsed.action !== "string") {
      protocolErrors++;
      consecutiveProtocol++;
      trace.push({ turn, raw_reply_head: head, action: null, detail: "no parseable action object" });
      lastResult = `PROTOCOL ERROR: your reply carried no single JSON action object. Reply with exactly one of the documented action shapes.`;
      if (consecutiveProtocol >= MAX_CONSECUTIVE_PROTOCOL) { aborted = "protocol"; break; }
      continue;
    }
    consecutiveProtocol = 0;

    const a = parsed as Record<string, unknown> & { action: string };
    if (a.action === "tool") {
      const toolName = String(a.tool ?? "");
      try {
        const rec = await runTool(ctx, toolName, (a.args as Record<string, unknown>) ?? {});
        toolCalls++;
        if (typeof rec.args.statement === "string") examinedStatements.add(rec.args.statement);
        if (digest.has(rec.evidence_id)) {
          const unexamined = Object.keys(STATEMENTS).filter((s) => !examinedStatements.has(s));
          lastResult =
            `REPEAT CALL: ${rec.evidence_id} is already ON FILE above — read it there; re-requesting cannot show more. ` +
            `Examine something new` +
            (unexamined.length ? ` (statements not yet read: ${unexamined.slice(0, 10).join(", ")})` : "") + `.`;
          trace.push({ turn, raw_reply_head: head, action: "tool", detail: `repeat ${toolName}(${JSON.stringify(a.args ?? {})})`, evidence_id: rec.evidence_id });
        } else {
          deliver(rec);
          lastResult = `${rec.evidence_id} delivered — now ON FILE above.`;
          trace.push({ turn, raw_reply_head: head, action: "tool", detail: `${toolName}(${JSON.stringify(a.args ?? {})})`, evidence_id: rec.evidence_id });
        }
        const focus = typeof rec.args.statement === "string"
          ? (rec.args.statement as string)
          : ["search_filing_text", "get_source_page"].includes(toolName) ? "filing_text" : toolName;
        recentFocus.push(focus);
        if (recentFocus.length > FOCUS_WINDOW) recentFocus.shift();
        if (recentFocus.length === FOCUS_WINDOW && new Set(recentFocus).size === 1 && turn < MAX_TURNS - 2) {
          lastResult += ` NOTE: your last ${FOCUS_WINDOW} queries all probed ${focus} — a real event leaves counterparts elsewhere; test a different lead, or emit what is already supported.`;
        }
      } catch (e) {
        protocolErrors++;
        const msg = e instanceof ToolError ? e.message : String(e).slice(0, 200);
        lastResult = `TOOL ERROR (${toolName}): ${msg}`;
        trace.push({ turn, raw_reply_head: head, action: "tool", detail: toolName, error: msg });
      }
      continue;
    }
    if (a.action === "hypotheses") {
      const set = Array.isArray(a.set) ? (a.set as Hypothesis[]) : null;
      if (!set) {
        protocolErrors++;
        lastResult = `PROTOCOL ERROR: "hypotheses" needs a "set" array.`;
        trace.push({ turn, raw_reply_head: head, action: "hypotheses", detail: "malformed", error: "no set" });
        continue;
      }
      hypotheses = set.slice(0, 12);
      lastResult = `hypothesis ledger updated (${hypotheses.length} entries). Continue.`;
      trace.push({ turn, raw_reply_head: head, action: "hypotheses", detail: `${hypotheses.length} entries` });
      continue;
    }
    if (a.action === "finding") {
      const problems = findingProblems(a.finding);
      if (problems.length) {
        protocolErrors++;
        lastResult = `FINDING REJECTED (structural): ${problems.join("; ")}. Fix and resubmit — a finding without machine-checkable claims cannot be verified.`;
        trace.push({ turn, raw_reply_head: head, action: "finding", detail: "rejected", error: problems.join("; ") });
        continue;
      }
      const cand = a.finding as Finding;
      // Deterministic verification AT EMISSION (same verifier that gates the
      // final report) — a wrong number or wrong evidence pointer comes back
      // as a named failing check with ONE repair chance, instead of silently
      // dying at publication.
      const verdict = verifyFindings([...findings, cand], ctx.log, ctx.defaults).findings.at(-1);
      if (verdict && verdict.verdict === "fail") {
        verifierBounces++;
        const failed = verdict.checks.filter((c) => !c.ok && c.severity === "fail").map((c) => `${c.check} — ${c.detail}`).slice(0, 6);
        const attempts = (findingRepairs.get(cand.finding_id) ?? 0) + 1;
        findingRepairs.set(cand.finding_id, attempts);
        if (attempts >= 2 || verifierBounces >= 4) {
          lastResult = `FINDING ${cand.finding_id} REJECTED (verification failed again): ${failed.join("; ")}. Drop it — emit a different finding, conclude, or abstain.`;
          trace.push({ turn, raw_reply_head: head, action: "finding", detail: `rejected_by_verifier ${cand.finding_id}`, error: failed.join("; ").slice(0, 300) });
        } else {
          lastResult =
            `FINDING ${cand.finding_id} FAILED VERIFICATION (one repair allowed): ${failed.join("; ")}. ` +
            `Every cited number must appear in the evidence_id you cite — fix the values or cite the evidence that actually contains them, and resubmit the corrected finding.`;
          trace.push({ turn, raw_reply_head: head, action: "finding", detail: `verifier_repair ${cand.finding_id}`, error: failed.join("; ").slice(0, 300) });
        }
        continue;
      }
      findings.push(cand);
      lastResult = `finding ${cand.finding_id} accepted (verification ${verdict?.verdict ?? "pass"}). ${findings.length >= 3 ? "Finding budget reached — conclude or abstain." : "Continue, or conclude."}`;
      trace.push({ turn, raw_reply_head: head, action: "finding", detail: cand.finding_id });
      continue;
    }
    if (a.action === "abstain") {
      abstained = findings.length === 0;
      abstainReason = String(a.reason ?? "");
      trace.push({ turn, raw_reply_head: head, action: "abstain", detail: abstainReason.slice(0, 200) });
      break;
    }
    if (a.action === "conclude") {
      trace.push({ turn, raw_reply_head: head, action: "conclude", detail: String(a.reason ?? "").slice(0, 200) });
      break;
    }
    protocolErrors++;
    consecutiveProtocol++;
    lastResult = `PROTOCOL ERROR: unknown action '${a.action}'.`;
    trace.push({ turn, raw_reply_head: head, action: a.action, detail: "unknown action" });
    if (consecutiveProtocol >= MAX_CONSECUTIVE_PROTOCOL) { aborted = "protocol"; break; }
  }

  if (turn >= MAX_TURNS && !aborted) aborted = "turn_budget";
  if (aborted && findings.length === 0 && !abstainReason) {
    abstained = true;
    abstainReason = `aborted (${aborted}) before any finding — treat as abstention`;
  }

  return {
    findings,
    hypotheses,
    abstained,
    abstain_reason: abstainReason,
    metrics: {
      turns: turn,
      tool_calls: toolCalls,
      protocol_errors: protocolErrors,
      duration_ms: Date.now() - t0,
      model,
      aborted,
    },
    traceJsonl: trace.map((t) => JSON.stringify(t)).join("\n") + "\n",
  };
}
