"use client";

/**
 * OwnershipNetwork — sector-wide ownership graph on /ownership.
 *
 * Overview: all banks on a circle (grouped + colored by BDDK type), with only
 * the entities shared across ≥2 banks drawn inside (Treasury, TVF, BKM,
 * Takasbank, KGF, …) and bank-to-bank stakes as dashed arrows. Per-bank
 * leaves (~300) stay hidden at rest — click a bank to swap to its radial fan
 * (same view as /banks/[ticker]), where bank-linked nodes refocus on click.
 *
 * Overview supports wheel-zoom + drag-pan via viewBox manipulation; focus is
 * mirrored to ?focus=TICKER with shallow history.replaceState (no server
 * roundtrip on a force-dynamic page).
 */
import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import {
  layoutNetwork,
  NETWORK_SIZE,
  type OwnershipGraph,
  type GraphLeaf,
} from "@/app/lib/ownership-graph";
import { RadialFanView } from "./OwnershipRadial";
import { seriesColor, useChartTheme } from "@/app/lib/chart-theme";
import { BANK_TYPE_BADGE_LABELS, bankDisplayName } from "@/app/lib/bank_names";
import { fmtPct } from "@/app/lib/ownership-format";

interface ViewBox {
  x: number;
  y: number;
  w: number;
  h: number;
}

const INITIAL_VB: ViewBox = { x: 0, y: 0, w: NETWORK_SIZE, h: NETWORK_SIZE };

interface Props {
  graph: OwnershipGraph;
  initialFocus?: string;
}

export default function OwnershipNetwork({ graph, initialFocus }: Props) {
  const t = useChartTheme();
  const validFocus = (f: string | null | undefined) =>
    f && graph.banks.some((b) => b.ticker === f) ? f : null;
  const [focus, setFocus] = useState<string | null>(() => validFocus(initialFocus));
  const [hover, setHover] = useState<string | null>(null);
  const [selectedShared, setSelectedShared] = useState<string | null>(null);

  const layout = useMemo(() => layoutNetwork(graph), [graph]);
  const bankPos = useMemo(
    () => new Map(layout.banks.map((b) => [b.ticker, b])),
    [layout],
  );
  const sharedByKey = useMemo(
    () => new Map(graph.sharedHolders.map((s) => [s.key, s])),
    [graph],
  );

  // ----- overview zoom/pan (viewBox manipulation, no library) --------------
  const [vb, setVb] = useState<ViewBox>(INITIAL_VB);
  const svgRef = useRef<SVGSVGElement | null>(null);
  const dragRef = useRef<{ px: number; py: number; moved: number } | null>(null);
  const lastDragMoved = useRef(0);
  const wasDrag = () => lastDragMoved.current > 4;
  const isZoomed = vb.x !== 0 || vb.y !== 0 || vb.w !== NETWORK_SIZE;

  // Native non-passive wheel listener — React's synthetic onWheel is passive,
  // so preventDefault (needed to stop page scroll) would warn. Re-attach when
  // leaving focus mode (the overview SVG remounts). Cursor-anchored zoom: the
  // SVG point under the cursor stays fixed while w/h scale.
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
        const w = Math.min(Math.max(cur.w * factor, NETWORK_SIZE * 0.4), NETWORK_SIZE * 2.5);
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
  }, [focus]);

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

  const changeFocus = (next: string | null) => {
    setFocus(next);
    setSelectedShared(null);
    setHover(null);
    window.history.replaceState(
      null,
      "",
      next ? `?focus=${next}` : window.location.pathname,
    );
  };

  // ----- focus mode -------------------------------------------------------
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

  // ----- overview ---------------------------------------------------------
  const holderColor = t.palette[1];
  const subColor = t.palette[2];
  const bankEdgeColor = t.palette[3];
  const c = layout.size / 2;
  const hoveredBank = hover ? bankPos.get(hover) : null;
  const selShared = selectedShared
    ? layout.shared.find((s) => s.key === selectedShared)
    : null;

  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-muted-foreground">
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
        <span className="ml-auto">scroll to zoom · drag to pan · click a bank to focus</span>
        {isZoomed && (
          <button
            type="button"
            onClick={() => setVb(INITIAL_VB)}
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
              if (!wasDrag()) setSelectedShared(null);
            }}
          />

          {/* Shared-entity spokes */}
          {layout.shared.map((s) =>
            s.links.map((l, i) => {
              const b = bankPos.get(l.ticker);
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
            const a = bankPos.get(e.from);
            const b = bankPos.get(e.to);
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
          {layout.shared.map((s) => {
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
                  className={active ? "fill-foreground font-medium" : "fill-muted-foreground"}
                >
                  {s.label}
                </text>
              </g>
            );
          })}

          {/* Bank nodes */}
          {layout.banks.map((b) => {
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
                  className={active ? "fill-foreground font-medium" : "fill-muted-foreground"}
                >
                  {b.name}
                </text>
              </g>
            );
          })}
        </svg>

        {/* Bank hover tooltip */}
        {hoveredBank && (
          <div
            className="pointer-events-none absolute z-10 w-52 rounded-md border border-border bg-card px-3 py-2 text-xs shadow-md"
            style={{
              left: `${((hoveredBank.x - vb.x) / vb.w) * 100}%`,
              top: `${((hoveredBank.y - vb.y) / vb.h) * 100}%`,
              transform: `translate(${hoveredBank.x > c ? "-104%" : "14px"}, -50%)`,
            }}
          >
            <div className="font-medium text-foreground">{hoveredBank.name}</div>
            <div className="text-muted-foreground">
              {hoveredBank.typeCode ? BANK_TYPE_BADGE_LABELS[hoveredBank.typeCode] : ""}
            </div>
            <div className="mt-0.5 text-muted-foreground">
              {hoveredBank.hasData
                ? `${hoveredBank.nHolders} shareholders · ${hoveredBank.nSubs} subsidiaries`
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
    </div>
  );
}
