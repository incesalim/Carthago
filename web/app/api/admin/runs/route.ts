/**
 * GET /api/admin/runs — recent GitHub Actions runs + the dispatchable workflow
 * list. Admin-gated. Returns { configured:false } (not an error) when the
 * GitHub token isn't set, so the UI can show a setup hint.
 */
import { requireAdminOr403 } from "@/app/lib/admin-auth";
import {
  AUDIT_BANKS,
  AUDIT_WORKFLOW,
  GitHubNotConfigured,
  WORKFLOWS,
  listRuns,
} from "@/app/lib/github";

export const dynamic = "force-dynamic";

// Static bits the UI needs to render the per-bank audit picker, regardless of
// whether the GitHub token is configured.
const META = { workflows: WORKFLOWS, auditWorkflow: AUDIT_WORKFLOW, auditBanks: AUDIT_BANKS };

export async function GET() {
  const gate = await requireAdminOr403();
  if ("response" in gate) return gate.response;

  try {
    const runs = await listRuns(25);
    return Response.json({ configured: true, ...META, runs });
  } catch (e) {
    if (e instanceof GitHubNotConfigured) {
      return Response.json({ configured: false, ...META, runs: [] });
    }
    const detail = e instanceof Error ? e.message : "failed to list runs";
    return Response.json({ configured: true, ...META, runs: [], error: detail }, { status: 502 });
  }
}
