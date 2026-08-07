/**
 * GET /api/admin/agents — the agent registry plus the latest Actions run for
 * each dispatchable one. Admin-gated.
 *
 * Mirrors /api/admin/runs: a missing GitHub token is `configured: false`, not
 * an error, so the panel renders the roster and explains what is missing
 * instead of collapsing into an error state.
 */
import { requireAdminOr403 } from "@/app/lib/admin-auth";
import { AGENTS } from "@/app/lib/agents-registry";
import { GitHubNotConfigured, listRuns, type WorkflowRun } from "@/app/lib/github";

export const dynamic = "force-dynamic";

export async function GET() {
  const gate = await requireAdminOr403();
  if ("response" in gate) return gate.response;

  const files = new Set(AGENTS.map((a) => a.workflowFile).filter(Boolean) as string[]);

  try {
    // One list call covers every agent — the runs endpoint is per-repo, not
    // per-workflow, so filtering here beats N round trips from the client.
    const runs = (await listRuns(50)).filter((r) => files.has(r.workflowFile));
    const latest: Record<string, WorkflowRun> = {};
    for (const run of runs) {
      // listRuns returns newest-first; keep the first sighting per workflow.
      if (!latest[run.workflowFile]) latest[run.workflowFile] = run;
    }
    return Response.json({ configured: true, agents: AGENTS, latest, runs: runs.slice(0, 20) });
  } catch (e) {
    if (e instanceof GitHubNotConfigured) {
      return Response.json({ configured: false, agents: AGENTS, latest: {}, runs: [] });
    }
    const detail = e instanceof Error ? e.message : "failed to list runs";
    return Response.json(
      { configured: true, agents: AGENTS, latest: {}, runs: [], error: detail },
      { status: 502 },
    );
  }
}
