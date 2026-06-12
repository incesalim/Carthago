/**
 * Force-directed layout for the combined /ownership network ("All holdings").
 *
 * d3-force simulation run synchronously and deterministically (seeded
 * randomSource + seeded initial positions), so server render and client
 * hydration agree and the layout is stable across visits.
 *
 * Structure: banks are anchored loosely to a ring (forceRadial) in BDDK
 * type-group order — link forces then pull cross-held banks and shared
 * entities together, while each bank's own holdings settle as an organic
 * blob around it. Node radius encodes total assets for banks and stake
 * size for holdings.
 */
import {
  forceCollide,
  forceLink,
  forceManyBody,
  forceRadial,
  forceSimulation,
  forceX,
  forceY,
  type SimulationLinkDatum,
  type SimulationNodeDatum,
} from "d3-force";
import type { GraphLeaf, OwnershipGraph, SharedHolderLink } from "./ownership-graph";

export interface ForceNode extends SimulationNodeDatum {
  id: string;
  kind: "bank" | "shared" | "leaf";
  label: string;
  r: number;
  /** Bank nodes: own ticker. Leaf nodes: the owning/owned bank. */
  ticker: string;
  typeCode?: string;
  hasData?: boolean;
  nHolders?: number;
  nSubs?: number;
  freeFloatPct?: number | null;
  leaf?: GraphLeaf;
  sharedKey?: string;
  sharedLinks?: SharedHolderLink[];
  x: number;
  y: number;
}

export interface ForceEdge {
  source: ForceNode;
  target: ForceNode;
  kind: "holder" | "sub" | "bankEdge";
  ratioPct: number | null;
}

export interface ForceLayout {
  size: number;
  nodes: ForceNode[];
  edges: ForceEdge[];
  /** node id → ids of itself + direct neighbors (for ego highlighting). */
  neighbors: Map<string, Set<string>>;
}

export const FORCE_SIZE = 1200;
const RING_R = 330;
const GROUP_ORDER = ["10006", "10005", "10007", "10003", "10004"];

/** Bank node radius from latest total assets (√ scale, 10–30px). */
function bankRadius(assets: number | null | undefined, maxAssets: number): number {
  if (assets == null || assets <= 0 || maxAssets <= 0) return 9;
  return 10 + 20 * Math.sqrt(assets / maxAssets);
}

function leafRadius(ratioPct: number | null): number {
  const ratio = Math.min(Math.max(ratioPct ?? 0, 0), 100);
  return 3 + 5.5 * Math.sqrt(ratio / 100);
}

