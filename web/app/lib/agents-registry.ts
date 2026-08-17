/**
 * Agent registry — the hand-authored data model behind /admin/agents.
 *
 * Every model-driven lane in the system, described once: what question it
 * answers and for whom, where it runs, what it may be handed, what proves its
 * output, and the internal stages worth drawing. The page renders this; the
 * dispatch route validates against it; `scripts/check_agents_registry.py`
 * diffs it against `.github/workflows/` so a renamed dispatch input fails CI
 * instead of 422-ing at the moment someone presses Run.
 *
 * Pure and dependency-free on purpose — it is imported by a server component,
 * an API route and a test, and must stay cheap in the Worker bundle.
 *
 * ── Adding an agent ────────────────────────────────────────────────────────
 * Append an `AgentDef`. `stages`/`edges` draw the diagram, `inputs` generate
 * BOTH the run form and its server-side validation. If it runs in Actions,
 * `workflowFile` must exist and every input `name` must be a real
 * `workflow_dispatch` input of that file — the gate enforces both directions.
 *
 * ── Two deliberate omissions ───────────────────────────────────────────────
 *  - `analyst-daily.yml`'s `push` input is NOT exposed. It is a publishing
 *    decision, not an agent parameter, and it triggers a `_FULL_REBUILD` of
 *    three D1 tables (~9,030 billed rows). Rows written are ~1000× the price
 *    of a read; that button belongs behind a deliberate dispatch, not one
 *    click away from a run form.
 *  - Worker-resident agents (the Q&A bot) carry no `workflowFile`. They answer
 *    per request and cannot be "triggered"; the page shows them for the map,
 *    with no Run control.
 */

export type AgentStatus = "live" | "evaluation" | "planned";
export type AgentRuntime = "actions" | "worker";

/** What a run of this agent persists. Surfaced in the confirm dialog — a D1
 *  write is a cost event, not a neutral one. */
export type AgentWrites = "artifacts" | "d1" | "none";

/**
 * Stage kinds carry the architectural claim this whole layer rests on:
 * deterministic code finds and proves, the model only investigates and writes.
 * The diagram colours them apart so a glance shows where judgment enters.
 */
export type StageKind = "deterministic" | "model" | "guard" | "output";

export interface AgentStage {
  id: string;
  label: string;
  kind: StageKind;
  /** Second line in the node — what it actually does. */
  detail?: string;
}

/** `flow` advances; `loop` returns for another turn; `reject` discards;
 *  `retry` is a bounded second chance with the failure named. */
export type StageEdgeKind = "flow" | "loop" | "reject" | "retry";

export interface AgentStageEdge {
  from: string;
  to: string;
  kind?: StageEdgeKind;
  label?: string;
}

export interface AgentInput {
  /** MUST match the workflow_dispatch input name — CI-gated. */
  name: string;
  label: string;
  type: "text" | "choice" | "boolean";
  options?: string[];
  default?: string;
  placeholder?: string;
  /** Serialized regex, applied server-side before dispatch. */
  pattern?: string;
  help?: string;
}

export interface AgentDef {
  id: string;
  name: string;
  /** One line: what it is. */
  tagline: string;
  /** Who asks this, in the language of the person asking. */
  audience: string;
  /** The question a run answers. The reason the agent exists. */
  question: string;
  status: AgentStatus;
  runtime: AgentRuntime;
  writes: AgentWrites;
  /** Absent for Worker-resident agents — nothing to dispatch. */
  workflowFile?: string;
  /** Repo-relative doc that explains it properly. */
  docs?: string;
  /** Model chain, in failover order. */
  models: string;
  /** The thing that stops a wrong number reaching a reader. */
  guardrail: string;
  outputs: string[];
  stages: AgentStage[];
  edges: AgentStageEdge[];
  inputs: AgentInput[];
  /** Caveats worth reading before pressing Run. */
  notes?: string[];
}

const KIND_INPUT: AgentInput = {
  name: "kind",
  label: "Basis",
  type: "choice",
  options: ["unconsolidated", "consolidated"],
  default: "unconsolidated",
  help: "Consolidated matches how banks present themselves and is where group events appear; unconsolidated is the solo bank.",
};

const PERIOD_INPUT: AgentInput = {
  name: "period",
  label: "Period",
  type: "text",
  default: "2026Q1",
  placeholder: "YYYYQn",
  pattern: "^\\d{4}Q[1-4]$",
};

