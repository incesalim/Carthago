"use client";

/**
 * Custom React Flow node renderers for the /pipeline graph, one per node `kind`
 * plus a non-interactive lane band drawn behind everything. All styling uses the
 * design-system semantic tokens (bg-card, border-border, text-positive, …) so
 * light/dark track the app theme automatically.
 */
import type { ReactNode } from "react";
import Link from "next/link";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { cn } from "@/app/lib/cn";
import { NODE_W } from "@/app/lib/pipeline-layout";
import type { NodeKind, PipelineNode } from "@/app/lib/pipeline-graph";
import type { NodeStatus, StatusTone } from "@/app/lib/pipeline-status";
import { relativeFromHours, relativeFromIso } from "@/app/lib/format-time";

export interface RunBadge {
  status: string | null; // queued | in_progress | completed
  conclusion: string | null; // success | failure | …
  createdAt: string;
  url: string;
}

export interface PNodeData {
  node: PipelineNode;
  status?: NodeStatus;
  run?: RunBadge;
  runConfigured?: boolean;
  dimmed?: boolean;
}

export interface BandData {
  label: string;
}

const TONE_DOT: Record<StatusTone, string> = {
  positive: "bg-positive",
  warning: "bg-warning",
  negative: "bg-negative",
  info: "bg-info",
  muted: "bg-muted-foreground/40",
};

const KIND_ACCENT: Record<NodeKind, string> = {
  source: "border-l-chart-2",
  workflow: "border-l-chart-4",
  store: "border-l-chart-3",
  page: "border-l-primary",
};

function compact(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(n >= 10_000_000 ? 0 : 1)}M`;
  if (n >= 1_000) return `${Math.round(n / 1_000)}k`;
  return `${n}`;
}

const HANDLE_STYLE = { width: 6, height: 6, background: "transparent", border: "none" } as const;

function Dot({ tone }: { tone: StatusTone }) {
  return <span className={cn("size-2 shrink-0 rounded-full", TONE_DOT[tone])} aria-hidden="true" />;
}

function Shell({
  data,
  children,
  href,
}: {
  data: PNodeData;
  children: ReactNode;
  href?: string;
}) {
  const base = cn(
    "rounded-lg border border-border border-l-4 bg-card px-3 py-2 shadow-sm transition-opacity",
    KIND_ACCENT[data.node.kind],
    data.dimmed ? "opacity-25" : "opacity-100",
    href && "hover:border-primary/60 cursor-pointer",
  );
  const inner = (
    <>
      <Handle type="target" position={Position.Left} style={HANDLE_STYLE} isConnectable={false} />
      {children}
      <Handle type="source" position={Position.Right} style={HANDLE_STYLE} isConnectable={false} />
    </>
  );
  return href ? (
    <Link href={href} className={cn(base, "block")} style={{ width: NODE_W }}>
      {inner}
    </Link>
  ) : (
    <div className={base} style={{ width: NODE_W }}>
      {inner}
    </div>
  );
}

function Title({ data, dot }: { data: PNodeData; dot?: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="truncate text-[12px] font-semibold leading-tight text-foreground">
        {data.node.label}
      </span>
      {dot}
    </div>
  );
}

function Sub({ text }: { text?: string }) {
  if (!text) return null;
  return <div className="mt-0.5 truncate text-[10px] leading-tight text-muted-foreground">{text}</div>;
}

/** Row count + freshness line for source / store nodes. */
function StatusLine({ status }: { status?: NodeStatus }) {
  if (!status) return null;
  const parts: string[] = [];
  if (status.rowCount != null) parts.push(`${compact(status.rowCount)} rows`);
  if (status.latest) parts.push(status.latest);
  else if (status.ageHours != null) parts.push(relativeFromHours(status.ageHours));
  if (!parts.length) return null;
  return <div className="mt-1 truncate text-[10px] tabular-nums text-muted-foreground">{parts.join(" · ")}</div>;
}

export function SourceNode({ data }: NodeProps) {
  const d = data as unknown as PNodeData;
  return (
    <Shell data={d}>
      <Title data={d} dot={d.status ? <Dot tone={d.status.tone} /> : undefined} />
      <Sub text={d.node.sublabel} />
      <StatusLine status={d.status} />
    </Shell>
  );
}

export function StoreNode({ data }: NodeProps) {
  const d = data as unknown as PNodeData;
  return (
    <Shell data={d}>
      <Title data={d} dot={d.status ? <Dot tone={d.status.tone} /> : undefined} />
      <Sub text={d.node.sublabel} />
      <StatusLine status={d.status} />
    </Shell>
  );
}

function runTone(run: RunBadge | undefined, configured: boolean | undefined): StatusTone {
  if (!configured || !run) return "muted";
  if (run.status && run.status !== "completed") return "info";
  switch (run.conclusion) {
    case "success":
      return "positive";
    case "failure":
    case "timed_out":
      return "negative";
    case "cancelled":
    case "skipped":
      return "warning";
    default:
      return "muted";
  }
}

function runLabel(run: RunBadge | undefined, configured: boolean | undefined): string {
  if (configured === false) return "token not set";
  if (!run) return "no recent run";
  const state = run.status && run.status !== "completed" ? run.status.replace("_", " ") : run.conclusion ?? "—";
  return `${state} · ${relativeFromIso(run.createdAt)}`;
}

export function WorkflowNode({ data }: NodeProps) {
  const d = data as unknown as PNodeData;
  const tone = runTone(d.run, d.runConfigured);
  return (
    <Shell data={d}>
      <Title data={d} dot={<Dot tone={tone} />} />
      <Sub text={d.node.sublabel} />
      <div className="mt-1 truncate text-[10px] text-muted-foreground">{runLabel(d.run, d.runConfigured)}</div>
    </Shell>
  );
}

export function PageNode({ data }: NodeProps) {
  const d = data as unknown as PNodeData;
  return (
    <Shell data={d} href={d.node.href}>
      <Title data={d} />
      <Sub text={d.node.sublabel} />
    </Shell>
  );
}

export function LaneBandNode({ data }: NodeProps) {
  const d = data as unknown as BandData;
  return (
    <div className="pointer-events-none relative size-full rounded-2xl border border-dashed border-border/70 bg-muted/30">
      <span className="absolute left-4 top-2 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
        {d.label}
      </span>
    </div>
  );
}

export const pipelineNodeTypes = {
  source: SourceNode,
  workflow: WorkflowNode,
  store: StoreNode,
  page: PageNode,
  laneBand: LaneBandNode,
};
