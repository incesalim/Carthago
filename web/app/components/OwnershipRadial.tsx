"use client";

/**
 * OwnershipRadial — interactive radial ownership map on /banks/[ticker].
 *
 * Bank node in the center; ≥5% shareholders fan the top arc, §7 subsidiaries
 * the bottom (node size + edge width ∝ stake). Hover shows a tooltip; click
 * pins a details panel under the SVG with the un-truncated filing fields.
 * Renders nothing when the bank has no KAP form (e.g. ATBANK).
 *
 * The SVG fan itself is exported as `RadialFanView` so the /ownership sector
 * network reuses it in focus mode (with refocus hooks for bank-linked nodes).
 */
import { useMemo, useState } from "react";
import type { KapOwnershipRow } from "@/app/lib/kap";
import {
  buildBankNodes,
  layoutRadial,
  trimLabel,
  type GraphLeaf,
  type PlacedLeaf,
  type SharedHolder,
} from "@/app/lib/ownership-graph";
import { seriesColor, useChartTheme, type ChartTheme } from "@/app/lib/chart-theme";
import { BANK_TYPE_BY_TICKER, bankDisplayName } from "@/app/lib/bank_names";
import { fmtAmount, fmtAsOf, fmtPct, relationLabel } from "@/app/lib/ownership-format";

// ---------------------------------------------------------------------------
// Shared fan view (per-bank card + sector focus mode)
// ---------------------------------------------------------------------------

export interface RadialFanProps {
  ticker: string;
  typeCode?: string;
  holders: GraphLeaf[];
  subs: GraphLeaf[];
  indirect: { fullName: string; ratioPct: number | null }[];
  freeFloatPct: number | null;
  /** Sector mode: refocus when a leaf that is itself a bank is clicked. */
  onBankRefClick?: (ticker: string) => void;
  /** Sector mode: resolve a leaf's sharedKey to its cross-bank links. */
  sharedLookup?: (key: string) => SharedHolder | undefined;
}

function leafColor(leaf: GraphLeaf, t: ChartTheme): string {
  if (leaf.isOther || leaf.collapsed) return t.palette[5];
  if (leaf.bankRef) return seriesColor(t, BANK_TYPE_BY_TICKER[leaf.bankRef] ?? "", 3);
  return leaf.kind === "holder" ? t.palette[1] : t.palette[2];
}

