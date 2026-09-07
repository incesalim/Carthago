import { readFileSync } from "node:fs";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { ReviewedTableList } from "../admin/DocumentReviewedTables";
import { describe, expect, it, vi } from "vitest";
import { getReviewedTables } from "./document-table-review";
import { parseCorpusRevision, type CorpusBucket } from "./document-corpus";

vi.mock("@opennextjs/cloudflare", () => ({ getCloudflareContext: vi.fn() }));
const fixture = JSON.parse(readFileSync(new URL("../../../tests/fixtures/document_table_review_wire.json", import.meta.url), "utf8"));
const filing = fixture.index.filing;
const revision = parseCorpusRevision(fixture.index, filing)!;
const plFixture = JSON.parse(readFileSync(new URL("../../../tests/fixtures/document_table_review_pl_wire.json", import.meta.url), "utf8"));
const plRevision = parseCorpusRevision(plFixture.index, plFixture.index.filing)!;
const bucketFor = (index: unknown, missing = "", data = fixture, sourceRevision = revision) => ({ get: vi.fn(async (key: string) => {
  if (key === missing) return null;
  const body = key === sourceRevision.evidence_key ? data.source_gzip : key === sourceRevision.structure_current?.key ? data.structure_gzip : null;
  if (!body) return { size: 100, uploaded: new Date(0), json: async () => index };
  const bytes = Buffer.from(body, "base64");
  return { size: bytes.length, uploaded: new Date(0), body: new ReadableStream<Uint8Array>({ start(c) { c.enqueue(bytes); c.close(); } }) };
}) }) as unknown as CorpusBucket;

describe("source-checked reviewed table views", () => {
  it("serves and renders all 62 printed P&L rows while retaining the two physical rows", async () => {
    const tables = await getReviewedTables(bucketFor(plFixture.index, "", plFixture, plRevision), plFixture.index.filing, plRevision, 13);
    expect(tables).toHaveLength(1);
    const table = tables[0];
    expect(table.rows).toHaveLength(63);
    expect(table.physical_table.rows).toHaveLength(2);
    expect(table.rows.map(r => r.source_row)).toEqual([0, ...Array(62).fill(1)]);
    const literal = table.rows.slice(1).map(row => row.cells.map(c => c.text?.replace(/\s+/g, " ").trim()));
    const entry = plFixture.index.resume_receipt.benchmark.checks[0].reviewed_tables[0];
    expect(literal).toEqual(entry.numbered_rows[0].rows);
    expect(literal.at(-2)).toEqual(["XXIV. NET DÖNEM KARI/ZARARI (XIII+XXIII)", "(11)", "148.071", "-"]);
    expect(literal.at(-1)).toEqual(["Hisse Başına Kar/Zarar (Tam TL)", "", "0,09871", "-"]);
    const occurrences = table.rows.flatMap(r => r.cells.flatMap(c => c.source_fragments.flatMap(p =>
      Array.from({ length: p.end - p.start }, (_, i) => `${p.word_id}:${p.start + i}`))));
    expect(new Set(occurrences).size).toBe(occurrences.length);
    const html = renderToStaticMarkup(createElement(ReviewedTableList, { tables, filing: "TOMK|2023Q3|unconsolidated", page: 13 }));
    expect(html.match(/<tr(?:\s|>)/g)).toHaveLength(63);
    expect(html.match(/<td(?:\s|>)/g)).toHaveLength(252);
    for (const text of ["0,09871", "Tam TL", "148.071", "(11)", "row and column assignments", "artifact=table-reviews", "page=13"]) expect(html).toContain(text);
  });
  it.each(["figure", "note", "eps_unit", "missing_word", "duplicate_word", "different_occurrence", "wrong_column", "row_order", "missing_row", "empty_row", "merge_rows", "duplicate_split", "missing_review", "wrong_physical_row", "printed_grid"])("rejects P&L %s corruption before serving", async mutation => {
    const index = structuredClone(plFixture.index);
    const entry = index.resume_receipt.benchmark.checks[0].reviewed_tables[0];
    const split = entry.row_splits[0], rows = split.rows;
    if (mutation === "figure") rows.at(-2).cells[2].text = "148.070";
    if (mutation === "note") rows.at(-2).cells[1].text = "-11";
    if (mutation === "eps_unit") rows.at(-1).cells[0].text = "Hisse Başına Kar/Zarar (Bin TL)";
    if (mutation === "missing_word") rows[0].cells[0].source_word_ids.pop();
    if (mutation === "duplicate_word") rows[0].cells[0].source_word_ids.push(rows[0].cells[0].source_word_ids[0]);
    if (mutation === "different_occurrence") [rows[1].cells[3].source_word_ids, rows[2].cells[3].source_word_ids] = [rows[2].cells[3].source_word_ids, rows[1].cells[3].source_word_ids];
    if (mutation === "wrong_column") [rows.at(-2).cells[1], rows.at(-2).cells[2]] = [rows.at(-2).cells[2], rows.at(-2).cells[1]];
    if (mutation === "row_order") [rows[1], rows[2]] = [rows[2], rows[1]];
    if (mutation === "missing_row") rows.pop();
    if (mutation === "empty_row") rows.splice(1, 0, { cells: Array.from({ length: 4 }, () => ({ text: "", source_word_ids: [] })) });
    if (mutation === "merge_rows") {
      for (let c = 0; c < 4; c++) {
        rows[1].cells[c].text += " " + rows[2].cells[c].text;
        rows[1].cells[c].source_word_ids.push(...rows[2].cells[c].source_word_ids);
      }
      rows.splice(2, 1);
    }
    if (mutation === "duplicate_split") entry.row_splits.push(structuredClone(split));
    if (mutation === "missing_review") split.source_review = "";
    if (mutation === "wrong_physical_row") split.row = 0;
    if (mutation === "printed_grid") entry.numbered_rows[0].rows.pop();
    await expect(getReviewedTables(bucketFor(index, "", plFixture, plRevision), plFixture.index.filing, plRevision, 13)).rejects.toThrow();
  });
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
