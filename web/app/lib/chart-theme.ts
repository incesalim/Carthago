"use client";

/**
 * Theme-aware colours for Recharts.
 *
 * Recharts paints SVG via presentation attributes (`stroke`, `fill`) which
 * can't read CSS variables, so chart chrome is resolved here in JS against the
 * active next-themes theme. Series colours mirror the `--chart-*` token order
 * defined in globals.css.
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

// "Fresh / Flat" chart chrome — series mirror --chart-1..6, grid is a hairline
// (--border), axis ticks are the faint caption tone (--faint).
const LIGHT: ChartTheme = {
  mode: "light",
  palette: ["#2F6BED", "#15AABF", "#7C5CFC", "#F7A23B", "#F368A6", "#8B98AD"],
  grid: "#E8ECF2",
  axis: "#9AA3B2",
  cursor: "rgba(47,107,237,0.06)",
  reference: "#9AA3B2",
  tooltipBg: "#ffffff",
  tooltipBorder: "#E8ECF2",
  tooltipText: "#1A2230",
};

const DARK: ChartTheme = {
  mode: "dark",
  palette: ["#5B86F7", "#2BD4CC", "#9A7CFF", "#FBB454", "#FB85BE", "#9FB0C6"],
  grid: "#232C3A",
  axis: "#5E6A7D",
  cursor: "rgba(91,134,247,0.10)",
  reference: "#5E6A7D",
  tooltipBg: "#181F2A",
  tooltipBorder: "#232C3A",
  tooltipText: "#EAEEF4",
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
  "10001": 5, // Sector — neutral grey (aggregate / reference)
  "10007": 0, // Foreign
  "10005": 1, // Private
  "10006": 2, // State
  "10003": 3, // Participation
  "10004": 4, // Dev & Inv
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
