"use client";

/**
 * Pipeline panel — recent GitHub Actions runs + manual trigger buttons.
 * Fetches /api/admin/runs (same-origin, so the Cloudflare Access cookie rides
 * along) and POSTs /api/admin/dispatch. Shows a setup hint when the GitHub
 * token isn't configured.
 */
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { SecHead } from "@/app/components/desk";
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
  auditWorkflow?: string;
  auditBanks?: string[];
  runs: WorkflowRun[];
  error?: string;
}

// Status → dot colour + mono-caps word. Green/red read run state; in-flight and
// idle stay a quiet context grey — never blue (blue is links only here).
function runStatus(run: WorkflowRun | undefined): { text: string; dot: string; label: string } {
  if (!run) return { text: "text-faint", dot: "bg-context", label: "no runs" };
  if (run.status && run.status !== "completed") {
    return { text: "text-muted-foreground", dot: "bg-context", label: run.status.replace("_", " ") };
  }
  switch (run.conclusion) {
    case "success":
      return { text: "text-positive", dot: "bg-positive", label: "success" };
    case "failure":
      return { text: "text-negative", dot: "bg-negative", label: "failure" };
    case "cancelled":
      return { text: "text-faint", dot: "bg-context", label: "cancelled" };
    default:
      return { text: "text-faint", dot: "bg-context", label: run.conclusion ?? "unknown" };
  }
}

export default function PipelinePanel() {
  const [data, setData] = useState<RunsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  // Selected ticker for the audit workflow ("" = all banks). Other workflows
  // ignore this.
  const [auditBank, setAuditBank] = useState("");

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
    // Fetch the run list on mount; load() synchronously flips `loading`, which
    // is the intended fetch-on-mount pattern here.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [load]);

  async function dispatch(w: WorkflowDef, bank?: string) {
    if (busy) return;
    const scope = bank ? ` for ${bank} (latest period)` : "";
    if (!window.confirm(`Trigger "${w.label}"${scope} now?`)) return;
    setBusy(w.file);
    try {
      const res = await fetch("/api/admin/dispatch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ workflow: w.file, ...(bank ? { bank } : {}) }),
      });
      const body = (await res.json().catch(() => ({}))) as { error?: string };
      if (res.ok) {
        toast.success(`Triggered ${w.label}${scope}`, { description: "Refreshing run status…" });
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
  const latestFor = (file: string) => data?.runs.find((r) => r.workflowFile === file);

  return (
    <>
      <SecHead
        title="Pipeline"
        meta="scraper workflows · status & manual triggers"
        action={
          <button
            type="button"
            onClick={() => void load()}
            disabled={loading}
            className="font-mono text-[9.5px] uppercase tracking-[0.06em] text-muted-foreground underline decoration-border underline-offset-4 transition-colors hover:text-foreground hover:decoration-current disabled:opacity-50"
          >
            {loading ? "Refreshing…" : "Refresh status"}
          </button>
        }
        className="mb-1"
      />

      {data && !data.configured && (
        <p className="mt-3 text-[12.5px] leading-relaxed text-muted-foreground">
          <span className="font-medium text-foreground">GitHub control not configured.</span> Run
          status and triggers need a token. Add a fine-grained PAT (Actions: read+write) with{" "}
          <code className="rounded bg-muted px-1 font-mono text-[11px]">
            npx wrangler secret put GITHUB_DISPATCH_TOKEN
          </code>
          . You can still trigger workflows from the GitHub Actions tab meanwhile.
        </p>
      )}
      {data?.error && data.configured && (
        <p className="mt-3 text-[12.5px] text-muted-foreground">
          <span className="font-mono text-[9px] uppercase tracking-[0.06em] text-warning">
            GitHub error
          </span>{" "}
          — {data.error}
        </p>
      )}

      <div className="mt-2">
        {workflows.map((w) => {
          const run = latestFor(w.file);
          const st = runStatus(run);
          const isAudit = w.file === data?.auditWorkflow;
          const banks = data?.auditBanks ?? [];
          const disabled = !!busy || (data ? !data.configured : true);
          return (
            <div
              key={w.file}
              className="grid grid-cols-[1fr_auto] items-center gap-x-4 gap-y-2 border-b border-hair py-2.5 sm:grid-cols-[1.5fr_0.8fr_1.5fr_auto]"
            >
              <div className="min-w-0">
                <div className="truncate text-[13px] font-medium text-foreground">{w.label}</div>
                <div className="mt-0.5 truncate text-[11.5px] text-faint">{w.description}</div>
              </div>
              <div
                className={`hidden items-center gap-1.5 font-mono text-[9px] uppercase tracking-[0.05em] sm:inline-flex ${st.text}`}
              >
                <span className={`h-1.5 w-1.5 rounded-full ${st.dot}`} />
                {st.label}
              </div>
              <div className="hidden font-mono text-[11px] text-muted-foreground sm:block">
                {run ? (
                  <>
                    {relativeFromIso(run.createdAt)} · {run.event} ·{" "}
                    <a href={run.url} target="_blank" rel="noreferrer" className="text-primary hover:underline">
                      view
                    </a>
                  </>
                ) : (
                  "no recent runs"
                )}
              </div>
              <div className="flex shrink-0 items-center gap-3 justify-self-end">
                {isAudit && banks.length > 0 && (
                  <select
                    aria-label="Bank to scrape"
                    title="Pick a bank to scrape only its latest published quarter; All banks runs the full sweep."
                    value={auditBank}
                    onChange={(e) => setAuditBank(e.target.value)}
                    disabled={disabled}
                    className="h-6 rounded border border-border bg-transparent px-1.5 font-mono text-[10px] text-foreground outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:opacity-50"
                  >
                    <option value="">All banks</option>
                    {banks.map((b) => (
                      <option key={b} value={b}>
                        {b}
                      </option>
                    ))}
                  </select>
                )}
                <button
                  type="button"
                  onClick={() => void dispatch(w, isAudit ? auditBank || undefined : undefined)}
                  disabled={disabled}
                  className="font-mono text-[9.5px] uppercase tracking-[0.06em] text-muted-foreground underline decoration-border underline-offset-4 transition-colors hover:text-foreground hover:decoration-current disabled:opacity-40"
                >
                  {busy === w.file ? "Triggering…" : "Run"}
                </button>
              </div>
            </div>
          );
        })}
        {workflows.length === 0 && !loading && (
          <p className="py-3 text-[12.5px] text-muted-foreground">No workflows to show.</p>
        )}
      </div>
    </>
  );
}
