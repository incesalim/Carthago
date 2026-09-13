import { readFileSync } from "node:fs";
import { describe, expect, it, vi } from "vitest";
import { checkedReviewedTable } from "./document-table-review";
import { SourceTablesBuilder, tableLaneCandidates } from "./document-source-tables";

vi.mock("@opennextjs/cloudflare", () => ({ getCloudflareContext: vi.fn() }));
const fixture = JSON.parse(readFileSync(new URL("../../../tests/fixtures/document_primary_dipnotes_tomk.json", import.meta.url), "utf8"));
function build(input = fixture, reviewed = true) {
  const builder = new SourceTablesBuilder(input.revision, input.sections);
  for (const p of input.pages) {
    const reviews = reviewed ? input.reviewed_tables.filter((r: { page: number }) => r.page === p.source.page).map((r: Record<string, unknown>) =>
      checkedReviewedTable(r, p.source, p.structure, r.native_page_sha256, r.structure_page_sha256)) : [];
    builder.addPage(p.structure, p.source, reviews);
  }
  return builder.finish();
}

describe("source tables and their dipnotes", () => {
  it("associates the printed off-balance title and keeps the combined OCI title out of P&L", () => {
    const section = fixture.sections.find((s: { role: string }) => s.role === "financial_statements");
    expect(tableLaneCandidates(section, "KONSOLİDE OLMAYAN NAZIM HESAPLAR TABLOSU")).toEqual(["off_balance"]);
    expect(tableLaneCandidates(section, "KAR VEYA ZARAR VE DİĞER KAPSAMLI GELİR TABLOSU")).toEqual(["other_comprehensive_income"]);
  });
  it("retains all eight printed assets columns and links the printed note column", () => {
    const result = build(), assets = result.tables.find(t => t.id === "p10:ruled0")!;
    expect(assets.column_count).toBe(8);
    expect(assets.verification.native_cells).toBe("checked");
    expect(assets.verification.row_assignments).toBe("named_source_review");
    expect(assets.rows.length).toBeGreaterThan(40);
    expect(assets.candidate_lanes).toContain("balance_sheet_assets");
    const bank = assets.rows.find(r => r.cells.some(c => c.text?.includes("Bankalar")))!;
    expect(bank.cells[1].text).toBe("(1)");
    expect(bank.cells[5].text).toBe("1.004.154");
    expect(bank.cells[7].text).toBe("1.004.154");
    const link = assets.dipnote_links.find(l => l.row === bank.row && l.column === 1)!;
    expect(link).toMatchObject({ marker: "(1)", address: { section: 5, group: "I", item: "1" }, status: "resolved" });
    const target = result.notes.find(n => n.id === link.target_ids[0])!;
    const text = result.passages.filter(p => target.passage_ids.includes(p.id)).map(p => p.raw_text).join("\n");
    expect(text).toContain("1.004.154");
    expect(text).not.toContain("940.366");
    expect(assets.dipnote_links.filter(l => l.status === "resolved").map(l => l.address!.item)).toEqual(["1", "2", "3", "4", "5", "6"]);
    expect(result.verification.report_complete).toBe(false);
  });
  it("retains unreviewed and overlapping physical candidates without certifying logical rows", () => {
    const result = build();
    expect(result.tables).toHaveLength(fixture.pages.reduce((n: number, p: { structure: { tables: unknown[] } }) => n + p.structure.tables.length, 0));
    const physical = result.tables.find(t => t.id === "p38:ruled0")!;
    expect(physical.verification).toMatchObject({ native_cells: "checked", row_assignments: "physical_only", table_boundaries: "not_verified" });
    expect(physical.rows.flatMap(r => r.cells).some(c => c.state === "dash" && c.text === "-")).toBe(true);
    expect(result.tables.find(t => t.id === "p10:numeric1")).toBeDefined();
  });
  it.each(["change", "drop", "borrow", "duplicate"])("rejects a %s in a source cell, keeping the candidate visible", mutation => {
    const input = structuredClone(fixture);
    const p = input.pages.find((p: { source: { page: number } }) => p.source.page === 38);
    const table = p.structure.tables.find((t: { id: string }) => t.id === "p38:ruled0");
    const cell = table.rows.flatMap((r: { cells: { word_ids: number[] }[] }) => r.cells).find((c: { word_ids: number[] }) => c.word_ids.length > 0);
    if (mutation === "change") cell.text += "99";
    if (mutation === "drop") { cell.text = ""; cell.word_ids = []; delete cell.source_fragments; }
    if (mutation === "borrow") cell.word_ids = [p.source.words[0].id];
    if (mutation === "duplicate") cell.word_ids.push(cell.word_ids[0]);
    const result = build(input, false).tables.find(t => t.id === table.id)!;
    expect(result.verification.native_cells).toBe("rejected");
    expect(result.verification.issues.length).toBeGreaterThan(0);
  });
  it("never collapses blank, dash and absent source cells to zero", () => {
    const cells = build().tables.flatMap(t => t.rows.flatMap(r => r.cells));
    expect(cells.some(c => c.text === null && c.state === "absent")).toBe(true);
    expect(cells.some(c => c.text === "" && c.state === "blank")).toBe(true);
    expect(cells.filter(c => c.state === "dash").every(c => c.text !== "0")).toBe(true);
  });
});
