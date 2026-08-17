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

/**
 * A committed line of inquiry. The plan is the model's own answer to "what am I
 * going to check, and where would it show up" — made BEFORE it starts pulling
 * data, and then held against it.
 *
 * Distinct from a hypothesis on purpose. A hypothesis is a claim about the world
 * that evidence can support or reject; a lead is a piece of WORK the run has
 * committed to doing. Conflating them is how "I never looked" gets recorded as
 * "unresolved".
 */
export interface Lead {
  lead_id: string;
  /** What examining this would establish. */
  question: string;
  /** Where its counterparts would show — statement names from the registry. */
  statements: string[];
  status: "open" | "closed";
  /** Required to close: what settled it, or why it was dropped. */
  resolution?: string;
}

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
  plan: Lead[];
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
 * Tool calls one "tools" action may carry. The loop is budgeted in TURNS, so
 * strictly-one-call-per-turn made turn economy the ceiling on breadth: measured
 * rounds spent 8 straight turns on one line's filing-text trail and 9 more
 * re-delivering evicted evidence, out of 32. A counterpart sweep — the method
 * this prompt actually teaches — is by construction a set of INDEPENDENT reads,
 * so it should cost one turn, not four.
 *
 * Held at 4 deliberately. Turn budget × batch size is the new worst case for the
 * case file, and DIGEST_BUDGET was sized when that product was 32: a run that
 * batches hard can now evict where it previously never did. Eviction degrades
 * gracefully (stub + re-call re-delivers) but costs turns, which is the very
 * thing this buys. Raise it only against a measured eval run, not on the
 * reasoning that more must be better.
 */
const MAX_BATCH = 4;
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

{"action":"plan","leads":[{"lead_id":"L1","question":"what examining this would establish","statements":["equity_change","profit_loss"],"status":"open"}]}
{"action":"tool","tool":"<name>","args":{...}}
{"action":"tools","calls":[{"tool":"<name>","args":{...}},{"tool":"<name>","args":{...}}]}
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
0b. PLAN FIRST. Your FIRST action is "plan": 2–5 leads drawn from the scout
   candidates, each naming the statements where its counterparts would show.
   Decide what is worth checking BEFORE you start pulling data — chosen up
   front, the leads compete with each other on materiality; chosen one query
   at a time, whatever you just read always looks like the most interesting
   thing. Re-issue "plan" whenever the evidence changes what is worth doing:
   drop a lead by setting status "closed" with a resolution saying what settled
   it or why you are dropping it. You cannot conclude with a lead still open —
   test it or close it, and "closed: looked, nothing there" is a fine answer.
   An open lead you never examined is not an unresolved hypothesis, it is
   unfinished work.
1. Start from the scout candidates, but they are LEADS, not conclusions.
   Work BREADTH-FIRST: a real economic event leaves matching fingerprints in
   MORE THAN ONE statement (P&L ↔ balance sheet ↔ equity ↔ notes), so before
   going deep on any single line, rank movements on the major statements and
   look for its counterparts. A large number whose counterpart trail you
   cannot find is more likely an extraction or presentation artifact than a
   story. If a hypothesis resists confirmation after several probes, mark it
   unresolved and test the NEXT lead — do not tunnel.
