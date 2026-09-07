import { readFileSync } from "node:fs";
import { describe, expect, it, vi } from "vitest";
import { getReviewedTables } from "./document-table-review";
import { parseCorpusRevision, type CorpusBucket } from "./document-corpus";

vi.mock("@opennextjs/cloudflare", () => ({ getCloudflareContext: vi.fn() }));
const fixture = JSON.parse(readFileSync(new URL("../../../tests/fixtures/document_table_review_wire.json", import.meta.url), "utf8"));
const filing = fixture.index.filing;
const revision = parseCorpusRevision(fixture.index, filing)!;
const bucketFor = (index: unknown, missing = "", data = fixture, sourceRevision = revision) => ({ get: vi.fn(async (key: string) => {
  if (key === missing) return null;
  const body = key === sourceRevision.evidence_key ? data.source_gzip : key === sourceRevision.structure_current?.key ? data.structure_gzip : null;
  if (!body) return { size: 100, uploaded: new Date(0), json: async () => index };
  const bytes = Buffer.from(body, "base64");
  return { size: bytes.length, uploaded: new Date(0), body: new ReadableStream<Uint8Array>({ start(c) { c.enqueue(bytes); c.close(); } }) };
}) }) as unknown as CorpusBucket;

describe("source-checked reviewed table views", () => {
  it("reads the Python-produced four-page transcription and keeps physical cells", async () => {
    const bucket = bucketFor(fixture.index);
    const tables = (await Promise.all([26, 27, 28, 29].map(page => getReviewedTables(bucket, filing, revision, page)))).flat();
    expect(tables).toHaveLength(4);
    expect(tables.reduce((n, t) => n + t.rows.length, 0)).toBe(107);
    expect(tables[0].rows[0].cells.map(c => c.text)).toEqual(["ÇEKİRDEK SERMAYE", "Cari Dönem\n30 Eylül 2023", "Önceki Dönem\n31 Aralık 2022"]);
    expect(tables[0].physical_table.rows[0].cells[1].text).toBeNull();
    expect(tables[0].merged_spans).toEqual([]);
    expect(tables[2].rows[9].cells[0].text?.replace(/\s+/g, " ")).toContain("ve finansal kuruluşların");
    expect(tables[2].rows[9].cells[1].text).toBe("-");
    expect(tables[2].physical_table.rows[9].cells[1].text).toBe("l\n-");
    expect(tables[3].rows[0].cells[1].text).toBe("");
    expect(tables[3].source_context.at(-1)?.text).toContain("fark bulunmamaktadır");
    expect(tables.every(t => t.financial_series_interpretation === "not_performed")).toBe(true);
  });
  it("returns no review for an unreviewed page or historical receipt", async () => {
    expect(await getReviewedTables(bucketFor(fixture.index), filing, revision, 1)).toEqual([]);
    const index = structuredClone(fixture.index); delete index.resume_receipt;
    expect(await getReviewedTables(bucketFor(index), filing, revision, 26)).toEqual([]);
  });
  it("retains Garanti's reviewed nonrectangular tables, blank labels and merged slots", async () => {
    const data = JSON.parse(readFileSync(new URL("../../../tests/fixtures/document_table_review_garan_wire.json", import.meta.url), "utf8"));
    const r = parseCorpusRevision(data.index, data.index.filing)!;
    const bucket = bucketFor(data.index, "", data, r);
    const tables = (await Promise.all([117, 179, 181].map(page => getReviewedTables(bucket, data.index.filing, r, page)))).flat();
    expect(tables).toHaveLength(6);
    const branches = tables.find(t => t.review_id === "parent_bank_branches_complete_grid")!;
    expect(branches.rows[7].cells[0].text).toBe("");
    expect(branches.absent_slots).toContainEqual({ row: 0, column: 4 });
    expect(branches.merged_spans).toContainEqual({ row: 1, column: 3, row_span: 2, column_span: 1 });
  });
  it.each(["pdf", "native", "structure", "receipt", "status", "scope", "duplicate", "native_hash", "structure_hash", "figure", "period", "null", "merge", "missing_row", "unit", "ending", "missing_native", "missing_structure", "logical_digit", "word_loss", "word_duplicate", "word_order", "wrong_column", "wrong_row", "different_occurrence", "logical_review", "logical_duplicate"])("rejects changed %s evidence", async mutation => {
    const index = structuredClone(fixture.index), receipt = index.resume_receipt, check = receipt.benchmark.checks[0];
    const entry = check.reviewed_tables.find((r: { page: number }) => r.page === 26);
    let page = 26, missing = "";
    if (mutation === "pdf") index.current.source.pdf_sha256 = "0".repeat(64);
    if (mutation === "native") receipt.evidence_artifact_sha256 = "0".repeat(64);
    if (mutation === "structure") receipt.structure_artifact_sha256 = "0".repeat(64);
    if (mutation === "receipt") receipt.schema_version = "other";
    if (mutation === "status") receipt.benchmark.status = "failed";
    if (mutation === "scope") entry.scope = "whole_report";
    if (mutation === "duplicate") check.reviewed_tables.push(structuredClone(entry));
    if (mutation === "native_hash") entry.native_page_sha256 = "0".repeat(64);
    if (mutation === "structure_hash") entry.structure_page_sha256 = "0".repeat(64);
    if (mutation === "figure") entry.physical_rows[1][1] = "1.500.001";
    if (mutation === "period") entry.physical_rows[0][0] = entry.physical_rows[0][0].replace("2022", "2021");
    if (mutation === "null") entry.physical_rows[0][1] = "";
    if (mutation === "merge") entry.merged_spans[0].column_span = 2;
    if (mutation === "missing_row") entry.physical_rows.pop();
    if (mutation === "unit") entry.source_context[0].text = "Million TL";
    if (mutation === "ending") { page = 29; check.reviewed_tables.find((r: { page: number }) => r.page === 29).source_context[1].text = "Fark bulunmaktadır."; }
    if (mutation === "missing_native") missing = revision.evidence_key;
    if (mutation === "missing_structure") missing = revision.structure_current!.key;
    const logical = entry.logical_rows[0];
    if (mutation === "logical_digit") logical.cells[1].text = "Cari Dönem 30 Eylül 2022";
    if (mutation === "word_loss") logical.cells[1].source_word_ids.pop();
    if (mutation === "word_duplicate") logical.cells[1].source_word_ids.push(logical.cells[1].source_word_ids[0]);
    if (mutation === "word_order") logical.cells[1].source_word_ids.reverse();
    if (mutation === "wrong_column") [logical.cells[1], logical.cells[2]] = [logical.cells[2], logical.cells[1]];
    if (mutation === "wrong_row") logical.row = 1;
    if (mutation === "different_occurrence") logical.cells[1].source_word_ids[0] = 0;
    if (mutation === "logical_review") logical.source_review = "";
    if (mutation === "logical_duplicate") entry.logical_rows.push(structuredClone(logical));
    await expect(getReviewedTables(bucketFor(index, missing), filing, revision, page)).rejects.toThrow();
  });
});
