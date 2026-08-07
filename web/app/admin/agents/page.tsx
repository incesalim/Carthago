/**
 * /admin/agents — the agent register.
 *
 * One page answering three questions about every model-driven lane we run:
 * whose question it answers, how it works stage by stage, and what happens if
 * you press Run. Gated by requireAdmin() like /admin, and noindex.
 *
 * The roster is hand-authored in `app/lib/agents-registry.ts`; latest run state
 * is fetched here on the server so each card can render its status without a
 * client round trip. Dispatch itself is a client island per agent.
 */
import type { Metadata } from "next";
import { AdminAuthError, requireAdmin } from "@/app/lib/admin-auth";
import { AGENTS, type AgentDef } from "@/app/lib/agents-registry";
import { GitHubNotConfigured, listRuns, type WorkflowRun } from "@/app/lib/github";
import { relativeFromIso } from "@/app/lib/format-time";
import { Card } from "@/app/components/ui";
import { Colophon, SecHead } from "@/app/components/desk";
import AgentFlow from "./AgentFlow";
import AgentRunControls from "./AgentRunControls";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Agents",
  robots: { index: false, follow: false },
};

const STATUS_STYLE: Record<AgentDef["status"], { text: string; dot: string; label: string }> = {
  live: { text: "text-positive", dot: "bg-positive", label: "live" },
  evaluation: { text: "text-warning", dot: "bg-warning", label: "evaluation" },
  planned: { text: "text-faint", dot: "bg-context", label: "planned" },
};

/** What a run persists. A D1 write is a cost event and is called one. */
const WRITES_LABEL: Record<AgentDef["writes"], string> = {
  artifacts: "run artifacts only",
  d1: "writes to D1",
  none: "writes nothing",
};

function Forbidden() {
  return (
    <main className="mx-auto max-w-md px-4 py-24">
      <Card className="p-8 text-center">
        <h1 className="text-lg font-semibold text-foreground">Admin not configured</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Set an <code className="rounded bg-muted px-1">ADMIN_PASSWORD</code> secret on the Worker
          to enable the password login. See{" "}
          <code className="rounded bg-muted px-1">docs/ADMIN.md</code>.
        </p>
      </Card>
    </main>
  );
}

function runLine(run: WorkflowRun | undefined) {
  if (!run) return { text: "text-faint", dot: "bg-context", label: "no runs", detail: "never dispatched" };
  const detail = `${relativeFromIso(run.createdAt)} · ${run.event}`;
  if (run.status && run.status !== "completed") {
    return { text: "text-muted-foreground", dot: "bg-context", label: run.status.replace("_", " "), detail };
  }
  switch (run.conclusion) {
    case "success":
      return { text: "text-positive", dot: "bg-positive", label: "success", detail };
    case "failure":
      return { text: "text-negative", dot: "bg-negative", label: "failure", detail };
    default:
      return { text: "text-faint", dot: "bg-context", label: run.conclusion ?? "unknown", detail };
  }
}

function Meta({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="border-t border-hair pt-2">
      <div className="font-mono text-[8.5px] uppercase tracking-[0.07em] text-muted-foreground">
        {label}
      </div>
      <div className="mt-1 text-[12px] leading-relaxed text-foreground">{children}</div>
    </div>
  );
}

