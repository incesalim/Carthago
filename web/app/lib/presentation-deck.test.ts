import { describe, expect, it } from "vitest";
import { buildDeckHtml, type DeckData } from "./presentation-deck";

const DATA: DeckData = {
  asOf: "2026-05",
  vitals: [
    { label: "Assets · y/y", value: 36.0, unit: "%", decimals: 1 },
    { label: "NPL ratio", value: 2.69, unit: "%", decimals: 2 },
    { label: "Capital adequacy", value: 16.3, unit: "%", decimals: 1 },
    { label: "Return on equity", value: 24.7, unit: "%", decimals: 1 },
  ],
  sections: [
    {
      tab: "overview",
      headline: "As of 2026-05: the sector is growing (assets 36.0% y/y).",
      items: ["Balance sheet expanding — assets 36.0% y/y."],
    },
    {
      tab: "credit",
      headline: "Credit is growing 36.4% y/y and cooling.",
      items: ["Loan growth 36.4% y/y.", "Gearing at 10.6× equity."],
      chart: {
        label: "Loan growth · y/y %",
        unit: "%",
        points: [
          { period: "2024-06", value: 40.1 },
          { period: "2025-06", value: 38.0 },
          { period: "2026-05", value: 36.4 },
        ],
      },
    },
  ],
};

describe("buildDeckHtml", () => {
  const html = buildDeckHtml(DATA, { generatedAt: "2026-07-05" });

  it("is a standalone print-sized document", () => {
    expect(html.startsWith("<!doctype html>")).toBe(true);
    expect(html).toContain("@page { size: 1280px 720px; margin: 0; }");
  });

  it("renders a title, a KPI vitals slide, section slides, and a closing slide", () => {
    const slides = html.match(/class="slide /g) ?? [];
    // title + vitals + (sections minus overview = 1) + closing
    expect(slides.length).toBe(4);
    expect(html).toContain("Sector Vitals · 2026-05");
    expect(html).toContain("01 · CREDIT");
    expect(html).not.toContain("· OVERVIEW"); // overview becomes the vitals slide
  });

  it("renders KPI tiles from vitals", () => {
    expect(html).toContain("16.3<span class=\"u\">%</span>");
    expect(html).toContain("2.69<span class=\"u\">%</span>");
    expect(html).toContain("Return on equity");
  });

  it("draws an inline-SVG chart when a section has series", () => {
    expect(html).toContain("<svg");
    expect(html).toContain("grad-credit"); // unique gradient id per section
    expect(html).toContain('class="chart-title">Loan growth · y/y %');
  });

  it("strips + re-capitalises the As-of headline and emphasises figures", () => {
    expect(html).toContain("The sector is growing"); // capitalised, prefix stripped
    expect(html).toContain('<span class="fig">36.4%</span>');
    expect(html).toContain('<span class="fig">10.6×</span>');
    expect(html).not.toContain('<span class="fig">2026</span>');
  });

  it("escapes untrusted text before inserting markup", () => {
    const evil = buildDeckHtml(
      { asOf: "2026-05", vitals: [], sections: [{ tab: "credit", headline: "x", items: ["<script>alert(1)</script> 5%"] }] },
      { generatedAt: "2026-07-05" },
    );
    expect(evil).toContain("&lt;script&gt;");
    expect(evil).not.toContain("<script>alert(1)</script>");
  });

  it("fires the print dialog only when autoPrint is set", () => {
    expect(buildDeckHtml(DATA, { autoPrint: true })).toContain('addEventListener("load"');
    expect(html).toContain('onclick="window.print()"'); // toolbar button always present
    expect(html).not.toContain('addEventListener("load"');
  });
});
