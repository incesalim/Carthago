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
  REEXTRACT_WORKFLOW,
  STATEMENT_TYPES,
  WORKFLOWS,
  dispatchWorkflow,
} from "@/app/lib/github";

export const dynamic = "force-dynamic";

const ALLOWED = new Set([...WORKFLOWS.map((w) => w.file), REEXTRACT_WORKFLOW]);
const AUDIT_BANK_SET = new Set<string>(AUDIT_BANKS);
const KINDS = new Set(["consolidated", "unconsolidated"]);
const PERIOD_RE = /^\d{4}Q[1-4]$/;

export async function POST(req: Request) {
  const gate = await requireAdminOr403();
  if ("response" in gate) return gate.response;

  let payload: {
    workflow?: unknown;
    bank?: unknown;
    period?: unknown;
    statement?: unknown;
    kind?: unknown;
  };
  try {
    payload = (await req.json()) ?? {};
  } catch {
    return Response.json({ error: "invalid JSON body" }, { status: 400 });
  }
  const { workflow, bank, period, statement, kind } = payload;
  if (typeof workflow !== "string" || !ALLOWED.has(workflow)) {
    return Response.json({ error: "unknown or disallowed workflow" }, { status: 400 });
  }

  // All dispatch inputs are validated against known sets / patterns before being
  // forwarded (guards against injecting an arbitrary workflow input).
  let inputs: Record<string, string> | undefined;

  if (workflow === REEXTRACT_WORKFLOW) {
    // Single-cell re-extract — every field required. Forces just this one
    // (bank, period, kind, statement) table (only_failing off, force on); broad
    // re-extracts keep the guard.
    if (typeof bank !== "string" || !AUDIT_BANK_SET.has(bank)) {
      return Response.json({ error: "unknown bank" }, { status: 400 });
    }
    if (typeof period !== "string" || !PERIOD_RE.test(period)) {
      return Response.json({ error: "period must be YYYYQn (e.g. 2024Q4)" }, { status: 400 });
    }
    if (typeof statement !== "string" || !STATEMENT_TYPES.has(statement)) {
      return Response.json({ error: "unknown statement type" }, { status: 400 });
    }
    if (typeof kind !== "string" || !KINDS.has(kind)) {
      return Response.json({ error: "kind must be consolidated or unconsolidated" }, { status: 400 });
    }
    inputs = {
      statement,
      banks: bank,
      periods: period,
      kind,
      force: "true",
      only_failing: "false",
    };
  } else {
    // refresh-audit.yml + the blind-trigger workflows: optional `bank`/`period`.
    if (statement != null && statement !== "") {
      return Response.json(
        { error: "statement is only valid for the re-extract workflow" },
        { status: 400 },
      );
    }
    if (kind != null && kind !== "") {
      return Response.json(
        { error: "kind is only valid for the re-extract workflow" },
        { status: 400 },
      );
    }
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
      if (typeof period !== "string" || !PERIOD_RE.test(period)) {
        return Response.json({ error: "period must be YYYYQn (e.g. 2024Q4)" }, { status: 400 });
      }
      inputs.period = period;
    }
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
