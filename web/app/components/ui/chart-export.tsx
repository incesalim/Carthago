"use client";

/**
 * Header controls for a chart card: copy the chart image to the clipboard,
 * download it as a PNG, download the underlying data as a CSV, or pop the chart
 * up large in the centre of the screen.
 *
 * Render it anywhere inside a card carrying `data-chart-card` (see ChartCard) —
 * the buttons climb to that element via `closest()`, so no ref threading is
 * needed and ChartCard stays a plain server component. They mirror
 * CopyTableButton's look (hover-revealed pills via the parent's `group` class).
 *
 * Copy/PNG rasterise the whole card (title + chart); the export library is
 * lazy-imported on click so it never lands in the initial bundle. Expand
 * re-parents the *live* card node into a centred modal so Recharts re-measures
 * and the chart stays interactive (tooltips, legend hover/pin) at the larger
 * size — the card is restored to its exact slot on close.
 *
 * The CSV pill only appears when the card contains a `[data-chart-csv]` payload
 * (charts stamp one via `<ChartData>`, see chart-csv.tsx); we detect it in a
 * post-mount effect so SSR/first paint omit the pill and there's no hydration
 * mismatch.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Check, Clipboard, Download, Maximize2, Minimize2, Sheet, X } from "lucide-react";
import { toast } from "sonner";
import { toCsv, type ChartTable } from "@/app/lib/chart-csv";
import { DARK, LIGHT, type ChartTheme } from "@/app/lib/chart-theme";

const BTN =
  "inline-flex items-center justify-center rounded-md border border-border bg-card p-1.5 text-muted-foreground opacity-0 transition-opacity hover:text-foreground focus-visible:opacity-100 group-hover:opacity-100 disabled:opacity-50";

function slugify(s: string): string {
  return (
    s
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 80) || "chart"
  );
}

// ── Force-light export ────────────────────────────────────────────────────
//
// The downloaded / copied image must ALWAYS be the light sheet, whatever theme
// is on screen. modern-screenshot rasterises the LIVE DOM — it inlines the
// element's computed styles onto the clone — so in dark mode the capture comes
// out dark. We can't re-theme React mid-capture: Recharts bakes its colours into
// SVG `stroke`/`fill` attributes at render time, and the card chrome is driven by
// CSS design tokens. So instead we substitute every dark colour for its light
// counterpart on the cloned node, inside modern-screenshot's `onCloneEachNode`
// hook (which fires AFTER the computed styles are inlined).
//
// Two sources of "dark": the chart ink (the ChartTheme DARK object) and the card
// chrome (the CSS tokens). The one value they share — #7FA3D8 is both the dark
// hero line and dark `--primary` — must land on navy in the plot but link-blue in
// the text, so SVG nodes resolve the chart palette first and HTML nodes the
// tokens first.

/** Dark UI token → light token. LOCKSTEP with app/globals.css (`:root` vs `.dark`):
 *  a token colour that changes there changes here. */
const TOKEN_PAIRS: ReadonlyArray<readonly [string, string]> = [
  ["#171B21", "#FFFFFF"], // --card (the sheet)
  ["#101318", "#F7F8F6"], // --background
  ["#E6E9E6", "#12161B"], // --foreground (titles, values)
  ["#9AA3AD", "#68707A"], // --muted-foreground
  ["#6B747E", "#A0A7AE"], // --faint (metas, axis labels)
  ["#262C34", "#E1E3DD"], // --border
  ["#1F252C", "#ECEDE8"], // --hair
  ["#7FA3D8", "#2757A8"], // --primary (links inside a card)
];

/** The light sheet the export always sits on (light `--card`). */
const LIGHT_CARD = "#FFFFFF";

type Lookups = {
  svg: Map<string, string>;
  html: Map<string, string>;
  canon: (c: string) => string | null;
};

let lookups: Lookups | null = null;

/** Build the DARK→LIGHT substitution maps once, keyed by canonical `r,g,b`.
 *  A 1px canvas normalises any CSS colour (hex, `rgb()`, `oklch()`, named) to the
 *  same form, so the map matches whatever `getComputedStyle` inlined. */