export default async function AgentsPage() {
  try {
    await requireAdmin();
  } catch (e) {
    if (e instanceof AdminAuthError && e.mode === "login") {
      // The login form lives on /admin; send an unauthenticated visitor there
      // rather than duplicating the form.
      return (
        <main className="mx-auto max-w-md px-4 py-24">
          <Card className="p-8 text-center">
            <h1 className="text-lg font-semibold text-foreground">Sign in required</h1>
            <p className="mt-2 text-sm text-muted-foreground">
              <a href="/admin" className="text-primary hover:underline">
                Sign in on the control center
              </a>{" "}
              and come back.
            </p>
          </Card>
        </main>
      );
    }
    return <Forbidden />;
  }

  // Latest run per workflow. A missing token is a state to render, not an error.
  let latest: Record<string, WorkflowRun> = {};
  let configured = true;
  let ghError: string | null = null;
  const files = new Set(AGENTS.map((a) => a.workflowFile).filter(Boolean) as string[]);
  try {
    for (const run of await listRuns(50)) {
      if (files.has(run.workflowFile) && !latest[run.workflowFile]) latest[run.workflowFile] = run;
    }
  } catch (e) {
    if (e instanceof GitHubNotConfigured) {
      configured = false;
      latest = {};
    } else {
      ghError = e instanceof Error ? e.message : "failed to list runs";
    }
  }

  const runnable = AGENTS.filter((a) => a.workflowFile).length;
  const record = `internal · ${AGENTS.length} agents · ${runnable} dispatchable · ${
    AGENTS.filter((a) => a.status === "live").length
  } live`;

  return (
    <main className="mx-auto w-full max-w-[1200px] px-4 py-8 sm:px-6 lg:px-8">
      <header className="flex flex-wrap items-start justify-between gap-x-6 gap-y-3">
        <div>
          <h1 className="text-[24px] font-bold tracking-tight text-foreground">Agents</h1>
          <p className="mt-1.5 font-mono text-[9.5px] uppercase tracking-[0.07em] text-muted-foreground">
            {record}
          </p>
        </div>
        <a
          href="/admin"
          className="font-mono text-[9.5px] uppercase tracking-[0.06em] text-muted-foreground underline decoration-border underline-offset-4 transition-colors hover:text-foreground hover:decoration-current"
        >
          ← Control center
        </a>
      </header>

      <p className="mt-5 max-w-[70ch] text-[13px] leading-relaxed text-muted-foreground">
        Every model-driven lane, with the question it answers and for whom. Deterministic code finds
        and proves; the model investigates and writes; a guard decides what survives. The diagrams
        colour those apart — where judgment enters is the thing worth seeing at a glance.
      </p>

      {!configured && (
        <p className="mt-4 text-[12.5px] leading-relaxed text-muted-foreground">
          <span className="font-medium text-foreground">GitHub control not configured.</span> Run
          status and triggers need a token —{" "}
          <code className="rounded bg-muted px-1 font-mono text-[11px]">
            npx wrangler secret put GITHUB_DISPATCH_TOKEN
          </code>
          . The roster below still reads correctly.
        </p>
      )}
      {ghError && (
        <p className="mt-4 text-[12.5px] text-muted-foreground">
          <span className="font-mono text-[9px] uppercase tracking-[0.06em] text-warning">
            GitHub error
          </span>{" "}
          — {ghError}
        </p>
      )}

      {AGENTS.map((agent) => {
        const st = STATUS_STYLE[agent.status];
        const run = agent.workflowFile ? latest[agent.workflowFile] : undefined;
        const rl = runLine(run);
        return (
          <section key={agent.id} className="mt-9">
            <SecHead
              title={agent.name}
              meta={agent.tagline}
              action={
                <span className="flex items-center gap-3">
                  <span
                    className={`inline-flex items-center gap-1.5 font-mono text-[9px] uppercase tracking-[0.06em] ${st.text}`}
                  >
                    <span className={`h-1.5 w-1.5 rounded-full ${st.dot}`} />
                    {st.label}
                  </span>
                  <span className="font-mono text-[9px] uppercase tracking-[0.06em] text-faint">
                    {agent.runtime === "actions" ? "GitHub Actions" : "Worker"}
                  </span>
                </span>
              }
              className="mb-1"
            />

            <div className="mt-2 grid gap-x-8 gap-y-1 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
              <p className="text-[13px] leading-relaxed text-foreground">
                <span className="font-mono text-[8.5px] uppercase tracking-[0.07em] text-muted-foreground">
                  Answers
                </span>
                <br />
                {agent.question}
              </p>
              <p className="text-[13px] leading-relaxed text-foreground">
                <span className="font-mono text-[8.5px] uppercase tracking-[0.07em] text-muted-foreground">
                  For
                </span>
                <br />
                {agent.audience}
              </p>
            </div>

            <AgentFlow stages={agent.stages} edges={agent.edges} />

            <div className="mt-4 grid gap-x-8 gap-y-3 sm:grid-cols-3">
              <Meta label="Models">{agent.models}</Meta>
              <Meta label="What proves it">{agent.guardrail}</Meta>
              <Meta label="Output">
                <ul className="space-y-0.5">
                  {agent.outputs.map((o) => (
                    <li key={o} className="font-mono text-[10.5px] text-muted-foreground">
                      {o}
                    </li>
                  ))}
                </ul>
              </Meta>
            </div>

            {agent.notes && agent.notes.length > 0 && (
              <ul className="mt-3 space-y-1">
                {agent.notes.map((n) => (
                  <li key={n} className="text-[12px] leading-relaxed text-muted-foreground">
                    — {n}
                  </li>
                ))}
              </ul>
            )}

            <div className="mt-4 flex flex-wrap items-center justify-between gap-x-6 gap-y-3 border-t border-hair pt-3">
              <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5">
                <span
                  className={`inline-flex items-center gap-1.5 font-mono text-[9px] uppercase tracking-[0.05em] ${rl.text}`}
                >
                  <span className={`h-1.5 w-1.5 rounded-full ${rl.dot}`} />
                  {rl.label}
                </span>
                <span className="font-mono text-[10.5px] text-muted-foreground">
                  {rl.detail}
                  {run && (
                    <>
                      {" · "}
                      <a
                        href={run.url}
                        target="_blank"
                        rel="noreferrer"
                        className="text-primary hover:underline"
                      >
                        view run
                      </a>
                    </>
                  )}
                </span>
                <span
                  className={`font-mono text-[9px] uppercase tracking-[0.05em] ${
                    agent.writes === "d1" ? "text-warning" : "text-faint"
                  }`}
                >
                  {WRITES_LABEL[agent.writes]}
                </span>
                {agent.docs && (
                  <span className="font-mono text-[10.5px] text-faint">{agent.docs}</span>
                )}
              </div>

              {agent.workflowFile ? (
                <AgentRunControls agent={agent} disabled={!configured} />
              ) : (
                <span className="text-[12px] text-faint">
                  Runs per request in the Worker — nothing to dispatch.
                </span>
              )}
            </div>
          </section>
        );
      })}

      <Colophon>
        Internal agent register · roster hand-authored in app/lib/agents-registry.ts and CI-gated
        against .github/workflows · run status from GitHub Actions · dispatch is admin-gated and
        validated against each agent&rsquo;s declared inputs
      </Colophon>
    </main>
  );
}
