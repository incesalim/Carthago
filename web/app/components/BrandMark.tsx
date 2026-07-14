import { cn } from "@/app/lib/cn";

/**
 * The Carthago mark: an open navy "C" enclosing a data mosaic (left) and a
 * rising bar chart (right).
 *
 * Inline SVG rather than the raster in `public/logo.png` so it stays crisp at
 * nav size on any DPR and can re-tone itself for the dark sheet — the mark is
 * multi-tone, so the old `dark:brightness-0 dark:invert` silhouette trick would
 * flatten it into a blob.
 *
 * The geometry here is the SOURCE OF TRUTH for the brand. `scripts/make_brand_assets.py`
 * mirrors these exact numbers (same 64×64 grid) to rasterise the favicon, app
 * icons and social cards — change one, re-run the other.
 */

// 64×64 grid, disc centred on (32, 32).
const RING = { cx: 32, cy: 32, r: 25.5, w: 8 }; // stroke, round caps
const DISC_R = 19.5; // clips the mosaic + bars, giving the globe's curved edge

// Mosaic: 4.7 cells on a 5.5 pitch (0.8 gap — the same gutter the bars use),
// kept wherever the cell centre falls inside the disc. Rim cells are left to be
// clipped by it: that cut edge is what reads as a globe.
// Tone key: p = pale, l = light, m = mid.
const CELLS: Array<[x: number, y: number, tone: "p" | "l" | "m"]> = [
  [13.5, 19.5, "m"],
  [13.5, 25.0, "p"],
  [13.5, 30.5, "l"],
  [13.5, 36.0, "m"],
  [19.0, 14.0, "p"],
  [19.0, 19.5, "l"],
  [19.0, 25.0, "m"],
  [19.0, 30.5, "p"],
  [19.0, 36.0, "l"],
  [19.0, 41.5, "p"],
  [24.5, 14.0, "l"],
  [24.5, 19.5, "p"],
  [24.5, 25.0, "l"],
  [24.5, 30.5, "m"],
  [24.5, 36.0, "p"],
  [24.5, 41.5, "l"],
];

// Bars rise left→right off a y=44 baseline and deepen in tone as they grow.
const BARS: Array<[x: number, top: number, tone: "l" | "m" | "d"]> = [
  [30.2, 36.5, "l"],
  [36.0, 30.0, "m"],
  [41.8, 23.0, "d"],
];

// Light sheet → dark sheet. The tonal ramp inverts on the dark ground so the
// tallest bar stays the highest-contrast element in both themes.
const TONE = {
  p: "fill-[#E6EEF6] dark:fill-[#C9D8E8]",
  l: "fill-[#7FA0BF] dark:fill-[#4E7092]",
  m: "fill-[#2D5B8C] dark:fill-[#6E97C8]",
  d: "fill-[#1F2E4A] dark:fill-[#A8C3E0]",
} as const;

// Ring endpoints at ±38° off east — the C's opening, which the tall bar points into.
const RING_PATH = "M 52.1 47.7 A 25.5 25.5 0 1 1 52.1 16.3";

export default function BrandMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 64 64"
      aria-hidden
      focusable="false"
      className={cn("shrink-0", className)}
    >
      <defs>
        <clipPath id="carthago-disc">
          <circle cx={RING.cx} cy={RING.cy} r={DISC_R} />
        </clipPath>
      </defs>

      <g clipPath="url(#carthago-disc)">
        {CELLS.map(([x, y, tone]) => (
          <rect
            key={`c${x}-${y}`}
            x={x}
            y={y}
            width={4.7}
            height={4.7}
            rx={0.5}
            className={TONE[tone]}
          />
        ))}
        {BARS.map(([x, top, tone]) => (
          <rect
            key={`b${x}`}
            x={x}
            y={top}
            width={5.0}
            height={44 - top}
            rx={0.6}
            className={TONE[tone]}
          />
        ))}
      </g>

      <path
        d={RING_PATH}
        fill="none"
        strokeWidth={RING.w}
        strokeLinecap="round"
        className="stroke-[#0D1B2A] dark:stroke-[#E6E9E6]"
      />
    </svg>
  );
}
