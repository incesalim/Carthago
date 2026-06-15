/**
 * Deterministic layered layout for the pipeline graph.
 *
 * React Flow needs explicit x/y per node; rather than pull in a layout engine
 * (dagre/elkjs), positions are derived purely from each node's `layer` (→ column)
 * and `lane` (→ horizontal band). Same input ⇒ same output every render, which
 * also keeps SSR/hydration stable.
 *
 *   columns:  source → ingestion → storage → page   (left → right)
 *   bands:    bulletin (top) → audit → shared        (stacked vertically)
 *
 * Each (lane, layer) group is centred vertically within its band so the columns
 * stay visually balanced despite very different node counts.
 */
import type { Layer, Lane, PipelineNode } from "./pipeline-graph";

export const NODE_W = 234;
export const NODE_H = 64;
const COL_GAP = 340; // x-distance between column origins
const ROW_PITCH = NODE_H + 24; // y-distance between stacked nodes
const LANE_GAP = 96; // vertical gutter between bands
const BAND_PAD_X = 28;
const BAND_PAD_Y = 44; // room for the band's title above its first row

const LAYER_ORDER: Layer[] = ["source", "ingestion", "storage", "page"];
const LANE_ORDER: Lane[] = ["bulletin", "audit", "shared"];

export interface LaneBand {
  id: string;
  lane: Lane;
  label: string;
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface PipelineLayout {
  positions: Record<string, { x: number; y: number }>;
  bands: LaneBand[];
  width: number;
  height: number;
}

const LANE_LABEL: Record<Lane, string> = {
  bulletin: "Bulletin & macro lane · bddk-pipeline",
  audit: "Audit lane · bddk-audit",
  shared: "Shared infra · snapshots · cache · CI/CD · monitoring",
};

export function computeLayout(nodes: PipelineNode[]): PipelineLayout {
  // Bucket nodes by lane → layer, preserving array order within each group.
  const byLane = new Map<Lane, Map<Layer, PipelineNode[]>>();
  for (const lane of LANE_ORDER) byLane.set(lane, new Map());
  for (const n of nodes) {
    const lane = byLane.get(n.lane);
    if (!lane) continue;
    const group = lane.get(n.layer) ?? [];
    group.push(n);
    lane.set(n.layer, group);
  }

  const totalWidth = (LAYER_ORDER.length - 1) * COL_GAP + NODE_W;
  const positions: Record<string, { x: number; y: number }> = {};
  const bands: LaneBand[] = [];

  let bandTop = 0;
  for (const lane of LANE_ORDER) {
    const layers = byLane.get(lane)!;
    const bandRows = Math.max(1, ...LAYER_ORDER.map((l) => layers.get(l)?.length ?? 0));
    const bandHeight = bandRows * ROW_PITCH;

    for (let li = 0; li < LAYER_ORDER.length; li++) {
      const group = layers.get(LAYER_ORDER[li]) ?? [];
      const startRow = (bandRows - group.length) / 2; // centre the column in the band
      group.forEach((n, i) => {
        positions[n.id] = {
          x: li * COL_GAP,
          y: bandTop + (startRow + i) * ROW_PITCH,
        };
      });
    }

    bands.push({
      id: `band-${lane}`,
      lane,
      label: LANE_LABEL[lane],
      x: -BAND_PAD_X,
      y: bandTop - BAND_PAD_Y,
      width: totalWidth + BAND_PAD_X * 2,
      height: bandHeight + BAND_PAD_Y,
    });

    bandTop += bandHeight + LANE_GAP;
  }

  return { positions, bands, width: totalWidth, height: bandTop };
}