function getLookups(): Lookups {
  if (lookups) return lookups;
  const ctx = document.createElement("canvas").getContext("2d")!;
  const cache = new Map<string, string | null>();
  const canon = (c: string): string | null => {
    if (!c || c === "none" || c === "transparent" || c.startsWith("url(")) return null;
    const hit = cache.get(c);
    if (hit !== undefined) return hit;
    ctx.fillStyle = "#000"; // reset, so an unparseable value can't inherit the last
    ctx.fillStyle = c;
    ctx.fillRect(0, 0, 1, 1);
    const [r, g, b, a] = ctx.getImageData(0, 0, 1, 1).data;
    const key = a === 0 ? null : `${r},${g},${b}`;
    cache.set(c, key);
    return key;
  };

  const chartPairs: Array<[string, string]> = [];
  (Object.keys(LIGHT) as Array<keyof ChartTheme>).forEach((k) => {
    const l = LIGHT[k];
    const d = DARK[k];
    if (Array.isArray(d) && Array.isArray(l)) {
      d.forEach((dv, i) => chartPairs.push([dv, l[i]]));
    } else if (typeof d === "string" && typeof l === "string") {
      chartPairs.push([d, l]);
    }
  });

  const build = (
    primary: ReadonlyArray<readonly [string, string]>,
    secondary: ReadonlyArray<readonly [string, string]>,
  ): Map<string, string> => {
    const m = new Map<string, string>();
    for (const [d, l] of secondary) {
      const k = canon(d);
      if (k) m.set(k, l);
    }
    for (const [d, l] of primary) {
      const k = canon(d);
      if (k) m.set(k, l); // primary wins on a shared key
    }
    return m;
  };

  lookups = {
    canon,
    svg: build(chartPairs, TOKEN_PAIRS), // SVG ink: chart palette wins
    html: build(TOKEN_PAIRS, chartPairs), // card chrome: tokens win
  };
  return lookups;
}

const COLOR_STYLE_PROPS = [
  "color",
  "backgroundColor",
  "fill",
  "stroke",
  "stopColor",
  "outlineColor",
  "borderTopColor",
  "borderRightColor",
  "borderBottomColor",
  "borderLeftColor",
] as const;
const COLOR_ATTRS = ["fill", "stroke", "stop-color", "color"] as const;

/** Rewrite one cloned node's dark colours to their light counterparts. */
function forceLight(node: Node): void {
  if (!(node instanceof Element)) return;
  const isSvg = node instanceof SVGElement;
  const { svg, html, canon } = getLookups();
  const map = isSvg ? svg : html;

  const style = (node as HTMLElement | SVGElement).style as CSSStyleDeclaration | undefined;
  if (style) {
    for (const prop of COLOR_STYLE_PROPS) {
      const v = style[prop];
      if (!v) continue;
      const k = canon(v);
      const light = k && map.get(k);
      if (light) style[prop] = light;
    }
  }
  // Recharts sets stroke/fill as presentation ATTRIBUTES; inline style wins over
  // them in the SVG cascade, but remap both so nothing stale survives.
  if (isSvg) {
    for (const attr of COLOR_ATTRS) {
      const v = node.getAttribute(attr);
      if (!v) continue;
      const k = canon(v);
      const light = k && map.get(k);
      if (light) node.setAttribute(attr, light);
    }
  }
}

async function captureBlob(card: HTMLElement): Promise<Blob> {
  const { domToBlob } = await import("modern-screenshot");
  const blob = await domToBlob(card, {
    scale: 2,
    backgroundColor: LIGHT_CARD, // the export is always the light sheet
    // Drop the export controls (and anything else opted out) from the image.
    filter: (node: Node) =>
      !(node instanceof HTMLElement && node.dataset.chartNoExport === ""),
    onCloneEachNode: forceLight,
    fetch: { requestInit: { cache: "no-cache" } },
  });
  if (!blob) throw new Error("chart capture produced no image");
  return blob;
}

function cardOf(e: React.MouseEvent<HTMLButtonElement>): HTMLElement | null {
  return e.currentTarget.closest<HTMLElement>("[data-chart-card]");
}

