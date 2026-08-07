/**
 * POST /api/admin/agents/dispatch { agent, inputs } — run one registered agent
 * on master via workflow_dispatch. Admin-gated.
 *
 * Why this exists next to /api/admin/dispatch: that route is shaped around the
 * audit lane (a `bank`, an optional `period`, and a hard reject for anything
 * else). Agents take boolean and choice inputs whose names differ per agent, so
 * validation has to come from the registry rather than a fixed field list.
 *
 * Nothing reaches GitHub that the agent did not declare: `validateAgentInputs`
 * rejects unknown keys, enforces patterns and option sets, and fills declared
 * defaults. A worker-resident agent has no workflow and is refused outright.
 */
import { requireAdminOr403 } from "@/app/lib/admin-auth";
import { agentById, validateAgentInputs } from "@/app/lib/agents-registry";
import { GitHubNotConfigured, dispatchWorkflow } from "@/app/lib/github";

export const dynamic = "force-dynamic";

export async function POST(req: Request) {
  const gate = await requireAdminOr403();
  if ("response" in gate) return gate.response;

  let payload: { agent?: unknown; inputs?: unknown };
  try {
    payload = (await req.json()) ?? {};
  } catch {
    return Response.json({ error: "invalid JSON body" }, { status: 400 });
  }

  const { agent: agentId, inputs: rawInputs } = payload;
  if (typeof agentId !== "string") {
    return Response.json({ error: "agent is required" }, { status: 400 });
  }
  const agent = agentById(agentId);
  if (!agent) return Response.json({ error: `unknown agent: ${agentId}` }, { status: 400 });
  if (!agent.workflowFile) {
    return Response.json(
      { error: `${agent.name} runs in the Worker — there is nothing to dispatch` },
      { status: 400 },
    );
  }
  if (rawInputs != null && (typeof rawInputs !== "object" || Array.isArray(rawInputs))) {
    return Response.json({ error: "inputs must be an object" }, { status: 400 });
  }

  const validated = validateAgentInputs(agent, (rawInputs ?? {}) as Record<string, unknown>);
  if ("error" in validated) return Response.json({ error: validated.error }, { status: 400 });

  try {
    await dispatchWorkflow(agent.workflowFile, { inputs: validated.inputs });
    return Response.json({ ok: true, agent: agent.id, workflow: agent.workflowFile, inputs: validated.inputs });
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
