"use client";

/**
 * Pipeline panel — recent GitHub Actions runs + manual trigger buttons.
 * Fetches /api/admin/runs (same-origin, so the Cloudflare Access cookie rides
 * along) and POSTs /api/admin/dispatch. Shows a setup hint when the GitHub
 * token isn't configured.
 */
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Badge, Button, Card, Section, type BadgeProps } from "@/app/components/ui";
import { relativeFromIso } from "@/app/lib/format-time";

interface WorkflowDef {
  file: string;
  label: string;
  description: string;
}
interface WorkflowRun {
  id: number;
  name: string;
  workflowFile: string;
  status: string | null;
  conclusion: string | null;
  event: string;
  createdAt: string;
  updatedAt: string;
  url: string;
}
interface RunsResponse {
  configured: boolean;
  workflows: WorkflowDef[];
  runs: WorkflowRun[];
  error?: string;
}

function runBadge(run: WorkflowRun | undefined): { variant: BadgeProps["variant"]; label: string } {
  if (!run) return { variant: "secondary", label: "no runs" };
  if (run.status && run.status !== "completed") {
    return { variant: "info", label: run.status.replace("_", " ") };
  }
  switch (run.conclusion) {
    case "success":
      return { variant: "positive", label: "success" };
    case "failure":
      return { variant: "negative", label: "failure" };
    case "cancelled":
      return { variant: "secondary", label: "cancelled" };
    default:
      return { variant: "secondary", label: run.conclusion ?? "unknown" };
  }
}

export default function PipelinePanel() {
  const [data, setData] = useState<RunsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/admin/runs", { cache: "no-store" });
      if (res.status === 403) {
        setData({ configured: false, workflows: [], runs: [], error: "forbidden" });
        return;
      }
      setData((await res.json()) as RunsResponse);
    } catch {
      toast.error("Failed to load workflow runs");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function dispatch(w: WorkflowDef) {
    if (busy) return;
    if (!window.confirm(`Trigger "${w.label}" now?`)) return;
    setBusy(w.file);
    try {
      const res = await fetch("/api/admin/dispatch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ workflow: w.file }),
      });
      const body = (await res.json().catch(() => ({}))) as { error?: string };
      if (res.ok) {
        toast.success(`Triggered ${w.label}`, { description: "Refreshing run status…" });
        setTimeout(() => void load(), 3000);
      } else {
        toast.error(`Couldn't trigger ${w.label}`, { description: body.error ?? `HTTP ${res.status}` });
      }
    } catch {
      toast.error(`Couldn't trigger ${w.label}`);
    } finally {
      setBusy(null);
    }
  }

  const workflows = data?.workflows ?? [];
  const latestFor = (file: string) =>
    data?.runs.find((r) => r.workflowFile === file);

  return (
    <Section
      title="Pipeline"
      description="Scraper workflows — status and manual triggers"
      actions={
        <Button variant="outline" size="sm" onClick={() => void load()} disabled={loading}>
          {loading ? "Refreshing…" : "Refresh"}
        </Button>
      }
    >
      {data && !data.configured && (
        <Card className="mb-3 p-4 text-sm text-muted-foreground">
          <p className="font-medium text-foreground">GitHub control not configured.</p>
          <p className="mt-1">
            Run status and triggers need a token. Add a fine-grained PAT (Actions:
            read+write) with{" "}
            <code className="rounded bg-muted px-1">
              npx wrangler secret put GITHUB_DISPATCH_TOKEN
            </code>
            . You can still trigger workflows from the GitHub Actions tab meanwhile.
          </p>
        </Card>
      )}
      {data?.error && data.configured && (
        <Card className="mb-3 p-4 text-sm">
          <Badge variant="warning">GitHub error</Badge>
          <p className="mt-2 text-muted-foreground">{data.error}</p>
        </Card>
      )}

      <div className="grid gap-3 sm:grid-cols-2">
        {workflows.map((w) => {
          const run = latestFor(w.file);
          const badge = runBadge(run);
          return (
            <Card key={w.file} className="flex items-center justify-between gap-3 p-4">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="truncate text-sm font-semibold text-foreground">{w.label}</span>
                  <Badge variant={badge.variant}>{badge.label}</Badge>
                </div>
                <p className="mt-0.5 truncate text-xs text-muted-foreground">{w.description}</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  {run ? (
                    <>
                      {relativeFromIso(run.createdAt)} · {run.event}
                      {" · "}
                      <a
                        href={run.url}
                        target="_blank"
                        rel="noreferrer"
                        className="underline hover:text-foreground"
                      >
                        view
                      </a>
                    </>
                  ) : (
                    "no recent runs"
                  )}
                </p>
              </div>
              <Button
                size="sm"
                onClick={() => void dispatch(w)}
                disabled={!!busy || (data ? !data.configured : true)}
              >
                {busy === w.file ? "Triggering…" : "Run"}
              </Button>
            </Card>
          );
        })}
        {workflows.length === 0 && !loading && (
          <p className="text-sm text-muted-foreground">No workflows to show.</p>
        )}
      </div>
    </Section>
  );
}
