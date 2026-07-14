"use client";

/**
 * Theme-aware colours for Recharts.
 *
 * Recharts paints SVG via presentation attributes (`stroke`, `fill`) which
 * can't read CSS variables, so chart chrome is resolved here in JS against the
 * active next-themes theme. Series colours mirror the `--chart-*` token order
 * defined in globals.css.
 *
 * LOCKSTEP RULE: `tooltipBg`/`tooltipBorder` mirror `--card`/`--border` in
 * globals.css — any change to those tokens MUST be applied here in the same
 * commit, or tooltips/end-dot rings drift off the card surface.
 */
import { useTheme } from "next-themes";

export interface ChartTheme {
  /** Active theme — use this instead of sniffing palette[0] for a light check. */
  mode: "light" | "dark";
  /** Categorical series palette (matches --chart-1..6). */
  palette: string[];
  grid: string;
  axis: string;
  /** Band highlight behind the hovered category (bar charts). */
  cursor: string;
  /** Hover crosshair — the vertical hairline dropped at the hovered date. */
  crosshair: string;
  reference: string;
  tooltipBg: string;
  tooltipBorder: string;
  tooltipText: string;
  /** Hero line in hero+context mode (the series the eye should track). */
  hero: string;
  /** Context lines at rest — thin grey; clears the grid, sits behind the hero. */
  context: string;
  /** A context line when its end-label is hovered/pinned — darkened ink, NOT
   *  the hero navy, so an isolated context line can't impersonate the hero. */
  contextActive: string;
  /** Muted text ink for direct end-labels (between axis tone and full ink). */
  inkMuted: string;
  /** Direction marks. Green/red state DATA DIRECTION only (DESIGN.md rule 3) —
   *  never decoration. LOCKSTEP with --negative / --positive / --warning. */
  negative: string;
  positive: string;
  warning: string;
}

// "The Desk" chart chrome — navy hero + grey context (mirror --chart-1..6),
// whisper hairline grid, faint mono axis ticks, white-sheet tooltip.
const LIGHT: ChartTheme = {
  mode: "light",
  palette: ["#2B4E7E", "#4E79B8", "#8FA8C8", "#B98514", "#7A5C8A", "#A0A7AE"],
  grid: "#ECEDE8",
  axis: "#A0A7AE",
  cursor: "rgba(43,78,126,0.06)",
  crosshair: "#C9CDC5",
  reference: "#A0A7AE",
  tooltipBg: "#FFFFFF",
  tooltipBorder: "#E1E3DD",
  tooltipText: "#12161B",
  hero: "#2B4E7E",
  context: "#C0C8D1",
  contextActive: "#454D57",
  inkMuted: "#68707A",
  negative: "#C24847",
  positive: "#187A53",
  warning: "#B98514",
};

const DARK: ChartTheme = {
  mode: "dark",
  palette: ["#7FA3D8", "#9BB4D8", "#C1CEDE", "#D9A83F", "#B092C0", "#8B939C"],
  grid: "#1F252C",
  axis: "#6B747E",
  cursor: "rgba(127,163,216,0.10)",
  crosshair: "#39424C",
  reference: "#6B747E",
  tooltipBg: "#171B21",
  tooltipBorder: "#262C34",
  tooltipText: "#E6E9E6",
  hero: "#7FA3D8",
  context: "#4A525C",
  contextActive: "#C9D2DC",
  inkMuted: "#9AA3AD",
  negative: "#E0716B",
  positive: "#4FB98A",
  warning: "#D9A83F",
};

/** Resolve the chart palette for the active theme (defaults to light pre-mount). */
export function useChartTheme(): ChartTheme {
  const { resolvedTheme } = useTheme();
  return resolvedTheme === "dark" ? DARK : LIGHT;
}

/**
 * Fixed palette slot per BDDK bank-type code, so each group keeps ONE colour
 * across every chart regardless of which subset a given chart renders (e.g.
 * Private was previously slot 3 on the full chart but slot 1 on a 3-series
 * chart). Sector — the aggregate — takes the neutral grey; the five groups get
 * distinct hues.
 */
