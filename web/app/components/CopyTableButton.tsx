"use client";

/**
 * Copy-to-clipboard button for the financial-statement table cards.
 *
 * Render it inside a card whose <section> has the `group` class — the button
 * stays invisible until the card is hovered (or the button itself is focused,
 * for keyboard users). On click it serializes the nearest <table> in the card
 * to tab-separated text, so a paste lands as proper rows/columns in Excel,
 * Google Sheets, or a plain editor.
 */
import { useState } from "react";

export default function CopyTableButton() {
  const [copied, setCopied] = useState(false);

  async function copy(e: React.MouseEvent<HTMLButtonElement>) {
    const table = e.currentTarget.closest("section")?.querySelector("table");
    if (!table) return;
    const tsv = Array.from(table.rows)
      .map((row) =>
        Array.from(row.cells)
          // Drop the ⚠ validation marker from period headers; keep text as shown.
          .map((cell) => cell.innerText.replace(/⚠/g, "").trim())
          .join("\t"),
      )
      .join("\n");
    try {
      await navigator.clipboard.writeText(tsv);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard unavailable (e.g. insecure context) — nothing to clean up.
    }
  }

  return (
    <button
      type="button"
      onClick={copy}
      aria-label="Copy table to clipboard"
      className="inline-flex items-center gap-1 rounded-md border border-border bg-card px-2 py-0.5 text-[11px] text-muted-foreground opacity-0 transition-opacity hover:text-foreground focus-visible:opacity-100 group-hover:opacity-100"
    >
      {copied ? (
        <>
          <svg viewBox="0 0 16 16" className="size-3" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden>
            <path d="M3 8.5l3.5 3.5L13 5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          Copied
        </>
      ) : (
        <>
          <svg viewBox="0 0 16 16" className="size-3" fill="none" stroke="currentColor" strokeWidth="1.2" aria-hidden>
            <rect x="5.5" y="5.5" width="8" height="9" rx="1.5" />
            <path d="M10.5 5.5v-2a1.5 1.5 0 0 0-1.5-1.5H4A1.5 1.5 0 0 0 2.5 3.5V11A1.5 1.5 0 0 0 4 12.5h1.5" />
          </svg>
          Copy
        </>
      )}
    </button>
  );
}
