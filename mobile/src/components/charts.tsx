/**
 * The chart layer — react-native-svg, because Recharts is web-DOM only.
 *
 * SINGLE-SERIES BY CONSTRUCTION, and that is a decision rather than a
 * limitation. Two reasons, one of them a defect found while porting:
 *
 *   1. A 390pt-wide multi-series line chart is unreadable. The website plots six
 *      ownership groups per chart because a laptop can resolve them; the phone's
 *      job is the sector line, with the breakdown a tap away on the web.
 *   2. The Desk's categorical ramp does not survive the colorblind check in dark
 *      mode. Running the palette validator over `--chart-1..6`: chart-2 (#9BB4D8)
 *      against chart-1 (#7FA3D8) scores ΔE 6.1 for NORMAL vision — below the 15
 *      floor, i.e. hard to tell apart even with full colour vision — and
 *      chart-5 vs chart-6 drops to ΔE 5.3 under protanopia. The website gets away
 *      with it because every chart carries a direct-labelled ChartFoot; a phone
 *      chart has no room for one. So identity here is never carried by hue.
 *
 * Both charts therefore use `colors.data` — the hero navy — and nothing else.
 * When a second series is genuinely needed, the answer is two stacked charts
 * (small multiples), not a second colour. See the note in docs/PROJECT_STATE.md.
 */
import { useCallback, useMemo, useState } from "react";
import { View, type LayoutChangeEvent } from "react-native";
import Svg, { Circle, Line, Path } from "react-native-svg";

import type { WirePoint } from "../api/types";
import { useTheme } from "../theme";

/** Points with a value, and the min/max the plot is scaled against. */
function useGeometry(points: WirePoint[], width: number, height: number, pad: number) {
  return useMemo(() => {
    const usable = points.filter((p) => p.v != null) as { t: string; v: number }[];
    if (usable.length < 2 || width <= 0) return null;

    const values = usable.map((p) => p.v);
    const min = Math.min(...values);
    const max = Math.max(...values);
    // A flat series has zero range; dividing by it puts every point at NaN and
    // the path renders as nothing. Centre it instead.
    const range = max - min || 1;

    const innerW = width - pad * 2;
    const innerH = height - pad * 2;
    const x = (i: number) => pad + (i / (usable.length - 1)) * innerW;
    const y = (v: number) => pad + innerH - ((v - min) / range) * innerH;

    const coords = usable.map((p, i) => ({ x: x(i), y: y(p.v), t: p.t, v: p.v }));
    const d = coords
      .map((c, i) => `${i === 0 ? "M" : "L"}${c.x.toFixed(2)},${c.y.toFixed(2)}`)
      .join(" ");

    return { coords, d, min, max, usable };
  }, [points, width, height, pad]);
}

/**
 * Sparkline — the micro-trend inside a vitals cell.
 *
 * No axes, no labels, no touch target. The figure it sits beside IS the reading;
 * this shows only the shape that produced it, which is why it needs neither a
 * scale nor a tooltip (a stat tile's plot is the one form that skips the hover
 * layer). The end dot marks "you are here" so the eye doesn't have to work out
 * which end is now.
 */
export function Sparkline({
  points,
  height = 28,
  color,
}: {
  points: WirePoint[];
  height?: number;
  color?: string;
}) {
  const { colors } = useTheme();
  const [width, setWidth] = useState(0);
  const onLayout = useCallback(
    (e: LayoutChangeEvent) => setWidth(e.nativeEvent.layout.width),
    [],
  );

  const stroke = color ?? colors.data;
  const geo = useGeometry(points, width, height, 3);
  const last = geo?.coords.at(-1);

  return (
    <View onLayout={onLayout} style={{ height }}>
      {geo && width > 0 && (
        <Svg width={width} height={height}>
          <Path
            d={geo.d}
            stroke={stroke}
            strokeWidth={1.5}
            fill="none"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          {last && <Circle cx={last.x} cy={last.y} r={2.5} fill={stroke} />}
        </Svg>
      )}
    </View>
  );
}

