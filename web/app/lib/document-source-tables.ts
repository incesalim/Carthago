/** Complete physical table evidence and source-addressed dipnotes, without changing series. */
import { CORPUS_PREFIX, readVerifiedPages, type CorpusBucket, type CorpusRevision } from "./document-corpus";
import { ProseBuilder, type ProsePassage, type ProseSection } from "./document-prose";
import { indexDipnotes, isDisclosureSectionBanner, linkDipnotes, printedNoteHeadings, type DipnoteLink, type NoteCell, type NoteTarget } from "./document-dipnotes";
import { checkedReviewedTable, tableReviewRecords, validateGrid, type Box, type Part, type PhysicalTable, type ReviewedTable, type Span } from "./document-table-review";

export type SourceCell = { column: number; text: string | null;
  state: "absent" | "blank" | "dash" | "zero" | "text"; source_fragments: Part[] };
export type SourceTable = {
  id: string; page: number; bbox: Box; method: string; section: ProseSection | null;
  rows: { row: number; cells: SourceCell[] }[]; column_count: number;
  merged_spans: Span[]; absent_slots: { row: number; column: number }[];
  context_passage_ids: string[]; page_unit_passage_ids: string[]; page_context_passage_ids: string[]; candidate_lanes: string[];
  verification: { native_cells: "checked" | "rejected"; row_assignments: "named_source_review" | "physical_only";
    table_boundaries: "named_source_review" | "not_verified"; issues: string[]; review: string | null };
  dipnote_links: DipnoteLink[];
  disclosure_ids: string[];
  unresolved_source?: unknown;
};
export type SourceTables = {
  schema_version: "audit-source-tables-1"; source: CorpusRevision["source"]; structure_sha256: string;
  page_count: number; sections: ProseSection[]; tables: SourceTable[];
  notes: NoteTarget[]; passages: ProsePassage[];
  verification: { report_complete: false; financial_interpretation: "not_performed";
    pages_read: number; source_spans_checked: number; pages_without_native_text: number[] };
};
type SourcePage = Parameters<ProseBuilder["addPage"]>[1] & { words: { id: number; text: string; bbox: Box }[] };
type StructurePage = Parameters<ProseBuilder["addPage"]>[0] & { tables: (PhysicalTable & { method: string })[];
  table_context?: { tables: { table_id: string; physical_grid?: { anchors: Span[] } | null }[] } };
const record = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);
const validBox = (v: unknown): v is Box => Array.isArray(v) && v.length === 4 && v.every(Number.isFinite) && v[0] < v[2] && v[1] < v[3];
const key = (r: number, c: number) => `${r}:${c}`;
const literal = (s: string) => Array.from(s);
const compact = (s: string) => s.normalize("NFKC").replace(/\s/gu, "");
const inside = (a: Box, b: Box) => (a[0] + a[2]) / 2 >= b[0] - .1 && (a[0] + a[2]) / 2 <= b[2] + .1
  && (a[1] + a[3]) / 2 >= b[1] - .1 && (a[1] + a[3]) / 2 <= b[3] + .1;
const cellState = (text: string | null): SourceCell["state"] => text === null ? "absent" : !text.trim() ? "blank"
  : /^[-−–—]$/u.test(text.trim()) ? "dash" : /^0(?:[.,]0+)?$/u.test(text.trim()) ? "zero" : "text";
function fail(reason: string): never { throw new Error(reason); }

/** Check source text, characters, cell membership and grid topology independently.
 * A failed physical candidate remains inspectable, with an explicit rejection.
 */
