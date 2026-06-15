/**
 * GET /api/pipeline/runs — recent GitHub Actions runs for the /pipeline graph's
 * workflow-status overlay. Public (read-only run metadata for a public repo;
 * no token leaked, no triggers). Edge-cached for 5 min so the client poll never
 * hits GitHub's rate limit — and, unlike the D1 reads, never touches KV.
 *
 * Returns { configured:false } (HTTP 200, not an error) when GITHUB_DISPATCH_TOKEN
 * isn't set, so the graph degrades to neutral workflow badges instead of failing.
 */
import { GitHubNotConfigured, listRuns } from "@/app/lib/github";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const runs = await listRuns(50);
    return Response.json(
      { configured: true, runs },
      { headers: { "Cache-Control": "public, max-age=300" } },
    );
  } catch (e) {
    if (e instanceof GitHubNotConfigured) {
      return Response.json({ configured: false, runs: [] });
    }
    const detail = e instanceof Error ? e.message : "failed to list runs";
    return Response.json({ configured: true, runs: [], error: detail }, { status: 502 });
  }
}
