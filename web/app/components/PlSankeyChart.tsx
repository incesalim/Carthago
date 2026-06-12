"use client";

/**
 * PlSankeyChart — hand-rolled SVG Sankey of one period's P&L flows.
 *
 * Layout comes precomputed from `layoutPlSankey` (pure, in app/lib/pl-sankey);
 * this component only paints: nodes as rounded rects, links as filled bezier
 * ribbons, labels beside the nodes, and an HTML hover tooltip (same overlay
 * pattern as OwnershipRadial). Everything scales with container width via
 * viewBox; fonts are in viewBox units.
 */
import { useMemo, useState } from "react";
import { useChartTheme } from "@/app/lib/chart-theme";
import {
  layoutPlSankey,
  type PlSankeyResult,
  type PlacedNode,
  type PlNodeKind,
} from "@/app/lib/pl-sankey";

const NF_COMPACT = new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 });
const NF_FULL = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });

/** Node fills per id (falling back to kind), light / dark. */
const FILLS_BY_ID: Record<string, [string, string]> = {
  interest_income: ["#1f4068", "#6f9fe0"],
  net_interest: ["#1f4068", "#6f9fe0"],
  net_fees: ["#0f7b6c", "#34c9b0"],
  dividend: ["#5b1a8c", "#b07ee0"],
  trading: ["#4a7aa3", "#8fb8e8"],
  other_income: ["#5a5a5a", "#a3a3a3"],
  equity_method: ["#5b1a8c", "#b07ee0"],
  monetary: ["#4a7aa3", "#8fb8e8"],
  disc_ops: ["#5a5a5a", "#a3a3a3"],
  tax_credit: ["#0f7b6c", "#34c9b0"],
  interest_expense: ["#a16500", "#e0a23c"],
  ecl: ["#7a0d2e", "#f0608a"],
  other_prov: ["#7a0d2e", "#f0608a"],
  personnel: ["#a16500", "#e0a23c"],
  other_opex: ["#a16500", "#e0a23c"],
  tax: ["#a16500", "#e0a23c"],
  net_profit: ["#15803d", "#4ade80"],
};

const FILLS_BY_KIND: Record<PlNodeKind, [string, string]> = {
  source: ["#1f4068", "#6f9fe0"],
  subtotal: ["#334155", "#94a3b8"],
  deduction: ["#a16500", "#e0a23c"],
  rerouted: ["#e11d48", "#fb7185"],
  loss: ["#e11d48", "#fb7185"],
  result: ["#15803d", "#4ade80"],
};

function nodeFill(n: PlacedNode, dark: boolean): string {
  // Synthetic / loss-tinted kinds win over the id palette (a "net_profit"
  // node flips to the loss red when the period is loss-making).
  const byKind = FILLS_BY_KIND[n.kind];
  const pair =
    n.kind === "rerouted" || n.kind === "loss" || (n.id === "net_profit" && n.kind !== "result")
      ? byKind
      : FILLS_BY_ID[n.id] ?? byKind;
  return pair[dark ? 1 : 0];
}

interface Props {
  graph: PlSankeyResult;
  /** Caption suffix, e.g. the period-end date. */
  ariaLabel: string;
}

