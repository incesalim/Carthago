"use client";

/**
 * Direct end-of-line labels + on-chart annotations for the line charts.
 *
 * FT-style at-rest legibility: every series gets a `Name 16.4%` label at the
 * end of its line (collision-resolved), replacing the bottom legend on wide
 * charts. Hover a label to isolate its line; right-click to pin — the same
 * gestures the legend owned.
 *
 * `EndLabelLayer` renders as a chart CHILD (like `NearestActiveDot` in
 * nearest-hover.tsx), so the Recharts 3.8+ context hooks (`useXAxisScale`,
 * `useYAxisScale`, `usePlotArea`) are valid inside it. Label-column width is
 * estimated from string lengths only — never DOM-measured — so there is no
 * layout feedback loop with ResponsiveContainer.
 */
import {
  ReferenceArea,
  ReferenceLine,
  usePlotArea,
  useXAxisScale,
  useYAxisScale,
} from "recharts";
import { useChartTheme, type ChartTheme } from "@/app/lib/chart-theme";

type Row = Record<string, string | number | null>;

/** Vertical spacing between stacked labels (11px type). */
const LABEL_PITCH = 15;
/** Names longer than this are truncated with an ellipsis (full name in <title>). */
const NAME_MAX = 16;

const SANS = "var(--font-geist-sans), ui-sans-serif, sans-serif";
const MONO = "var(--font-geist-mono), ui-monospace, monospace";

/** Per-series LAST NON-NULL point (series may end at different periods). */
export function lastPoint(
  rows: ReadonlyArray<Row>,
  periodKey: string,
  key: string,
): { period: string; value: number; index: number } | null {
  for (let i = rows.length - 1; i >= 0; i--) {
    const v = rows[i][key];
    if (typeof v === "number" && !Number.isNaN(v)) {
      return { period: String(rows[i][periodKey]), value: v, index: i };
    }
  }
  return null;
}

/**
 * Estimated pixel width of the end-label column — char-width heuristic
 * (≈6.1px/char sans name at 11px + ≈6.6px/char mono value + dot/padding),
 * clamped so a stray long label can't eat the plot.
 */
export function estimateEndLabelWidth(
  entries: ReadonlyArray<{ name: string; value: string }>,
  valueOnly = false,
): number {
  let max = 0;
  for (const e of entries) {
    const nameLen = valueOnly ? 0 : Math.min(e.name.length, NAME_MAX + 1);
    const w = nameLen * 6.1 + e.value.length * 6.6 + 22;
    if (w > max) max = w;
  }
  return Math.round(Math.min(150, Math.max(76, max)));
}

export interface EndLabelLayerProps {
  rows: ReadonlyArray<Row>;
  periodKey: string;
  /** Series keys in render order. */
  keys: string[];
  labelFor: (key: string) => string;
  /** Ink for the label NAME (hero navy / muted / series colour). */
  colorFor: (key: string) => string;
  /** Stroke for the leader line — the LINE colour (defaults to colorFor). */
  lineColorFor?: (key: string) => string;
  formatValue: (v: number) => string;
  /** The emphasised series (semibold label). */
  heroKey?: string | null;
  /** Isolation state owned by the chart (hovered ?? pinned). */
  active?: string | null;
  pinned?: string | null;
  onHover?: (key: string | null) => void;
  onPinToggle?: (key: string) => void;
  /** Single-series mode: render the value only, no name. */
  valueOnly?: boolean;
}

