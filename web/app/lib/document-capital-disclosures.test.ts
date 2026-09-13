import { readFileSync } from "node:fs";
import { gunzipSync } from "node:zlib";
import { describe, expect, it, vi } from "vitest";
import { SourceTablesBuilder } from "./document-source-tables";
import { indexDipnotes, linkDipnotes, type NoteTarget } from "./document-dipnotes";

vi.mock("@opennextjs/cloudflare", () => ({ getCloudflareContext: vi.fn() }));
const fixture = JSON.parse(gunzipSync(readFileSync(new URL("../../../tests/fixtures/document_capital_disclosure_garan.json.gz", import.meta.url))).toString("utf8"));
const tomk = JSON.parse(gunzipSync(readFileSync(new URL("../../../tests/fixtures/document_capital_disclosure_tomk.json.gz", import.meta.url))).toString("utf8"));
function build(input = fixture) {
  const b = new SourceTablesBuilder(input.revision, input.sections);
  for (const p of input.pages) b.addPage(p.structure, p.source, []);
  return b.finish();
}
const capital = (notes: NoteTarget[]) => notes.find(n => n.address.section === 4 && n.address.group === "1" && n.address.item === "1")!;

describe("complete capital disclosure and qualifications", () => {
  it("groups all four source pages without concatenating or changing their grids", () => {
    const report = build(), note = capital(report.notes);
    expect(note).toMatchObject({ page_start: 55, page_end: 58, boundary: "next_heading" });
    const grids = report.tables.filter(t => note.table_ids.includes(t.id) && t.rows.length);
    expect(grids.map(t => t.id)).toEqual(["p55:ruled0", "p56:ruled0", "p57:ruled0", "p58:ruled0"]);
    for (const table of grids) {
      expect(table.column_count).toBe(3);
      expect(table.verification.native_cells).toBe("checked");
      expect(table.verification.table_boundaries).toBe("not_verified");
      expect(table.disclosure_ids).toEqual([note.id]);
      expect(table.candidate_lanes).toContain("capital");
      const native = fixture.pages.find((p: { source: { page: number } }) => p.source.page === table.page)
        .structure.tables.find((t: { id: string }) => t.id === table.id);
      expect(table.rows.map(r => r.cells.map(c => c.text))).toEqual(native.rows.map((r: { cells: { text: string | null }[] }) => r.cells.map(c => c.text)));
    }
    expect(grids[0].rows).toHaveLength(31);
    expect(grids[1].rows).toHaveLength(36);
    expect(grids[3].rows).toHaveLength(11);
    // Source page58 uses different column widths. Keep its own physical grid.
    expect(grids[3].bbox).not.toEqual(grids[2].bbox);
    expect(note.table_ids).not.toContain("p59:ruled0");
    expect(report.verification.report_complete).toBe(false);
  });
  it("retains the title's star, the insurance qualification and both printed periods", () => {
    const report = build(), note = capital(report.notes);
    expect(note.heading).toContain("(*)");
    const text = report.passages.filter(p => note.passage_ids.includes(p.id)).map(p => p.raw_text).join("\n");
    expect(text).toContain("insurance subsidiary");
    expect(text).toContain("As the consolidated capital calculated including the insurance subsidiary is lesser");
    expect(text).toContain("16.78%");
    expect(text).toContain("252 business days");
    expect(text).toContain("10%");
    expect(text).not.toContain("Information about instruments included in total capital calculation");
    for (const p of [55, 56, 57, 58]) {
      const table = report.tables.find(t => t.id === `p${p}:ruled0`)!;
      expect(table.rows[0].cells.slice(1).map(c => c.text)).toEqual(["Current Period", "Prior Period"]);
    }
  });
  it("does not call the disclosure closed when the next source heading was not read", () => {
    const partial = structuredClone(fixture);
    partial.pages = partial.pages.slice(0, 4);
    const report = build(partial), note = capital(report.notes);
    expect(note.boundary).toBe("open");
    const link = linkDipnotes([{ table_id: "test", row: 1, column: 1, text: "4.1.1", source_word_ids: [], is_note_column: true, note_prefix: null }], report.notes)[0];
    expect(link.status).toBe("unresolved");
  });
  it("a missing middle page makes an otherwise plausible disclosure incomplete", () => {
    const partial = structuredClone(fixture);
    partial.pages = partial.pages.filter((p: { source: { page: number } }) => p.source.page !== 56);
    const note = capital(build(partial).notes);
    expect(note.boundary).toBe("source_gap");
    expect(note.table_ids).not.toContain("p57:ruled0");
    const link = linkDipnotes([{ table_id: "test", row: 1, column: 1, text: "4.1.1", source_word_ids: [], is_note_column: true, note_prefix: null }], [note])[0];
    expect(link.status).toBe("unresolved");
  });
  it("repeated qualified continuation headings retain their wording and one address", () => {
    const report = build(), note = capital(report.notes);
    const rows = report.passages.filter(p => note.passage_ids.includes(p.id));
    const seed = rows.find(p => p.kind === "heading")!;
    const repeat = { ...seed, id: "repeat", element_id: "repeat", page: 56, heading_marker: null,
      text: "4.1.1 Components of consolidated total capital (continued)", raw_text: "4.1.1 Components of consolidated total capital (continued)" };
    const split = rows.findIndex(p => p.page === 56);
    const notes = indexDipnotes([...rows.slice(0, split), repeat, ...rows.slice(split)]);
    const found = notes.filter(n => n.address.item === "1");
    expect(found).toHaveLength(1);
    expect(found[0].passage_ids).toContain("repeat");
  });
  it("supports a Turkish Roman-numbered capital group across four pages", () => {
    const report = build(tomk);
    const note = report.notes.find(n => n.address.section === 4 && n.address.group === "I" && n.address.item === "")!;
    expect(note).toMatchObject({ page_start: 26, page_end: 29, boundary: "next_heading" });
    const grids = report.tables.filter(t => note.table_ids.includes(t.id) && t.rows.length);
    expect(grids.map(t => t.id)).toEqual(["p26:ruled0", "p27:ruled0", "p28:ruled0", "p29:ruled0"]);
    expect(grids.map(t => t.rows.length)).toEqual([20, 35, 30, 22]);
    expect(grids.every(t => t.disclosure_ids.includes(note.id) && t.candidate_lanes.includes("capital"))).toBe(true);
    const text = report.passages.filter(p => note.passage_ids.includes(p.id)).map(p => p.text).join("\n");
    expect(text).toContain("ÖZKAYNAKLARA İLİŞKİN AÇIKLAMALAR (Devamı)");
    expect(text).toContain("mutabakatı sağlamak");
    expect(note.passage_ids.every(id => report.passages.find(p => p.id === id)!.page <= 29)).toBe(true);
    expect(text).not.toContain("KUR RİSKİNE İLİŞKİN AÇIKLAMALAR");
    // Repeated section banners remain available as the correct page's context.
    const banner = report.passages.find(p => p.element_id === "p29:narrative4")!;
    expect(report.tables.find(t => t.id === "p29:ruled0")!.page_context_passage_ids).toContain(banner.id);
    expect(note.table_ids).not.toContain("p30:underline0");
    expect(report.notes.filter(n => n.address.section === 4 && n.address.group === "I" && n.address.item === "")).toHaveLength(1);
  });
});
