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

const BTN =
  "inline-flex items-center gap-1 rounded-md border border-border bg-card px-2 py-0.5 text-[11px] text-muted-foreground opacity-0 transition-opacity hover:text-foreground focus-visible:opacity-100 group-hover:opacity-100 disabled:opacity-50";

function slugify(s: string): string {
  return (
    s
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 80) || "chart"
  );
}

/**
 * Resolve a card's background to an explicit sRGB string. The theme tokens are
 * `oklch(...)` and getComputedStyle may hand those back verbatim; a 1px canvas
 * round-trip converts any CSS colour to exact rgb so the PNG's bounding box
 * (including the rounded corners) is filled instead of left transparent.
 */
function resolveBg(el: HTMLElement): string {
  const ctx = document.createElement("canvas").getContext("2d");
  const declared = getComputedStyle(el).backgroundColor;
  if (!ctx) return declared;
  ctx.fillStyle = declared;
  ctx.fillRect(0, 0, 1, 1);
  const [r, g, b] = ctx.getImageData(0, 0, 1, 1).data;
  return `rgb(${r}, ${g}, ${b})`;
}

async function captureBlob(card: HTMLElement): Promise<Blob> {
  const { domToBlob } = await import("modern-screenshot");
  const blob = await domToBlob(card, {
    scale: 2,
    backgroundColor: resolveBg(card),
    // Drop the export controls (and anything else opted out) from the image.
    filter: (node: Node) =>
      !(node instanceof HTMLElement && node.dataset.chartNoExport === ""),
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
          title="Copy image"
          className={BTN}
        >
          {copied ? (
            <Check className="size-3" aria-hidden />
          ) : (
            <Clipboard className="size-3" aria-hidden />
          )}
          {copied ? "Copied" : "Copy"}
        </button>
        <button
          type="button"
          onClick={onDownload}
          disabled={busy}
          aria-label="Download chart as PNG"
          title="Download PNG"
          className={BTN}
        >
          <Download className="size-3" aria-hidden />
          {busy ? "…" : "PNG"}
        </button>
        {hasCsv && (
          <button
            type="button"
            onClick={onCsv}
            aria-label="Download chart data as CSV"
            title="Download CSV"
            className={BTN}
          >
            <Sheet className="size-3" aria-hidden />
            CSV
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
            <Minimize2 className="size-3" aria-hidden />
          ) : (
            <Maximize2 className="size-3" aria-hidden />
          )}
          {expanded ? "Restore" : "Expand"}
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
                  viewport so tall charts scroll rather than overflow. */}
              <div ref={mountRef} className="max-h-[90vh] w-full overflow-auto" />
            </div>
          </div>,
          document.body,
        )}
    </>
  );
}
