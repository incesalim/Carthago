import { readFileSync } from "node:fs";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { ReviewedTableList } from "../admin/DocumentReviewedTables";
import { getReviewedTables } from "./document-table-review";
import { parseCorpusRevision, type CorpusBucket } from "./document-corpus";

vi.mock("@opennextjs/cloudflare", () => ({ getCloudflareContext: vi.fn() }));
const fixture = JSON.parse(readFileSync(new URL("../../../tests/fixtures/document_table_review_balance_wire.json", import.meta.url), "utf8"));
const filing = fixture.index.filing;
const revision = parseCorpusRevision(fixture.index, filing)!;
const bucketFor = (index: unknown) => ({ get: vi.fn(async (key: string) => {
  const data = key === revision.evidence_key ? fixture.source_gzip : key === revision.structure_current?.key ? fixture.structure_gzip : null;
  if (!data) return { size: 100, uploaded: new Date(0), json: async () => index };
  const bytes = Buffer.from(data, "base64");
  return { size: bytes.length, uploaded: new Date(0), body: new ReadableStream<Uint8Array>({ start(c) { c.enqueue(bytes); c.close(); } }) };
}) }) as unknown as CorpusBucket;

describe("independently reviewed balance-sheet grids", () => {
  it("serves all 163 rows, separated period currencies and the original physical tables", async () => {
    const tables = (await Promise.all([10, 11, 12].map(page => getReviewedTables(bucketFor(fixture.index), filing, revision, page)))).flat();
    expect(tables.map(t => t.rows.length)).toEqual([50, 44, 69]);
    expect(tables.map(t => t.physical_table.n_cols)).toEqual([8, 8, 4]);
    expect(tables.every(t => t.physical_table.row_count === 5 && !t.absent_slots.length)).toBe(true);
    for (const table of tables) {
      const record = fixture.index.resume_receipt.benchmark.checks[0].reviewed_tables.find((t: { page: number }) => t.page === table.page);
      const actual = table.rows.map(r => r.cells.map(c => c.text === null ? null : c.text.replace(/\s+/g, " ").trim()));
      expect(actual).toEqual(record.reviewed_grid.rows.map((r: { text: string | null }[]) => r.map(c => c.text)));
      expect(actual[2]).toEqual([null, null, "TP", "YP", "Toplam", "TP", "YP", "Toplam"]);
      expect(table.merged_spans).toEqual(record.reviewed_grid.spans);
      const occurrences = table.rows.flatMap(r => r.cells.flatMap(c => c.source_fragments.flatMap(p =>
        Array.from({ length: p.end - p.start }, (_, i) => `${p.word_id}:${p.start + i}`))));
      expect(new Set(occurrences).size).toBe(occurrences.length);
      const html = renderToStaticMarkup(createElement(ReviewedTableList, { tables: [table], filing: "TOMK|2023Q3|unconsolidated", page: table.page }));
      expect(html.match(/<tr(?:\s|>)/g)).toHaveLength(table.rows.length);
      expect(html.match(/<td(?:\s|>)/g)).toHaveLength(table.rows.length * 8 - 13);
      expect(html).toContain('colSpan="3"');
      expect(html).toContain(`${table.rows.length} rows · 8 columns`);
      expect(html).toContain("31 Aralık 2022");
      expect(html).toContain("artifact=table-reviews");
    }
    expect(tables[1].rows.at(-2)?.cells.map(c => c.text)).toEqual([
      "14.6.2 Dönem Net Kâr veya Zararı", "", "148.071", "-", "148.071", "(1.870)", "-", "(1.870)",
    ]);
    expect(tables[2].rows.at(-1)?.cells.slice(2).map(c => c.text)).toEqual(["900.145", "12.028", "912.173", "-", "-", "-"]);
    expect(tables[2].source_context.at(-1)?.text.endsWith("parçasıdır")).toBe(true);
    const third = tables[0].rows.findIndex(r => r.cells[0].text?.startsWith("III."));
    expect(tables[0].rows.slice(third, third + 2).map(r => r.cells.slice(2).map(c => c.text))).toEqual([Array(6).fill("-"), Array(6).fill("-")]);
  });

  it.each(["digit", "date", "currency", "dash_zero", "empty_zero", "covered_blank", "word_loss", "word_duplicate", "occurrence_swap", "column_swap", "row_swap", "word_order", "missing_wording", "word_bool", "edge_removal", "edge_outside", "edge_reversed", "edge_nan", "edge_bool", "span_overlap", "span_duplicate", "span_outside", "span_at_covered", "missing_review", "mixed_view", "empty_source_row"])("rejects %s before serving any reviewed grid", async mutation => {
    for (const page of [10, 11, 12]) {
      const index = structuredClone(fixture.index);
      const entry = index.resume_receipt.benchmark.checks[0].reviewed_tables.find((t: { page: number }) => t.page === page);
      const grid = entry.reviewed_grid, rows = grid.rows;
      if (mutation === "digit") rows.at(-1)[2].text += "0";
      if (mutation === "date") rows[1][5].text = rows[1][5].text.replace("2022", "2023");
      if (mutation === "currency") rows[2][3].text = "TP";
      if (mutation === "dash_zero") rows.slice(3).flat().find((c: { text: string | null }) => c.text === "-").text = "0";
      if (mutation === "empty_zero") rows[3][1].text = "0";
      if (mutation === "covered_blank") rows[0][1].text = "";
      if (mutation === "word_loss") rows[3][0].source_word_ids.pop();
      if (mutation === "word_duplicate") rows[3][0].source_word_ids.push(rows[3][0].source_word_ids[0]);
      if (mutation === "occurrence_swap") {
        const dashes = rows.slice(3).flat().filter((c: { text: string | null }) => c.text === "-");
        [dashes[0].source_word_ids, dashes[1].source_word_ids] = [dashes[1].source_word_ids, dashes[0].source_word_ids];
      }
      if (mutation === "column_swap") [rows.at(-1)[2], rows.at(-1)[3]] = [rows.at(-1)[3], rows.at(-1)[2]];
      if (mutation === "row_swap") [rows[3], rows[4]] = [rows[4], rows[3]];
      if (mutation === "word_order") rows[0][0].source_word_ids.reverse();
      if (mutation === "missing_wording") delete rows[3][1].text;
      if (mutation === "word_bool") rows[3][0].source_word_ids[0] = true;
      if (mutation === "edge_removal") grid.y_edges[3] += 1;
      if (mutation === "edge_outside") grid.x_edges[grid.x_edges.length - 1] += 1;
      if (mutation === "edge_reversed") [grid.x_edges[1], grid.x_edges[2]] = [grid.x_edges[2], grid.x_edges[1]];
      if (mutation === "edge_nan") grid.x_edges[3] = Number.NaN;
      if (mutation === "edge_bool") grid.x_edges[3] = true;
      if (mutation === "span_overlap") grid.spans[1].column_span = 2;
      if (mutation === "span_duplicate") grid.spans.push(structuredClone(grid.spans[0]));
      if (mutation === "span_outside") grid.spans[0].column_span = 9;
      if (mutation === "span_at_covered") grid.spans.push({ row: 0, column: 1, row_span: 1, column_span: 2 });
      if (mutation === "missing_review") grid.source_review = " ";
      if (mutation === "mixed_view") entry.logical_rows = [{ row: 3 }];
      if (mutation === "empty_source_row") rows[3] = Array.from({ length: 8 }, () => ({ text: "", source_word_ids: [] }));
      await expect(getReviewedTables(bucketFor(index), filing, revision, page)).rejects.toThrow();
    }
  });
});