export function buildForceLayout(
  graph: OwnershipGraph,
  assets: Record<string, number | null>,
): ForceLayout {
  const c = FORCE_SIZE / 2;
  const maxAssets = Math.max(0, ...Object.values(assets).map((v) => v ?? 0));

  const ordered = [...graph.banks].sort((a, b) => {
    const ga = GROUP_ORDER.indexOf(a.typeCode ?? "");
    const gb = GROUP_ORDER.indexOf(b.typeCode ?? "");
    return ga !== gb ? ga - gb : a.ticker.localeCompare(b.ticker);
  });

  const nodes: ForceNode[] = [];
  const rawEdges: { source: string; target: string; kind: ForceEdge["kind"]; ratioPct: number | null }[] = [];
  const bankAngle = new Map<string, number>();

  // Banks seeded on a ring in type-group order.
  ordered.forEach((b, i) => {
    const a = -Math.PI / 2 + (2 * Math.PI * i) / ordered.length;
    bankAngle.set(b.ticker, a);
    nodes.push({
      id: b.ticker,
      kind: "bank",
      label: b.name,
      r: bankRadius(assets[b.ticker], maxAssets),
      ticker: b.ticker,
      typeCode: b.typeCode,
      hasData: b.holders.length + b.subs.length > 0,
      nHolders: b.holders.length,
      nSubs: b.subs.length,
      freeFloatPct: b.freeFloatPct,
      x: c + RING_R * Math.cos(a),
      y: c + RING_R * Math.sin(a),
    });
  });

  // Shared entities seeded at the centroid of their banks, pulled inward.
  for (const s of graph.sharedHolders) {
    const tickers = [...new Set(s.links.map((l) => l.ticker))];
    let vx = 0;
    let vy = 0;
    for (const t2 of tickers) {
      const a = bankAngle.get(t2);
      if (a == null) continue;
      vx += Math.cos(a);
      vy += Math.sin(a);
    }
    const id = `s:${s.key}`;
    nodes.push({
      id,
      kind: "shared",
      label: s.label,
      r: 7 + Math.min(s.links.length, 6),
      ticker: tickers[0] ?? "",
      sharedKey: s.key,
      sharedLinks: s.links,
      x: c + (vx / tickers.length) * RING_R * 0.45,
      y: c + (vy / tickers.length) * RING_R * 0.45,
    });
    for (const l of s.links) {
      rawEdges.push({ source: id, target: l.ticker, kind: l.kind, ratioPct: l.ratioPct });
    }
  }

  // Per-bank holdings (golden-angle spiral seed around the bank).
  const GOLDEN = 2.399963229728653;
  for (const b of graph.banks) {
    const a0 = bankAngle.get(b.ticker) ?? 0;
    const bx = c + RING_R * Math.cos(a0);
    const by = c + RING_R * Math.sin(a0);
    const own = [...b.holders, ...b.subs].filter(
      (l) => !l.sharedKey && !l.bankRef && !l.isOther,
    );
    own.forEach((leaf, j) => {
      const id = `l:${b.ticker}:${leaf.id}`;
      const sa = a0 + j * GOLDEN;
      const sr = 30 + 7 * Math.sqrt(j);
      nodes.push({
        id,
        kind: "leaf",
        label: leaf.label,
        r: leafRadius(leaf.ratioPct),
        ticker: b.ticker,
        leaf,
        x: bx + sr * Math.cos(sa),
        y: by + sr * Math.sin(sa),
      });
      rawEdges.push({ source: b.ticker, target: id, kind: leaf.kind, ratioPct: leaf.ratioPct });
    });
  }

  for (const e of graph.bankEdges) {
    rawEdges.push({ source: e.from, target: e.to, kind: "bankEdge", ratioPct: e.ratioPct });
  }

  interface SimLink extends SimulationLinkDatum<ForceNode> {
    kind: ForceEdge["kind"];
    ratioPct: number | null;
  }
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const links: SimLink[] = rawEdges
    .filter((e) => byId.has(e.source) && byId.has(e.target))
    .map((e) => ({ ...e }));

  // Deterministic LCG so coincident-node jiggle is reproducible (SSR ===
  // client hydration).
  let seed = 42;
  const rand = () => {
    seed = (seed * 1664525 + 1013904223) % 4294967296;
    return seed / 4294967296;
  };

  const sim = forceSimulation(nodes)
    .randomSource(rand)
    .force(
      "link",
      forceLink<ForceNode, SimLink>(links)
        .id((d) => d.id)
        .distance((l) => {
          const s = l.source as ForceNode;
          const t2 = l.target as ForceNode;
          if (l.kind === "bankEdge") return 170;
          if (s.kind === "shared" || t2.kind === "shared") return 130;
          return s.r + t2.r + 16;
        })
        .strength((l) => {
          if (l.kind === "bankEdge") return 0.25;
          const s = l.source as ForceNode;
          const t2 = l.target as ForceNode;
          if (s.kind === "shared" || t2.kind === "shared") return 0.2;
          return 0.85;
        }),
    )
    .force(
      "charge",
      forceManyBody<ForceNode>().strength((d) =>
        d.kind === "bank" ? -320 : d.kind === "shared" ? -140 : -14,
      ),
    )
    .force(
      "collide",
      forceCollide<ForceNode>()
        .radius((d) => d.r + (d.kind === "bank" ? 14 : d.kind === "shared" ? 9 : 2.5))
        .iterations(2),
    )
    .force(
      "ring",
      forceRadial<ForceNode>(RING_R, c, c).strength((d) =>
        d.kind === "bank" ? 0.12 : 0,
      ),
    )
    .force("cx", forceX<ForceNode>(c).strength(0.015))
    .force("cy", forceY<ForceNode>(c).strength(0.015))
    .stop();

  for (let i = 0; i < 280; i++) sim.tick();

  // Keep everything inside the canvas.
  const pad = 26;
  for (const n of nodes) {
    n.x = Math.min(Math.max(n.x, pad + n.r), FORCE_SIZE - pad - n.r);
    n.y = Math.min(Math.max(n.y, pad + n.r), FORCE_SIZE - pad - n.r);
  }

  // After the simulation, d3 has resolved string ids to node references.
  const edges: ForceEdge[] = links.map((l) => ({
    source: l.source as ForceNode,
    target: l.target as ForceNode,
    kind: l.kind,
    ratioPct: l.ratioPct,
  }));

  const neighbors = new Map<string, Set<string>>();
  const touch = (a: string, b: string) => {
    if (!neighbors.has(a)) neighbors.set(a, new Set([a]));
    neighbors.get(a)!.add(b);
  };
  for (const e of edges) {
    touch(e.source.id, e.target.id);
    touch(e.target.id, e.source.id);
  }
  for (const n of nodes) if (!neighbors.has(n.id)) neighbors.set(n.id, new Set([n.id]));

  return { size: FORCE_SIZE, nodes, edges, neighbors };
}