1b. BATCH INDEPENDENT READS. Use "tools" (up to __MAX_BATCH__ calls) whenever the
   next queries do not depend on each other's results — reading four statements
   to look for one event's counterparts is ONE turn, not four. They run
   concurrently and all land on file together. Use single "tool" only when what
   you ask next genuinely depends on what the last result said. Turns, not
   queries, are the scarce resource here: a counterpart sweep you batch is a
   counterpart sweep you can afford.
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
  let plan: Lead[] = [];
  // The exit gate fires ONCE. Holding the model to its own plan is worth one
  // bounce; holding it there forever is the harness starving the model again,
  // and an agent that cannot leave is worse than one that leaves early.
  let exitBlocked = false;
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

  /**
   * Run one or more tool calls and fold every result into the case file.
   * A batch runs CONCURRENTLY; a single call takes the identical path, so the
   * one-call behaviour (repeat pointer, focus nudge, trace shape) is unchanged.
   *
   * Per-call failure is isolated: one bad tool name does not discard the three
   * good reads beside it. Identical (tool, args) inside one batch are deduped
   * before dispatch — they resolve to the same evidence id, so concurrent twins
   * would both miss the log cache and run the same query twice for one row.
   * Two DIFFERENT spellings of the same query (omitted vs explicit default) still
   * race, because the id is only known after arg validation; the loser is then
   * reported as a repeat, which is correct but costs one wasted query.
   */
  const executeCalls = async (
    calls: { tool: string; args: Record<string, unknown> }[],
    turnNo: number,
    head: string,
  ): Promise<string> => {
    const seenKeys = new Set<string>();
    const unique = calls.filter((c) => {
      const k = `${c.tool}:${JSON.stringify(c.args ?? {})}`;
      if (seenKeys.has(k)) return false;
      seenKeys.add(k);
      return true;
    });
    const settled = await Promise.all(
      unique.map(async (c) => {
        try {
          return { c, rec: await runTool(ctx, c.tool, c.args ?? {}) };
        } catch (e) {
          return { c, err: e instanceof ToolError ? e.message : String(e).slice(0, 200) };
        }
      }),
    );
    const lines: string[] = [];
    let lastFocus = "";
    for (const s of settled) {
      const label = `${s.c.tool}(${JSON.stringify(s.c.args ?? {})})`;
      if ("err" in s) {
        protocolErrors++;
        lines.push(`TOOL ERROR (${s.c.tool}): ${s.err}`);
        trace.push({ turn: turnNo, raw_reply_head: head, action: "tool", detail: s.c.tool, error: s.err });
        continue;
      }
      const rec = s.rec;
      toolCalls++;
      if (typeof rec.args.statement === "string") examinedStatements.add(rec.args.statement);
      if (digest.has(rec.evidence_id)) {
        const unexamined = Object.keys(STATEMENTS).filter((st) => !examinedStatements.has(st));
        lines.push(
          `REPEAT CALL: ${rec.evidence_id} is already ON FILE above — read it there; re-requesting cannot show more. ` +
            `Examine something new` +
            (unexamined.length ? ` (statements not yet read: ${unexamined.slice(0, 10).join(", ")})` : "") + `.`,
        );
        trace.push({ turn: turnNo, raw_reply_head: head, action: "tool", detail: `repeat ${label}`, evidence_id: rec.evidence_id });
      } else {
        deliver(rec);
        lines.push(`${rec.evidence_id} delivered — now ON FILE above.`);
        trace.push({ turn: turnNo, raw_reply_head: head, action: "tool", detail: label, evidence_id: rec.evidence_id });
      }
      lastFocus = typeof rec.args.statement === "string"
        ? (rec.args.statement as string)
        : ["search_filing_text", "get_source_page"].includes(s.c.tool) ? "filing_text" : s.c.tool;
      recentFocus.push(lastFocus);
      if (recentFocus.length > FOCUS_WINDOW) recentFocus.shift();
    }
    let out = lines.join("\n");
    // Evaluated once per TURN, not once per call: a batch that sweeps four
    // statements is the opposite of tunnelling and must not trip the detector.
    if (recentFocus.length === FOCUS_WINDOW && new Set(recentFocus).size === 1 && turnNo < MAX_TURNS - 2) {
      out += ` NOTE: your last ${FOCUS_WINDOW} queries all probed ${lastFocus} — a real event leaves counterparts elsewhere; test a different lead, or emit what is already supported.`;
    }
    return out;
  };

  /**
   * The plan as the model sees it each turn. Per open lead it names which of
   * the statements that lead itself nominated have still not been read — the
   * cheapest honest coverage signal available, and it reuses state the loop
   * already keeps for the repeat detector.
   */
  const renderPlan = (): string => {
    if (!plan.length) return `PLAN: none committed — your first action must be "plan".`;
    const open = plan.filter((l) => l.status === "open");
    const lines = plan.map((l) => {
      if (l.status === "closed") return `  [${l.lead_id}] CLOSED — ${l.resolution ?? ""}`;
      const unread = l.statements.filter((s) => !examinedStatements.has(s));
      return `  [${l.lead_id}] OPEN — ${l.question}` +
        (unread.length ? ` · not yet read: ${unread.join(", ")}` : ` · every statement it named has been read`);
    });
    return `PLAN (${open.length} open of ${plan.length}; you cannot conclude or abstain while any is open):\n${lines.join("\n")}`;
  };

  const system = SYSTEM
    .replace("__TOOL_CATALOG__", toolCatalog())
    .replace("__FINDING_SCHEMA__", FINDING_SCHEMA_PROMPT)
    .replace("__MAX_BATCH__", String(MAX_BATCH));
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
      `\n\n${renderPlan()}\n\n` +
      `HYPOTHESIS LEDGER (yours to maintain):\n${JSON.stringify(hypotheses)}\n\n` +
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
        // deepseek-flash leads every lane (user decision, 2026-08-17). Luna-pro
        // drops to second — it kept the lead here until then because multi-turn
        // investigation is where model capability binds and its 1.05M context
        // absorbs a full case file without truncation pressure.
        // ⚠️ The docs/ANALYST_V2.md acceptance result (Albaraka free-provision
        // story found cold, zero unsupported claims) was measured on a LUNA-PRO
        // LEAD. Re-run the eval corpus (scripts/analyst/eval_research.py) before
        // treating that result as still current under this chain — the loop is
        // budgeted in turns, so a lead change moves the discovery ceiling.
        providerOrder: [
          "openrouter/deepseek-v4-flash",
          "openrouter/gpt-5.6-luna-pro",
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
    if (a.action === "plan") {
      const raw = Array.isArray(a.leads) ? a.leads : null;
      if (!raw || raw.length === 0) {
        protocolErrors++;
        lastResult = `PROTOCOL ERROR: "plan" needs a non-empty "leads" array of {"lead_id","question","statements","status"} objects.`;
        trace.push({ turn, raw_reply_head: head, action: "plan", detail: "malformed", error: "no leads" });
        continue;
      }
      plan = raw.slice(0, 8).map((r) => {
        const o = (r ?? {}) as Record<string, unknown>;
        return {
          lead_id: String(o.lead_id ?? ""),
          question: String(o.question ?? ""),
          statements: Array.isArray(o.statements) ? o.statements.map(String) : [],
          status: o.status === "closed" ? "closed" : "open",
          resolution: typeof o.resolution === "string" ? o.resolution : undefined,
        } satisfies Lead;
      });
      // Closing a lead without saying what settled it is exactly how "I never
      // looked" disappears from the record. Re-open rather than reject: the rest
      // of the plan is still good, and a rejected action costs a whole turn.
      const reopened = plan.filter((l) => l.status === "closed" && !(l.resolution ?? "").trim());
      for (const l of reopened) l.status = "open";
      const openCount = plan.filter((l) => l.status === "open").length;
      lastResult =
        `plan committed — ${plan.length} leads, ${openCount} open.` +
        (reopened.length
          ? ` ⚠ ${reopened.map((l) => l.lead_id).join(", ")} were closed with no resolution and have been RE-OPENED: closing a lead requires saying what settled it.`
          : "") +
        ` Investigate.`;
      trace.push({ turn, raw_reply_head: head, action: "plan", detail: `${plan.length} leads, ${openCount} open` });
      continue;
    }
    if (a.action === "tool") {
      lastResult = await executeCalls(
        [{ tool: String(a.tool ?? ""), args: (a.args as Record<string, unknown>) ?? {} }],
        turn,
        head,
      );
      continue;
    }
    if (a.action === "tools") {
      const raw = Array.isArray(a.calls) ? a.calls : null;
      if (!raw || raw.length === 0) {
        protocolErrors++;
        lastResult = `PROTOCOL ERROR: "tools" needs a non-empty "calls" array of {"tool":"<name>","args":{...}} objects.`;
        trace.push({ turn, raw_reply_head: head, action: "tools", detail: "malformed", error: "no calls" });
        continue;
      }
      const calls = raw.slice(0, MAX_BATCH).map((r) => {
        const o = (r ?? {}) as Record<string, unknown>;
        return { tool: String(o.tool ?? ""), args: (o.args as Record<string, unknown>) ?? {} };
      });
      lastResult = await executeCalls(calls, turn, head);
      // Truncate rather than reject: the calls that fit still ran, and telling
      // the model which ones were dropped is cheaper than spending the turn on
      // a protocol error that returns no evidence at all.
      if (raw.length > MAX_BATCH) {
        lastResult += `\nNOTE: ${raw.length} calls requested but ${MAX_BATCH} is the per-turn maximum — the first ${MAX_BATCH} ran, the rest were dropped. Re-request any you still need.`;
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
    if (a.action === "abstain" || a.action === "conclude") {
      // Both exits, not just conclude: gating only one would leave the other as
      // the way out, and "abstained" on work never started is the exact record
      // this is here to prevent.
      const stillOpen = plan.filter((l) => l.status === "open");
      if (stillOpen.length && !exitBlocked) {
        exitBlocked = true;
        lastResult =
          `CANNOT ${a.action.toUpperCase()} YET — ${stillOpen.length} lead(s) you committed to are still open: ` +
          stillOpen.map((l) => `${l.lead_id} (${l.question})`).join("; ") + `. ` +
          `Test them, or re-issue "plan" closing each with a resolution. ` +
          `"Looked, nothing there" is a valid resolution — leaving it open is not.`;
        trace.push({ turn, raw_reply_head: head, action: a.action, detail: `blocked — ${stillOpen.length} open leads` });
        continue;
      }
      if (a.action === "abstain") {
        abstained = findings.length === 0;
        abstainReason = String(a.reason ?? "");
        trace.push({ turn, raw_reply_head: head, action: "abstain", detail: abstainReason.slice(0, 200) });
      } else {
        trace.push({ turn, raw_reply_head: head, action: "conclude", detail: String(a.reason ?? "").slice(0, 200) });
      }
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
    plan,
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
