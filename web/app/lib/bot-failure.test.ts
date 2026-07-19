import { describe, expect, it } from "vitest";
import { llmFailureMessage } from "./bot";

describe("llmFailureMessage — say which kind of failure it was", () => {
  it("names an exhausted free tier as temporary", () => {
    const m = llmFailureMessage(
      "all LLM providers failed — groq/openai/gpt-oss-120b: HTTP 429: rate_limit_exceeded; " +
      "cerebras/gpt-oss-120b: HTTP 429: too many requests",
    );
    expect(m).toContain("quota");
    expect(m).toContain("few minutes");
  });

  it("says a credentials failure needs an operator, not a retry", () => {
    const m = llmFailureMessage("all LLM providers failed — groq: HTTP 401: invalid api key");
    expect(m).toContain("operator");
    expect(m).not.toContain("try again shortly");
  });

  it("distinguishes an unconfigured chain", () => {
    expect(llmFailureMessage("no LLM provider configured")).toContain("No language model");
  });

  it("distinguishes a timeout", () => {
    expect(llmFailureMessage("The operation was aborted")).toContain("timed out");
  });

  it("falls back to the generic message for an unknown cause", () => {
    expect(llmFailureMessage("something odd")).toContain("unavailable right now");
  });
});
