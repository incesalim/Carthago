"use client";

/**
 * Interactive pipeline graph (React Flow). The static topology + layout are
 * pure/deterministic; this component layers in live status: D1 freshness/counts
 * arrive as the `status` prop (server-rendered), GitHub workflow runs are fetched
 * client-side from the edge-cached /api/pipeline/runs. Hovering a node dims the
 * rest of the graph to its direct neighbourhood.
 */
import { useCallback, useEffect, useMemo, useState, type CSSProperties } from "react";
import {
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  ReactFlow,
  MarkerType,
  useEdgesState,
  useNodesState,
  type ColorMode,
  type Edge,
  type Node,
} from "@xyflow/react";
import { useTheme } from "next-themes";
import { useChartTheme } from "@/app/lib/chart-theme";
import { PIPELINE_EDGES, PIPELINE_NODES, type PipelineEdge } from "@/app/lib/pipeline-graph";
import { computeLayout } from "@/app/lib/pipeline-layout";
import type { PipelineStatusMap } from "@/app/lib/pipeline-status";
import { pipelineNodeTypes, type PNodeData, type RunBadge } from "./PipelineNodes";

interface RawRun {
  workflowFile: string;
  status: string | null;
  conclusion: string | null;
  createdAt: string;
  url: string;
}

function edgeStyle(e: PipelineEdge, active: boolean | null): CSSProperties {
  const dashed = e.kind === "snapshot" || e.kind === "guard";
  const dash = dashed ? "5 4" : undefined;
  const base =
    e.kind === "snapshot"
      ? "var(--info)"
      : e.kind === "guard"
        ? "var(--warning)"
        : "var(--muted-foreground)";
  if (active === false) return { stroke: base, strokeWidth: 1, strokeOpacity: 0.08, strokeDasharray: dash };
  if (active === true) return { stroke: "var(--primary)", strokeWidth: 2.2, strokeOpacity: 0.95, strokeDasharray: dash };
  return { stroke: base, strokeWidth: 1.4, strokeOpacity: 0.4, strokeDasharray: dash };
}

/** Visible in both themes; SVG marker fill is an attribute, so no CSS var. */
const ARROW_COLOR = "#9ca3af";

export default function PipelineFlow({ status }: { status: PipelineStatusMap }) {
  const { resolvedTheme } = useTheme();
  const colorMode: ColorMode = resolvedTheme === "dark" ? "dark" : "light";
  const theme = useChartTheme();
  // MiniMap fills are SVG attributes (no CSS vars) → use resolved hex palette.
  const miniColor = (type: string | undefined): string => {
    switch (type) {
      case "source":
        return theme.palette[1];
      case "workflow":
        return theme.palette[3];
      case "store":
        return theme.palette[2];
      case "page":
        return theme.palette[0];
      default:
        return theme.axis;
    }
  };

  const layout = useMemo(() => computeLayout(PIPELINE_NODES), []);

  // Adjacency for hover ego-highlighting.
  const neighbors = useMemo(() => {
    const m = new Map<string, Set<string>>();
    const add = (a: string, b: string) => {
      const s = m.get(a) ?? new Set<string>();
      s.add(b);
      m.set(a, s);
    };
    for (const e of PIPELINE_EDGES) {
      add(e.source, e.target);
      add(e.target, e.source);
    }
    return m;
  }, []);

  const initialNodes = useMemo<Node[]>(() => {
    const bands: Node[] = layout.bands.map((b) => ({
      id: b.id,
      type: "laneBand",
      position: { x: b.x, y: b.y },
      data: { label: b.label },
      draggable: false,
      selectable: false,
      connectable: false,
      zIndex: -1,
      style: { width: b.width, height: b.height, pointerEvents: "none" },
    }));
    const real: Node[] = PIPELINE_NODES.map((n) => ({
      id: n.id,
      type: n.kind,
      position: layout.positions[n.id] ?? { x: 0, y: 0 },
      data: { node: n, status: n.statusKey ? status[n.statusKey] : undefined, dimmed: false } satisfies PNodeData,
    }));
    return [...bands, ...real];
  }, [layout, status]);

  const initialEdges = useMemo<Edge[]>(
    () =>
      PIPELINE_EDGES.map((e, i) => ({
        id: `e${i}`,
        source: e.source,
        target: e.target,
        markerEnd: { type: MarkerType.ArrowClosed, width: 12, height: 12, color: ARROW_COLOR },
        style: edgeStyle(e, null),
        data: { kind: e.kind },
      })),
    [],
  );

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);
  const [hoverId, setHoverId] = useState<string | null>(null);

  // Pull GitHub Actions runs once on mount; merge into workflow nodes.
  useEffect(() => {
    let cancelled = false;
    fetch("/api/pipeline/runs")
      .then((r) => r.json())
      .then((j: { configured?: boolean; runs?: RawRun[] }) => {
        if (cancelled) return;
        const byFile = new Map<string, RunBadge>();
        for (const r of j.runs ?? []) {
          if (r.workflowFile && !byFile.has(r.workflowFile)) {
            byFile.set(r.workflowFile, {
              status: r.status,
              conclusion: r.conclusion,
              createdAt: r.createdAt,
              url: r.url,
            });
          }
        }
        setNodes((ns) =>
          ns.map((n) => {
            if (n.type !== "workflow") return n;
            const d = n.data as unknown as PNodeData;
            const wf = d.node.workflowFile;
            return { ...n, data: { ...d, run: wf ? byFile.get(wf) : undefined, runConfigured: j.configured } };
          }),
        );
      })
      .catch(() => {
        /* leave workflow badges neutral */
      });
    return () => {
      cancelled = true;
    };
  }, [setNodes]);

  // Apply hover dimming to nodes + edges.
  useEffect(() => {
    setNodes((ns) =>
      ns.map((n) => {
        if (n.type === "laneBand") return n;
        const dim = hoverId != null && n.id !== hoverId && !neighbors.get(hoverId)?.has(n.id);
        const d = n.data as unknown as PNodeData;
        if (d.dimmed === dim) return n;
        return { ...n, data: { ...d, dimmed: dim } };
      }),
    );
    setEdges((es) =>
      es.map((e) => {
        const active = hoverId == null ? null : e.source === hoverId || e.target === hoverId;
        return { ...e, animated: active === true, style: edgeStyle({ source: e.source, target: e.target, kind: (e.data as { kind?: PipelineEdge["kind"] })?.kind }, active) };
      }),
    );
  }, [hoverId, neighbors, setNodes, setEdges]);

  const onNodeMouseEnter = useCallback((_: unknown, node: Node) => {
    if (node.type !== "laneBand") setHoverId(node.id);
  }, []);
  const onNodeMouseLeave = useCallback(() => setHoverId(null), []);

  return (
    <div className="h-[calc(100vh-13rem)] min-h-[560px] w-full overflow-hidden rounded-lg border border-border bg-background">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeMouseEnter={onNodeMouseEnter}
        onNodeMouseLeave={onNodeMouseLeave}
        nodeTypes={pipelineNodeTypes}
        colorMode={colorMode}
        fitView
        fitViewOptions={{ padding: 0.08 }}
        minZoom={0.1}
        maxZoom={1.8}
        nodesConnectable={false}
        elementsSelectable={false}
        proOptions={{ hideAttribution: false }}
      >
        <Background variant={BackgroundVariant.Dots} gap={22} size={1} />
        <MiniMap pannable zoomable nodeColor={(n) => miniColor(n.type)} nodeStrokeWidth={2} />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}
