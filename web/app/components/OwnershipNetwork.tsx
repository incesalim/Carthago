"use client";

/**
 * OwnershipNetwork — sector-wide ownership graph on /ownership.
 *
 * Two overview modes:
 *  - "All holdings" (default): force-directed layout (d3-force, precomputed
 *    deterministically in useMemo) — banks anchored loosely to a type-ordered
 *    ring, sized by total assets; each bank's holdings settle as an organic
 *    cluster around it; shared entities are pulled between the banks that
 *    hold them. Hovering highlights the ego-network and fades the rest;
 *    holding names appear on hover or as you zoom in.
 *  - "Shared only": the quiet structural ring — just banks, cross-bank
 *    entities and bank-to-bank stakes.
 *
 * Click a bank in either mode for its radial fan (same view as
 * /banks/[ticker]); state mirrors to ?view=&focus= via shallow
 * history.replaceState (no server roundtrip on a force-dynamic page).
 */
import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import {
  layoutNetwork,
  trimLabel,
  type OwnershipGraph,
  type GraphLeaf,
} from "@/app/lib/ownership-graph";
import {
  buildForceLayout,
  type ForceEdge,
  type ForceNode,
} from "@/app/lib/ownership-force";
import { LeafPanel, RadialFanView } from "./OwnershipRadial";
import { seriesColor, useChartTheme } from "@/app/lib/chart-theme";
import { BANK_TYPE_BADGE_LABELS, bankDisplayName } from "@/app/lib/bank_names";
import { fmtPct } from "@/app/lib/ownership-format";

interface ViewBox {
  x: number;
  y: number;
  w: number;
  h: number;
}

type ViewMode = "all" | "shared";

interface Props {
  graph: OwnershipGraph;
  /** Latest total assets per ticker (sizes bank nodes); may be empty. */
  assets: Record<string, number | null>;
  initialFocus?: string;
  initialView?: string;
}

/** Quadratic path between two nodes with a perpendicular bow. */
function curvedPath(sx: number, sy: number, tx: number, ty: number, k: number): string {
  const dx = tx - sx;
  const dy = ty - sy;
  const d = Math.hypot(dx, dy) || 1;
  const mx = (sx + tx) / 2 + (-dy / d) * k * d;
  const my = (sy + ty) / 2 + (dx / d) * k * d;
  return `M ${sx} ${sy} Q ${mx} ${my} ${tx} ${ty}`;
}

