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
  cursor: string;
  reference: string;
  tooltipBg: string;
  tooltipBorder: string;
  tooltipText: string;
}

// "Editorial" chart chrome — navy-led series (mirror --chart-1..6), warm
// hairline grid, faint mono axis ticks, warm-paper tooltip.
const LIGHT: ChartTheme = {
  mode: "light",
  palette: ["#1C3A60", "#3E6098", "#88A0C0", "#B98A5E", "#6E4B6E", "#9AA1AD"],
  grid: "#ECE8DF",
  axis: "#9AA1AD",
  cursor: "rgba(28,58,96,0.06)",
  reference: "#9AA1AD",
  tooltipBg: "#FFFFFF",
  tooltipBorder: "#D8D1C2",
  tooltipText: "#16243B",
};

const DARK: ChartTheme = {
  mode: "dark",
  palette: ["#7FA0C8", "#9BB1D0", "#C2CEDF", "#D2A878", "#B391B3", "#A79F8E"],
  grid: "#36322B",
  axis: "#8A8472",
  cursor: "rgba(127,160,200,0.10)",
  reference: "#8A8472",
  tooltipBg: "#26231C",
  tooltipBorder: "#3E382E",
  tooltipText: "#ECE8E0",
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
