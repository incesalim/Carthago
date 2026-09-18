import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import Vitals from "./Vitals";
import { GridTable } from "./CoverageGrid";
import { PartitionStrip } from "./CoverageDrawer";
import type { CoverageCell, CoverageVitals } from "@/app/lib/coverage";

const hoursAgo = (h: number) => new Date(Date.now() - h * 3600 * 1000).toISOString();

describe("coverage vitals strip", () => {
  it("states lane parity and sync age quietly when the spine is healthy", () => {
    const vitals: CoverageVitals = {
      spine: { syncedAt: hoursAgo(2), lanesDeclared: 20, lanesInD1: 20 },
      lastValidated: hoursAgo(1),
      trend: [],
    };
    const html = renderToStaticMarkup(<Vitals error={3} missing={4} vitals={vitals} />);
    expect(html).toContain("20/20 lanes in D1");
    expect(html).toContain("validated");
    expect(html).toContain(">3</span> errors");
    expect(html).not.toContain("text-warning\">spine");
  });

  it("warns when D1 holds fewer lanes than the last sync declared", () => {
    // The risk_profile blind spot: a lane registered in code, absent in D1.
    const vitals: CoverageVitals = {
      spine: { syncedAt: hoursAgo(2), lanesDeclared: 20, lanesInD1: 19 },
      lastValidated: null,
      trend: [],
    };
    const html = renderToStaticMarkup(<Vitals error={0} missing={0} vitals={vitals} />);
    expect(html).toContain("19/20 lanes in D1");
    expect(html).toContain("text-warning");
  });

  it("says never-synced rather than rendering nothing", () => {
    const html = renderToStaticMarkup(
      <Vitals error={0} missing={0} vitals={{ spine: { syncedAt: null, lanesDeclared: null, lanesInD1: 19 }, lastValidated: null, trend: [] }} />,
    );
    expect(html).toContain("spine never synced");
    expect(html).toContain("19 lanes in D1");
    expect(html).toContain("text-warning");
  });

  it("renders trend chips with direction tones once a baseline exists", () => {
    const trend = [
      { checked_at: hoursAgo(1), ok: 1, manual: 0, error: 12, missing: 6, not_expected: 0, lanes: 20 },
      { checked_at: hoursAgo(8 * 24), ok: 1, manual: 0, error: 41, missing: 12, not_expected: 0, lanes: 20 },
    ];
    const html = renderToStaticMarkup(
      <Vitals error={12} missing={6} vitals={{ spine: { syncedAt: hoursAgo(2), lanesDeclared: 20, lanesInD1: 20 }, lastValidated: null, trend }} />,
    );
    expect(html).toContain("errors 41→12 (8d)");
    expect(html).toContain("missing 12→6 (8d)");
    // improving reads positive, not negative
    expect(html).toContain("text-positive\">errors 41→12");
  });
});

describe("coverage grid table", () => {
  const cells: CoverageCell[] = [
    { bank_ticker: "AKBNK", period: "2026Q2", kind: "consolidated", status: "ok", row_count: 40, checks_failed: 0, is_manual: 0, pdf_present: 1 },
    { bank_ticker: "AKBNK", period: "2026Q1", kind: "consolidated", status: "error", row_count: 40, checks_failed: 2, is_manual: 0, pdf_present: 1 },
    { bank_ticker: "GARAN", period: "2026Q2", kind: "consolidated", status: "missing", row_count: 0, checks_failed: 0, is_manual: 0, pdf_present: 0 },
  ];
  const html = renderToStaticMarkup(
    <GridTable banks={["AKBNK", "GARAN"]} periods={["2026Q1", "2026Q2"]} cells={cells} onOpen={() => {}} />,
  );

  it("renders one glyph cell per (bank, period) with status in the tooltip and sr-only text", () => {
    expect(html).toContain("’26Q2");
    expect(html).toContain("’26Q1");
    expect(html).toContain("AKBNK 2026Q1 · cons — error (2 failed)");
    expect(html).toContain("GARAN 2026Q2 · cons — missing");
    // sr-only keeps the grid screen-reader legible without cluttering visuals
    expect(html).toContain('<span class="sr-only">error</span>');
    expect(html).toContain('<span class="sr-only">ok</span>');
  });

  it("keeps absent cells a quiet dot, not a false status", () => {
    // GARAN 2026Q1 has no coverage row — blank, distinct from missing.
    expect(html.match(/GARAN[^<]*<\/td><td class="px-1\.5 text-center text-faint">/)).toBeTruthy();
  });

  it("states the legend so the glyphs never stand alone", () => {
    expect(html).toContain("✓ ok · ✎ manual · ! error");
  });
});

describe("partition strip", () => {
  const coverage = [
    { statement_type: "balance_sheet_assets", status: "ok", row_count: 220, label: "Balance sheet — assets" },
    { statement_type: "loans_currency", status: "error", row_count: 12, label: "Loans by sector — currency" },
    { statement_type: "risk_profile", status: "missing", row_count: 0, label: "Pillar 3 risk profile" },
  ];
  const html = renderToStaticMarkup(
    <PartitionStrip coverage={coverage} activeType="loans_currency" onSwitch={() => {}} />,
  );

  it("lists every lane with label, glyph and row count", () => {
    expect(html).toContain("Balance sheet — assets");
    expect(html).toContain("220 rows");
    expect(html).toContain("Pillar 3 risk profile");
    // zero rows render an empty span, not "0 rows" — a nil cell is not a count
    expect(html).not.toContain(">0 rows<");
    expect(html).toContain(">220 rows<");
  });

  it("marks the drawer's current lane and keeps the others switchable", () => {
    expect(html).toContain("border-foreground");
    expect((html.match(/<button/g) ?? []).length).toBe(coverage.length);
  });
});
