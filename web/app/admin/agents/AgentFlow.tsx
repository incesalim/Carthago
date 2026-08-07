/**
 * Agent workflow diagram — one inline SVG per agent, computed from the
 * registry's `stages` + `edges`.
 *
 * Deliberately NOT React Flow. /pipeline uses it for a 60-node topology that
 * needs pan, zoom and a minimap; an agent is five to seven stages and reads
 * better as a fixed strip — no client JS, crisp at any zoom, prints, and it
 * cannot drift out of layout when a stage is added.
 *
 * The colour carries the architectural claim: deterministic stages find and
 * prove, model stages investigate and write, guard stages decide what survives.
 * Where judgment enters is the thing you should be able to see from across the
 * room. These are marks, not text, so they sit outside check_contrast.py — the
 * legend labels beside them use real text tokens.
 */
import type { AgentStage, AgentStageEdge, StageEdgeKind, StageKind } from "@/app/lib/agents-registry";

const W = 128; // node width
const H = 58; // node height
const GAP = 34; // horizontal gap between nodes
const MARGIN = 16; // room for the outermost arcs
const TOP = 50; // headroom for arcs, and for adjacent-edge labels
const BOTTOM = 52; // headroom for arcs drawn below

const KIND_COLOR: Record<StageKind, string> = {
  deterministic: "var(--data)",
  model: "var(--info)",
  guard: "var(--positive)",
  output: "var(--muted-foreground)",
};

const KIND_LABEL: Record<StageKind, string> = {
  deterministic: "deterministic",
  model: "model",
  guard: "guard",
  output: "output",
};

const EDGE_COLOR: Record<StageEdgeKind, string> = {
  flow: "var(--muted-foreground)",
  loop: "var(--info)",
  retry: "var(--warning)",
  reject: "var(--negative)",
};

/**
 * Split a detail line into at most `maxLines` SVG lines — SVG has no text
 * wrapping. Greedy fill; anything past the last line is elided with an ellipsis
 * so a long detail truncates visibly rather than overrunning the node.
 */