const BANK_TYPE_COLOR_INDEX: Record<string, number> = {
  "10001": 0, // Sector — navy emphasis (the aggregate the eye should track)
  "10006": 1, // State
  "10005": 2, // Private
  "10007": 3, // Foreign
  "10003": 4, // Participation
  "10004": 5, // Dev & Inv — gray
};

/**
 * Fixed slots for the /digital tab's synthetic acquisition series, so a series
 * keeps one colour across the tab's line, share and by-method charts. Without
 * this, `branch` lands on slot 0 (maroon) in the by-method stack but slot 1
 * (navy) in the digital-vs-branch line/share — the same word in two colours.
 * Here the remote (digital) side reads warm (maroon/orange/purple) and branch
 * reads navy — the navy the line/share charts already use.
 */
const DIGITAL_SERIES_COLOR_INDEX: Record<string, number> = {
  digital: 0, // remote/digital aggregate — maroon
  branch: 1, // branch (non-digital) — navy, everywhere
  remote_rep: 0, // largest remote method — shares the digital maroon
  remote_courier: 3, // orange
  bulk: 4, // purple
};

/**
 * Stroke colour for a series. Known bank-type codes (and the /digital tab's
 * acquisition keys) map to their fixed slot; any other key (synthetic segment
 * codes, EVDS labels) falls back to its positional index, which is stable
 * within a single chart.
 */
export function seriesColor(
  t: ChartTheme,
  key: string,
  fallbackIndex: number,
): string {
  const idx =
    BANK_TYPE_COLOR_INDEX[key] ?? DIGITAL_SERIES_COLOR_INDEX[key] ?? fallbackIndex;
  return t.palette[idx % t.palette.length];
}

/**
 * The hover crosshair: a vertical hairline at the hovered date, on every chart
 * with a time axis. Recharts draws one by default but hard-codes `stroke:#ccc`,
 * which is invisible against the dark sheet and too heavy against the light one
 * — pass this to `<Tooltip cursor>` so the line is a Desk hairline in both.
 * Bar charts keep the band highlight (`t.cursor`) instead: a line down the
 * middle of a bar reads as a gridline, a band reads as "this column".
 */
export function crosshairCursor(t: ChartTheme) {
  return { stroke: t.crosshair, strokeWidth: 1 } as const;
}

/**
 * The left gutter, written down once.
 *
 * Recharts gives a <YAxis> a DEFAULT width of 60px, and that width sits ON TOP
 * OF `margin.left` — so a `left: 60` margin pushed the plot 120px in from the
 * sheet's text column, parking every line chart well to the right of its own
 * heading. Instead: let the axis size itself to its ticks (`width="auto"`,
 * Recharts ≥3.1 — a "₺1,234 bn" tick gets the room it needs, a "0%" tick
 * doesn't take it), and keep only a thin margin so the leftmost x-tick label,
 * which is centred on its tick, can't clip at the SVG boundary.
 *
 * Every chart with a value (non-category) y-axis uses this pair. A category
 * y-axis — BarByBank's bank names — is content, not scale furniture, and keeps
 * its own explicit width.
 */
export const Y_AXIS_WIDTH = "auto" as const;
export const PLOT_MARGIN_LEFT = 8;

/** Shared Recharts tooltip styling for a given theme. */
export function tooltipStyles(t: ChartTheme) {
  return {
    contentStyle: {
      background: t.tooltipBg,
      border: `1px solid ${t.tooltipBorder}`,
      borderRadius: 8,
      boxShadow: "0 4px 16px rgba(0,0,0,0.10)",
      fontSize: 11,
      padding: "6px 10px",
      color: t.tooltipText,
    } as const,
    labelStyle: { color: t.tooltipText, fontWeight: 600, marginBottom: 2 } as const,
    itemStyle: { color: t.tooltipText, padding: 0 } as const,
  };
}
