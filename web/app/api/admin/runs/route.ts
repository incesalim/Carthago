/**
 * GET /api/admin/runs — recent GitHub Actions runs + the dispatchable workflow
 * list. Admin-gated. Returns { configured:false } (not an error) when the
 * GitHub token isn't set, so the UI can show a setup hint.
 */
import { requireAdminOr403 } from "@/app/lib/admin-auth";
import { GitHubNotConfigured, WORKFLOWS, listRuns } from "@/app/lib/github";

export const dynamic = "force-dynamic";

export async function GET() {
  const gate = await requireAdminOr403();
  if ("response" in gate) return gate.response;

  try {
    const runs = await listRuns(25);
    return Response.json({ configured: true, workflows: WORKFLOWS, runs });
  } catch (e) {
    if (e instanceof GitHubNotConfigured) {
      return Response.json({ configured: false, workflows: WORKFLOWS, runs: [] });
    }
    const detail = e instanceof Error ? e.message : "failed to list runs";
    return Response.json({ configured: true, workflows: WORKFLOWS, runs: [], error: detail }, { status: 502 });
  }
}
