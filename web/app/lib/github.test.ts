import { describe, expect, it } from "vitest";
import {
  AUDIT_WORKFLOW,
  DISPATCHABLE,
  REEXTRACT_WORKFLOW,
  WORKFLOWS,
  dispatchWorkflow,
} from "./github";

/**
 * The coverage matrix's "Force re-extract this cell" button was dead: the admin
 * route allowed `WORKFLOWS + REEXTRACT_WORKFLOW`, while the guard inside
 * dispatchWorkflow was built from WORKFLOWS alone — and REEXTRACT_WORKFLOW is
 * deliberately not in WORKFLOWS. Every press returned 502
 * "workflow not allowed: reextract-statement.yml", which read as a GitHub
 * outage rather than a bug on our side.
 */
describe("dispatch allow-list", () => {
  it("includes the targeted re-extract workflow", () => {
    expect(DISPATCHABLE.has(REEXTRACT_WORKFLOW)).toBe(true);
  });

  it("includes every workflow the admin panel offers a button for", () => {
    for (const w of WORKFLOWS) expect(DISPATCHABLE.has(w.file)).toBe(true);
    expect(DISPATCHABLE.has(AUDIT_WORKFLOW)).toBe(true);
  });

  it("keeps re-extract out of the panel's button list", () => {
    // It needs a statement, so it is not a blind trigger — that is WHY the two
    // lists differ, and why they have to be derived from one place.
    expect(WORKFLOWS.map((w) => w.file)).not.toContain(REEXTRACT_WORKFLOW);
  });

  it("still refuses a workflow that is not on the list", async () => {
    await expect(dispatchWorkflow("rm-rf.yml")).rejects.toThrow(/not allowed/);
  });

  it("gets past the allow-list for re-extract (and fails later, on the token)", async () => {
    // The allow-list check runs before the token lookup, so an allowed workflow
    // must NOT fail with "not allowed" — proving the guard let it through.
    await expect(dispatchWorkflow(REEXTRACT_WORKFLOW)).rejects.not.toThrow(/not allowed/);
  });
});
