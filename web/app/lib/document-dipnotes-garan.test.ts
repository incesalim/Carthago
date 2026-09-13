import { readFileSync } from "node:fs";
import { describe, expect, it, vi } from "vitest";
import { SourceTablesBuilder } from "./document-source-tables";
import { linkDipnotes, parseNoteAddress, type NoteCell } from "./document-dipnotes";

vi.mock("@opennextjs/cloudflare", () => ({ getCloudflareContext: vi.fn() }));
const f = JSON.parse(readFileSync(new URL("../../../tests/fixtures/document_dipnotes_garan.json", import.meta.url), "utf8"));
const builder = new SourceTablesBuilder(f.revision, f.sections);
for (const p of f.pages) builder.addPage(p.structure, p.source);
const report = builder.finish();
const cell = (text: string, dedicated = true): NoteCell => ({ table_id: "test", row: 0, column: 1, text,
  source_word_ids: [], is_note_column: dedicated, note_prefix: null });
describe("GARAN's fully numbered note addresses", () => {
  it("keeps nested numeric addresses and whole-group addresses distinct", () => {
    expect(parseNoteAddress("5.1.1.1", null)).toEqual({ section: 5, group: "1", item: "1.1" });
    expect(parseNoteAddress("5.6", null)).toEqual({ section: 5, group: "6", item: "" });
    expect(linkDipnotes([cell("5.6", false), cell("5.401.481")], report.notes)).toEqual([]);
  });
  it("includes the cash subnotes and qualifications in the parent interval", () => {
    const links = linkDipnotes([cell("5.1.1\n5.1.1.1\n5.1.1.2")], report.notes);
    expect(links.map(l => l.status)).toEqual(["resolved", "resolved", "resolved"]);
    const parent = report.notes.find(n => n.id === links[0].target_ids[0])!;
    const text = report.passages.filter(p => parent.passage_ids.includes(p.id)).map(p => p.raw_text).join("\n");
    expect(parent).toMatchObject({ page_start: 121, page_end: 123 });
    expect(text).toContain("130,364,387");
    expect(text).toContain("The reserve requirements");
    expect(text).toContain("Due from foreign banks");
    expect(text).not.toContain("5.1.2");
  });
  it("links all eight printed cash-flow Footnotes cells to the entire 5.6 group", () => {
    const table = report.tables.find(t => t.id === "p21:ruled0")!;
    expect(table.dipnote_links).toHaveLength(8);
    expect(table.dipnote_links.every(l => l.marker === "5.6" && l.status === "resolved")).toBe(true);
    const note = report.notes.find(n => n.id === table.dipnote_links[0].target_ids[0])!;
    expect(note).toMatchObject({ address: { section: 5, group: "6", item: "" }, page_start: 175, page_end: 176, boundary: "next_heading" });
    const text = report.passages.filter(p => note.passage_ids.includes(p.id)).map(p => p.raw_text).join("\n");
    for (const value of ["49,955,024", "149,464,536", "122,462,323", "Cash and cash equivalents at end of period"]) expect(text.includes(value), value).toBe(true);
    expect(note.table_ids.length).toBeGreaterThan(1);
  });
});
