/**
 * POST /api/admin/dispatch { workflow, bank?, period? } — manually trigger an
 * allow-listed refresh workflow on master via workflow_dispatch. Admin-gated.
 * `bank`/`period` are audit-only; `period` forces a targeted re-extraction.
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

  let payload: { workflow?: unknown; bank?: unknown; period?: unknown };
  try {
    payload = (await req.json()) ?? {};
  } catch {
    return Response.json({ error: "invalid JSON body" }, { status: 400 });
  }
  const { workflow, bank, period } = payload;
  if (typeof workflow !== "string" || !ALLOWED.has(workflow)) {
    return Response.json({ error: "unknown or disallowed workflow" }, { status: 400 });
  }

  // Optional `bank` / `period` inputs — only the audit workflow accepts them,
  // and only a known ticker / well-formed quarter (guards against injecting an
  // arbitrary workflow input). `period` forces a targeted re-extraction.
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
  if (period != null && period !== "") {
    if (!inputs) {
      return Response.json({ error: "period requires a bank" }, { status: 400 });
    }
    if (typeof period !== "string" || !/^\d{4}Q[1-4]$/.test(period)) {
      return Response.json({ error: "period must be YYYYQn (e.g. 2024Q4)" }, { status: 400 });
    }
    inputs.period = period;
  }

  try {
    await dispatchWorkflow(workflow, { inputs });
    return Response.json({ ok: true, workflow, ...(inputs ?? {}) });
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
