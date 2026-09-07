/** Reviewed transcription views rechecked against the current stored source pages. */
import { CORPUS_PREFIX, parseCorpusRevision, readVerifiedPage, type CorpusBucket, type CorpusRevision, type FilingIdentity } from "./document-corpus";

type Box = [number, number, number, number];
type Word = { id: number; text: string; bbox: Box };
type Part = { word_id: number; start: number; end: number; text: string; bbox: Box };
type Cell = { text: string | null; bbox: Box | null; column: number; word_ids: number[]; source_fragments?: Part[] };
type PhysicalTable = { id: string; n_cols: number; row_count: number; bbox: Box; rows: { index: number; cells: Cell[] }[] };
type Span = { row: number; column: number; row_span: number; column_span: number };
type LogicalRow = { row: number; source_review: string; cells: { text: string; source_word_ids: number[] }[] };
export type ReviewedTable = { review_id: string; table_id: string; page: number; source_review: string;
  native_page_sha256: string; structure_page_sha256: string;
  scope: "named_table_transcription"; financial_series_interpretation: "not_performed";
  rows: { row: number; reviewed_assignment: boolean; cells: { column: number; text: string | null; source_fragments: Part[] }[] }[];
  merged_spans: Span[]; absent_slots: { row: number; column: number }[];
  source_context: { bbox: Box; text: string }[]; physical_table: PhysicalTable };

const record = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);
const integer = (v: unknown): v is number => typeof v === "number" && Number.isSafeInteger(v) && v >= 0;
const box = (v: unknown): v is Box => Array.isArray(v) && v.length === 4 && v.every(n => typeof n === "number" && Number.isFinite(n)) && v[0] < v[2] && v[1] < v[3];
const norm = (s: string) => s.normalize("NFKC").trim().replace(/\s+/gu, " ");
const literal = (s: string) => Array.from(s);
function fail(): never { throw new Error("Reviewed table differs from its source evidence"); }
const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);
const slot = (r: number, c: number) => `${r}:${c}`;

function sourceLines(words: Word[]): Word[][] {
  const center = (w: Word) => (w.bbox[1] + w.bbox[3]) / 2;
  const height = (w: Word) => w.bbox[3] - w.bbox[1];
  const median = (values: number[]) => { values.sort((a, b) => a - b); const i = Math.floor(values.length / 2); return values.length % 2 ? values[i] : (values[i - 1] + values[i]) / 2; };
  const lines: Word[][] = [];
  for (const word of [...words].sort((a, b) => center(a) - center(b) || a.bbox[0] - b.bbox[0] || a.id - b.id)) {
    const matches = lines.filter(line => Math.abs(center(word) - median(line.map(center))) <= .3 * Math.min(height(word), ...line.map(height)));
    if (matches.length > 1) fail();
    if (matches.length) matches[0].push(word); else lines.push([word]);
  }
  for (const line of lines) line.sort((a, b) => a.bbox[0] - b.bbox[0] || a.bbox[1] - b.bbox[1] || a.id - b.id);
  if (lines.some((line, i) => i > 0 && Math.max(...lines[i - 1].map(w => w.bbox[3])) > Math.min(...line.map(w => w.bbox[1])))) fail();
  return lines;
}

function validateGrid(table: PhysicalTable, spans: Span[], absent: { row: number; column: number }[]) {
  if (!Array.isArray(spans) || !Array.isArray(absent) || !box(table.bbox)) fail();
  const spanMap = new Map<string, Span>(), holes = new Set<string>(), covered = new Set<string>();
  const edges = [new Map<number, number>(), new Map<number, number>()];
  const addEdge = (axis: number, index: number, value: number) => {
    const previous = edges[axis].get(index); if (previous !== undefined && Math.abs(previous - value) > .1) fail();
    edges[axis].set(index, value);
  };
  for (const s of spans) {
    if (!record(s) || ![s.row, s.column, s.row_span, s.column_span].every(integer) || s.row_span < 1 || s.column_span < 1 || s.row_span * s.column_span < 2 || spanMap.has(slot(s.row, s.column))) fail();
    spanMap.set(slot(s.row, s.column), s);
  }
  for (const s of absent) {
    if (!record(s) || !integer(s.row) || !integer(s.column) || s.row >= table.row_count || s.column >= table.n_cols || holes.has(slot(s.row, s.column))) fail();
    holes.add(slot(s.row, s.column));
  }
  const used = new Set<string>();
  for (const row of table.rows) for (const cell of row.cells) {
    if (cell.bbox === null) continue;
    if (!box(cell.bbox)) fail();
    const r = row.index, c = cell.column, s = spanMap.get(slot(r, c));
    const rs = s?.row_span ?? 1, cs = s?.column_span ?? 1;
    if (r + rs > table.row_count || c + cs > table.n_cols) fail();
    if (s) used.add(slot(r, c));
    for (let rr = r; rr < r + rs; rr++) for (let cc = c; cc < c + cs; cc++) {
      const key = slot(rr, cc); if (covered.has(key) || holes.has(key)) fail(); covered.add(key);
    }
    addEdge(0, c, cell.bbox[0]); addEdge(0, c + cs, cell.bbox[2]);
    addEdge(1, r, cell.bbox[1]); addEdge(1, r + rs, cell.bbox[3]);
  }
  if (used.size !== spanMap.size || covered.size + holes.size !== table.row_count * table.n_cols) fail();
  const result = edges.map((axis, n) => {
    const count = n === 0 ? table.n_cols : table.row_count;
    if (axis.size !== count + 1) fail();
    const values = Array.from({ length: count + 1 }, (_, i) => axis.get(i) ?? fail());
    if (values.some((v, i) => i > 0 && v <= values[i - 1]) || Math.abs(values[0] - table.bbox[n]) > .1 || Math.abs(values[count] - table.bbox[n + 2]) > .1) fail();
    return values;
  });
  return { x: result[0], y: result[1] };
}