export default function ChartExport() {
  const [copied, setCopied] = useState(false);
  const [busy, setBusy] = useState(false);

  // CSV pill: only shown when the card carries a `[data-chart-csv]` payload.
  // Detect it after mount (the chart sibling is in the DOM by then) so the
  // server render — which can't see the sibling — matches the first client pass.
  const barRef = useRef<HTMLDivElement | null>(null);
  const [hasCsv, setHasCsv] = useState(false);
  useEffect(() => {
    const card = barRef.current?.closest<HTMLElement>("[data-chart-card]");
    setHasCsv(!!card?.querySelector("[data-chart-csv]"));
  }, []);

  // Centre-screen popup. We move the *real* card DOM into the modal (rather than
  // cloning) so Recharts' ResponsiveContainer re-measures and the chart stays
  // live. A comment placeholder marks the card's original slot for restoration.
  const [expanded, setExpanded] = useState(false);
  const cardRef = useRef<HTMLElement | null>(null);
  const placeholderRef = useRef<Comment | null>(null);

  function closeExpand() {
    const card = cardRef.current;
    const ph = placeholderRef.current;
    // Restore the card to its slot *before* unmounting the modal, so React only
    // ever removes the now-empty mount — never the card itself.
    if (card && ph?.parentNode) {
      ph.parentNode.insertBefore(card, ph);
      ph.remove();
    }
    cardRef.current = null;
    placeholderRef.current = null;
    setExpanded(false);
  }

  function openExpand(e: React.MouseEvent<HTMLButtonElement>) {
    if (expanded) return;
    const card = cardOf(e);
    if (!card?.parentNode) return;
    const ph = document.createComment("chart-expand");
    card.parentNode.insertBefore(ph, card);
    cardRef.current = card;
    placeholderRef.current = ph;
    setExpanded(true);
  }

  // The mount lands in the DOM during commit (before paint), so appending the
  // card here — instead of in an effect — avoids an empty-modal flash. Stable
  // identity keeps it from re-firing on Copy/PNG re-renders while open.
  const mountRef = useCallback((el: HTMLDivElement | null) => {
    if (el && cardRef.current) el.appendChild(cardRef.current);
  }, []);

  // Esc-to-close + lock body scroll while the popup is open.
  useEffect(() => {
    if (!expanded) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") closeExpand();
    };
    window.addEventListener("keydown", onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [expanded]);

  async function onDownload(e: React.MouseEvent<HTMLButtonElement>) {
    const card = cardOf(e);
    if (!card || busy) return;
    setBusy(true);
    try {
      const title = card
        .querySelector<HTMLElement>("[data-chart-title]")
        ?.textContent?.trim();
      const blob = await captureBlob(card);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${slugify(title ?? "chart")}.png`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error("chart download failed", err);
      toast.error("Could not export chart as an image.");
    } finally {
      setBusy(false);
    }
  }

  async function onCopy(e: React.MouseEvent<HTMLButtonElement>) {
    const card = cardOf(e);
    if (!card || busy) return;
    setBusy(true);
    try {
      const blob = await captureBlob(card);
      await navigator.clipboard.write([
        new ClipboardItem({ "image/png": blob }),
      ]);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch (err) {
      console.error("chart copy failed", err);
      toast.error("Copying the chart image isn't supported in this browser.");
    } finally {
      setBusy(false);
    }
  }

  function onCsv(e: React.MouseEvent<HTMLButtonElement>) {
    const card = cardOf(e);
    const json = card?.querySelector("[data-chart-csv]")?.textContent;
    if (!json) return;
    try {
      const table = JSON.parse(json) as ChartTable;
      const title = card!
        .querySelector<HTMLElement>("[data-chart-title]")
        ?.textContent?.trim();
      const blob = new Blob([toCsv(table)], {
        type: "text/csv;charset=utf-8",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${slugify(title ?? "chart")}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error("chart CSV export failed", err);
      toast.error("Could not export the chart data.");
    }
  }

  return (
    <>
      <div ref={barRef} data-chart-no-export="" className="flex items-center gap-1">
        <button
          type="button"
          onClick={onCopy}
          disabled={busy}
          aria-label="Copy chart image to clipboard"
          title={copied ? "Copied" : "Copy image"}
          className={BTN}
        >
          {copied ? (
            <Check className="size-3.5" aria-hidden />
          ) : (
            <Clipboard className="size-3.5" aria-hidden />
          )}
        </button>
        <button
          type="button"
          onClick={onDownload}
          disabled={busy}
          aria-label="Download chart as PNG"
          title="Download PNG"
          className={BTN}
        >
          <Download className="size-3.5" aria-hidden />
        </button>
        {hasCsv && (
          <button
            type="button"
            onClick={onCsv}
            aria-label="Download chart data as CSV"
            title="Download CSV"
            className={BTN}
          >
            <Sheet className="size-3.5" aria-hidden />
          </button>
        )}
        <button
          type="button"
          onClick={expanded ? closeExpand : openExpand}
          aria-label={expanded ? "Close expanded chart" : "Expand chart to centre of screen"}
          title={expanded ? "Restore" : "Expand"}
          className={BTN}
        >
          {expanded ? (
            <Minimize2 className="size-3.5" aria-hidden />
          ) : (
            <Maximize2 className="size-3.5" aria-hidden />
          )}
        </button>
      </div>

      {expanded &&
        createPortal(
          <div
            className="fixed inset-0 z-[60] flex items-center justify-center p-4 sm:p-8"
            role="dialog"
            aria-modal="true"
          >
            <button
              type="button"
              aria-label="Close"
              onClick={closeExpand}
              className="absolute inset-0 bg-background/80 backdrop-blur-sm"
            />
            <div className="relative w-full max-w-5xl">
              <button
                type="button"
                onClick={closeExpand}
                aria-label="Close expanded chart"
                title="Close"
                className="absolute -top-10 right-0 z-10 inline-flex size-8 items-center justify-center rounded-full border border-border bg-card text-muted-foreground shadow-sm transition-colors hover:text-foreground"
              >
                <X className="size-4" aria-hidden />
              </button>
              {/* The live card is moved in here by mountRef; capped to the
                  viewport so tall charts scroll vertically rather than overflow.
                  X is clipped, not auto: the chart is always width-responsive, so
                  a horizontal scrollbar is never needed — but a tooltip rendering
                  at the chart edge momentarily overflows the width, and `auto`
                  would flash a horizontal scrollbar for that one frame. */}
              <div ref={mountRef} className="max-h-[90vh] w-full overflow-x-hidden overflow-y-auto" />
            </div>
          </div>,
          document.body,
        )}
    </>
  );
}
