/** Source-faithful prose over the retained corpus. No numerical facts are minted. */
import { readVerifiedPages, type CorpusBucket, type CorpusRevision } from "./document-corpus";

type Box = [number, number, number, number];
type SpanId = string | number;
type Span = { id: SpanId; text: string; block: number; line: number; bbox: Box };
type Element = { id: string; text: string; kind: string; span_ids: SpanId[];
  source_lines: [number, number][]; bbox: Box; font_size?: number;
  heading_path?: { id: string; text: string }[]; table_ids: string[]; candidate_table_ids?: string[] };
export type ProseSection = { number: number; title: string; role: string; page_start: number; page_end: number };
export type ProseHeading = { id: string; text: string; page: number; marker: string | null; marker_element_id: string | null };
export type ProsePassage = {
  id: string; element_id: string; order: number; source_order: number; page: number;
  kind: "heading" | "heading_marker" | "paragraph" | "list_item" | "table_note" | "table_text" | "mixed_text" | "furniture" | "unclassified";
  raw_text: string; text: string; source_span_ids: SpanId[]; source_lines: [number, number][]; bbox: Box;
  section: ProseSection | null; heading_path: ProseHeading[]; heading_scope: "page" | "document_candidate";
  heading_marker: { element_id: string; text: string } | null;
  table_ids: string[]; candidate_table_ids: string[]; note_links: { table_id: string; column: number; marker: string }[];
  continuation_from: string | null; language: "tr" | "en" | "und";
  issues: string[];
};
export type StructuredProse = {
  schema_version: "audit-prose-1"; source: CorpusRevision["source"]; structure_sha256: string;
  page_count: number; sections: ProseSection[]; passages: ProsePassage[];
  verification: { source_spans_checked: number; source_text_verified: true; semantic_verification: "not_performed";
    paragraph_boundaries_verified: false; heading_relationships_verified: false };
  pages_without_native_text: number[]; pages_with_issues: { page: number; issues: string[] }[];
};
type SourcePage = { page: number; spans: Span[]; height: number; images?: unknown[]; replacement_character_count?: number };
type StructurePage = { page: number; narrative_elements?: Element[]; tables: { id: string }[];
  reading_layout?: { element_order?: string[]; issues?: { kind: string }[] };
  table_notes?: { tables: { table_id: string; links: { marker_element_id: string; text_element_id: string;
    text: string; column: number; label: string }[] }[] } };

const compact = (text: string) => text.replace(/\s+/gu, " ").trim();
const fold = (text: string) => compact(text).replaceAll("ı", "i").replaceAll("İ", "I")
  .normalize("NFD").replace(/\p{M}/gu, "").toUpperCase();
const bounds = (spans: Span[]): Box => [Math.min(...spans.map(s => s.bbox[0])), Math.min(...spans.map(s => s.bbox[1])),
  Math.max(...spans.map(s => s.bbox[2])), Math.max(...spans.map(s => s.bbox[3]))];
const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);
const record = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);
const box = (v: unknown): v is Box => Array.isArray(v) && v.length === 4 && v.every(Number.isFinite);

function sourceLines(source: SourcePage) {
  const lines = new Map<string, Span[]>();
  const ids = new Set<SpanId>();
  for (const s of source.spans) {
    if (!record(s) || typeof s.text !== "string" || !box(s.bbox) || !Number.isInteger(s.block)
        || !Number.isInteger(s.line) || !(typeof s.id === "string" || Number.isSafeInteger(s.id)) || ids.has(s.id)) {
      throw new Error("Invalid or duplicate source span");
    }
    ids.add(s.id);
    const key = JSON.stringify([s.block, s.line]);
    lines.set(key, [...(lines.get(key) ?? []), s]);
  }
  return new Map([...lines].filter(([, spans]) => spans.some(s => s.text.trim())));
}

