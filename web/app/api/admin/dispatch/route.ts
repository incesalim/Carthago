/**
 * POST /api/admin/dispatch { workflow } — manually trigger an allow-listed
 * refresh workflow on master via workflow_dispatch. Admin-gated.
 */
import { requireAdminOr403 } from "@/app/lib/admin-auth";
import { GitHubNotConfigured, WORKFLOWS, dispatchWorkflow } from "@/app/lib/github";

export const dynamic = "force-dynamic";

const ALLOWED = new Set(WORKFLOWS.map((w) => w.file));

export async function POST(req: Request) {
  const gate = await requireAdminOr403();
  if ("response" in gate) return gate.response;

  let workflow: unknown;
  try {
    workflow = (await req.json())?.workflow;
  } catch {
    return Response.json({ error: "invalid JSON body" }, { status: 400 });
  }
  if (typeof workflow !== "string" || !ALLOWED.has(workflow)) {
    return Response.json({ error: "unknown or disallowed workflow" }, { status: 400 });
  }

  try {
    await dispatchWorkflow(workflow);
    return Response.json({ ok: true, workflow });
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
