/**
 * POST /api/admin/dispatch { workflow } — manually trigger an allow-listed
 * refresh workflow on master via workflow_dispatch. Admin-gated.
 */
import { requireAdminOr403 } from "@/app/lib/admin-auth";
import {
  AUDIT_BANKS,
  AUDIT_WORKFLOW,
  GitHubNotConfigured,
  WORKFLOWS,
  dispatchWorkflow,
} from "@/app/lib/github";

export const dynamic = "force-dynamic";

const ALLOWED = new Set(WORKFLOWS.map((w) => w.file));
const AUDIT_BANK_SET = new Set<string>(AUDIT_BANKS);

export async function POST(req: Request) {
  const gate = await requireAdminOr403();
  if ("response" in gate) return gate.response;

  let payload: { workflow?: unknown; bank?: unknown };
  try {
    payload = (await req.json()) ?? {};
  } catch {
    return Response.json({ error: "invalid JSON body" }, { status: 400 });
  }
  const { workflow, bank } = payload;
  if (typeof workflow !== "string" || !ALLOWED.has(workflow)) {
    return Response.json({ error: "unknown or disallowed workflow" }, { status: 400 });
  }

  // Optional `bank` input — only the audit workflow accepts it, and only a
  // known ticker (guards against injecting an arbitrary workflow input).
  let inputs: Record<string, string> | undefined;
  if (bank != null && bank !== "") {
    if (workflow !== AUDIT_WORKFLOW) {
      return Response.json({ error: "bank is only valid for the audit workflow" }, { status: 400 });
    }
    if (typeof bank !== "string" || !AUDIT_BANK_SET.has(bank)) {
      return Response.json({ error: "unknown bank" }, { status: 400 });
    }
    inputs = { bank };
  }

  try {
    await dispatchWorkflow(workflow, { inputs });
    return Response.json({ ok: true, workflow, ...(inputs ? { bank: inputs.bank } : {}) });
  } catch (e) {
    if (e instanceof GitHubNotConfigured) {
      return Response.json(
        { error: "GitHub token not configured (set GITHUB_DISPATCH_TOKEN)" },
        { status: 409 },
      );
    }
    const detail = e instanceof Error ? e.message : "dispatch failed";
    return Response.json({ error: detail }, { status: 502 });
  }
}
