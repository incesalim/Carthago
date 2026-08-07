/**
 * Agent workflow diagram — swimlanes by kind.
 *
 * A row per kind of work (deterministic · model · guard · output), a column per
 * step in the flow. That makes the architectural claim STRUCTURAL rather than a
 * colour legend: you can see the investigation crossing out of deterministic
 * code into the model and back again, and you can see that everything reaching
 * the output row passed through guard.
 *
 * Replaces a single-row strip whose details all truncated to "…" and whose
 * return arcs crossed each other under the nodes — it looked like information
 * without being readable.
 *
 * Routing is orthogonal, which is what keeps it legible: forward edges elbow
 * between columns, and RETURN edges (loop/retry, i.e. anything going backwards)
 * drop into a dedicated channel below the lanes, each at its own depth so two
 * returns never share a line. Deliberately not React Flow — see the git history
 * on this file; a fixed diagram costs no client JS and prints.
 */
import type { AgentStage, AgentStageEdge, StageEdgeKind, StageKind } from "@/app/lib/agents-registry";

const LABEL_W = 86; // left gutter for lane names
const W = 140; // column width
const GAP = 30;
const NH = 60; // node height — sized so the longest stage detail (64 chars) fits without eliding
const LH = 78; // lane height
const MARGIN = 14;
const TOP_PAD = 8;
const CHANNEL_GAP = 12; // first return channel, below the last lane
const CHANNEL_STEP = 11; // each further return drops another step

/** Fixed lane order — work flows down this list, never up it. */
const LANE_ORDER: StageKind[] = ["deterministic", "model", "guard", "output"];

const KIND_COLOR: Record<StageKind, string> = {
  deterministic: "var(--data)",
  model: "var(--info)",
  guard: "var(--positive)",
  output: "var(--muted-foreground)",
};

const EDGE_COLOR: Record<StageEdgeKind, string> = {
  flow: "var(--muted-foreground)",
  loop: "var(--info)",
  retry: "var(--warning)",
  reject: "var(--negative)",
};

/**
 * Split a detail into at most `maxLines` SVG lines — SVG has no text wrapping.
 * Greedy fill; tokens longer than a line are hard-broken (`registry-allowlisted`
 * is 20 chars against a 19-char line and would otherwise overrun the node);
 * anything past the last line is elided so truncation is visible, not silent.
 */
export function wrap(text: string, perLine = 25, maxLines = 3): string[] {
  const words = text.split(" ").flatMap((w) => {
    if (w.length <= perLine) return [w];
    const parts: string[] = [];
    for (let i = 0; i < w.length; i += perLine) parts.push(w.slice(i, i + perLine));
    return parts;
  });
  const lines: string[] = [];
  let line = "";
  let consumed = 0;
  for (const w of words) {
    const candidate = line ? `${line} ${w}` : w;
    if (line && candidate.length > perLine) {
      lines.push(line);
      if (lines.length === maxLines) {
        line = "";
        break;
      }
      line = w;
    } else {
      line = candidate;
    }
    consumed += 1;
  }
  if (line && lines.length < maxLines) {
    lines.push(line);
    consumed = words.length;
  }
  if (consumed < words.length && lines.length) {
    const last = lines[lines.length - 1];
    lines[lines.length - 1] = `${last.slice(0, Math.max(0, perLine - 1))}…`;
  }
  return lines;
}

