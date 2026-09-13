import { readFileSync } from "node:fs";
import { describe, expect, it, vi } from "vitest";
import { ProseBuilder, type ProsePassage } from "./document-prose";
import { indexDipnotes, linkDipnotes, parseNoteAddress, printedNoteHeadings, type NoteCell } from "./document-dipnotes";

vi.mock("@opennextjs/cloudflare", () => ({ getCloudflareContext: vi.fn() }));

const fixture = JSON.parse(readFileSync(new URL("../../../tests/fixtures/document_primary_dipnotes_tomk.json", import.meta.url), "utf8"));
function sourceNotes() {
  const builder = new ProseBuilder(fixture.revision, fixture.sections), headings = new Set<string>();
  for (const p of fixture.pages) {
    builder.addPage(p.structure, p.source);
    for (const id of printedNoteHeadings(p.structure, p.source)) headings.add(id);
  }
  return { passages: builder.report.passages, targets: indexDipnotes(builder.report.passages, headings), headings };
}
const cell = (text: string, prefix: string | null = "V-I", dedicated = true): NoteCell => ({
  table_id: "p10:ruled0", row: 7, column: 1, text, source_word_ids: [1], is_note_column: dedicated, note_prefix: prefix,
});

describe("table dipnotes", () => {
  it.each(["(5.I.1)", "(V-I-1)", "( 5 . I . 1 )"])("retains a complete printed address %s", text => {
    expect(parseNoteAddress(text, null)).toEqual({ section: 5, group: "I", item: "1" });
  });
  it("requires the printed note-column context for a bare marker", () => {
    expect(parseNoteAddress("(1)", "Dipnot (V-I)")).toEqual({ section: 5, group: "I", item: "1" });
    expect(parseNoteAddress("(1)", null)).toBeNull();
    expect(parseNoteAddress("(II-1)", "Dipnot (V-I)")).toEqual({ section: 5, group: "II", item: "1" });
    expect(parseNoteAddress("(1.1)", "Dipnot (V-I)")).toEqual({ section: 5, group: "I", item: "1.1" });
    expect(parseNoteAddress("(1)", "Footnotes (5.4)")).toEqual({ section: 5, group: "4", item: "1" });
  });
  it("links all six visually checked assets dipnotes to their actual section 5-I intervals", () => {
    const { passages, targets } = sourceNotes();
    const wanted = targets.filter(n => n.address.group === "I" && n.address.item);
    expect(wanted.map(n => n.address.item)).toEqual(fixture.expected.note_items);
    expect(wanted.every(n => n.boundary !== "open")).toBe(true);
    const links = linkDipnotes(fixture.expected.note_items.map((id: string) => cell(`(${id})`)), targets);
    expect(links.map(l => l.status)).toEqual(Array(6).fill("resolved"));
    const noteText = (id: string) => passages.filter(p => wanted.find(n => n.address.item === id)!.passage_ids.includes(p.id)).map(p => p.raw_text).join("\n");
    expect(noteText("1")).toContain(fixture.expected.bank_placement_prior_tl);
    expect(noteText("1")).not.toContain("940.366"); // belongs to the NEXT note's table
    expect(noteText("4")).toContain(fixture.expected.software_prior_net);
    expect(noteText("2")).toContain("Yatırım Fonları"); // includes the table's (*) qualification
    expect(noteText("5")).toContain("Mahsup edilebilir mali zararlar");
    expect(noteText("5")).toContain("48.253"); // retains the note's second table
    expect(noteText("6")).toContain("%10");
  });
  it("does not read financial parentheses as note references", () => {
    expect(linkDipnotes([cell("(10)", null, false), cell("(1.545)", null, false)], [])).toEqual([]);
    expect(linkDipnotes([cell("(5.I.1)", null, false)], sourceNotes().targets)[0].status).toBe("resolved");
  });
  it("keeps missing, ambiguous and unsupported references visible", () => {
    const { targets } = sourceNotes();
    const one = targets.find(t => t.address.item === "1")!;
    const result = linkDipnotes([cell("(1)"), cell("(99)"), cell("(*)"), cell("(1,2)")], [...targets, { ...one, id: "duplicate" }]);
    expect(result.map(r => r.status)).toEqual(["ambiguous", "unresolved", "unresolved", "unresolved"]);
    expect(result[0].target_ids).toHaveLength(2);
  });
  it("never substitutes a same-numbered note from another group", () => {
    const targets = sourceNotes().targets.filter(t => t.address.group === "I");
    expect(linkDipnotes([cell("(1)", "V-II")], targets)[0].status).toBe("unresolved");
  });
  it("keeps TOMK's contradictory printed P&L continuation group unresolved", () => {
    const { targets } = sourceNotes();
    // Page 42 prints IV; page 43 prints III (continued), while the P&L's
    // dipnot header is V-IV. A plausible title is not permission to repair it.
    expect(targets.some(t => t.address.group === "III" && t.address.item === "4" && t.page_start === 43)).toBe(true);
    expect(linkDipnotes([cell("(4)", "V-IV")], targets)[0]).toMatchObject({ status: "unresolved", target_ids: [] });
  });
  it("does not resolve a note whose end has not been read", () => {
    const { targets } = sourceNotes();
    expect(linkDipnotes([cell("(1)")], targets.map(t => ({ ...t, boundary: "open" as const })))[0].status).toBe("unresolved");
  });
  it("requires bold source text outside ruled tables for envelope recovery", () => {
    const page = structuredClone(fixture.pages.find((p: { source: { page: number } }) => p.source.page === 38));
    expect(printedNoteHeadings(page.structure, page.source).has("p38:narrative7")).toBe(true);
    for (const span of page.source.spans) span.flags = 0;
    expect(printedNoteHeadings(page.structure, page.source).has("p38:narrative7")).toBe(false);
  });
  it("a continuation banner does not truncate an open note", () => {
    const seed = sourceNotes().passages.find(p => p.section?.role === "notes")!;
    const p = (id: string, text: string, kind = "heading", page = 38): ProsePassage => ({
      ...seed, id, element_id: id, text, raw_text: text, kind: kind as ProsePassage["kind"], page, table_ids: [], heading_marker: null,
    });
    const rows = [p("group", "I. Assets"), p("one", "1. Banks"), p("body", "First page", "paragraph"),
      p("continued", "I. Assets (Continued)", "heading", 39), p("more", "Second page", "paragraph", 39), p("two", "2. Investments", "heading", 39)];
    const first = indexDipnotes(rows).find(n => n.address.item === "1")!;
    expect(first.passage_ids).toEqual(["one", "body", "continued", "more"]);
    expect(first.page_end).toBe(39);
    expect(first.boundary).toBe("next_heading");
  });
});