/** Independently reconstruct EVERY passage from native spans, not from its checksum alone. */
function checkedElements(page: StructurePage, source: SourcePage): { elements: Element[]; spans: number; fallback: boolean } {
  const lines = sourceLines(source);
  const fallback = !Array.isArray(page.narrative_elements);
  // Older captures still expose all wording. Physical lines are explicitly unclassified.
  const elements: Element[] = fallback ? [...lines].map(([key, spans], i) => ({
    id: `p${page.page}:source-line${i}`, kind: "unclassified", text: spans.map(s => s.text).join(""),
    span_ids: spans.map(s => s.id), source_lines: [JSON.parse(key)], bbox: bounds(spans), table_ids: [],
  })) : page.narrative_elements!;
  const ids = new Set<string>(), actual: SpanId[] = [];
  const tables = new Set(page.tables.map(t => t.id));
  for (const e of elements) {
    if (!record(e) || typeof e.id !== "string" || ids.has(e.id) || typeof e.text !== "string"
        || !Array.isArray(e.source_lines) || !e.source_lines.length || !Array.isArray(e.span_ids)
        || !box(e.bbox) || !Array.isArray(e.table_ids) || typeof e.kind !== "string") throw new Error("Invalid prose element");
    ids.add(e.id);
    const groups = e.source_lines.map(key => lines.get(JSON.stringify(key)));
    if (groups.some(group => !group)) throw new Error("Unknown prose source line");
    const spans = (groups as Span[][]).flat();
    if (!same(e.span_ids, spans.map(s => s.id)) || !same(e.bbox, bounds(spans))
        || e.text !== groups.map(group => group!.map(s => s.text).join("")).join("\n")) {
      throw new Error("Prose differs from native source spans");
    }
    if (![...e.table_ids, ...(e.candidate_table_ids ?? [])].every(id => tables.has(id))) throw new Error("Unknown prose table reference");
    actual.push(...e.span_ids);
  }
  const expected = [...lines.values()].flat().map(s => s.id);
  if (!same(actual, expected)) throw new Error("Prose drops, duplicates or reorders source spans");
  const seen = new Map<string, Element>();
  for (const e of elements) {
    for (const h of e.heading_path ?? []) {
      const original = seen.get(h.id);
      if (!original || original.kind !== "heading_candidate" || compact(original.text) !== h.text) {
        throw new Error("Prose heading reference does not match its source");
      }
    }
    seen.set(e.id, e);
  }
  return { elements, spans: expected.length, fallback };
}

function marker(text: string): { key: string; depth: number } | null {
  const m = /^(\d+(?:\.\d+)+)[.)]?\s+\S/u.exec(compact(text))
    ?? /^([IVX]+|[a-zA-Z]|\d+)[.)]\s+\S/u.exec(compact(text));
  if (!m) return null;
  const key = m[1];
  return { key, depth: key.includes(".") ? 2 + key.split(".").length : /^[IVX]+$/.test(key) ? 1 : /^\d+$/.test(key) ? 3 : 2 };
}

/** Unique, adjacent fragments on the same printed line; keep both original elements. */
function separatedMarkers(elements: Element[], source: SourcePage) {
  const found = new Map<string, Element>();
  const spans = new Map(source.spans.map(s => [s.id, s]));
  for (const heading of elements.filter(e => e.kind === "heading_candidate" && !marker(e.text))) {
    const first = heading.span_ids.map(id => spans.get(id)!).filter(s => s.block === heading.source_lines[0][0] && s.line === heading.source_lines[0][1]);
    const b = bounds(first), height = b[3] - b[1];
    const choices = elements.filter(e => ["paragraph_candidate", "list_item_candidate"].includes(e.kind)
      && !e.table_ids.length && /^(?:\d+(?:\.\d+)*[.)]?|[IVX]+[.)]|[a-zA-Z][.)])$/.test(compact(e.text))
      && e.bbox[2] <= b[0] && b[0] - e.bbox[2] <= 4 * height
      && Math.abs(e.bbox[1] - b[1]) <= .2 * height && Math.abs(e.bbox[3] - b[3]) <= .2 * height);
    if (choices.length === 1) found.set(heading.id, choices[0]);
  }
  const uses = new Map<string, number>();
  for (const e of found.values()) uses.set(e.id, (uses.get(e.id) ?? 0) + 1);
  return new Map([...found].filter(([, e]) => uses.get(e.id) === 1));
}
function language(text: string): ProsePassage["language"] {
  const words = ` ${fold(text)} `;
  const tr = (words.match(/\b(VE|ILE|ILISKIN|BANKA|OLARAK|TARIH|BULUNMAMAKTADIR|DONEM|ACIKLAMALAR)\b/g) ?? []).length;
  const en = (words.match(/\b(THE|AND|WITH|OF|FOR|BANK|IS|ARE|NOT|DISCLOSURES)\b/g) ?? []).length;
  return tr > en ? "tr" : en > tr ? "en" : "und";
}
const kinds: Record<string, ProsePassage["kind"]> = { heading_candidate: "heading", paragraph_candidate: "paragraph",
  list_item_candidate: "list_item", table_text: "table_text", mixed_text: "mixed_text",
  running_header_candidate: "furniture", running_footer_candidate: "furniture", page_number_candidate: "furniture" };