export function wrap(text: string, perLine = 19, maxLines = 2): string[] {
  // Hard-break tokens that can never fit — `registry-allowlisted` is 20 chars
  // against a 19-char line, and word wrapping alone would push it past the
  // node's right edge with nothing to clip it.
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
  const x = (i: number) => MARGIN + i * (W + GAP);
  const spineY = TOP + H / 2;
  const width = MARGIN * 2 + stages.length * W + (stages.length - 1) * GAP;
  const height = TOP + H + BOTTOM;

  // Arc depth grows with span so two edges over the same stretch don't coincide.
  const arcDepth = (span: number) => Math.min(14 + span * 9, TOP - 8);

  // Edges are drawn in two passes — every line first, then every label. Keeping
  // a label inside its own edge's group let a LATER arc paint straight through
  // it, which no amount of halo fixes.
  const drawn = edges.flatMap((e, n) => {
    const a = index.get(e.from);
    const b = index.get(e.to);
    if (a == null || b == null) return []; // unresolved ids are caught by the test
    const kind: StageEdgeKind = e.kind ?? "flow";
    const color = EDGE_COLOR[kind];
    const dashed = kind !== "flow";
    const span = Math.abs(b - a);
    const forward = b > a;

    let d: string;
    let labelX: number;
    let labelY: number;

    if (forward && span === 1) {
      // Adjacent step — a straight line along the spine. Its label goes ABOVE
      // the node row, not in the gap: at 34px the gap cannot hold "ranked
      // leads", and a label centred there renders underneath both nodes
      // (nodes paint after edges), which is how it first shipped.
      const x1 = x(a) + W;
      const x2 = x(b);
      d = `M ${x1} ${spineY} L ${x2 - 6} ${spineY}`;
      labelX = (x1 + x2) / 2;
      labelY = TOP - 7;
    } else {
      // Everything else arcs clear of the spine: forward skips above,
      // returns (loop/retry) below, rejections above in their own colour.
      const below = !forward || kind === "loop" || kind === "retry";
      const depth = arcDepth(span);
      const x1 = forward ? x(a) + W / 2 : x(a) + W / 2;
      const x2 = forward ? x(b) + W / 2 : x(b) + W / 2;
      const edgeY = below ? TOP + H : TOP;
      const ctrlY = below ? edgeY + depth : edgeY - depth;
      d = `M ${x1} ${edgeY} C ${x1} ${ctrlY}, ${x2} ${ctrlY}, ${x2} ${below ? edgeY : edgeY - 4}`;
      labelX = (x1 + x2) / 2;
      // A cubic with both controls at ctrlY peaks at ~0.75 of that depth, so
      // +3 put the glyphs straight through the curve. Clear it properly.
      labelY = below ? ctrlY + 9 : ctrlY - 8;
    }

    const key = `${e.from}-${e.to}-${n}`;
    return [
      {
        path: (
          <path
            key={key}
            d={d}
            fill="none"
            stroke={color}
            strokeWidth={kind === "flow" ? 1.4 : 1.1}
            strokeDasharray={dashed ? "4 3" : undefined}
            strokeOpacity={kind === "flow" ? 0.6 : 0.85}
            markerEnd={`url(#agent-arrow-${kind})`}
          />
        ),
        label: e.label ? (
          <text
            key={key}
            x={labelX}
            y={labelY}
            textAnchor="middle"
            fontSize={8}
            fill={color}
            fillOpacity={0.95}
            // Arcs of different spans cross the same strip of space, so a label
            // will sometimes land on another curve even in the second pass. A
            // background-coloured halo under the glyphs keeps it readable
            // wherever it falls — cheaper than solving the geometry.
            stroke="var(--background)"
            strokeWidth={3}
            paintOrder="stroke"
            style={{ fontFamily: "var(--font-mono)", letterSpacing: "0.04em" }}
          >
            {e.label}
          </text>
        ) : null,
      },
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
          aria-label={`Workflow: ${stages.map((s) => s.label).join(" then ")}`}
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

          {drawn.map((e) => e.path)}

          {stages.map((s, i) => {
            const color = KIND_COLOR[s.kind];
            const detail = s.detail ? wrap(s.detail) : [];
            return (
              <g key={s.id}>
                <rect
                  x={x(i)}
                  y={TOP}
                  width={W}
                  height={H}
                  rx={3}
                  fill="var(--card)"
                  stroke="var(--border)"
                  strokeWidth={1}
                />
                {/* Kind reads as a left rule, not a fill — hairlines over boxes. */}
                <rect x={x(i)} y={TOP} width={2.5} height={H} rx={1} fill={color} />
                <text
                  x={x(i) + 11}
                  y={TOP + 17}
                  fontSize={10.5}
                  fill="var(--foreground)"
                  style={{ fontWeight: 600 }}
                >
                  {s.label}
                </text>
                {detail.map((line, li) => (
                  <text
                    key={li}
                    x={x(i) + 11}
                    y={TOP + 32 + li * 10}
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

          {/* Labels last: above every line AND every node. */}
          {drawn.map((e) => e.label)}
        </svg>
      </div>

      <figcaption className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1.5">
        {(Object.keys(KIND_COLOR) as StageKind[]).map((k) => (
          <span key={k} className="inline-flex items-center gap-1.5">
            <span
              aria-hidden
              className="inline-block h-2 w-[3px] rounded-sm"
              style={{ background: KIND_COLOR[k] }}
            />
            <span className="font-mono text-[8.5px] uppercase tracking-[0.06em] text-muted-foreground">
              {KIND_LABEL[k]}
            </span>
          </span>
        ))}
        <span className="font-mono text-[8.5px] uppercase tracking-[0.06em] text-faint">
          dashed = return path · loop / retry / reject
        </span>
      </figcaption>
    </figure>
  );
}