export default function OwnershipNetwork({
  graph,
  assets,
  initialFocus,
  initialView,
}: Props) {
  const t = useChartTheme();
  const validFocus = (f: string | null | undefined) =>
    f && graph.banks.some((b) => b.ticker === f) ? f : null;
  const [focus, setFocus] = useState<string | null>(() => validFocus(initialFocus));
  const [view, setView] = useState<ViewMode>(initialView === "shared" ? "shared" : "all");
  const [hover, setHover] = useState<string | null>(null);
  const [selectedShared, setSelectedShared] = useState<string | null>(null);
  const [selectedLeaf, setSelectedLeaf] = useState<{
    ticker: string;
    leaf: GraphLeaf;
  } | null>(null);

  const ring = useMemo(() => layoutNetwork(graph), [graph]);
  const force = useMemo(() => buildForceLayout(graph, assets), [graph, assets]);
  const sharedByKey = useMemo(
    () => new Map(graph.sharedHolders.map((s) => [s.key, s])),
    [graph],
  );
  const ringBankPos = useMemo(
    () => new Map(ring.banks.map((b) => [b.ticker, b])),
    [ring],
  );
  const nodeById = useMemo(
    () => new Map(force.nodes.map((n) => [n.id, n])),
    [force],
  );

  const size = view === "all" ? force.size : ring.size;

  // ----- zoom/pan (viewBox manipulation) ------------------------------------
  const [vb, setVb] = useState<ViewBox>({ x: 0, y: 0, w: size, h: size });
  // The two view modes use different canvas sizes — re-frame on switch
  // (state-adjust-during-render pattern, not an effect).
  const [vbSize, setVbSize] = useState(size);
  if (vbSize !== size) {
    setVbSize(size);
    setVb({ x: 0, y: 0, w: size, h: size });
  }
  const svgRef = useRef<SVGSVGElement | null>(null);
  const dragRef = useRef<{ px: number; py: number; moved: number } | null>(null);
  const lastDragMoved = useRef(0);
  const animRef = useRef<number | null>(null);
  const wasDrag = () => lastDragMoved.current > 4;
  const isZoomed = vb.x !== 0 || vb.y !== 0 || vb.w !== size;

  /** Ease the viewBox to a target over ~350ms (used by Reset). */
  const animateVbTo = (target: ViewBox) => {
    if (animRef.current != null) cancelAnimationFrame(animRef.current);
    const start = performance.now();
    const from = { ...vb };
    const D = 350;
    const step = (now: number) => {
      const p = Math.min((now - start) / D, 1);
      const e = 1 - Math.pow(1 - p, 3); // ease-out cubic
      setVb({
        x: from.x + (target.x - from.x) * e,
        y: from.y + (target.y - from.y) * e,
        w: from.w + (target.w - from.w) * e,
        h: from.h + (target.h - from.h) * e,
      });
      if (p < 1) animRef.current = requestAnimationFrame(step);
    };
    animRef.current = requestAnimationFrame(step);
  };

  // Native non-passive wheel listener — React's synthetic onWheel is passive,
  // so preventDefault (needed to stop page scroll) would warn. Re-attach when
  // the overview SVG remounts (focus/view switches). Cursor-anchored zoom.
  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const rect = svg.getBoundingClientRect();
      const factor = e.deltaY > 0 ? 1.15 : 1 / 1.15;
      setVb((cur) => {
        const sx = cur.x + ((e.clientX - rect.left) / rect.width) * cur.w;
        const sy = cur.y + ((e.clientY - rect.top) / rect.height) * cur.h;
        const w = Math.min(Math.max(cur.w * factor, size * 0.15), size * 2.5);
        return {
          x: sx - ((sx - cur.x) * w) / cur.w,
          y: sy - ((sy - cur.y) * w) / cur.h,
          w,
          h: w,
        };
      });
    };
    svg.addEventListener("wheel", onWheel, { passive: false });
    return () => svg.removeEventListener("wheel", onWheel);
  }, [focus, size]);

  const onPointerDown = (e: React.PointerEvent<SVGSVGElement>) => {
    if (e.button !== 0) return;
    dragRef.current = { px: e.clientX, py: e.clientY, moved: 0 };
    e.currentTarget.setPointerCapture(e.pointerId);
  };
  const onPointerMove = (e: React.PointerEvent<SVGSVGElement>) => {
    const drag = dragRef.current;
    if (!drag) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const dx = e.clientX - drag.px;
    const dy = e.clientY - drag.py;
    drag.px = e.clientX;
    drag.py = e.clientY;
    drag.moved += Math.abs(dx) + Math.abs(dy);
    setVb((cur) => ({
      ...cur,
      x: cur.x - (dx * cur.w) / rect.width,
      y: cur.y - (dy * cur.h) / rect.height,
    }));
  };
  const onPointerUp = () => {
    // Keep `moved` readable in the click handlers that fire right after.
    lastDragMoved.current = dragRef.current?.moved ?? 0;
    dragRef.current = null;
  };

  const syncUrl = (nextFocus: string | null, nextView: ViewMode) => {
    const params = new URLSearchParams();
    if (nextView !== "all") params.set("view", nextView);
    if (nextFocus) params.set("focus", nextFocus);
    const qs = params.toString();
    window.history.replaceState(null, "", qs ? `?${qs}` : window.location.pathname);
  };

  const changeFocus = (next: string | null) => {
    setFocus(next);
    setSelectedShared(null);
    setSelectedLeaf(null);
    setHover(null);
    syncUrl(next, view);
  };

  const changeView = (next: ViewMode) => {
    setView(next);
    setSelectedShared(null);
    setSelectedLeaf(null);
    setHover(null);
    syncUrl(focus, next);
  };

  // ----- focus mode ---------------------------------------------------------
  const focusBank = focus ? graph.banks.find((b) => b.ticker === focus) : null;
  const focusFan = useMemo(() => {
    if (!focusBank) return null;
    // Stakes filed only by the counterparty (e.g. İş Bankası's 20.58% in
    // ATBANK, Ziraat's stake in Ziraat Katılım) become synthetic leaves so
    // the focused fan shows both directions.
    const holders = [...focusBank.holders];
    const subs = [...focusBank.subs];
    for (const e of graph.bankEdges) {
      const synth = (ticker: string, kind: "holder" | "sub"): GraphLeaf => ({
        id: `edge:${e.from}:${e.to}`,
        kind,
        label: bankDisplayName(ticker),
        fullName: bankDisplayName(ticker),
        ratioPct: e.ratioPct,
        votingPct: null,
        shareAmt: null,
        currency: null,
        activity: null,
        relation: null,
        asOf: null,
        bankRef: ticker,
      });
      if (e.to === focusBank.ticker && !holders.some((l) => l.bankRef === e.from)) {
        holders.push(synth(e.from, "holder"));
      }
      if (e.from === focusBank.ticker && !subs.some((l) => l.bankRef === e.to)) {
        subs.push(synth(e.to, "sub"));
      }
    }
    return { holders, subs };
  }, [focusBank, graph.bankEdges]);

  if (focus && focusBank && focusFan) {
    return (
      <div>
        <div className="mb-3 flex flex-wrap items-baseline gap-x-3 gap-y-1 text-sm">
          <button
            type="button"
            onClick={() => changeFocus(null)}
            className="text-muted-foreground hover:text-foreground"
          >
            ← All banks
          </button>
          <span className="font-semibold text-foreground">{focusBank.name}</span>
          {focusBank.typeCode && (
            <span className="text-xs text-muted-foreground">
              {BANK_TYPE_BADGE_LABELS[focusBank.typeCode]}
            </span>
          )}
          <Link
            href={`/banks/${focusBank.ticker}`}
            className="ml-auto text-xs text-muted-foreground hover:text-foreground"
          >
            Open bank page →
          </Link>
        </div>
        <RadialFanView
          ticker={focusBank.ticker}
          typeCode={focusBank.typeCode}
          holders={focusFan.holders}
          subs={focusFan.subs}
          indirect={focusBank.indirect}
          freeFloatPct={focusBank.freeFloatPct}
          onBankRefClick={(next) => changeFocus(next)}
          sharedLookup={(key) => sharedByKey.get(key)}
        />
      </div>
    );
  }

  // ----- overview -----------------------------------------------------------
  const holderColor = t.palette[1];
  const subColor = t.palette[2];
  const bankEdgeColor = t.palette[3];
  const halo = t.tooltipBg;
  const c = size / 2;

  // Ego highlighting (force view): hovering any node fades everything outside
  // its direct neighborhood.
  const ego = view === "all" ? hover : null;
  const egoSet = ego ? force.neighbors.get(ego) : null;
  const nodeDimmed = (id: string) => !!egoSet && !egoSet.has(id);
  const edgeDimmed = (e: ForceEdge) =>
    !!ego && e.source.id !== ego && e.target.id !== ego;

  const zoomMid = vb.w < size * 0.5;
  const zoomDeep = vb.w < size * 0.28;
  const leafLabelVisible = (n: ForceNode) =>
    hover === n.id ||
    (!!egoSet && egoSet.has(n.id)) ||
    zoomDeep ||
    (zoomMid && n.r >= 5.5);

  const hoveredNode = view === "all" && hover ? (nodeById.get(hover) ?? null) : null;
  const hoveredRingBank =
    view === "shared" && hover && !hover.includes(":")
      ? (ringBankPos.get(hover) ?? null)
      : null;
  const selShared = selectedShared ? (sharedByKey.get(selectedShared) ?? null) : null;

  const edgeColor = (e: ForceEdge) =>
    e.kind === "bankEdge" ? bankEdgeColor : e.kind === "holder" ? holderColor : subColor;

  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-muted-foreground">
        <div className="flex gap-1 rounded-[9px] border border-border bg-card p-[3px]">
          {(["all", "shared"] as const).map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => changeView(m)}
              className={`px-2 py-0.5 rounded-lg transition ${
                view === m
                  ? "bg-primary/10 font-semibold text-primary"
                  : "hover:text-foreground"
              }`}
            >
              {m === "all" ? "All holdings" : "Shared only"}
            </button>
          ))}
        </div>
        {Object.entries(BANK_TYPE_BADGE_LABELS).map(([code, label]) => (
          <span key={code} className="inline-flex items-center gap-1.5">
            <span
              className="inline-block size-2.5 rounded-full"
              style={{ background: seriesColor(t, code, 0) }}
            />
            {label}
          </span>
        ))}
        <span className="inline-flex items-center gap-1.5">
          <span
            className="inline-block size-2.5 rotate-45"
            style={{ background: t.palette[5] }}
          />
          Shared entity
        </span>
        {view === "all" && (
          <>
            <span className="inline-flex items-center gap-1.5">
              <span
                className="inline-block size-2 rounded-full"
                style={{ background: holderColor }}
              />
              Shareholder
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span
                className="inline-block size-2 rounded-full"
                style={{ background: subColor }}
              />
              Subsidiary
            </span>
          </>
        )}
        <span className="ml-auto">
          hover to highlight · scroll to zoom
          {view === "all" ? " (zoom in for names)" : ""} · click a bank to focus
        </span>
        {isZoomed && (
          <button
            type="button"
            onClick={() => animateVbTo({ x: 0, y: 0, w: size, h: size })}
            className="rounded border border-border px-1.5 py-0.5 hover:text-foreground"
          >
            Reset view
          </button>
        )}
      </div>

      <div className="relative">
        <svg
          ref={svgRef}
          viewBox={`${vb.x} ${vb.y} ${vb.w} ${vb.h}`}
          className="w-full h-auto cursor-grab select-none touch-none active:cursor-grabbing"
          role="img"
          aria-label="Sector ownership network"
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
        >
          <defs>
            <marker
              id="own-arrow"
              viewBox="0 0 8 8"
              refX={7}
              refY={4}
              markerWidth={7}
              markerHeight={7}
              orient="auto-start-reverse"
            >
              <path d="M0,0 L8,4 L0,8 z" fill={bankEdgeColor} />
            </marker>
          </defs>

          <rect
            x={vb.x}
            y={vb.y}
            width={vb.w}
            height={vb.h}
            fill="transparent"
            onClick={() => {
              if (!wasDrag()) {
                setSelectedShared(null);
                setSelectedLeaf(null);
              }
            }}
          />

          {view === "all" ? (
            <>
              {/* Edges (curved; quiet by default, lit inside the ego-network) */}
              {force.edges.map((e, i) => {
                const dim = edgeDimmed(e);
                const lit = !!ego && !dim;
                const isLeafEdge = e.source.kind === "leaf" || e.target.kind === "leaf";
                return (
                  <path
                    key={i}
                    d={curvedPath(
                      e.source.x,
                      e.source.y,
                      e.target.x,
                      e.target.y,
                      isLeafEdge ? 0.06 : 0.14,
                    )}
                    fill="none"
                    stroke={edgeColor(e)}
                    strokeWidth={
                      e.kind === "bankEdge"
                        ? lit
                          ? 2
                          : 1.25
                        : 0.7 + 1.6 * (Math.min(e.ratioPct ?? 0, 100) / 100)
                    }
                    strokeOpacity={
                      dim ? 0.02 : lit ? 0.75 : e.kind === "bankEdge" ? 0.5 : isLeafEdge ? 0.16 : 0.26
                    }
                    strokeDasharray={e.kind === "bankEdge" ? "5 4" : undefined}
                    markerEnd={e.kind === "bankEdge" ? "url(#own-arrow)" : undefined}
                    style={{ transition: "stroke-opacity 200ms, stroke-width 200ms" }}
                  />
                );
              })}

              {/* Nodes: leaves under shared under banks */}
              {(["leaf", "shared", "bank"] as const).map((kindPass) =>
                force.nodes
                  .filter((n) => n.kind === kindPass)
                  .map((n) => {
                    const active = hover === n.id;
                    const dim = nodeDimmed(n.id);
                    const color =
                      n.kind === "bank"
                        ? seriesColor(t, n.typeCode ?? "", 0)
                        : n.kind === "shared"
                          ? t.palette[5]
                          : n.leaf?.kind === "holder"
                            ? holderColor
                            : subColor;
                    return (
                      <g
                        key={n.id}
                        className="cursor-pointer"
                        style={{ opacity: dim ? 0.08 : 1, transition: "opacity 200ms" }}
                        onMouseEnter={() => setHover(n.id)}
                        onMouseLeave={() => setHover(null)}
                        onClick={(e) => {
                          e.stopPropagation();
                          if (wasDrag()) return;
                          if (n.kind === "bank") changeFocus(n.ticker);
                          else if (n.kind === "shared") {
                            setSelectedLeaf(null);
                            setSelectedShared(
                              selectedShared === n.sharedKey ? null : (n.sharedKey ?? null),
                            );
                          } else if (n.leaf) {
                            setSelectedShared(null);
                            setSelectedLeaf(
                              selectedLeaf?.leaf === n.leaf
                                ? null
                                : { ticker: n.ticker, leaf: n.leaf },
                            );
                          }
                        }}
                      >
                        {n.kind === "shared" ? (
                          <rect
                            x={n.x - n.r / 1.4}
                            y={n.y - n.r / 1.4}
                            width={(2 * n.r) / 1.4}
                            height={(2 * n.r) / 1.4}
                            transform={`rotate(45 ${n.x} ${n.y})`}
                            fill={color}
                            fillOpacity={active ? 1 : 0.8}
                          />
                        ) : (
                          <circle
                            cx={n.x}
                            cy={n.y}
                            r={active ? n.r + 1.5 : n.r}
                            fill={n.kind === "bank" && !n.hasData ? "transparent" : color}
                            fillOpacity={active ? 1 : n.kind === "leaf" ? 0.8 : 0.92}
                            stroke={n.kind === "bank" ? color : "none"}
                            strokeWidth={n.kind === "bank" ? (n.hasData ? 1 : 2) : 0}
                            strokeOpacity={0.9}
                          />
                        )}
                        {(n.kind === "bank" ||
                          n.kind === "shared" ||
                          leafLabelVisible(n)) && (
                          <text
                            x={n.x}
                            y={n.kind === "shared" ? n.y - n.r - 5 : n.y + n.r + 4}
                            dy={n.kind === "shared" ? 0 : "0.7em"}
                            textAnchor="middle"
                            fontSize={n.kind === "bank" ? 11 : n.kind === "shared" ? 10 : 8}
                            fontWeight={n.kind === "bank" ? 600 : 400}
                            paintOrder="stroke"
                            stroke={halo}
                            strokeWidth={3}
                            strokeLinejoin="round"
                            className={
                              active || n.kind === "bank"
                                ? "fill-foreground"
                                : "fill-muted-foreground"
                            }
                          >
                            {n.kind === "leaf" ? trimLabel(n.label, 26) : n.label}
                          </text>
                        )}
                      </g>
                    );
                  }),
              )}
            </>
          ) : (
            <>
              {/* Shared-entity spokes */}
              {ring.shared.map((s) =>
                s.links.map((l, i) => {
                  const b = ringBankPos.get(l.ticker);
                  if (!b) return null;
                  const active = hover === `s:${s.key}` || hover === l.ticker;
                  return (
                    <line
                      key={`${s.key}:${i}`}
                      x1={s.x}
                      y1={s.y}
                      x2={b.x}
                      y2={b.y}
                      stroke={l.kind === "holder" ? holderColor : subColor}
                      strokeWidth={0.75 + 2 * (Math.min(l.ratioPct ?? 0, 100) / 100)}
                      strokeOpacity={active ? 0.85 : 0.22}
                    />
                  );
                }),
              )}

              {/* Bank-to-bank stakes (dashed arrows owner → owned) */}
              {graph.bankEdges.map((e, i) => {
                const a = ringBankPos.get(e.from);
                const b = ringBankPos.get(e.to);
                if (!a || !b) return null;
                const mx = (a.x + b.x) / 2;
                const my = (a.y + b.y) / 2;
                // Bow the curve toward the center so it doesn't cut across labels.
                const qx = mx + (c - mx) * 0.35;
                const qy = my + (c - my) * 0.35;
                const active = hover === e.from || hover === e.to;
                return (
                  <path
                    key={i}
                    d={`M ${a.x} ${a.y} Q ${qx} ${qy} ${b.x} ${b.y}`}
                    fill="none"
                    stroke={bankEdgeColor}
                    strokeWidth={active ? 2 : 1.25}
                    strokeOpacity={active ? 0.9 : 0.5}
                    strokeDasharray="5 4"
                    markerEnd="url(#own-arrow)"
                  />
                );
              })}

              {/* Shared-entity nodes (diamonds) */}
              {ring.shared.map((s) => {
                const active = hover === `s:${s.key}` || selectedShared === s.key;
                const r = 7 + Math.min(s.links.length, 6);
                return (
                  <g
                    key={s.key}
                    className="cursor-pointer"
                    onMouseEnter={() => setHover(`s:${s.key}`)}
                    onMouseLeave={() => setHover(null)}
                    onClick={(e) => {
                      e.stopPropagation();
                      if (wasDrag()) return;
                      setSelectedShared(selectedShared === s.key ? null : s.key);
                    }}
                  >
                    <rect
                      x={s.x - r / 1.4}
                      y={s.y - r / 1.4}
                      width={(2 * r) / 1.4}
                      height={(2 * r) / 1.4}
                      transform={`rotate(45 ${s.x} ${s.y})`}
                      fill={t.palette[5]}
                      fillOpacity={active ? 1 : 0.8}
                      stroke={active ? t.palette[5] : "none"}
                      strokeWidth={2}
                      strokeOpacity={0.35}
                    />
                    <text
                      x={s.x}
                      y={s.y - r - 5}
                      textAnchor="middle"
                      fontSize={10}
                      paintOrder="stroke"
                      stroke={halo}
                      strokeWidth={3}
                      strokeLinejoin="round"
                      className={
                        active ? "fill-foreground font-medium" : "fill-muted-foreground"
                      }
                    >
                      {s.label}
                    </text>
                  </g>
                );
              })}

              {/* Bank nodes */}
              {ring.banks.map((b) => {
                const color = seriesColor(t, b.typeCode ?? "", 0);
                const active = hover === b.ticker;
                return (
                  <g
                    key={b.ticker}
                    className="cursor-pointer"
                    onMouseEnter={() => setHover(b.ticker)}
                    onMouseLeave={() => setHover(null)}
                    onClick={(e) => {
                      e.stopPropagation();
                      if (!wasDrag()) changeFocus(b.ticker);
                    }}
                  >
                    <circle
                      cx={b.x}
                      cy={b.y}
                      r={active ? 13 : 11}
                      fill={b.hasData ? color : "transparent"}
                      fillOpacity={active ? 1 : 0.85}
                      stroke={color}
                      strokeWidth={b.hasData ? 0 : 2}
                    />
                    <text
                      x={b.labelX}
                      y={b.labelY}
                      dy={b.anchor === "middle" ? (b.y < c ? "0" : "0.85em") : "0.32em"}
                      textAnchor={b.anchor}
                      fontSize={11}
                      className={
                        active ? "fill-foreground font-medium" : "fill-muted-foreground"
                      }
                    >
                      {b.name}
                    </text>
                  </g>
                );
              })}
            </>
          )}
        </svg>

        {/* Hover tooltip (force view: any node) */}
        {hoveredNode && (
          <div
            className="pointer-events-none absolute z-10 w-56 rounded-md border border-border bg-card px-3 py-2 text-xs shadow-md"
            style={{
              left: `${((hoveredNode.x - vb.x) / vb.w) * 100}%`,
              top: `${((hoveredNode.y - vb.y) / vb.h) * 100}%`,
              transform: `translate(${hoveredNode.x > vb.x + vb.w / 2 ? "-104%" : "12px"}, -50%)`,
            }}
          >
            {hoveredNode.kind === "bank" ? (
              <>
                <div className="font-medium text-foreground">{hoveredNode.label}</div>
                <div className="text-muted-foreground">
                  {hoveredNode.typeCode ? BANK_TYPE_BADGE_LABELS[hoveredNode.typeCode] : ""}
                </div>
                <div className="mt-0.5 text-muted-foreground">
                  {hoveredNode.hasData
                    ? `${hoveredNode.nHolders} shareholders · ${hoveredNode.nSubs} subsidiaries`
                    : "No KAP form filed — shown via counterparty stakes"}
                  {hoveredNode.freeFloatPct != null &&
                    ` · free float ${fmtPct(hoveredNode.freeFloatPct)}`}
                </div>
              </>
            ) : hoveredNode.kind === "shared" ? (
              <>
                <div className="font-medium text-foreground">{hoveredNode.label}</div>
                <div className="text-muted-foreground">
                  Linked to {new Set(hoveredNode.sharedLinks?.map((l) => l.ticker)).size}{" "}
                  banks — click for details
                </div>
              </>
            ) : (
              <>
                <div className="font-medium text-foreground">
                  {hoveredNode.leaf?.fullName}
                </div>
                <div className="text-muted-foreground">
                  {hoveredNode.leaf?.kind === "holder" ? "Shareholder of" : "Held by"}{" "}
                  {bankDisplayName(hoveredNode.ticker)} ·{" "}
                  <span className="tabular-nums">
                    {fmtPct(hoveredNode.leaf?.ratioPct ?? null)}
                  </span>
                </div>
                {hoveredNode.leaf?.activity && (
                  <div className="mt-0.5 text-muted-foreground line-clamp-2">
                    {hoveredNode.leaf.activity}
                  </div>
                )}
              </>
            )}
          </div>
        )}

        {/* Hover tooltip (ring view: banks) */}
        {hoveredRingBank && (
          <div
            className="pointer-events-none absolute z-10 w-52 rounded-md border border-border bg-card px-3 py-2 text-xs shadow-md"
            style={{
              left: `${((hoveredRingBank.x - vb.x) / vb.w) * 100}%`,
              top: `${((hoveredRingBank.y - vb.y) / vb.h) * 100}%`,
              transform: `translate(${hoveredRingBank.x > c ? "-104%" : "14px"}, -50%)`,
            }}
          >
            <div className="font-medium text-foreground">{hoveredRingBank.name}</div>
            <div className="text-muted-foreground">
              {hoveredRingBank.typeCode
                ? BANK_TYPE_BADGE_LABELS[hoveredRingBank.typeCode]
                : ""}
            </div>
            <div className="mt-0.5 text-muted-foreground">
              {hoveredRingBank.hasData
                ? `${hoveredRingBank.nHolders} shareholders · ${hoveredRingBank.nSubs} subsidiaries`
                : "No KAP form filed — shown via counterparty stakes"}
            </div>
          </div>
        )}
      </div>

      {/* Shared-entity panel */}
      {selShared && (
        <div className="mt-2 border-t border-border px-1 pt-3 text-xs">
          <div className="font-medium text-foreground">{selShared.label}</div>
          <div className="mt-1 flex flex-wrap gap-x-4 gap-y-0.5">
            {selShared.links.map((l, i) => (
              <button
                key={i}
                type="button"
                onClick={() => changeFocus(l.ticker)}
                className="text-foreground underline-offset-2 hover:underline"
              >
                {bankDisplayName(l.ticker)}{" "}
                <span className="tabular-nums text-muted-foreground">
                  {l.kind === "holder" ? "shareholder" : "subsidiary"} · {fmtPct(l.ratioPct)}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Pinned holding panel (force view) */}
      {selectedLeaf && (
        <div className="mt-2 border-t border-border px-1 pt-3 text-xs">
          <div className="mb-1 text-muted-foreground">
            {selectedLeaf.leaf.kind === "holder" ? "Shareholder of" : "Holding of"}{" "}
            <button
              type="button"
              onClick={() => changeFocus(selectedLeaf.ticker)}
              className="text-foreground underline-offset-2 hover:underline"
            >
              {bankDisplayName(selectedLeaf.ticker)} →
            </button>
          </div>
          <LeafPanel
            leaf={selectedLeaf.leaf}
            sharedLookup={(key) => sharedByKey.get(key)}
            onBankRefClick={(next) => changeFocus(next)}
            focusTicker={selectedLeaf.ticker}
          />
        </div>
      )}
    </div>
  );
}
