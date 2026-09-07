import { readFileSync } from "node:fs";
import { gzipSync } from "node:zlib";
import { describe, expect, it, vi } from "vitest";
import { ProseBuilder, readDocumentProse } from "./document-prose";
import type { CorpusBucket, CorpusRevision } from "./document-corpus";

vi.mock("@opennextjs/cloudflare", () => ({ getCloudflareContext: vi.fn() }));

const cases = JSON.parse(readFileSync(new URL("../../../tests/fixtures/document_prose_source_cases.json", import.meta.url), "utf8"));
const revision: CorpusRevision = { source: { bank_ticker: "TEST", period: "2026Q1", kind: "consolidated", pdf_sha256: "a".repeat(64) },
  page_count: 2, evidence_key: "source", original_key: "original", structure_current: { key: "structure.jsonl.gz", artifact_sha256: "b".repeat(64) } };
const sections = [{ number: 4, title: "Risk disclosures", role: "risk", page_start: 1, page_end: 2 }];

function page(number: number, texts: [string, string][]) {
  const spans = texts.map(([text], i) => ({ id: i, text, block: i, line: 0, bbox: [40, 100 + i * 20, 400, 110 + i * 20] as [number, number, number, number] }));
  const source = { page: number, height: 800, spans };
  const structure = { page: number, tables: [{ id: "table" }], narrative_elements: texts.map(([text, kind], i) => ({
    id: `p${number}:n${i}`, text, kind, span_ids: [i], source_lines: [[i, 0] as [number, number]], bbox: spans[i].bbox,
    table_ids: [] as string[], heading_path: [] as { id: string; text: string }[],
  })), reading_layout: { element_order: texts.map((_, i) => `p${number}:n${i}`), issues: [] } };
  return { source, structure };
}

describe("structured audit prose", () => {
  it("retains all 14 independently reviewed Turkish passages, negations, figures, spans and immediate headings", () => {
    const c = cases[0], builder = new ProseBuilder(c.revision, c.sections);
    for (const p of c.pages) builder.addPage(p.structure, p.source);
    expect(c.expected).toHaveLength(14);
    for (const gold of c.expected) {
      const found = builder.report.passages.filter(p => p.page === gold.page && p.raw_text === gold.raw_text);
      expect(found, gold.raw_text).toHaveLength(1);
      expect(found[0].source_span_ids).toEqual(gold.source_span_ids);
      expect(["paragraph", "table_note"]).toContain(found[0].kind);
      for (const h of gold.heading_path) expect(found[0].heading_path.map(h => h.text)).toContain(h.text);
    }
    expect(builder.report.passages.some(p => p.text === "Bulunmamaktadır.")).toBe(true);
    expect(builder.report.verification.semantic_verification).toBe("not_performed");
  });
  it("preserves English report paragraphs without translating or assigning uncertain language", () => {
    const c = cases[1], builder = new ProseBuilder(c.revision, c.sections);
    for (const p of c.pages) builder.addPage(p.structure, p.source);
    const found = builder.report.passages.find(p => p.text.startsWith("The Bank operates in corporate"))!;
    expect(found.language).toBe("en");
    expect(found.heading_path.at(-1)?.text).toBe("Segment reporting");
    expect(found.section?.role).toBe("accounting_policies");
  });
  it.each(["negation", "figure", "drop", "duplicate", "source-lines", "bbox", "heading", "table"])("rejects damaged %s even in a checksummed structured artifact", mutation => {
    const c = structuredClone(cases[0]), p = c.pages[0];
    const elements = p.structure.narrative_elements;
    const paragraph = elements.find((e: { text: string }) => e.text.includes("93,47"));
    if (mutation === "negation") paragraph.text += " NOT";
    if (mutation === "figure") paragraph.text = paragraph.text.replace("93,47", "93,74");
    if (mutation === "drop") elements.splice(elements.indexOf(paragraph), 1);
    if (mutation === "duplicate") elements.push(paragraph);
    if (mutation === "source-lines") paragraph.source_lines = [[999, 0]];
    if (mutation === "bbox") paragraph.bbox[0] += 1;
    if (mutation === "heading") paragraph.heading_path[0].text = "Different heading";
    if (mutation === "table") paragraph.table_ids = ["other"];
    expect(() => new ProseBuilder(c.revision, c.sections).addPage(p.structure, p.source)).toThrow();
  });
  it("carries explicit numbered headings, links possible continuation, and replaces sibling headings", () => {
    const builder = new ProseBuilder(revision, sections);
    const p1 = page(1, [["IV. Risk management", "heading_candidate"], ["The bank is exposed to", "paragraph_candidate"]]);
    const p2 = page(2, [["the following risks.", "paragraph_candidate"], ["V. Other risks", "heading_candidate"], ["None.", "paragraph_candidate"]]);
    builder.addPage(p1.structure, p1.source); builder.addPage(p2.structure, p2.source);
    const p = builder.report.passages;
    expect(p[2].heading_path.map(h => h.text)).toEqual(["IV. Risk management"]);
    expect(p[2].continuation_from).toBe(p[1].id);
    expect(p[2].heading_scope).toBe("document_candidate");
    expect(p[4].heading_path.map(h => h.text)).toEqual(["V. Other risks"]);
    expect(p[1].raw_text).toBe("The bank is exposed to"); // never silently concatenate
  });
  it("does not carry cover typography, section changes, or a complete sentence into the next paragraph", () => {
    const builder = new ProseBuilder(revision, [{ ...sections[0], page_start: 2 }]);
    const p1 = page(1, [["Cover title", "heading_candidate"], ["The cover is complete.", "paragraph_candidate"]]);
    const p2 = page(2, [["the audit opinion begins here.", "paragraph_candidate"]]);
    builder.addPage(p1.structure, p1.source); builder.addPage(p2.structure, p2.source);
    expect(builder.report.passages[2].heading_path).toEqual([]);
    expect(builder.report.passages[2].continuation_from).toBeNull();
  });
  it("retains every original line when old captures lack paragraphs, and reports unreadable pages", () => {
    const builder = new ProseBuilder(revision, []);
    const p = page(1, [["No paragraph structure.", "paragraph_candidate"]]);
    const legacy = { page: 1, tables: p.structure.tables };
    builder.addPage(legacy, p.source);
    const blank = page(2, []); builder.addPage(blank.structure, blank.source);
    expect(builder.report.passages[0].kind).toBe("unclassified");
    expect(builder.report.pages_without_native_text).toEqual([2]);
    expect(builder.report.pages_with_issues[0].issues).toContain("paragraph_structure_unavailable");
  });
  it("rejects invalid layout as an ordering guide while retaining all original passages", () => {
    const builder = new ProseBuilder(revision, sections);
    const p = page(1, [["First.", "paragraph_candidate"], ["Second.", "paragraph_candidate"]]);
    p.structure.reading_layout.element_order = ["p1:n0", "p1:n0"];
    builder.addPage(p.structure, p.source);
    expect(builder.report.passages.map(p => p.text)).toEqual(["First.", "Second."]);
    expect(builder.report.pages_with_issues[0].issues).toContain("reading_layout_unavailable");
  });
  it("retains sourced table-note associations and fails a false note reference", () => {
    const p = page(1, [["1.", "list_item_candidate"], ["This is not deducted.", "paragraph_candidate"]]);
    const structure = { ...p.structure, table_notes: { tables: [{ table_id: "table", links: [{ marker_element_id: "p1:n0",
      text_element_id: "p1:n1", text: "This is not deducted.", column: 2, label: "1" }] }] } };
    const builder = new ProseBuilder(revision, sections); builder.addPage(structure, p.source);
    expect(builder.report.passages[1]).toMatchObject({ kind: "table_note", note_links: [{ table_id: "table", column: 2, marker: "1" }] });
    structure.table_notes.tables[0].links[0].text = "This is deducted.";
    expect(() => new ProseBuilder(revision, sections).addPage(structure, p.source)).toThrow("note");
  });
});

