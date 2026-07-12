/**
 * Shared vocabulary for the Compare matchup — kept out of the components so the
 * scorecard (CompareBoard) and the evidence grid (HeatmapGrid) can both read it
 * without importing each other.
 */

/** The four the eye should be able to tell apart — chart-1/2/5/4 (navy, blue,
 *  plum, amber), all from the categorical palette in globals.css. Positional:
 *  the Nth pick always wears the Nth colour, on the strip and in the grid. */
export const PICK_COLORS = [
  "var(--chart-1)",
  "var(--chart-2)",
  "var(--chart-5)",
  "var(--chart-4)",
];

/** Four is the cap, and the cap is the point: it is what a person can hold at
 *  once. A fifth pick retires the first. */
export const MAX_PICKS = 4;

export interface BoardBank {
  ticker: string;
  name: string;
  groupCode: string;
  groupLabel: string;
}