export const AGENTS: AgentDef[] = [
  // ── Analyst V2 — the investigation ────────────────────────────────────────
  {
    id: "analyst-research",
    name: "Research analyst",
    tagline: "Agentic discovery over deterministic evidence",
    audience: "Credit, DFI and treasury desks reading one bank's quarter",
    question: "What actually happened at this bank this quarter that the ratios don't say?",
    status: "evaluation",
    runtime: "actions",
    writes: "artifacts",
    workflowFile: "analyst-research.yml",
    docs: "docs/ANALYST_V2.md",
    models: "deepseek-v4-flash (pinned @Baidu, seeded) → gpt-5.6-luna-pro → free OSS chain (nemotron excluded)",
    guardrail: "Deterministic verifier, 13 checks, run again at emission — findings that fail are excluded by name",
    outputs: [
      "analyst_summary_<B>_<P>_<K>.md — survivors only",
      "findings + verification + hypotheses JSON",
      "evidence.jsonl + research_trace.jsonl — every turn, every id",
    ],
    stages: [
      { id: "scout", label: "Anomaly scout", kind: "deterministic", detail: "QoQ/YoY z-scores · sign flips · reconciliation breaks" },
      { id: "plan", label: "Committed plan", kind: "model", detail: "2–5 leads named up front · closing one needs a reason" },
      { id: "loop", label: "Research loop", kind: "model", detail: "one action per turn · ≤4 concurrent tool calls · 32 turns · 14 min" },
      { id: "tools", label: "12 typed tools", kind: "deterministic", detail: "read-only · registry-allowlisted · EvidenceRecord out" },
      { id: "ledger", label: "Hypothesis ledger", kind: "model", detail: "open / supported / rejected / unresolved" },
      { id: "finding", label: "Structured finding", kind: "model", detail: "claims with subject · value · derivation · evidence ids" },
      { id: "verifier", label: "Verifier", kind: "guard", detail: "evidence resolution · association · arithmetic · causal language" },
      { id: "summary", label: "Rendered summary", kind: "output", detail: "survivors, with failures named" },
    ],
    edges: [
      { from: "scout", to: "plan", label: "ranked leads" },
      { from: "plan", to: "loop", label: "committed" },
      { from: "loop", to: "plan", kind: "loop", label: "re-plan / close a lead" },
      { from: "loop", to: "tools", kind: "flow" },
      { from: "tools", to: "loop", kind: "loop", label: "evidence on file" },
      { from: "loop", to: "ledger", kind: "flow" },
      { from: "ledger", to: "loop", kind: "loop" },
      { from: "loop", to: "finding", kind: "flow" },
      { from: "finding", to: "verifier", kind: "flow" },
      { from: "verifier", to: "summary", kind: "flow", label: "pass" },
      { from: "verifier", to: "loop", kind: "retry", label: "one repair" },
    ],
    inputs: [
      { name: "banks", label: "Banks", type: "text", default: "ALBRK", placeholder: "ALBRK or ALBRK,TEB", pattern: "^[A-Z]{2,10}(,[A-Z]{2,10})*$", help: "Comma-separated tickers. Each runs its own investigation." },
      { ...PERIOD_INPUT, default: "2025Q1" },
      KIND_INPUT,
      { name: "scout_only", label: "Scout only", type: "boolean", default: "false", help: "Deterministic half only — no model spend." },
    ],
    notes: [
      "Artifact-only by design: no D1 writes, no schedule, nothing publishes on its own.",
      "Abstention is a success. A run that finds nothing material and says what it checked is green.",
      "A full loop is up to 32 model calls carrying a large case file — the expensive mode. Scout only is free.",
    ],
  },

  // ── Analyst V1 — the memo, and the regression baseline ────────────────────
  {
    id: "analyst-memo",
    name: "Analyst memo",
    tagline: "Deterministic assembly, model prose, figure guard",
    audience: "Anyone who wants the quarter written up rather than investigated",
    question: "What is the one story of this bank's quarter, and what are the figures behind it?",
    status: "live",
    runtime: "actions",
    writes: "artifacts",
    workflowFile: "analyst-daily.yml",
    docs: "docs/ANALYST.md",
    models: "deepseek-v4-flash (pinned, seeded) → free OSS chain",
    guardrail: "Figure guard — every amount and percent must appear in the data block, or the paragraph is dropped whole",
    outputs: [
      "analyst_memo_<B>_<P>_<K>.json — body + guard verdict + gates",
      "analyst_sections_<B>_<P>_<K>.json — the assembled figures",
      "analyst_signals.jsonl — detector output, no model involved",
    ],
    stages: [
      { id: "detect", label: "Detectors", kind: "deterministic", detail: "unit switches · restatements · opinion changes · CAR−CET1" },
      { id: "assembly", label: "Assembly", kind: "deterministic", detail: "13 sections · peers · derivations precomputed" },
      { id: "gates", label: "Story gates", kind: "deterministic", detail: "6 candidates ruled LIVE/DEAD with the number · first live = LEAD" },
      { id: "block", label: "The data block", kind: "deterministic", detail: "the model's whole world — and the guard's answer key" },
      { id: "write", label: "Model writes", kind: "model", detail: "~2,500–4,000 words, fixed 13-section skeleton" },
      { id: "guard", label: "Figure guard", kind: "guard", detail: "figures · denomination · relation · placeholder · structure" },
      { id: "memo", label: "Memo artifact", kind: "output", detail: "hash-gated — unchanged data never regenerates" },
    ],
    edges: [
      { from: "detect", to: "assembly", label: "signals" },
      { from: "assembly", to: "gates" },
      { from: "gates", to: "block" },
      { from: "block", to: "write" },
      { from: "write", to: "guard" },
      { from: "guard", to: "memo", label: "clean" },
      { from: "guard", to: "write", kind: "retry", label: "one retry, problems named" },
      { from: "guard", to: "memo", kind: "reject", label: "still failing → FAILED, never published" },
    ],
    inputs: [
      { name: "banks", label: "Banks", type: "text", default: "CALIBRATE", placeholder: "GARAN or CALIBRATE or NONE", pattern: "^(CALIBRATE|NONE|[A-Z]{2,10}(,[A-Z]{2,10})*)$", help: "CALIBRATE = the ALBRK+SKBNK pair the hand memos cover. NONE = detectors only." },
      PERIOD_INPUT,
      KIND_INPUT,
      { name: "force_regen", label: "Force regenerate", type: "boolean", default: "false", help: "Without this, a memo whose data hash is unchanged is SKIPPED — you get no file, which looks like a failure and isn't." },
    ],
    notes: [
      "The `push` input (D1 write, ~9,030 rows) is deliberately not exposed here — dispatch it explicitly when you mean it.",
      "A memo that fails its fact-check turns the run red on purpose. That is a result to read, not a broken job.",
    ],
  },

  // ── Regulation briefing — single pass, contradiction-checked ──────────────
  {
    id: "regulation-brief",
    name: "Regulation briefing",
    tagline: "The week's TCMB/BDDK bodies into the regime in force",
    audience: "Anyone who needs to know what rule changed this week",
    question: "What did the regulator do since the last briefing, and does it contradict what we already published?",
    status: "live",
    runtime: "actions",
    writes: "d1",
    workflowFile: "summarize-regulations.yml",
    docs: "docs/OPERATIONS.md",
    models: "deepseek-flash (default, pinned @Baidu) or kimi, per the BRIEFING_LLM repo variable",
    guardrail: "find_contradictions() over the briefing, against the annual policy baseline",
    outputs: ["Weekly briefing rows in D1 → /regulation"],
    stages: [
      { id: "bodies", label: "Regulation bodies", kind: "deterministic", detail: "TCMB + BDDK feeds from the R2 snapshot" },
      { id: "baseline", label: "Annual baseline", kind: "deterministic", detail: "the hand-pinned 'Monetary Policy for YYYY' grounding" },
      { id: "summarize", label: "Model summarizes", kind: "model", detail: "per-section bullets, figures transcribed not inferred" },
      { id: "contradict", label: "Contradiction check", kind: "guard", detail: "against the baseline regime" },
      { id: "d1", label: "D1 → /regulation", kind: "output", detail: "content-hashed — a quiet week is a no-op" },
    ],
    edges: [
      { from: "bodies", to: "summarize" },
      { from: "baseline", to: "summarize", label: "grounding" },
      { from: "summarize", to: "contradict" },
      { from: "contradict", to: "d1", label: "clean" },
    ],
    inputs: [
      { name: "force", label: "Force regenerate", type: "boolean", default: "false", help: "Quiet weeks are a no-op otherwise." },
      { name: "llm", label: "Provider", type: "choice", options: ["", "kimi", "deepseek-flash"], default: "", help: "Blank = the BRIEFING_LLM repo variable." },
    ],
    notes: [
      "This one WRITES TO D1. A manual run bills rows; the content hash makes an unchanged week free.",
      "The annual baseline pin (baseline_url / baseline_year) is a once-a-year hand operation — dispatch it from Actions, not here.",
    ],
  },

  // ── Q&A bot — Worker-resident, no dispatch ────────────────────────────────
  {
    id: "qa-bot",
    name: "Q&A bot",
    tagline: "Natural-language questions against D1, read-only",
    audience: "Whoever is holding the phone",
    question: "Any question a reader can ask of the published numbers.",
    status: "live",
    runtime: "worker",
    writes: "none",
    docs: "docs/TELEGRAM_BOT.md",
    models: "deepseek-v4-flash (pinned @Baidu) → nemotron-3-super → Groq gpt-oss-120b → Cerebras gpt-oss-120b → gemma-4-31b",
    guardrail: "Read-only SQL gate + gotData guard + unsupportedFigures — a figure with no row behind it is stripped",
    outputs: ["A Telegram reply", "The query trace, per step"],
    stages: [
      { id: "question", label: "Question", kind: "deterministic", detail: "Telegram webhook, or /api/admin/bot-ask" },
      { id: "agent", label: "Agent loop", kind: "model", detail: "wall-clock budgeted — steps cost what the model costs" },
      { id: "sql", label: "Read-only SQL", kind: "deterministic", detail: "bot-sql.ts gate — SELECT only, allowlisted" },
      { id: "answer", label: "Grounded answer", kind: "guard", detail: "gotData + unsupportedFigures before it sends" },
      { id: "reply", label: "Reply", kind: "output" },
    ],
    edges: [
      { from: "question", to: "agent" },
      { from: "agent", to: "sql", kind: "flow" },
      { from: "sql", to: "agent", kind: "loop", label: "rows" },
      { from: "agent", to: "answer", kind: "flow" },
      { from: "answer", to: "reply", label: "grounded" },
      { from: "answer", to: "agent", kind: "retry", label: "no data → say so" },
    ],
    inputs: [],
    notes: [
      "Runs per message inside the Worker — there is nothing to trigger from here.",
      "Metered since 2026-08-17: the head of its chain is paid. It writes no D1 rows, but ~70–100k input tokens per question makes BOT_GLOBAL_DAILY (default 300) a spend cap, not just an abuse cap.",
      "To exercise it manually: GET /api/admin/bot-ask?key=<BOT_TEST_KEY>&q=… returns the reply plus the full query trace.",
    ],
  },
];