function physicalView(table: PhysicalTable, page: StructurePage, source: SourcePage) {
  const issues: string[] = [], words = new Map(source.words.map(w => [w.id, w]));
  if (!validBox(table.bbox) || !Number.isSafeInteger(table.row_count) || table.row_count < 1 || table.row_count > 2000
      || !Number.isSafeInteger(table.n_cols) || table.n_cols < 1 || table.n_cols > 100
      || !Array.isArray(table.rows) || table.rows.length !== table.row_count) fail("Invalid physical table dimensions");
  const anchors = page.table_context?.tables.find(t => t.table_id === table.id)?.physical_grid?.anchors ?? [];
  const spans = anchors.filter(s => s.row_span * s.column_span > 1), covered = new Set<string>();
  for (const s of spans) {
    if (![s.row, s.column, s.row_span, s.column_span].every(Number.isSafeInteger) || s.row < 0 || s.column < 0
        || s.row_span < 1 || s.column_span < 1 || s.row + s.row_span > table.row_count || s.column + s.column_span > table.n_cols) fail("Invalid physical table span");
    for (let r = s.row; r < s.row + s.row_span; r++) for (let c = s.column; c < s.column + s.column_span; c++) if (r !== s.row || c !== s.column) covered.add(key(r, c));
  }
  const absent: { row: number; column: number }[] = [], used = new Set<string>();
  const rows = table.rows.map((row, r) => {
    if (row.index !== r || !Array.isArray(row.cells) || row.cells.length !== table.n_cols) fail("Invalid physical row inventory");
    return { row: r, cells: row.cells.map((cell, c): SourceCell => {
      if (cell.column !== c || !(cell.text === null || typeof cell.text === "string") || !Array.isArray(cell.word_ids)) fail("Invalid physical cell");
      if (cell.bbox === null && !covered.has(key(r, c))) absent.push({ row: r, column: c });
      const parts = cell.source_fragments ?? cell.word_ids.flatMap(id => {
        const w = words.get(id); return w ? [{ word_id: id, start: 0, end: literal(w.text).length, text: w.text, bbox: w.bbox }] : [];
      });
      if (cell.word_ids.some(id => !words.has(id)) || new Set(cell.word_ids).size !== cell.word_ids.length
          || !Array.isArray(parts) || (cell.bbox === null && (parts.length || cell.text !== null))) issues.push("invalid_cell_source");
      if (compact(parts.map(p => p.text).join("")) !== compact(cell.text ?? "")) issues.push("cell_text_differs_from_source");
      if (JSON.stringify([...new Set(parts.map(p => p.word_id))].sort((a, b) => a - b)) !== JSON.stringify([...cell.word_ids].sort((a, b) => a - b))) issues.push("cell_word_inventory_differs");
      for (const part of parts) {
        const word = words.get(part.word_id);
        if (!word || !Number.isSafeInteger(part.start) || !Number.isSafeInteger(part.end) || part.start < 0 || part.end <= part.start
            || part.end > literal(word.text).length || literal(word.text).slice(part.start, part.end).join("") !== part.text
            || !validBox(part.bbox) || !validBox(cell.bbox) || !inside(part.bbox, cell.bbox) || !inside(part.bbox, word.bbox)) {
          issues.push("source_fragment_differs"); continue;
        }
        for (let i = part.start; i < part.end; i++) {
          const k = key(part.word_id, i); if (used.has(k)) issues.push("duplicated_source_character"); used.add(k);
        }
      }
      return { column: c, text: cell.text, state: cellState(cell.text), source_fragments: parts };
    }) };
  });
  const expected = new Set(source.words.filter(w => inside(w.bbox, table.bbox)).flatMap(w => literal(w.text).map((_, i) => key(w.id, i))));
  if (expected.size !== used.size || [...expected].some(k => !used.has(k))) issues.push("table_character_inventory_differs");
  try { validateGrid(table, spans, absent); } catch { issues.push("physical_grid_not_verified"); }
  return { rows, spans, absent, issues: [...new Set(issues)] };
}