export default function AgentFlow({
  stages,
  edges,
}: {
  stages: AgentStage[];
  edges: AgentStageEdge[];
}) {
  const index = new Map(stages.map((s, i) => [s.id, i]));
  // Only lanes this agent actually uses — a four-row grid with an empty row
  // reads as a missing stage.
  const lanes = LANE_ORDER.filter((k) => stages.some((s) => s.kind === k));
  const laneOf = new Map(lanes.map((k, i) => [k, i]));

  const x = (col: number) => LABEL_W + MARGIN + col * (W + GAP);
  const cx = (col: number) => x(col) + W / 2;
  const laneTop = (k: StageKind) => TOP_PAD + (laneOf.get(k) ?? 0) * LH;
  const nodeTop = (k: StageKind) => laneTop(k) + (LH - NH) / 2;
  const midY = (k: StageKind) => nodeTop(k) + NH / 2;
  const nodeBottom = (k: StageKind) => nodeTop(k) + NH;

  const lanesBottom = TOP_PAD + lanes.length * LH;
  const returns = edges.filter((e) => {
    const a = index.get(e.from);
    const b = index.get(e.to);
    return a != null && b != null && b <= a;
  });
  const height = lanesBottom + CHANNEL_GAP + Math.max(returns.length, 1) * CHANNEL_STEP + 16;
  const width = LABEL_W + MARGIN * 2 + stages.length * W + (stages.length - 1) * GAP;

  // Channel assignment is computed up front, not accumulated during render:
  // mutating a counter inside the map callback trips react-hooks/immutability
  // ("cannot reassign after render completes") and would give a different
  // layout on a re-render.
  const returnChannel = new Map(
    edges
      .map((e, i) => [i, e] as const)
      .filter(([, e]) => {
        const a = index.get(e.from);
        const b = index.get(e.to);
        return a != null && b != null && b <= a;
      })
      .map(([i], slot) => [i, slot] as const),
  );

  const drawn = edges.flatMap((e, n) => {
    const a = index.get(e.from);
    const b = index.get(e.to);
    if (a == null || b == null) return []; // unresolved ids are caught by the test
    const from = stages[a];
    const to = stages[b];
    const kind: StageEdgeKind = e.kind ?? "flow";
    const color = EDGE_COLOR[kind];
    const forward = b > a;

    let d: string;

    if (forward) {
      // Elbow: out the right edge, across at the column midpoint, into the left.
      const x1 = x(a) + W;
      const y1 = midY(from.kind);
      const x2 = x(b) - 5;
      const y2 = midY(to.kind);
      const mx = (x1 + x2) / 2;
      d = y1 === y2 ? `M ${x1} ${y1} L ${x2} ${y2}` : `M ${x1} ${y1} H ${mx} V ${y2} H ${x2}`;
    } else {
      // Return: drop out the bottom into this edge's own channel, travel back,
      // rise into the target's underside. One channel per return keeps two
      // from sharing a line.
      const depth = lanesBottom + CHANNEL_GAP + (returnChannel.get(n) ?? 0) * CHANNEL_STEP;
      const x1 = cx(a);
      const x2 = cx(b);
      d = `M ${x1} ${nodeBottom(from.kind)} V ${depth} H ${x2} V ${nodeBottom(to.kind) + 4}`;
    }

    return [
      <path
        key={`${e.from}-${e.to}-${n}`}
        d={d}
        fill="none"
        stroke={color}
        strokeWidth={kind === "flow" ? 1.4 : 1.1}
        strokeDasharray={kind === "flow" ? undefined : "4 3"}
        strokeOpacity={kind === "flow" ? 0.65 : 0.85}
        markerEnd={`url(#agent-arrow-${kind})`}
      />,
    ];
  });

  return (
    <figure className="mt-3">
      {/* Wide graphs scroll inside their own box — the page never scrolls sideways. */}
      <div className="overflow-x-auto pb-1">
        <svg
          width={width}
          height={height}
          viewBox={`0 0 ${width} ${height}`}
          role="img"
          // Edge labels are not drawn — they crowded the nodes. Their text is
          // kept in the registry and folded in here, so the semantics survive
          // for a screen reader even though the picture stays quiet.
          aria-label={
            `Workflow: ${stages.map((s) => `${s.label} (${s.kind})`).join(", then ")}. ` +
            edges
              .filter((e) => e.label)
              .map((e) => `${e.from} to ${e.to}: ${e.label}`)
              .join("; ")
          }
          className="max-w-none"
        >
          <defs>
            {(Object.keys(EDGE_COLOR) as StageEdgeKind[]).map((k) => (
              <marker
                key={k}
                id={`agent-arrow-${k}`}
                viewBox="0 0 8 8"
                refX="6"
                refY="4"
                markerWidth="5"
                markerHeight="5"
                orient="auto-start-reverse"
              >
                <path d="M 0 1 L 7 4 L 0 7 z" fill={EDGE_COLOR[k]} fillOpacity={0.8} />
              </marker>
            ))}
          </defs>

          {/* Lane rules + names. Hairlines, per DESIGN.md — the lane is the
              structure, so it gets the rule and the node does not get a box. */}
          {lanes.map((k, i) => {
            const top = TOP_PAD + i * LH;
            return (
              <g key={k}>
                <line
                  x1={0}
                  y1={top}
                  x2={width}
                  y2={top}
                  stroke="var(--hair)"
                  strokeWidth={1}
                />
                <text
                  x={0}
                  y={top + 14}
                  fontSize={8}
                  fill={KIND_COLOR[k]}
                  fillOpacity={0.9}
                  style={{ fontFamily: "var(--font-mono)", letterSpacing: "0.08em" }}
                >
                  {k.toUpperCase()}
                </text>
              </g>
            );
          })}
          <line
            x1={0}
            y1={lanesBottom}
            x2={width}
            y2={lanesBottom}
            stroke="var(--hair)"
            strokeWidth={1}
          />

          {drawn}

          {stages.map((s, i) => {
            const color = KIND_COLOR[s.kind];
            const detail = s.detail ? wrap(s.detail) : [];
            const top = nodeTop(s.kind);
            return (
              <g key={s.id}>
                <rect
                  x={x(i)}
                  y={top}
                  width={W}
                  height={NH}
                  rx={2}
                  fill="var(--card)"
                  stroke="var(--border)"
                  strokeWidth={1}
                />
                <rect x={x(i)} y={top} width={2.5} height={NH} rx={1} fill={color} />
                <text
                  x={x(i) + 10}
                  y={top + 16}
                  fontSize={10.5}
                  fill="var(--foreground)"
                  style={{ fontWeight: 600 }}
                >
                  {s.label}
                </text>
                {detail.map((line, li) => (
                  <text
                    key={li}
                    x={x(i) + 10}
                    y={top + 29 + li * 10}
                    fontSize={8}
                    fill="var(--muted-foreground)"
                    style={{ fontFamily: "var(--font-mono)" }}
                  >
                    {line}
                  </text>
                ))}
              </g>
            );
          })}

        </svg>
      </div>

      <figcaption className="mt-1.5">
        <span className="font-mono text-[8.5px] uppercase tracking-[0.06em] text-faint">
          rows = what kind of work · columns = order · dashed = return path (loop / retry / reject)
        </span>
      </figcaption>
    </figure>
  );
}
