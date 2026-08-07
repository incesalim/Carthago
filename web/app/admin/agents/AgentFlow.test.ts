import { describe, expect, it } from "vitest";
import { wrap } from "./AgentFlow";

/**
 * The first version broke out of the loop as soon as it filled line one, so
 * every node detail rendered as a single truncated line — visible only in a
 * browser, invisible to tsc and to every other test. Pinned here.
 */
describe("wrap", () => {
  it("uses both lines before truncating", () => {
    const out = wrap("QoQ/YoY z-scores · sign flips · reconciliation breaks");
    expect(out.length).toBe(2);
    expect(out[0]).not.toMatch(/…$/);
  });

  it("fills greedily and leaves a short detail alone", () => {
    expect(wrap("read-only · SELECT only")).toEqual(["read-only · SELECT", "only"]);
    expect(wrap("survivors")).toEqual(["survivors"]);
  });

  it("hard-breaks a token too long to ever fit", () => {
    // `registry-allowlisted` is 20 chars against a 19-char line — word wrapping
    // alone leaves it overflowing the node.
    const out = wrap("registry-allowlisted tools");
    for (const line of out) expect(line.length).toBeLessThanOrEqual(19);
  });

  it("elides only what does not fit", () => {
    const out = wrap("one two three four five six seven eight nine ten eleven twelve");
    expect(out.length).toBe(2);
    expect(out[1]).toMatch(/…$/);
  });

  it("never exceeds the line budget", () => {
    const out = wrap("a".repeat(60), 19, 2);
    expect(out.length).toBeLessThanOrEqual(2);
    for (const line of out) expect(line.length).toBeLessThanOrEqual(19);
  });
});