export function RadialFanView({
  ticker,
  typeCode,
  holders,
  subs,
  indirect,
  freeFloatPct,
  onBankRefClick,
  sharedLookup,
}: RadialFanProps) {
  const t = useChartTheme();
  const [hoverId, setHoverId] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const layout = useMemo(() => layoutRadial(holders, subs), [holders, subs]);
  const placed = useMemo(() => [...layout.top, ...layout.bottom], [layout]);
  const byId = useMemo(
    () => new Map(placed.map((p) => [p.leaf.id, p])),
    [placed],
  );

  const centerColor = seriesColor(t, typeCode ?? "", 0);
  const hovered = hoverId === "center" ? null : (hoverId && byId.get(hoverId)) || null;
  const selected =
    selectedId === "center" ? null : (selectedId && byId.get(selectedId)) || null;

  const { width: W, height: H, cx, cy } = layout;

  const labelDy = (p: PlacedLeaf, side: "top" | "bottom") =>
    p.anchor === "middle" ? (side === "top" ? "0" : "0.85em") : "0.32em";

  const renderSide = (side: "top" | "bottom", nodes: PlacedLeaf[]) => (
    <g key={side}>
      {nodes.map((p) => {
        const active = hoverId === p.leaf.id || selectedId === p.leaf.id;
        const color = leafColor(p.leaf, t);
        const ratio = Math.min(Math.max(p.leaf.ratioPct ?? 0, 0), 100);
        return (
          <g
            key={p.leaf.id}
            className="cursor-pointer"
            onMouseEnter={() => setHoverId(p.leaf.id)}
            onMouseLeave={() => setHoverId(null)}
            onClick={(e) => {
              e.stopPropagation();
              if (p.leaf.bankRef && onBankRefClick) onBankRefClick(p.leaf.bankRef);
              else setSelectedId(selectedId === p.leaf.id ? null : p.leaf.id);
            }}
          >
            <line
              x1={cx}
              y1={cy}
              x2={p.x}
              y2={p.y}
              stroke={color}
              strokeWidth={0.75 + 2.25 * (ratio / 100)}
              strokeOpacity={active ? 0.9 : 0.35}
            />
            <circle
              cx={p.x}
              cy={p.y}
              r={p.r}
              fill={color}
              fillOpacity={active ? 1 : 0.85}
              stroke={active ? color : "none"}
              strokeWidth={active ? 2 : 0}
              strokeOpacity={0.35}
              strokeDasharray={p.leaf.ratioPct == null ? "2 2" : undefined}
            />
            {p.leaf.bankRef && (
              <circle
                cx={p.x}
                cy={p.y}
                r={p.r + 3}
                fill="none"
                stroke={color}
                strokeWidth={1}
                strokeOpacity={0.6}
              />
            )}
            <text
              x={p.labelX}
              y={p.labelY}
              dy={labelDy(p, side)}
              textAnchor={p.anchor}
              fontSize={10}
              className={active ? "fill-foreground font-medium" : "fill-muted-foreground"}
            >
              {trimLabel(p.leaf.label)}
            </text>
          </g>
        );
      })}
    </g>
  );

  return (
    <div className="relative">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="w-full h-auto select-none"
        role="img"
        aria-label={`Ownership map of ${bankDisplayName(ticker)}`}
      >
        <rect
          width={W}
          height={H}
          fill="transparent"
          onClick={() => setSelectedId(null)}
        />
        {renderSide("top", layout.top)}
        {renderSide("bottom", layout.bottom)}

        {/* Center bank node */}
        <g
          className="cursor-pointer"
          onMouseEnter={() => setHoverId("center")}
          onMouseLeave={() => setHoverId(null)}
          onClick={(e) => {
            e.stopPropagation();
            setSelectedId(selectedId === "center" ? null : "center");
          }}
        >
          <circle
            cx={cx}
            cy={cy}
            r={30}
            fill={centerColor}
            stroke={selectedId === "center" ? centerColor : "none"}
            strokeWidth={2}
            strokeOpacity={0.35}
          />
          <text
            x={cx}
            y={cy}
            dy="0.35em"
            textAnchor="middle"
            fontSize={12}
            fontWeight={600}
            fill="#fff"
          >
            {ticker}
          </text>
        </g>

        {/* Arc captions */}
        {holders.length > 0 && (
          <text x={12} y={16} fontSize={10} className="fill-muted-foreground uppercase tracking-wide">
            Shareholders
          </text>
        )}
        {subs.length > 0 && (
          <text x={12} y={H - 8} fontSize={10} className="fill-muted-foreground uppercase tracking-wide">
            Subsidiaries &amp; investments
          </text>
        )}
      </svg>

      {/* Hover tooltip (HTML overlay — wraps long Turkish names, theme-aware) */}
      {hovered && hoverId !== selectedId && (
        <div
          className="pointer-events-none absolute z-10 w-60 rounded-md border border-border bg-card px-3 py-2 text-xs shadow-md"
          style={{
            left: `${(hovered.x / W) * 100}%`,
            top: `${(hovered.y / H) * 100}%`,
            transform: `translate(${hovered.x > cx ? "-104%" : "10px"}, -50%)`,
          }}
        >
          <div className="font-medium text-foreground">{hovered.leaf.fullName}</div>
          <div className="mt-1 space-y-0.5 text-muted-foreground">
            <div>
              {hovered.leaf.kind === "holder" ? "Share" : "Ownership"}:{" "}
              <span className="tabular-nums text-foreground">{fmtPct(hovered.leaf.ratioPct)}</span>
            </div>
            {hovered.leaf.kind === "holder" && hovered.leaf.votingPct != null && (
              <div>
                Voting: <span className="tabular-nums">{fmtPct(hovered.leaf.votingPct)}</span>
              </div>
            )}
            {hovered.leaf.kind === "sub" && (
              <>
                <div>Capital share: {fmtAmount(hovered.leaf.shareAmt, hovered.leaf.currency)}</div>
                <div>Relation: {relationLabel(hovered.leaf.relation)}</div>
              </>
            )}
            {hovered.leaf.activity && (
              <div className="line-clamp-3">{hovered.leaf.activity}</div>
            )}
            {fmtAsOf(hovered.leaf.asOf) && <div>Filed {fmtAsOf(hovered.leaf.asOf)}</div>}
          </div>
        </div>
      )}

      {/* Pinned details panel */}
      {(selected || selectedId === "center") && (
        <div className="mt-2 border-t border-border px-1 pt-3 text-xs">
          {selectedId === "center" ? (
            <CenterPanel
              ticker={ticker}
              freeFloatPct={freeFloatPct}
              indirect={indirect}
              nHolders={holders.length}
              nSubs={subs.length}
            />
          ) : selected ? (
            <LeafPanel
              leaf={selected.leaf}
              sharedLookup={sharedLookup}
              onBankRefClick={onBankRefClick}
              focusTicker={ticker}
            />
          ) : null}
        </div>
      )}
    </div>
  );
}