function view(saved: Record<string, unknown>, source: Record<string, unknown>, structured: Record<string, unknown>): ReviewedTable {
  if (saved.schema_version !== "annotated-table-view-1" || saved.scope !== "named_table_transcription" || saved.financial_series_interpretation !== "not_performed"
      || !["review_id", "table_id", "source_review"].every(k => typeof saved[k] === "string" && saved[k].trim())
      || !Array.isArray(saved.physical_rows) || !Array.isArray(saved.logical_rows) || !Array.isArray(saved.source_context)
      || !Array.isArray(source.words) || !Array.isArray(source.spans) || !Array.isArray(structured.tables)) fail();
  const tables = structured.tables.filter(t => record(t) && t.id === saved.table_id);
  if (tables.length !== 1) fail();
  const table = tables[0] as PhysicalTable;
  if (!integer(table.row_count) || !integer(table.n_cols) || !table.row_count || !table.n_cols || !Array.isArray(table.rows)
      || table.rows.length !== table.row_count || saved.physical_rows.length !== table.row_count) fail();
  const words = new Map<number, Word>();
  for (const w of source.words) {
    if (!record(w) || !integer(w.id) || typeof w.text !== "string" || !box(w.bbox) || words.has(w.id)) fail();
    words.set(w.id, w as Word);
  }
  const partsFor = (cell: Cell): Part[] => {
    if (!Array.isArray(cell.word_ids) || new Set(cell.word_ids).size !== cell.word_ids.length) fail();
    const parts = cell.source_fragments ?? cell.word_ids.map(id => {
      const w = words.get(id) ?? fail(); return { word_id: id, start: 0, end: literal(w.text).length, text: w.text, bbox: w.bbox };
    });
    if (!Array.isArray(parts)) fail();
    for (const p of parts) {
      const w = words.get(p.word_id); if (!w || !integer(p.start) || !integer(p.end) || p.end <= p.start || p.end > literal(w.text).length
          || !cell.word_ids.includes(p.word_id) || p.text !== literal(w.text).slice(p.start, p.end).join("") || !box(p.bbox)) fail();
    }
    return parts;
  };
  const physicalRows = saved.physical_rows;
  const rows = table.rows.map((row, r) => {
    const expected = physicalRows[r] as unknown;
    if (row.index !== r || !Array.isArray(row.cells) || row.cells.length !== table.n_cols || !Array.isArray(expected) || expected.length !== table.n_cols) fail();
    return { row: r, reviewed_assignment: false, cells: row.cells.map((c, column) => {
      if (c.column !== column || (c.text !== null && typeof c.text !== "string") || (c.text === null) !== (expected[column] === null)
          || (c.text !== null && (typeof expected[column] !== "string" || norm(c.text) !== norm(expected[column])))) fail();
      const parts = partsFor(c);
      if (c.text === null && (c.bbox !== null || parts.length)) fail();
      return { column, text: c.text, source_fragments: parts };
    }) };
  });
  const spans = saved.merged_spans as Span[], absent = saved.absent_slots as { row: number; column: number }[];
  const grid = validateGrid(table, spans, absent), changed = new Set<number>();
  const inventory = (parts: Part[]) => {
    const result = new Set<string>();
    for (const p of parts) for (let i = p.start; i < p.end; i++) { const id = `${p.word_id}:${i}`; if (result.has(id)) fail(); result.add(id); }
    return [...result].sort();
  };
  for (const override of saved.logical_rows as LogicalRow[]) {
    if (!record(override) || !integer(override.row) || override.row >= rows.length || changed.has(override.row)
        || typeof override.source_review !== "string" || !override.source_review.trim() || !Array.isArray(override.cells) || override.cells.length !== table.n_cols
        || spans.some(s => s.row <= override.row && override.row < s.row + s.row_span && s.row_span !== 1)) fail();
    const r = override.row, before = inventory(rows[r].cells.flatMap(c => c.source_fragments));
    const cells = override.cells.map((c, column) => {
      if (!record(c) || typeof c.text !== "string" || !Array.isArray(c.source_word_ids) || new Set(c.source_word_ids).size !== c.source_word_ids.length) fail();
      const selected = c.source_word_ids.map(id => words.get(id) ?? fail());
      if (selected.some(w => (w.bbox[0] + w.bbox[2]) / 2 < grid.x[column] || (w.bbox[0] + w.bbox[2]) / 2 > grid.x[column + 1]
          || w.bbox[1] < grid.y[r] || w.bbox[3] > grid.y[r + 1])) fail();
      const lines = sourceLines(selected), ordered = lines.flat();
      if (!same(ordered.map(w => w.id), c.source_word_ids) || norm(ordered.map(w => w.text).join(" ")) !== norm(c.text)) fail();
      return { column, text: lines.map(line => line.map(w => w.text).join(" ")).join("\n"),
        source_fragments: ordered.map(w => ({ word_id: w.id, start: 0, end: literal(w.text).length, text: w.text, bbox: w.bbox })) };
    });
    if (!same(before, inventory(cells.flatMap(c => c.source_fragments)))) fail();
    rows[r] = { row: r, reviewed_assignment: true, cells }; changed.add(r);
  }
  for (const region of saved.source_context) {
    if (!record(region) || !box(region.bbox) || typeof region.text !== "string") fail();
    const b = region.bbox;
    const spans = source.spans.filter(s => record(s) && box(s.bbox) && b[0] <= (s.bbox[0] + s.bbox[2]) / 2 && (s.bbox[0] + s.bbox[2]) / 2 <= b[2]
      && b[1] <= (s.bbox[1] + s.bbox[3]) / 2 && (s.bbox[1] + s.bbox[3]) / 2 <= b[3]);
    if (!spans.length || norm(spans.map(s => (s as Record<string, unknown>).text).join(" ")) !== norm(region.text)) fail();
  }
  return { review_id: String(saved.review_id), table_id: table.id, page: Number(saved.page), source_review: String(saved.source_review),
    native_page_sha256: String(saved.native_page_sha256), structure_page_sha256: String(saved.structure_page_sha256),
    scope: "named_table_transcription", financial_series_interpretation: "not_performed", rows,
    merged_spans: spans.filter(s => !changed.has(s.row)), absent_slots: absent,
    source_context: saved.source_context as ReviewedTable["source_context"], physical_table: table };
}