export class ProseBuilder {
  readonly report: StructuredProse;
  private headings: { heading: ProseHeading; depth: number }[] = [];
  private sectionNumber: number | null = null;
  private previousPageLast: ProsePassage | null = null;
  constructor(revision: CorpusRevision, sections: unknown) {
    if (!Array.isArray(sections) || sections.some(s => !record(s) || !Number.isInteger(s.number)
        || typeof s.title !== "string" || typeof s.role !== "string" || !Number.isInteger(s.page_start)
        || !Number.isInteger(s.page_end) || (s.page_start as number) < 1 || (s.page_end as number) > revision.page_count
        || (s.page_start as number) > (s.page_end as number))) throw new Error("Invalid prose sections");
    this.report = { schema_version: "audit-prose-1", source: revision.source, structure_sha256: revision.structure_current!.artifact_sha256,
      page_count: revision.page_count, sections: sections as ProseSection[], passages: [],
      verification: { source_spans_checked: 0, source_text_verified: true, semantic_verification: "not_performed",
        paragraph_boundaries_verified: false, heading_relationships_verified: false },
      pages_without_native_text: [], pages_with_issues: [] };
  }
  addPage(page: StructurePage, source: SourcePage) {
    if (page.page !== source.page || !Array.isArray(source.spans) || !Array.isArray(page.tables)) throw new Error("Invalid prose page");
    const checked = checkedElements(page, source);
    this.report.verification.source_spans_checked += checked.spans;
    const issues: string[] = [];
    if (checked.fallback) issues.push("paragraph_structure_unavailable");
    if (!checked.spans) { this.report.pages_without_native_text.push(page.page); issues.push("no_native_text"); }
    if (source.replacement_character_count) issues.push("source_replacement_characters");
    const sections = this.report.sections.filter(s => s.page_start <= page.page && page.page <= s.page_end);
    const section = sections.length === 1 ? sections[0] : null;
    if (sections.length > 1) issues.push("overlapping_section_candidates");
    if (section?.number !== this.sectionNumber || !section) this.headings = [];
    this.sectionNumber = section?.number ?? null;
    const elements = new Map(checked.elements.map(e => [e.id, e]));
    const storedOrder = checked.elements.map(e => e.id);
    const order = page.reading_layout?.element_order;
    const validOrder = order && order.length === elements.size && new Set(order).size === elements.size && order.every(id => elements.has(id));
    if (!validOrder) issues.push("reading_layout_unavailable");
    issues.push(...(page.reading_layout?.issues ?? []).map(i => i.kind));
    const prefixes = separatedMarkers(checked.elements, source);
    const prefixIds = new Set([...prefixes.values()].map(e => e.id));
    const numberOf = (e: Element) => marker(e.text) ?? (prefixes.has(e.id)
      ? marker(`${compact(prefixes.get(e.id)!.text).replace(/[.)]$/, "")}. ${e.text}`) : null);
    const reference = (e: Element): ProseHeading => ({ id: this.id(e.id), text: compact(e.text), page: page.page,
      marker: numberOf(e)?.key ?? null, marker_element_id: prefixes.has(e.id) ? this.id(prefixes.get(e.id)!.id) : null });
    const noteLinks = new Map<string, ProsePassage["note_links"]>();
    for (const table of page.table_notes?.tables ?? []) {
      if (!page.tables.some(t => t.id === table.table_id)) throw new Error("Unknown prose note table");
      for (const link of table.links) {
        if (!elements.has(link.marker_element_id) || elements.get(link.text_element_id)?.text !== link.text) {
          throw new Error("Table note does not match source prose");
        }
        for (const id of [link.marker_element_id, link.text_element_id]) noteLinks.set(id,
          [...(noteLinks.get(id) ?? []), { table_id: table.table_id, column: link.column, marker: link.label }]);
      }
    }
    let pageLast: ProsePassage | null = null;
    let firstBody = true;
    for (const id of validOrder ? order : storedOrder) {
      const e = elements.get(id)!;
      const kind = noteLinks.has(id) ? "table_note" : prefixIds.has(id) ? "heading_marker" : kinds[e.kind] ?? "unclassified";
      const text = compact(e.text);
      let headingPath = (e.heading_path ?? []).map(h => reference(elements.get(h.id)!));
      let headingScope: ProsePassage["heading_scope"] = "page";
      const numbered = kind === "heading" ? numberOf(e) : null;
      const divider = section && fold(text).replace(/\s*\((DEVAMI|CONTINUED)\)\s*$/, "") === fold(section.title);
      if (numbered && section) {
        if (numbered.key.startsWith(`${section.number}.`)) this.headings = this.headings.filter(h =>
          h.heading.marker && numbered.key.startsWith(`${h.heading.marker}.`));
        while (this.headings.length && this.headings.at(-1)!.depth >= numbered.depth) this.headings.pop();
        headingPath = this.headings.map(h => h.heading);
        headingScope = headingPath.some(h => h.page < page.page) ? "document_candidate" : "page";
        this.headings.push({ heading: reference(e), depth: numbered.depth });
      } else if (["paragraph", "list_item", "table_note", "mixed_text"].includes(kind)) {
        const leaf = headingPath.at(-1);
        const numberedLeaf = leaf && this.headings.findIndex(h => h.heading.id === leaf.id);
        if (typeof numberedLeaf === "number" && numberedLeaf >= 0) headingPath = this.headings.slice(0, numberedLeaf + 1).map(h => h.heading);
        else if (!leaf && this.headings.length) {
          headingPath = this.headings.map(h => h.heading);
          headingScope = "document_candidate";
        }
      } else if (kind === "heading" && !divider) {
        // An unnumbered new topic without an explicit numbered parent ends carry-over.
        if (!headingPath.some(h => this.headings.some(n => n.heading.id === h.id))) this.headings = [];
      }
      if (headingPath.some(h => h.page < page.page)) headingScope = "document_candidate";
      const passage: ProsePassage = { id: this.id(id), element_id: id, order: this.report.passages.length + 1,
        source_order: storedOrder.indexOf(id) + 1, page: page.page, kind, raw_text: e.text, text,
        source_span_ids: e.span_ids, source_lines: e.source_lines, bbox: e.bbox, section, heading_path: headingPath,
        heading_scope: headingScope, table_ids: e.table_ids, candidate_table_ids: e.candidate_table_ids ?? [],
        heading_marker: prefixes.has(id) ? { element_id: this.id(prefixes.get(id)!.id), text: compact(prefixes.get(id)!.text) } : null,
        note_links: noteLinks.get(id) ?? [], continuation_from: null, language: language(text), issues: [] };
      if (kind === "mixed_text") passage.issues.push("prose_and_table_overlap");
      if (e.candidate_table_ids?.length) passage.issues.push("candidate_table_overlap");
      if (headingScope === "document_candidate") passage.issues.push("cross_page_heading_candidate");
      if (!["furniture", "heading", "heading_marker"].includes(kind)) {
        const previous = this.previousPageLast;
        if (firstBody && kind === "paragraph" && previous?.kind === "paragraph" && previous.page === page.page - 1
            && section && previous.section?.number === section.number && headingPath.length > 0
            && same(headingPath.map(h => h.id), previous.heading_path.map(h => h.id))
            && !/[.!?:;][”’"')\]]*$/u.test(previous.text) && /^\p{Ll}/u.test(text)
            && Math.abs(previous.bbox[0] - passage.bbox[0]) < 12) {
          passage.continuation_from = previous.id;
          passage.issues.push("paragraph_continuation_candidate");
        }
        firstBody = false;
        pageLast = passage;
      }
      this.report.passages.push(passage);
    }
    this.previousPageLast = pageLast;
    if (issues.length) this.report.pages_with_issues.push({ page: page.page, issues: [...new Set(issues)] });
  }
  private id(element: string) { return `${this.report.source.pdf_sha256}:${element}`; }
}

/** An analyst can consume this exact contract; private admin export uses the same reader. */
export async function readDocumentProse(bucket: CorpusBucket, revision: CorpusRevision): Promise<StructuredProse> {
  if (!revision.structure_current?.key.endsWith(".jsonl.gz")) throw new Error("Prose needs a current structured capture");
  if (revision.page_count > 1000) throw new Error("Report exceeds prose reading limit");
  const [source, structure] = await Promise.all([bucket.get(revision.evidence_key), bucket.get(revision.structure_current.key)]);
  if (!source || !structure) throw new Error("Prose source artifacts are missing");
  const native = readVerifiedPages(source.body, revision.source.pdf_sha256, revision.page_count, "source");
  const structured = readVerifiedPages(structure.body, revision.source.pdf_sha256, revision.page_count, "structure");
  let builder: ProseBuilder | null = null, chars = 0;
  try {
    while (true) {
      const [s, p] = await Promise.all([native.next(), structured.next()]);
      if (s.done || p.done) { if (s.done !== p.done) throw new Error("Prose page inventory differs"); break; }
      for (const manifest of [s.value.manifest, p.value.manifest]) {
        if (!record(manifest.source) || ["bank_ticker", "period", "kind"].some(k => manifest.source &&
            (manifest.source as Record<string, unknown>)[k] !== revision.source[k as keyof typeof revision.source])) {
          throw new Error("Prose manifest filing differs");
        }
      }
      builder ??= new ProseBuilder(revision, p.value.manifest.sections);
      const start = builder.report.passages.length;
      builder.addPage(p.value.page as unknown as StructurePage, s.value.page as unknown as SourcePage);
      chars += builder.report.passages.slice(start).reduce((n, e) => n + e.raw_text.length, 0);
      if (chars > 8_000_000 || builder.report.passages.length > 60_000) throw new Error("Report exceeds prose reading limit");
    }
    if (!builder) throw new Error("Prose source is empty");
    return builder.report;
  } finally {
    await Promise.allSettled([native.return(), structured.return()]);
  }
}
