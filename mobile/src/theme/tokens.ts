/**
 * "The Desk" — the palette, ported from web/app/globals.css.
 *
 * These hexes are COPIES, and copies drift. The rule that keeps them honest is
 * the same one web/DESIGN.md sets for chart-theme.ts: the token names here match
 * the CSS custom properties one-for-one, so a change on either side is a
 * one-line diff in a file with the same shape. `npm run check:tokens`
 * (scripts/check-tokens.mjs) re-reads globals.css and fails if any value here
 * has fallen behind — contrast and hierarchy are arithmetic nobody re-verifies
 * by eye after nudging a hex.
 *
 * One deliberate DIVERGENCE from the website, not a porting mistake:
 *
 *   The Desk's figure-ground is a white sheet floating on cool paper. That
 *   metaphor needs margins to read, which a 390pt viewport does not have — and
 *   the website already knows it, dropping the sheet to full-bleed below `lg`
 *   (see the layout's `lg:rounded-[10px] lg:border`). So on the phone `card` IS
 *   the screen, and `background` demotes to what separates grouped sections.
 *   Inverting them would give a phone-shaped app a permanent grey border.
 */

export interface Palette {
  /** Screen behind grouped sections (the paper ground, demoted — see above). */
  background: string;
  /** The sheet. On the phone this is the screen fill. */
  card: string;
  foreground: string;
  mutedForeground: string;
  faint: string;
  muted: string;
  /** Sheet edge + card hairlines. */
  border: string;
  /** Inner row hairlines — one step quieter than `border`. */
  hair: string;
  /** Functional blue. Links and routes ONLY — never decoration, never a chart. */
  primary: string;
  primaryForeground: string;
  /** Chart hero navy: lines, KPI figures, sparklines. */
  data: string;
  /** The non-hero mark — context lines, peer ticks, coverage meters. */
  context: string;
  positive: string;
  negative: string;
  warning: string;
  /** Categorical chart ramp, navy-led. Not used by this app's charts — see the
   *  colorblind note in src/components/charts.tsx — but kept in lockstep so the
   *  drift gate covers the whole system rather than a subset of it. */
  chart: readonly string[];
}

export const light: Palette = {
  background: "#F7F8F6",
  card: "#FFFFFF",
  foreground: "#12161B",
  mutedForeground: "#50565E",
  faint: "#6A6E73",
  muted: "#F1F2EE",
  border: "#E1E3DD",
  hair: "#ECEDE8",
  primary: "#2757A8",
  primaryForeground: "#FFFFFF",
  data: "#2B4E7E",
  context: "#C0C8D1",
  positive: "#16714D",
  negative: "#A93F3E",
  warning: "#825D0E",
  chart: ["#2B4E7E", "#4E79B8", "#8FA8C8", "#B98514", "#7A5C8A", "#A0A7AE"],
};

export const dark: Palette = {
  background: "#101318",
  card: "#171B21",
  foreground: "#E6E9E6",
  mutedForeground: "#9AA3AD",
  faint: "#838A93",
  muted: "#1E232A",
  border: "#262C34",
  hair: "#1F252C",
  primary: "#7FA3D8",
  primaryForeground: "#101318",
  data: "#7FA3D8",
  context: "#4A525C",
  positive: "#4FB98A",
  negative: "#E0716B",
  warning: "#D9A83F",
  chart: ["#7FA3D8", "#9BB4D8", "#C1CEDE", "#D9A83F", "#B092C0", "#8B939C"],
};

/**
 * Type scale. The Desk gets its hierarchy from weight and size in ONE family,
 * not from a second typeface — so this is a size ramp, not a set of styles.
 *
 * Sizes run larger than the website's. The site prints 8.5px mono captions,
 * which is legible at a laptop's viewing distance and illegible at arm's length
 * on a phone; the floor here is 11. Where the site's caption tracking was tuned
 * for 8.5px it is re-tuned, not copied.
 */
export const type = {
  display: 28,
  title: 21,
  heading: 16,
  body: 15,
  small: 13,
  caption: 11,
} as const;

/** 4pt grid. The website's spacing is on a 4px grid too, so the rhythm carries. */
export const space = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  xxl: 32,
} as const;

/** 8px — "document, not app-chrome", per the website's `--radius`. */
export const radius = 8;

/**
 * Font families, by the names expo-font registers them under in the root
 * layout. The layout holds the splash until they resolve, and hides it even if
 * they fail — a bare custom family name renders nothing on Android, so a failed
 * font load must not be able to produce a blank app.
 */
export const font = {
  sans: "InstrumentSans_400Regular",
  sansMedium: "InstrumentSans_500Medium",
  sansSemibold: "InstrumentSans_600SemiBold",
  /** Labels and EVERY figure — the Desk's rule, and the reason columns align. */
  mono: "IBMPlexMono_400Regular",
  monoMedium: "IBMPlexMono_500Medium",
} as const;