export async function getReviewedTables(bucket: CorpusBucket, filing: FilingIdentity, revision: CorpusRevision, page: number): Promise<ReviewedTable[]> {
  if (!integer(page) || page < 1 || page > revision.page_count) fail();
  const object = await bucket.get(`${CORPUS_PREFIX}filings/${filing.bank_ticker}/${filing.period}/${filing.kind}.json`);
  if (!object || object.size > 8_000_000) fail();
  const index: unknown = await object.json(), current = parseCorpusRevision(index, filing);
  if (!current || current.source.pdf_sha256 !== revision.source.pdf_sha256 || current.evidence_key !== revision.evidence_key
      || current.structure_current?.key !== revision.structure_current?.key) fail();
  const receipt = record(index) && record(index.resume_receipt) ? index.resume_receipt : null;
  const benchmark = receipt && record(receipt.benchmark) ? receipt.benchmark : null;
  if (!benchmark) return [];
  if (!Array.isArray(benchmark.checks) || benchmark.checks.length > 100) fail();
  const records: Record<string, unknown>[] = [];
  for (const check of benchmark.checks) {
    if (!record(check)) fail();
    if (check.reviewed_tables === undefined) continue;
    if (check.passed !== true || !Array.isArray(check.reviewed_tables)) fail();
    for (const entry of check.reviewed_tables) {
      if (!record(entry) || !integer(entry.page)) fail();
      if (entry.page === page) records.push(entry);
    }
  }
  if (!records.length) return [];
  if (records.length > 100 || new Set(records.map(r => r.review_id)).size !== records.length
      || new Set(records.map(r => r.table_id)).size !== records.length || !receipt || !revision.structure_current
      || receipt.schema_version !== "corpus-receipt-1" || benchmark.status !== "passed" || benchmark.scope !== "annotated_cases_only"
      || revision.evidence_key !== `${CORPUS_PREFIX}sources/${revision.source.pdf_sha256}/${receipt.evidence_artifact_sha256}.jsonl.gz`
      || revision.structure_current.artifact_sha256 !== receipt.structure_artifact_sha256) fail();
  const read = async (key: string, kind: "source" | "structure") => {
    const object = await bucket.get(key); if (!object) fail();
    return readVerifiedPage(object.body, page, revision.source.pdf_sha256, revision.page_count, kind);
  };
  const [native, structured] = await Promise.all([read(revision.evidence_key, "source"), read(revision.structure_current.key, "structure")]);
  return records.map(r => {
    if (!Array.isArray(native.manifest.page_sha256) || !Array.isArray(structured.manifest.page_sha256)
        || native.manifest.page_sha256[page - 1] !== r.native_page_sha256 || structured.manifest.page_sha256[page - 1] !== r.structure_page_sha256) fail();
    return view(r, native.page, structured.page);
  });
}