/** Page/heading association is a candidate, never proof that a lane is complete. */
export function tableLaneCandidates(section: ProseSection | null, heading: string): string[] {
  const text = heading.normalize("NFD").replace(/\p{M}/gu, "").replace(/ı/gu, "i").toLocaleLowerCase("en");
  const lanes: [string, RegExp][] = section?.role === "financial_statements" ? [
    ["balance_sheet_assets", /(?:bilanco|balance sheet)[\s\S]*(?:aktif|varlik|assets)/u],
    ["balance_sheet_liabilities", /(?:bilanco|balance sheet)[\s\S]*(?:pasif|yukumluluk|liabilities)/u],
    ["off_balance", /bilanco disi|nazim hesap|off.balance/u], ["profit_loss", /gelir tablosu|kar veya zarar tablosu|income statement|profit or loss/u],
    ["other_comprehensive_income", /diger kapsamli|other comprehensive/u], ["equity_change", /ozkaynak.*degisim|changes in (?:shareholders['’]? )?equity/u], ["cash_flow", /nakit akis|statement of cash flows?|cash flow statement/u],
  ] : [
    ["capital", /sermaye yeterliligi|capital adequacy|(?:consolidated |regulatory |total )capital|ozkaynaklar/u], ["liquidity", /likidite|liquidity/u],
    ["fx_position", /kur riski|doviz pozisyon|currency risk|foreign exchange/u],
    ["repricing", /faiz orani riski|kar payi orani riski|interest rate risk/u], ["credit_quality", /kredi kalitesi|credit quality|kredi riski|credit risk/u],
    ["loans_by_sector", /sektor.*dagilim|sector.*distribution/u], ["npl_movement", /takipteki.*alacak|non.performing/u],
    ["free_provision", /serbest karsilik|free provision/u], ["profile", /personel|sube sayisi|personnel|branches/u],
  ];
  const found = lanes.filter(([, pattern]) => pattern.test(text)).map(([lane]) => lane);
  if (found.includes("equity_change")) return ["equity_change"];
  if (found.includes("other_comprehensive_income")) return found.filter(l => l !== "profit_loss");
  return found.includes("off_balance") ? found.filter(l => l !== "balance_sheet_assets" && l !== "balance_sheet_liabilities") : found;
}

function noteCells(table: SourceTable): NoteCell[] {
  const headers = new Map<number, string | null>();
  const headerCells = new Set<string>();
  for (const row of table.rows.slice(0, 6)) for (const cell of row.cells) {
    if (/\b(?:dipnot|(?:foot)?notes?)\b/iu.test(cell.text ?? "") && (cell.text?.length ?? 0) < 120) {
      headers.set(cell.column, /\(?\s*(?:[1-8]|[IVX]+)\s*[.\-–]\s*(?:[IVX]+|[1-9]\d?)\s*\)?/u.exec(cell.text ?? "")?.[0] ?? null);
      headerCells.add(key(row.row, cell.column));
    }
  }
  return table.rows.flatMap(row => row.cells.filter(cell => !headerCells.has(key(row.row, cell.column))).map(cell => ({ table_id: table.id, row: row.row, column: cell.column,
    text: cell.text ?? "", source_word_ids: [...new Set(cell.source_fragments.map(p => p.word_id))],
    is_note_column: headers.has(cell.column), note_prefix: headers.get(cell.column) ?? null })));
}

export class SourceTablesBuilder {
  readonly prose: ProseBuilder;
  readonly tables: SourceTable[] = [];
  private headings = new Set<string>();
  private pages = new Set<number>();
  private cellChars = 0;
  constructor(readonly revision: CorpusRevision, sections: unknown) { this.prose = new ProseBuilder(revision, sections); }
  addPage(page: StructurePage, source: SourcePage, reviews: ReviewedTable[] = []) {
    if (this.pages.has(page.page) || page.page !== source.page || !Array.isArray(source.words)
        || source.words.some(w => !Number.isSafeInteger(w.id) || typeof w.text !== "string" || !validBox(w.bbox))
        || new Set(source.words.map(w => w.id)).size !== source.words.length) fail("Invalid table source inventory");
    this.pages.add(page.page);
    this.prose.addPage(page, source);
    for (const id of printedNoteHeadings(page, source)) this.headings.add(id);
    const passages = this.prose.report.passages.filter(p => p.page === page.page);
    const section = this.prose.report.sections.find(s => s.page_start <= page.page && s.page_end >= page.page) ?? null;
    for (const physical of page.tables) {
      const reviewed = reviews.find(t => t.table_id === physical.id);
      const unresolved = !reviewed && physical.method === "legacy_numeric_geometry";
      const view = reviewed ? null : unresolved ? { rows: [], spans: [], absent: [], issues: ["unresolved_column_assignment"] } : physicalView(physical, page, source);
      const rows = reviewed ? reviewed.rows.map(row => ({ row: row.row, cells: row.cells.map(c => ({ ...c, state: cellState(c.text) })) })) : view!.rows;
      const context = passages.filter(p => p.bbox[3] <= physical.bbox[1] && physical.bbox[1] - p.bbox[3] < 160 && p.kind !== "furniture" && !p.table_ids.length);
      const units = passages.filter(p => (p.kind === "furniture" || p.bbox[3] <= physical.bbox[1])
        && /bin\s+(?:Türk\s+Lirası|TL)|thousands?\s+(?:of\s+)?(?:Turkish\s+Lira|TL)/iu.test(p.text));
      const pageContext = passages.filter(p => (p.kind === "furniture" || isDisclosureSectionBanner(p))
        && p.bbox[3] <= physical.bbox[1] + .1 && !p.table_ids.length);
      // Titles may be merged cells. Only the first rows and source text ABOVE the
      // table nominate lanes; incidental words in its body cannot do so.
      const heading = [...context.map(p => p.text), ...rows.slice(0, 3).flatMap(r => r.cells.map(c => c.text ?? "").filter(s => s.length < 300 && s.split("\n").length <= 5))].join("\n");
      this.cellChars += rows.reduce((n, r) => n + r.cells.reduce((m, c) => m + (c.text?.length ?? 0), 0), 0);
      if (this.cellChars > 8_000_000 || this.tables.length >= 5000) fail("Report exceeds table reading limit");
      this.tables.push({ id: physical.id, page: page.page, bbox: physical.bbox, method: physical.method, section,
        rows, column_count: rows[0]?.cells.length ?? physical.n_cols, merged_spans: reviewed?.merged_spans ?? view!.spans,
        absent_slots: reviewed?.absent_slots ?? view!.absent, context_passage_ids: context.map(p => p.id), page_unit_passage_ids: units.map(p => p.id),
        page_context_passage_ids: pageContext.map(p => p.id), candidate_lanes: tableLaneCandidates(section, heading),
        verification: { native_cells: reviewed || !view!.issues.length ? "checked" : "rejected",
          row_assignments: reviewed ? "named_source_review" : "physical_only", table_boundaries: reviewed ? "named_source_review" : "not_verified",
          issues: view?.issues ?? [], review: reviewed?.source_review ?? null }, dipnote_links: [], disclosure_ids: [],
        ...(unresolved ? { unresolved_source: physical } : {}) });
    }
  }
  finish(): SourceTables {
    const full = this.pages.size === this.revision.page_count && Array.from({ length: this.revision.page_count }, (_, i) => i + 1).every(p => this.pages.has(p));
    const notes = indexDipnotes(this.prose.report.passages, this.headings, full);
    for (const table of this.tables) {
      table.dipnote_links = table.verification.native_cells === "checked" ? linkDipnotes(noteCells(table), notes) : [];
      const containing = notes.filter(n => n.table_ids.includes(table.id));
      // Choose the most specific printed interval for each fragment. Parent
      // headings still nominate its family, but cannot glue child tables into
      // a single grid or imply a financial interpretation.
      table.disclosure_ids = containing.filter(n => !containing.some(child => child !== n
        && child.address.section === n.address.section && child.address.group === n.address.group
        && (n.address.item === "" ? child.address.item !== "" : child.address.item.startsWith(`${n.address.item}.`))
        && child.passage_ids.every(id => n.passage_ids.includes(id)))).map(n => n.id);
      table.candidate_lanes = [...new Set([...table.candidate_lanes,
        ...tableLaneCandidates(table.section, containing.map(n => n.heading).join("\n"))])];
    }
    return { schema_version: "audit-source-tables-1", source: this.revision.source, structure_sha256: this.prose.report.structure_sha256,
      page_count: this.revision.page_count, sections: this.prose.report.sections, tables: this.tables, notes, passages: this.prose.report.passages,
      verification: { report_complete: false, financial_interpretation: "not_performed", pages_read: this.pages.size,
        source_spans_checked: this.prose.report.verification.source_spans_checked, pages_without_native_text: this.prose.report.pages_without_native_text } };
  }
}

export async function readSourceTables(bucket: CorpusBucket, revision: CorpusRevision): Promise<SourceTables> {
  if (!revision.structure_current?.key.endsWith(".jsonl.gz") || revision.page_count > 1000) fail("Tables need a current bounded structured capture");
  const filing = revision.source;
  const [index, source, structure] = await Promise.all([
    bucket.get(`${CORPUS_PREFIX}filings/${filing.bank_ticker}/${filing.period}/${filing.kind}.json`),
    bucket.get(revision.evidence_key), bucket.get(revision.structure_current.key),
  ]);
  if (!index || index.size > 8_000_000 || !source || !structure) fail("Table source artifacts are missing");
  const reviews = tableReviewRecords(await index.json(), { bank_ticker: filing.bank_ticker, period: filing.period, kind: filing.kind }, revision);
  const native = readVerifiedPages(source.body, filing.pdf_sha256, revision.page_count, "source");
  const structured = readVerifiedPages(structure.body, filing.pdf_sha256, revision.page_count, "structure");
  let builder: SourceTablesBuilder | null = null, chars = 0;
  try {
    while (true) {
      const [s, p] = await Promise.all([native.next(), structured.next()]);
      if (s.done || p.done) { if (s.done !== p.done) fail("Table page inventory differs"); break; }
      for (const manifest of [s.value.manifest, p.value.manifest]) {
        if (!record(manifest.source) || ["bank_ticker", "period", "kind"].some(k => (manifest.source as Record<string, unknown>)[k] !== filing[k as keyof typeof filing])) fail("Table manifest filing differs");
      }
      builder ??= new SourceTablesBuilder(revision, p.value.manifest.sections);
      const page = Number(p.value.page.page), start = builder.prose.report.passages.length;
      const checked = reviews.filter(r => r.page === page).map(r => checkedReviewedTable(r, s.value.page, p.value.page,
        (s.value.manifest.page_sha256 as string[])[page - 1], (p.value.manifest.page_sha256 as string[])[page - 1]));
      builder.addPage(p.value.page as unknown as StructurePage, s.value.page as unknown as SourcePage, checked);
      chars += builder.prose.report.passages.slice(start).reduce((n, e) => n + e.raw_text.length, 0);
      if (chars > 8_000_000 || builder.prose.report.passages.length > 60_000) fail("Report exceeds note reading limit");
    }
    if (!builder) fail("Table source is empty");
    return builder.finish();
  } finally { await Promise.allSettled([native.return(), structured.return()]); }
}
