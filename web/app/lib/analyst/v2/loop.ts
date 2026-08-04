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
import type { ScoutResult } from "./scout";
import { runTool, toolCatalog, ToolError, type ToolContext } from "./tools";

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

const MAX_TURNS = 22;
const WALL_MS = 9 * 60_000;
const RESULT_CHARS = 6_000;
const MAX_CONSECUTIVE_PROTOCOL = 3;

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
1. Start from the scout candidates, but they are LEADS, not conclusions.
2. Keep the hypothesis ledger current ("hypotheses" action) — every idea you
   are working on, with status and open questions.
3. For your preferred explanation, actively SEEK COUNTEREVIDENCE before
   emitting a finding: check the other statements, the filing text, the
   validation status. An extraction defect and a real event look identical
   until reconciled.
4. Numbers: only ever cite numbers you have SEEN in a tool result, and cite
   the evidence_id that contains them. NULL means not-disclosed, never zero.
5. A validation-failing partition can still carry a story — but say so.
6. Emit at most 3 findings, most material first. If nothing clears the bar,
   abstain — a documented "ordinary quarter" is a correct result.
7. Budget: you have a limited number of turns (shown each turn). Spend them
   on investigation, not repetition — identical tool calls are cached.`;

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

function compactEvidence(rec: EvidenceRecord): string {
  const s = JSON.stringify({
    evidence_id: rec.evidence_id,
    tool: rec.tool,
    args: rec.args,
    warnings: rec.warnings,
    validation_warnings: rec.validation_warnings,
    rows_returned: rec.rows_returned,
    data: rec.data,
  });
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

  // Seed evidence the briefing references.
  const seedAvail = await runTool(ctx, "list_available_data", {});
  const seedValidation = await runTool(ctx, "get_validation_status", {});
  toolCalls += 2;

  const system = SYSTEM.replace("__TOOL_CATALOG__", toolCatalog()).replace("__FINDING_SCHEMA__", FINDING_SCHEMA_PROMPT);
  const briefing =
    `INVESTIGATION: ${ctx.defaults.bank} ${ctx.defaults.period} ${ctx.defaults.kind} · snapshot ${ctx.snapshot.id}\n\n` +
    `AVAILABLE DATA (${seedAvail.evidence_id}):\n${compactEvidence(seedAvail).slice(0, 2600)}\n\n` +
    `VALIDATION STATUS (${seedValidation.evidence_id}):\n${compactEvidence(seedValidation).slice(0, 1800)}\n\n` +
    `SCOUT — ranked movements (leads, not conclusions; scores are surprise-weighted):\n` +
    scout.candidates.slice(0, 28).map((c) => `  [${c.score}] ${c.source} ${c.statement ?? ""} ${c.row ?? c.metric ?? ""} — ${c.description} :: ${JSON.stringify(c.values)}`).join("\n");

  let lastResult = "(no tool called yet)";
  let turn = 0;

  while (turn < MAX_TURNS) {
    if (Date.now() > deadlineAt) { aborted = "wall_clock"; break; }
    turn++;
    const user =
      `${briefing}\n\nHYPOTHESIS LEDGER (yours to maintain):\n${JSON.stringify(hypotheses)}\n\n` +
      `FINDINGS EMITTED SO FAR: ${findings.length}\n` +
      `LAST TOOL RESULT:\n${lastResult}\n\n` +
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
        providerOrder: [
          "openrouter/deepseek-v4-flash",
          "cerebras/gpt-oss-120b",
          "groq/openai/gpt-oss-120b",
          "cerebras/gemma-4-31b",
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
        lastResult = compactEvidence(rec);
        trace.push({ turn, raw_reply_head: head, action: "tool", detail: `${toolName}(${JSON.stringify(a.args ?? {})})`, evidence_id: rec.evidence_id });
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
      findings.push(a.finding as Finding);
      lastResult = `finding ${(a.finding as Finding).finding_id} accepted structurally (verification runs after the loop). ${findings.length >= 3 ? "Finding budget reached — conclude or abstain." : "Continue, or conclude."}`;
      trace.push({ turn, raw_reply_head: head, action: "finding", detail: (a.finding as Finding).finding_id });
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
