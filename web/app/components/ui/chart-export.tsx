"use client";

/**
 * Export controls for a chart card: copy the chart image to the clipboard, or
 * download it as a PNG.
 *
 * Render it anywhere inside a card carrying `data-chart-card` (see ChartCard) —
 * the buttons climb to that element via `closest()` and rasterise it, so no ref
 * threading is needed and ChartCard stays a plain server component. They mirror
 * CopyTableButton's look (hover-revealed pills via the parent's `group` class).
 *
 * The captured node is the whole card (title + chart). The export library is
 * lazy-imported on click so it never lands in the initial bundle.
 */
import { useState } from "react";
import { Check, Clipboard, Download } from "lucide-react";
import { toast } from "sonner";

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

  return (
    <div data-chart-no-export="" className="flex items-center gap-1">
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
    </div>
  );
}
