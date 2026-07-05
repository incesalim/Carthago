import { describe, expect, it } from "vitest";
import { buildDeckHtml, type DeckSection } from "./presentation-deck";

const SECTIONS: DeckSection[] = [
  {
    tab: "overview",
    headline: "As of 2026-05: the sector is growing (assets 36.0% y/y).",
    items: ["Balance sheet expanding — assets 36.0% y/y, loans 37.5%.", "NPL ratio 2.69% (+0.04pp m/m)."],
  },
  {
    tab: "capital",
    headline: "The sector holds a 4.3pp buffer over the 12% minimum.",
    items: ["CAR 16.3% — a 4.3pp buffer.", "Gearing at 10.6× equity and rising."],
  },
];

describe("buildDeckHtml", () => {
  const html = buildDeckHtml(SECTIONS, { generatedAt: "2026-07-05" });

  it("is a standalone print-sized document", () => {
    expect(html.startsWith("<!doctype html>")).toBe(true);
    expect(html).toContain("@page { size: 1280px 720px; margin: 0; }");
  });

  it("renders one slide per section plus a title and closing slide", () => {
    // `slide ` with a trailing space → the real slides (slide-num/-foot excluded)
    const slides = html.match(/class="slide /g) ?? [];
    expect(slides.length).toBe(SECTIONS.length + 2);
    expect(html).toContain("01 · SECTOR OVERVIEW");
    expect(html).toContain("02 · CAPITAL");
  });

  it("shows the period pill and strips + re-capitalises the As-of headline", () => {
    expect(html).toContain("As of 2026-05");
    expect(html).toContain("The sector is growing"); // capitalised, prefix stripped
    expect(html).not.toContain("As of 2026-05: the sector"); // prefix gone from headline
  });

  it("emphasises figure tokens but leaves bare years plain", () => {
    expect(html).toContain('<span class="fig">36.0%</span>');
    expect(html).toContain('<span class="fig">+0.04pp</span>');
    expect(html).toContain('<span class="fig">10.6×</span>');
    // the '2026' inside the '2026-05' period must not be wrapped as a figure
    expect(html).not.toContain('<span class="fig">2026</span>');
  });

  it("escapes untrusted text before inserting markup", () => {
    const evil = buildDeckHtml(
      [{ tab: "overview", headline: "x", items: ["<script>alert(1)</script> 5%"] }],
      { generatedAt: "2026-07-05" },
    );
    expect(evil).toContain("&lt;script&gt;");
    expect(evil).not.toContain("<script>alert(1)</script>");
  });

  it("adds the print-on-load hook only when autoPrint is set", () => {
    expect(buildDeckHtml(SECTIONS, { autoPrint: true })).toContain("window.print()");
    expect(html).toContain('onclick="window.print()"'); // toolbar button always present
    expect(html).not.toContain("addEventListener(\"load\""); // no auto-fire without the flag
  });
});