async function wire(kind: "source" | "structure", pages: object[], source = revision.source) {
  const lines = pages.map(p => JSON.stringify({ ...p, type: kind === "source" ? "source_page" : "structured_page" }));
  const page_sha256 = await Promise.all(lines.map(async line => Buffer.from(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(line))).toString("hex")));
  return gzipSync([JSON.stringify({ type: `${kind}_manifest`, source, page_count: 2, page_sha256, sections }), ...lines, ""].join("\n"));
}
describe("complete report source verification", () => {
  it.each(["valid", "missing-page", "wrong-filing", "trailing", "altered-text"])("streams and verifies %s", async mutation => {
    const ps = [page(1, [["The figure is not 1,000.", "paragraph_candidate"]]), page(2, [["Bulunmamaktadır.", "paragraph_candidate"]])];
    const source = await wire("source", ps.map(p => p.source), mutation === "wrong-filing" ? { ...revision.source, bank_ticker: "OTHER" } : revision.source);
    if (mutation === "altered-text") ps[1].structure.narrative_elements[0].text = "New wording.";
    let structure = await wire("structure", (mutation === "missing-page" ? ps.slice(0, 1) : ps).map(p => p.structure));
    if (mutation === "trailing") {
      const { gunzipSync } = await import("node:zlib");
      structure = gzipSync(gunzipSync(structure).toString("utf8") + "extra");
    }
    const bucket = { get: async (key: string) => ({ body: new ReadableStream({ start(c) { c.enqueue(key === "source" ? source : structure); c.close(); } }) }) } as unknown as CorpusBucket;
    if (mutation === "valid") {
      const report = await readDocumentProse(bucket, revision);
      expect(report.verification.source_spans_checked).toBe(2);
      expect(report.passages.map(p => p.raw_text)).toEqual(["The figure is not 1,000.", "Bulunmamaktadır."]);
    } else await expect(readDocumentProse(bucket, revision)).rejects.toThrow();
  });
});
