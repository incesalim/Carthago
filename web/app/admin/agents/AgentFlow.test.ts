import { describe, expect, it } from "vitest";
// Relative, not "@/…": vitest does not resolve the alias here. The component
// gets away with the alias because its import is types-only and erases.
import { AGENTS } from "../../lib/agents-registry";
import { wrap } from "./AgentFlow";

/**
 * These assert BEHAVIOUR, not the constants. An earlier version hard-coded the
 * 19-char default and broke the moment the swimlane columns widened it to 23 —
 * a failing test that signalled nothing about the code being wrong.
 */
describe("wrap", () => {
  it("uses every available line before eliding", () => {
    const out = wrap("QoQ/YoY z-scores · sign flips · reconciliation breaks", 20, 3);
    expect(out.length).toBe(3);
    expect(out.slice(0, -1).some((l) => l.endsWith("…"))).toBe(false);
  });

  it("leaves a short detail alone", () => {
    expect(wrap("survivors")).toEqual(["survivors"]);
  });

  it("hard-breaks a token too long to ever fit", () => {
    const out = wrap("registry-allowlisted tools", 19, 2);
    for (const line of out) expect(line.length).toBeLessThanOrEqual(19);
    expect(out[0]).toBe("registry-allowliste");
  });

  it("elides visibly when it genuinely cannot fit", () => {
    const out = wrap("one two three four five six seven eight nine ten", 10, 2);
    expect(out.length).toBe(2);
    expect(out[1]).toMatch(/…$/);
  });

  it("never exceeds the line budget", () => {
    const out = wrap("a".repeat(60), 19, 2);
    expect(out.length).toBeLessThanOrEqual(2);
    for (const line of out) expect(line.length).toBeLessThanOrEqual(19);
  });
});

/**
 * The invariant that actually matters on the page: a stage detail must be
 * READABLE. The first shipped diagram elided nearly every one of them, which
 * looks like information without being any. If a new stage detail is too long
 * for the node, this fails here rather than quietly growing an ellipsis in the
 * UI — either shorten the detail or resize the node deliberately.
 */
describe("registry stage details fit their nodes", () => {
  it("renders every stage detail without eliding", () => {
    const offenders: string[] = [];
    for (const agent of AGENTS) {
      for (const stage of agent.stages) {
        if (!stage.detail) continue;
        const lines = wrap(stage.detail); // component defaults = the real node size
        if (lines.some((l) => l.endsWith("…"))) {
          offenders.push(`${agent.id}/${stage.id}: "${stage.detail}" (${stage.detail.length} chars)`);
        }
      }
    }
    expect(offenders, `stage details too long for the node:\n  ${offenders.join("\n  ")}`).toEqual([]);
  });
});
