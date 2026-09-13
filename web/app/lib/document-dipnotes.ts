/** Source-addressed links between table cells and notes in the same filing. */
import type { ProsePassage } from "./document-prose";

// An empty item addresses the whole printed group, e.g. the cash-flow note 5.6.
export type NoteAddress = { section: number; group: string; item: string };
export type NoteTarget = { id: string; address: NoteAddress; heading: string;
  page_start: number; page_end: number; passage_ids: string[]; table_ids: string[];
  boundary: "open" | "next_heading" | "section_end" | "report_end" };
export type NoteCell = { table_id: string; row: number; column: number; text: string;
  source_word_ids: number[]; is_note_column: boolean; note_prefix: string | null };
export type DipnoteLink = Omit<NoteCell, "text" | "is_note_column" | "note_prefix"> & {
  marker: string; address: NoteAddress | null; status: "resolved" | "unresolved" | "ambiguous";
  target_ids: string[]; method: "printed_section_group_and_note_address";
};

const roman: Record<string, number> = { I: 1, II: 2, III: 3, IV: 4, V: 5, VI: 6, VII: 7, VIII: 8 };
const compact = (s: string) => s.normalize("NFKC").replace(/[–—]/gu, "-").replace(/\s+/gu, "").toUpperCase();
const addressKey = (a: NoteAddress) => `${a.section}.${a.group}.${a.item}`;
const sectionNumber = (s: string) => /^[1-8]$/.test(s) ? Number(s) : roman[s];

/** A bare number gets its address ONLY from the table's printed note header. */
export function parseNoteAddress(marker: string, prefix: string | null): NoteAddress | null {
  const text = compact(marker).replace(/^\(/u, "").replace(/\)$/u, "");
  const context = prefix && /([1-8]|VIII|VII|VI|IV|V|III|II|I)[.-]([IVX]+|[1-9]\d?)\)?$/u.exec(compact(prefix));
  const qualified = /^([1-8])\.([1-9]\d?)(?:\.(\d+(?:\.\d+)*[A-Z]?))?$/u.exec(text);
  if (qualified && !context) return { section: Number(qualified[1]), group: qualified[2], item: qualified[3] ?? "" };
  const full = /^([1-8]|VIII|VII|VI|IV|V|III|II|I)[.-]([IVX]+)[.-](\d+(?:\.\d+)*[A-Z]?)$/u.exec(text);
  if (full && sectionNumber(full[1])) return { section: sectionNumber(full[1]), group: full[2], item: full[3] };
  if (!context || !sectionNumber(context[1])) return null;
  if (/^\d+(?:\.\d+)*[A-Z]?$/u.test(text)) return { section: sectionNumber(context[1]), group: context[2], item: text };
  const grouped = /^([IVX]+)[.-](\d+(?:\.\d+)*[A-Z]?)$/u.exec(text);
  return grouped ? { section: sectionNumber(context[1]), group: grouped[1], item: grouped[2] } : null;
}

function headingMarker(passage: ProsePassage, printedHeadings: Set<string>): string | null {
  if (!printedHeadings.has(passage.element_id) && (passage.kind !== "heading" || passage.table_ids.length)) return null;
  const text = passage.heading_marker?.text ?? passage.text;
  return /^\s*([IVX]+|\d+(?:\.\d+)*)(?:[.)]|\s|$)/u.exec(text)?.[1] ?? null;
}

/** Notes are source intervals, including embedded tables and continuation pages.
 * Repeated addresses stay ambiguous; no first-match or title similarity fallback.
 */