export interface ScrubPoint {
  t: string;
  v: number;
}

/**
 * The full chart — one series, with a touch-scrub readout.
 *
 * A phone has no hover, so the interaction layer the web chart gets from a
 * crosshair is a drag here: touch anywhere and the nearest point reports back
 * through `onScrub`, which the caller renders as the headline figure. Releasing
 * clears it and the headline returns to the latest value. That keeps the value
 * in ONE place on screen rather than in a floating tooltip that a thumb covers.
 *
 * `zeroLine` draws the y=0 rule for series that cross it (growth rates, real
 * returns) — without it "−3%" and "+3%" look like the same shape.
 */
export function MetricChart({
  points,
  height = 140,
  zeroLine = false,
  onScrub,
}: {
  points: WirePoint[];
  height?: number;
  zeroLine?: boolean;
  onScrub?: (p: ScrubPoint | null) => void;
}) {
  const { colors } = useTheme();
  const [width, setWidth] = useState(0);
  const [activeIndex, setActiveIndex] = useState<number | null>(null);

  const onLayout = useCallback(
    (e: LayoutChangeEvent) => setWidth(e.nativeEvent.layout.width),
    [],
  );

  const pad = 6;
  const geo = useGeometry(points, width, height, pad);

  const handleTouch = useCallback(
    (locationX: number) => {
      if (!geo) return;
      // Nearest point by x. A binary search would be premature here — these
      // series are 8 to 48 points long.
      let nearest = 0;
      let best = Infinity;
      geo.coords.forEach((c, i) => {
        const dist = Math.abs(c.x - locationX);
        if (dist < best) {
          best = dist;
          nearest = i;
        }
      });
      setActiveIndex(nearest);
      const c = geo.coords[nearest];
      onScrub?.({ t: c.t, v: c.v });
    },
    [geo, onScrub],
  );

  const clear = useCallback(() => {
    setActiveIndex(null);
    onScrub?.(null);
  }, [onScrub]);

  const active = activeIndex != null ? geo?.coords[activeIndex] : null;
  const last = geo?.coords.at(-1);

  // Where y=0 falls, if it falls inside the plotted range at all.
  const zeroY = useMemo(() => {
    if (!geo || !zeroLine) return null;
    const { min, max } = geo;
    if (min > 0 || max < 0) return null;
    const range = max - min || 1;
    return pad + (height - pad * 2) - ((0 - min) / range) * (height - pad * 2);
  }, [geo, zeroLine, height]);

  return (
    <View
      onLayout={onLayout}
      style={{ height }}
      // The whole plot is the hit target — a thumb cannot be asked to land on a
      // 2px line.
      onStartShouldSetResponder={() => true}
      onMoveShouldSetResponder={() => true}
      onResponderGrant={(e) => handleTouch(e.nativeEvent.locationX)}
      onResponderMove={(e) => handleTouch(e.nativeEvent.locationX)}
      onResponderRelease={clear}
      onResponderTerminate={clear}
    >
      {geo && width > 0 && (
        <Svg width={width} height={height}>
          {zeroY != null && (
            <Line
              x1={0}
              y1={zeroY}
              x2={width}
              y2={zeroY}
              stroke={colors.border}
              strokeWidth={1}
            />
          )}
          <Path
            d={geo.d}
            stroke={colors.data}
            strokeWidth={2}
            fill="none"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          {active && (
            <>
              <Line
                x1={active.x}
                y1={pad}
                x2={active.x}
                y2={height - pad}
                stroke={colors.context}
                strokeWidth={1}
              />
              {/* Surface ring so the marker reads against the line it sits on. */}
              <Circle cx={active.x} cy={active.y} r={5} fill={colors.card} />
              <Circle cx={active.x} cy={active.y} r={3.5} fill={colors.data} />
            </>
          )}
          {!active && last && (
            <Circle cx={last.x} cy={last.y} r={3} fill={colors.data} />
          )}
        </Svg>
      )}
    </View>
  );
}