/** Agents that can be dispatched from the panel. */
export const RUNNABLE_AGENTS = AGENTS.filter(
  (a): a is AgentDef & { workflowFile: string } => Boolean(a.workflowFile),
);

export function agentById(id: string): AgentDef | undefined {
  return AGENTS.find((a) => a.id === id);
}

/**
 * Validate a submitted input bag against an agent's declared inputs.
 * Returns the dispatch payload, or the first problem found. Unknown keys are
 * rejected rather than dropped — a typo'd field silently becoming a default is
 * how you dispatch the wrong thing and believe you dispatched the right one.
 */
export function validateAgentInputs(
  agent: AgentDef,
  raw: Record<string, unknown>,
): { inputs: Record<string, string> } | { error: string } {
  const declared = new Map(agent.inputs.map((i) => [i.name, i]));
  for (const key of Object.keys(raw)) {
    if (!declared.has(key)) return { error: `unknown input: ${key}` };
  }
  const inputs: Record<string, string> = {};
  for (const spec of agent.inputs) {
    const supplied = raw[spec.name];
    const value = supplied == null || supplied === "" ? spec.default : supplied;
    if (value == null || value === "") {
      // An empty optional (the regulation `llm` choice) is legitimately blank:
      // GitHub then applies the workflow's own default.
      if (spec.type === "choice" && spec.options?.includes("")) continue;
      return { error: `${spec.name} is required` };
    }
    if (typeof value !== "string") return { error: `${spec.name} must be a string` };
    if (spec.type === "boolean") {
      if (value !== "true" && value !== "false") return { error: `${spec.name} must be true or false` };
    } else if (spec.type === "choice") {
      if (!spec.options?.includes(value)) return { error: `${spec.name} must be one of: ${spec.options?.join(", ")}` };
    } else if (spec.pattern && !new RegExp(spec.pattern).test(value)) {
      return { error: `${spec.name} does not match ${spec.pattern}` };
    }
    inputs[spec.name] = value;
  }
  return { inputs };
}
