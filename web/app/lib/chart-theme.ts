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

const LIGHT: ChartTheme = {
  palette: ["#7a0d2e", "#1f4068", "#0f7b6c", "#a16500", "#5b1a8c", "#5a5a5a"],
  grid: "#ececec",
  axis: "#737373",
  cursor: "rgba(0,0,0,0.04)",
  reference: "#9ca3af",
  tooltipBg: "#ffffff",
  tooltipBorder: "#e5e5e5",
  tooltipText: "#171717",
};

const DARK: ChartTheme = {
  palette: ["#f0608a", "#6f9fe0", "#34c9b0", "#e0a23c", "#b07ee0", "#a3a3a3"],
  grid: "rgba(255,255,255,0.08)",
  axis: "#9ca3af",
  cursor: "rgba(255,255,255,0.06)",
  reference: "#6b7280",
  tooltipBg: "#1c1d22",
  tooltipBorder: "rgba(255,255,255,0.14)",
  tooltipText: "#ededed",
};

/** Resolve the chart palette for the active theme (defaults to light pre-mount). */
export function useChartTheme(): ChartTheme {
  const { resolvedTheme } = useTheme();
  return resolvedTheme === "dark" ? DARK : LIGHT;
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