/** Direct end-of-line labels, collision-resolved into the right margin. */
export function EndLabelLayer({
  rows,
  periodKey,
  keys,
  labelFor,
  colorFor,
  lineColorFor,
  formatValue,
  heroKey,
  active,
  pinned,
  onHover,
  onPinToggle,
  valueOnly = false,
}: EndLabelLayerProps) {
  const t = useChartTheme();
  const xScale = useXAxisScale();
  const yScale = useYAxisScale();
  const plot = usePlotArea();
  if (!xScale || !yScale || !plot) return null;

  // Collect each series' last point in pixel space.
  const items: {
    key: string;
    name: string;
    value: number;
    x: number;
    yTarget: number;
    y: number;
  }[] = [];
  for (const key of keys) {
    const lp = lastPoint(rows, periodKey, key);
    if (!lp) continue;
    const x = xScale(lp.period, { position: "middle" });
    const y = yScale(lp.value);
    if (x == null || y == null) continue;
    items.push({ key, name: labelFor(key), value: lp.value, x, yTarget: y, y });
  }
  if (!items.length) return null;

  // Collision: sort by target y, forward pass pushes down, backward pass
  // recovers if the stack ran past the bottom clamp.
  const top = plot.y + 7;
  const bottom = plot.y + plot.height - 7;
  items.sort((a, b) => a.yTarget - b.yTarget);
  items[0].y = Math.min(Math.max(items[0].yTarget, top), bottom);
  for (let i = 1; i < items.length; i++) {
    items[i].y = Math.min(
      Math.max(items[i].yTarget, items[i - 1].y + LABEL_PITCH),
      bottom,
    );
  }
  for (let i = items.length - 2; i >= 0; i--) {
    items[i].y = Math.min(items[i].y, items[i + 1].y - LABEL_PITCH);
  }

  const anchorX = plot.x + plot.width + 8;
  const plotRight = plot.x + plot.width;

  return (
    <g data-end-labels="">
      {items.map((it) => {
        const isHero = it.key === heroKey;
        const dimmed = active != null && active !== it.key;
        const nameInk = colorFor(it.key);
        const leaderInk = (lineColorFor ?? colorFor)(it.key);
        const displaced = Math.abs(it.y - it.yTarget) > 4;
        const endsEarly = it.x < plotRight - 2;
        const name =
          it.name.length > NAME_MAX ? `${it.name.slice(0, NAME_MAX - 1)}…` : it.name;
        return (
          <g
            key={it.key}
            pointerEvents="all"
            opacity={dimmed ? 0.35 : 1}
            onMouseEnter={onHover ? () => onHover(it.key) : undefined}
            onMouseLeave={onHover ? () => onHover(null) : undefined}
            onContextMenu={
              onPinToggle
                ? (e) => {
                    e.preventDefault();
                    onPinToggle(it.key);
                  }
                : undefined
            }
          >
            {(displaced || endsEarly) && (
              <polyline
                points={`${it.x},${it.yTarget} ${anchorX - 3},${it.y}`}
                fill="none"
                stroke={leaderInk}
                strokeWidth={1}
                strokeOpacity={0.4}
              />
            )}
            <text
              x={anchorX}
              y={it.y + 3.5}
              fontSize={11}
              style={{ cursor: "default", userSelect: "none" }}
            >
              {it.name.length > NAME_MAX && <title>{it.name}</title>}
              {!valueOnly && (
                <tspan
                  fill={nameInk}
                  fontFamily={SANS}
                  fontWeight={isHero || pinned === it.key ? 600 : 400}
                >
                  {name}{" "}
                </tspan>
              )}
              <tspan fill={t.tooltipText} fontFamily={MONO} fontWeight={600}>
                {formatValue(it.value)}
              </tspan>
            </text>
          </g>
        );
      })}
    </g>
  );
}

// ---------------------------------------------------------------------------
// Annotations
// ---------------------------------------------------------------------------

export interface ChartAnnotation {
  /** Period to mark ('YYYY-MM' / 'YYYYQN' — same key space as the chart). */
  period: string;
  /** Optional band end — renders a shaded ReferenceArea period→endPeriod. */
  endPeriod?: string;
  /** Short mono note drawn at the top of the line. */
  label?: string;
}

/** First period in `rows` ≥ `p` (lexical — chronological for our keys). */
function snapPeriod(
  rows: ReadonlyArray<Row>,
  periodKey: string,
  p: string,
): string | null {
  for (const r of rows) {
    const rp = String(r[periodKey]);
    if (rp >= p) return rp;
  }
  return null;
}

/**
 * Annotation elements (shaded band + dashed line + mono note) to spread as
 * DIRECT chart children — plain function, not a component, so Recharts
 * registers the Reference* elements. Annotations outside the (range-filtered)
 * window drop silently.
 */
export function renderAnnotations(
  annotations: ReadonlyArray<ChartAnnotation> | undefined,
  rows: ReadonlyArray<Row>,
  periodKey: string,
  t: ChartTheme,
) {
  if (!annotations?.length || !rows.length) return null;
  return annotations.flatMap((a, i) => {
    const x = snapPeriod(rows, periodKey, a.period);
    if (x == null) return [];
    const parts = [];
    if (a.endPeriod) {
      const x2 = snapPeriod(rows, periodKey, a.endPeriod) ?? String(rows[rows.length - 1][periodKey]);
      parts.push(
        <ReferenceArea
          key={`ann-band-${i}`}
          x1={x}
          x2={x2}
          fill={t.cursor}
          stroke="none"
        />,
      );
    }
    parts.push(
      <ReferenceLine
        key={`ann-line-${i}`}
        x={x}
        stroke={t.reference}
        strokeDasharray="3 3"
        label={
          a.label
            ? {
                value: a.label,
                position: "insideTopLeft",
                fill: t.axis,
                fontSize: 9.5,
                fontFamily: MONO,
              }
            : undefined
        }
      />,
    );
    return parts;
  });
}