export default function PlSankeyChart({ graph, ariaLabel }: Props) {
  const { resolvedDark, t } = useThemeDark();
  const [hover, setHover] = useState<
    | { type: "node"; id: string; x: number; y: number }
    | { type: "ribbon"; index: number; x: number; y: number }
    | null
  >(null);

  const layout = useMemo(() => layoutPlSankey(graph), [graph]);
  const byId = useMemo(() => new Map(layout.nodes.map((n) => [n.id, n])), [layout]);
  const { W, H } = layout;

  const ribbonFill = (sourceId: string, targetId: string): string => {
    const target = byId.get(targetId);
    const source = byId.get(sourceId);
    if (!target || !source) return t.reference;
    // Terminal-bound ribbons take the terminal's hue (the deduction reads as
    // "leaving"); flows between subtotals keep the source hue.
    const terminal = target.kind === "deduction" || target.kind === "rerouted";
    return nodeFill(terminal ? target : source, resolvedDark);
  };

  const ribbonActive = (sourceId: string, targetId: string): boolean => {
    if (!hover) return false;
    if (hover.type === "node") return hover.id === sourceId || hover.id === targetId;
    const r = layout.ribbons[hover.index];
    return r != null && r.source === sourceId && r.target === targetId;
  };

  const hoveredNode = hover?.type === "node" ? byId.get(hover.id) : null;
  const hoveredRibbon = hover?.type === "ribbon" ? layout.ribbons[hover.index] : null;

  return (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto select-none" role="img" aria-label={ariaLabel}>
        {/* Ribbons under nodes */}
        {layout.ribbons.map((r, i) => {
          const active = ribbonActive(r.source, r.target);
          return (
            <path
              key={`${r.source}->${r.target}`}
              d={r.path}
              fill={ribbonFill(r.source, r.target)}
              fillOpacity={hover ? (active ? 0.62 : 0.12) : 0.35}
              onMouseEnter={() => setHover({ type: "ribbon", index: i, x: r.mx, y: r.my })}
              onMouseLeave={() => setHover(null)}
            />
          );
        })}
        {layout.nodes.map((n) => {
          const active = hover?.type === "node" && hover.id === n.id;
          const fill = nodeFill(n, resolvedDark);
          return (
            <g
              key={n.id}
              onMouseEnter={() => setHover({ type: "node", id: n.id, x: n.x + n.w, y: n.y + n.h / 2 })}
              onMouseLeave={() => setHover(null)}
            >
              <rect
                x={n.x}
                y={n.y}
                width={n.w}
                height={n.h}
                rx={2}
                fill={fill}
                fillOpacity={hover && !active ? 0.55 : 0.95}
              />
              <text
                x={n.x + n.w + 5}
                y={n.y + n.h / 2}
                dy="-0.1em"
                fontSize={10.5}
                className={active ? "fill-foreground font-medium" : "fill-foreground"}
              >
                {n.label}
              </text>
              <text
                x={n.x + n.w + 5}
                y={n.y + n.h / 2}
                dy="0.95em"
                fontSize={9.5}
                className="fill-muted-foreground tabular-nums"
              >
                {n.reported != null ? NF_COMPACT.format(n.reported) : NF_COMPACT.format(n.value)}
              </text>
            </g>
          );
        })}
      </svg>

      {/* HTML tooltip overlay — wraps long labels, theme-aware */}
      {(hoveredNode || hoveredRibbon) && hover && (
        <div
          className="pointer-events-none absolute z-10 w-52 rounded-md border border-border bg-card px-3 py-2 text-xs shadow-md"
          style={{
            left: `${(hover.x / W) * 100}%`,
            top: `${(hover.y / H) * 100}%`,
            transform: `translate(${hover.x > W * 0.62 ? "-104%" : "12px"}, -50%)`,
          }}
        >
          {hoveredNode ? (
            <>
              <div className="font-medium text-foreground">{hoveredNode.label}</div>
              <div className="mt-0.5 text-muted-foreground">
                {hoveredNode.reported != null ? (
                  <>
                    Filed: <span className="tabular-nums text-foreground">{NF_FULL.format(hoveredNode.reported)}</span>
                  </>
                ) : (
                  <>
                    Balancing flow:{" "}
                    <span className="tabular-nums text-foreground">{NF_FULL.format(hoveredNode.value)}</span>
                  </>
                )}{" "}
                <span className="text-[10px]">(TL thousands)</span>
              </div>
            </>
          ) : hoveredRibbon ? (
            <>
              <div className="font-medium text-foreground">
                {byId.get(hoveredRibbon.source)?.label} → {byId.get(hoveredRibbon.target)?.label}
              </div>
              <div className="mt-0.5 text-muted-foreground">
                <span className="tabular-nums text-foreground">{NF_FULL.format(hoveredRibbon.value)}</span>{" "}
                <span className="text-[10px]">(TL thousands)</span>
              </div>
            </>
          ) : null}
        </div>
      )}
    </div>
  );
}

/** Bundles the theme hook with a dark flag (the FILLS map needs it). */
function useThemeDark() {
  const t = useChartTheme();
  // chart-theme exposes the resolved palette only; infer dark from a token.
  const resolvedDark = t.tooltipBg !== "#ffffff";
  return { t, resolvedDark };
}
