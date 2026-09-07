import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ReviewedTableList } from "./DocumentReviewedTables";
import type { ReviewedTable } from "@/app/lib/document-table-review";

const table: ReviewedTable = {
  review_id: "review", table_id: "p1:ruled0", page: 1, source_review: "Named source review",
  native_page_sha256: "a".repeat(64), structure_page_sha256: "b".repeat(64),
  scope: "named_table_transcription", financial_series_interpretation: "not_performed",
  rows: [["Reviewed title", null, null], ["finansal", "-", "0"], ["Blank", "", null]].map((texts, row) => ({
    row, reviewed_assignment: row === 1, cells: texts.map((text, column) => ({ column, text,
      source_fragments: text ? [{ word_id: 12 + row, start: 0, end: text.length, text, bbox: [0, 0, 10, 10] }] : [] })),
  })),
  merged_spans: [{ row: 0, column: 0, row_span: 1, column_span: 3 }], absent_slots: [{ row: 2, column: 2 }],
  source_context: [{ bbox: [0, 0, 10, 10], text: "Thousands of TL; ratios in %." }],
  physical_table: { id: "p1:ruled0", n_cols: 3, row_count: 3, bbox: [0, 0, 30, 30], rows: [] },
};

describe("reviewed table display", () => {
  it("keeps approved assignments, provenance, merged cells and every form of missingness distinct", () => {
    const html = renderToStaticMarkup(<ReviewedTableList tables={[table]} filing="TEST|2026Q1|consolidated" page={1} />);
    for (const text of ["finansal", ">-</td>", ">0</td>", "[empty source cell]", "[no physical cell]", "colSpan=\"3\"",
      "source word 13", "artifact=table-reviews", "page=1", "Thousands of TL; ratios in %.", "original physical cells remain"]) expect(html).toContain(text);
    expect(html.match(/\[no physical cell\]/g)).toHaveLength(1);
    expect(html).toContain("Financial interpretation and review of the complete report remain separate");
  });
  it("states the scope of an absent review", () => {
    const html = renderToStaticMarkup(<ReviewedTableList tables={[]} filing="TEST|2026Q1|consolidated" page={1} />);
    expect(html).toContain("No complete-table review is registered for this page");
    expect(html).not.toContain("Download reviewed tables");
  });
});
