import { describe, expect, it } from "vitest";
import { AGENTS, RUNNABLE_AGENTS, agentById, validateAgentInputs } from "./agents-registry";

describe("agent registry shape", () => {
  it("has unique agent ids", () => {
    const ids = AGENTS.map((a) => a.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it("resolves every stage edge to a declared stage", () => {
    for (const agent of AGENTS) {
      const ids = new Set(agent.stages.map((s) => s.id));
      expect(new Set(agent.stages.map((s) => s.id)).size, `${agent.id} duplicate stage id`).toBe(
        agent.stages.length,
      );
      for (const e of agent.edges) {
        expect(ids.has(e.from), `${agent.id}: edge from unknown stage "${e.from}"`).toBe(true);
        expect(ids.has(e.to), `${agent.id}: edge to unknown stage "${e.to}"`).toBe(true);
      }
    }
  });

  it("gives every agent at least one stage and something to show", () => {
    for (const agent of AGENTS) {
      expect(agent.stages.length, `${agent.id} has no stages`).toBeGreaterThan(0);
      expect(agent.question.length, `${agent.id} has no question`).toBeGreaterThan(0);
      expect(agent.outputs.length, `${agent.id} has no outputs`).toBeGreaterThan(0);
    }
  });

  it("declares well-formed inputs", () => {
    for (const agent of AGENTS) {
      const names = agent.inputs.map((i) => i.name);
      expect(new Set(names).size, `${agent.id} duplicate input name`).toBe(names.length);
      for (const input of agent.inputs) {
        if (input.type === "choice") {
          expect(input.options?.length, `${agent.id}.${input.name} choice without options`).toBeGreaterThan(0);
          if (input.default != null) expect(input.options).toContain(input.default);
        }
        if (input.type === "boolean") expect(["true", "false"]).toContain(input.default ?? "false");
        if (input.pattern && input.default) {
          expect(
            new RegExp(input.pattern).test(input.default),
            `${agent.id}.${input.name} default fails its own pattern`,
          ).toBe(true);
        }
      }
    }
  });

  it("only marks an agent runnable when it names a workflow file", () => {
    for (const agent of RUNNABLE_AGENTS) expect(agent.workflowFile).toMatch(/\.yml$/);
    expect(RUNNABLE_AGENTS.length).toBeLessThanOrEqual(AGENTS.length);
  });

  /**
   * Deliberate omission, pinned: analyst-daily.yml accepts `push`, which
   * rebuilds three D1 tables wholesale (~9,030 billed rows). It is a publishing
   * decision, not an agent parameter, and must not be one click from a run
   * form. If someone adds it, this test is where the argument happens.
   */
  it("never exposes a D1 push toggle in the run form", () => {
    for (const agent of AGENTS) {
      expect(agent.inputs.map((i) => i.name), `${agent.id} exposes push`).not.toContain("push");
    }
  });
});

describe("validateAgentInputs", () => {
  const agent = agentById("analyst-research")!;

  it("fills declared defaults when a field is omitted", () => {
    const out = validateAgentInputs(agent, {});
    expect(out).toEqual({
      inputs: { banks: "ALBRK", period: "2025Q1", kind: "unconsolidated", scout_only: "false" },
    });
  });

  it("rejects an unknown input rather than dropping it", () => {
    const out = validateAgentInputs(agent, { banks: "TEB", nonsense: "1" });
    expect(out).toEqual({ error: "unknown input: nonsense" });
  });

  it("enforces the period pattern", () => {
    expect(validateAgentInputs(agent, { period: "2025-Q1" })).toEqual({
      error: expect.stringContaining("period does not match"),
    });
    expect(validateAgentInputs(agent, { period: "2024Q4" })).toMatchObject({
      inputs: { period: "2024Q4" },
    });
  });

  it("enforces the ticker shape", () => {
    expect(validateAgentInputs(agent, { banks: "albrk" })).toMatchObject({
      error: expect.stringContaining("banks does not match"),
    });
    expect(validateAgentInputs(agent, { banks: "ALBRK,TEB" })).toMatchObject({
      inputs: { banks: "ALBRK,TEB" },
    });
  });

  it("enforces choice membership and boolean shape", () => {
    expect(validateAgentInputs(agent, { kind: "solo" })).toMatchObject({
      error: expect.stringContaining("kind must be one of"),
    });
    expect(validateAgentInputs(agent, { scout_only: "yes" })).toEqual({
      error: "scout_only must be true or false",
    });
  });

  it("lets a legitimately blank choice through so the workflow default applies", () => {
    const reg = agentById("regulation-brief")!;
    const out = validateAgentInputs(reg, { llm: "" });
    expect(out).toMatchObject({ inputs: { force: "false" } });
    expect("inputs" in out && out.inputs.llm).toBeUndefined();
  });
});