function CenterPanel({
  ticker,
  freeFloatPct,
  indirect,
  nHolders,
  nSubs,
}: {
  ticker: string;
  freeFloatPct: number | null;
  indirect: { fullName: string; ratioPct: number | null }[];
  nHolders: number;
  nSubs: number;
}) {
  return (
    <div className="space-y-1.5">
      <div className="font-medium text-foreground">{bankDisplayName(ticker)}</div>
      <div className="text-muted-foreground">
        {nHolders} disclosed shareholder{nHolders === 1 ? "" : "s"} ·{" "}
        {nSubs} subsidiar{nSubs === 1 ? "y" : "ies"} / investments
        {freeFloatPct != null && <> · free float {fmtPct(freeFloatPct)}</>}
      </div>
      {indirect.length > 0 && (
        <div>
          <div className="mt-1 text-[10px] uppercase tracking-wide text-muted-foreground">
            Indirect (ultimate) holders ≥5%
          </div>
          {indirect.map((h, i) => (
            <div key={i} className="flex justify-between gap-3 text-muted-foreground">
              <span className="min-w-0 truncate" title={h.fullName}>
                {h.fullName}
              </span>
              <span className="shrink-0 tabular-nums">{fmtPct(h.ratioPct)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function LeafPanel({
  leaf,
  sharedLookup,
  onBankRefClick,
  focusTicker,
}: {
  leaf: GraphLeaf;
  sharedLookup?: (key: string) => SharedHolder | undefined;
  onBankRefClick?: (ticker: string) => void;
  focusTicker: string;
}) {
  const shared = leaf.sharedKey && sharedLookup ? sharedLookup(leaf.sharedKey) : undefined;
  const otherLinks = shared?.links.filter((l) => l.ticker !== focusTicker) ?? [];

  if (leaf.collapsed) {
    return (
      <div className="space-y-1">
        <div className="font-medium text-foreground">{leaf.fullName}</div>
        {leaf.collapsed.map((c) => (
          <div key={c.id} className="flex justify-between gap-3 text-muted-foreground">
            <span className="min-w-0 truncate" title={c.fullName}>{c.fullName}</span>
            <span className="shrink-0 tabular-nums">{fmtPct(c.ratioPct)}</span>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-1">
      <div className="font-medium text-foreground">{leaf.fullName}</div>
      <div className="grid gap-x-6 gap-y-0.5 text-muted-foreground sm:grid-cols-2">
        <div>
          {leaf.kind === "holder" ? "Share of capital" : "Bank's ownership"}:{" "}
          <span className="tabular-nums text-foreground">{fmtPct(leaf.ratioPct)}</span>
        </div>
        {leaf.kind === "holder" && leaf.votingPct != null && (
          <div>
            Voting rights: <span className="tabular-nums">{fmtPct(leaf.votingPct)}</span>
          </div>
        )}
        {leaf.kind === "holder" && leaf.shareAmt != null && (
          <div>Nominal: {fmtAmount(leaf.shareAmt, "TRY")}</div>
        )}
        {leaf.kind === "sub" && (
          <>
            <div>Capital share: {fmtAmount(leaf.shareAmt, leaf.currency)}</div>
            <div>Relation: {relationLabel(leaf.relation)}</div>
          </>
        )}
        {fmtAsOf(leaf.asOf) && <div>Filed {fmtAsOf(leaf.asOf)}</div>}
      </div>
      {leaf.activity && <div className="text-muted-foreground">{leaf.activity}</div>}
      {otherLinks.length > 0 && (
        <div>
          <div className="mt-1 text-[10px] uppercase tracking-wide text-muted-foreground">
            Also linked to
          </div>
          <div className="flex flex-wrap gap-x-4 gap-y-0.5">
            {otherLinks.map((l, i) =>
              onBankRefClick ? (
                <button
                  key={i}
                  type="button"
                  onClick={() => onBankRefClick(l.ticker)}
                  className="text-foreground underline-offset-2 hover:underline"
                >
                  {bankDisplayName(l.ticker)}{" "}
                  <span className="tabular-nums text-muted-foreground">
                    {fmtPct(l.ratioPct)}
                  </span>
                </button>
              ) : (
                <span key={i} className="text-muted-foreground">
                  {bankDisplayName(l.ticker)}{" "}
                  <span className="tabular-nums">{fmtPct(l.ratioPct)}</span>
                </span>
              ),
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Per-bank card (default export, used on /banks/[ticker])
// ---------------------------------------------------------------------------

interface Props {
  ticker: string;
  rows: KapOwnershipRow[];
}

export default function OwnershipRadial({ ticker, rows }: Props) {
  const nodes = useMemo(() => buildBankNodes(rows), [rows]);
  if (nodes.holders.length === 0 && nodes.subs.length === 0) return null;

  return (
    <section className="mb-6 rounded-2xl border border-border bg-card overflow-hidden">
      <div className="px-5 py-3 border-b bg-muted flex items-baseline justify-between">
        <h2 className="text-sm font-semibold text-foreground">Ownership map</h2>
        <span className="text-[11px] text-muted-foreground">
          hover for details · click to pin
        </span>
      </div>
      <div className="px-3 py-2">
        <RadialFanView
          ticker={ticker}
          typeCode={BANK_TYPE_BY_TICKER[ticker]}
          holders={nodes.holders}
          subs={nodes.subs}
          indirect={nodes.indirect}
          freeFloatPct={nodes.freeFloatPct}
        />
      </div>
    </section>
  );
}