export function indexDipnotes(passages: ProsePassage[], printedHeadings = new Set<string>(), endOfReport = false): NoteTarget[] {
  const targets: NoteTarget[] = [];
  let section: number | null = null, group: string | null = null;
  let numbering: "roman" | "qualified" | null = null;
  const active: { target: NoteTarget; depth: number }[] = [];
  const byId = new Map(passages.map(p => [p.id, p]));
  const prefixes = new Set(passages.flatMap(p => p.heading_marker ? [p.heading_marker.element_id] : []));
  const close = (boundary: NoteTarget["boundary"], minimumDepth = 0) => {
    while (active.length && active.at(-1)!.depth >= minimumDepth) active.pop()!.target.boundary = boundary;
  };
  for (const passage of passages) {
    if (passage.section?.number !== section || passage.section?.role !== "notes") {
      close("section_end");
      group = null;
      numbering = null;
      section = passage.section?.number ?? null;
    }
    if (passage.section?.role !== "notes" || section === null) continue;
    if (prefixes.has(passage.id)) continue;
    const marker = headingMarker(passage, printedHeadings);
    if (marker && /^[IVX]+$/u.test(marker)) {
      if (marker === group && /devam[ıi]|continued/iu.test(passage.text)) continue;
      close("next_heading");
      group = marker;
      numbering = "roman";
    } else if (marker && /^\d/u.test(marker)) {
      const qualified = numbering !== "roman" && marker.startsWith(`${section}.`) ? parseNoteAddress(marker, null) : null;
      if (qualified) {
        if (qualified.group === group && !qualified.item && /continued|devam[ıi]/iu.test(passage.text)) continue;
        if (group !== qualified.group) close("next_heading");
        group = qualified.group;
        numbering = "qualified";
      }
      if (!group || numbering === "qualified" && !qualified) continue;
      const address = qualified ?? { section, group, item: marker };
      const depth = address.item ? address.item.split(".").length : 0;
      close("next_heading", depth);
      const prefix = passage.heading_marker && byId.get(passage.heading_marker.element_id);
      const target: NoteTarget = { id: `${passage.id}:dipnot`, address,
        heading: passage.text, page_start: prefix?.page ?? passage.page, page_end: passage.page,
        passage_ids: prefix ? [prefix.id] : [], table_ids: [], boundary: "open" };
      targets.push(target);
      active.push({ target, depth });
    }
    if (passage.kind === "furniture") continue;
    for (const { target } of active) {
      const prefix = passage.heading_marker && byId.get(passage.heading_marker.element_id);
      if (prefix && !target.passage_ids.includes(prefix.id)) target.passage_ids.push(prefix.id);
      if (!target.passage_ids.includes(passage.id)) target.passage_ids.push(passage.id);
      target.page_end = passage.page;
      for (const id of passage.table_ids) if (!target.table_ids.includes(id)) target.table_ids.push(id);
    }
  }
  if (endOfReport) close("report_end");
  return targets;
}

/** Recover explicitly bold numbered headings obscured by a legacy table envelope.
 * Printed ruled cells cannot supply these headings. Source spans remain intact.
 */
export function printedNoteHeadings(page: { tables: { method?: string; bbox?: number[] }[];
  narrative_elements?: { id: string; text: string; span_ids: (string | number)[] }[] },
source: { spans: { id: string | number; text: string; flags?: number; bbox: number[] }[] }): Set<string> {
  const ruled = page.tables.filter(t => t.method === "pymupdf_lines_strict" && t.bbox).map(t => t.bbox!);
  if (!ruled.length) return new Set();
  const spans = new Map(source.spans.map(s => [s.id, s]));
  return new Set((page.narrative_elements ?? []).filter(e => {
    if (!/^\s*(?:[IVX]+|\d{1,3}(?:\.\d{1,3})*)\.\s+\p{L}/u.test(e.text)) return false;
    const parts = e.span_ids.map(id => spans.get(id));
    if (parts.some(s => !s)) return false;
    const text = parts.filter(s => s!.text.trim()).map(s => s!);
    return text.length > 0 && text.every(s => (s.flags ?? 0) & 16)
      && text.every(s => ruled.every(b => s.bbox[2] <= b[0] || s.bbox[0] >= b[2]
        || s.bbox[3] <= b[1] || s.bbox[1] >= b[3]));
  }).map(e => e.id));
}

/** Parenthesised amounts are never treated as simple notes outside a note column. */
export function linkDipnotes(cells: NoteCell[], targets: NoteTarget[]): DipnoteLink[] {
  const indexed = new Map<string, NoteTarget[]>();
  for (const target of targets) {
    const key = addressKey(target.address);
    indexed.set(key, [...(indexed.get(key) ?? []), target]);
  }
  const links: DipnoteLink[] = [];
  for (const cell of cells) {
    const full = /\(\s*(?:[1-8]|VIII|VII|VI|IV|V|III|II|I)\s*[.-]\s*(?:[IVX]+|[1-9]\d?)\s*[.-]\s*\d+(?:\.\d+)*[a-z]?\s*\)/giu;
    // Keep unsupported reference spellings in a dedicated note column visible
    // as unresolved, including stars, lists and lettered subclauses.
    const dedicated = /\([^()]+\)|(?<![\d.(])[1-8]\.[1-9]\d?(?:\.\d+(?:\.\d+)*[a-z]?)?(?![\d.])/giu;
    const markers = [...cell.text.matchAll(cell.is_note_column ? dedicated : full)].map(m => m[0]);
    if (cell.is_note_column && !markers.length) markers.push(...cell.text.split(/\r?\n/u).map(s => s.trim()).filter(s => /^\d+[a-z]?$/iu.test(s)));
    for (const marker of markers) {
      const address = parseNoteAddress(marker, cell.note_prefix);
      const found = address ? indexed.get(addressKey(address)) ?? [] : [];
      const target_ids = found.map(t => t.id);
      links.push({ table_id: cell.table_id, row: cell.row, column: cell.column,
        source_word_ids: cell.source_word_ids, marker, address, target_ids,
        status: found.length > 1 ? "ambiguous" : found.length === 1 && found[0].boundary !== "open" ? "resolved" : "unresolved",
        method: "printed_section_group_and_note_address" });
    }
  }
  return links;
}
