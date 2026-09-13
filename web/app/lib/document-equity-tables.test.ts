import { readFileSync } from "node:fs";
import { gunzipSync } from "node:zlib";
import { describe, expect, it, vi } from "vitest";
import { SourceTablesBuilder } from "./document-source-tables";

vi.mock("@opennextjs/cloudflare", () => ({ getCloudflareContext: vi.fn() }));
const equity = JSON.parse(gunzipSync(readFileSync(new URL("../../../tests/fixtures/document_equity_table_garan.json.gz", import.meta.url))).toString("utf8"));
const notes = JSON.parse(readFileSync(new URL("../../../tests/fixtures/document_dipnotes_garan.json", import.meta.url), "utf8"));
function build() {
  const builder = new SourceTablesBuilder(notes.revision, notes.sections);
  builder.addPage(equity.structure, equity.source, []);
  for (const p of [...equity.related, ...notes.pages]) builder.addPage(p.structure, p.source, []);
  return builder.finish();
}

describe("wide equity source grid through the admin reader", () => {
  it("preserves every column, both periods, OCI group spans and native ellipsis", () => {
    const result = build(), table = result.tables.find(t => t.id === "p20:equityframe0")!;
    expect(table.column_count).toBe(18);
    expect(table.rows).toHaveLength(41);
    expect(table.candidate_lanes).toEqual(["equity_change"]);
    expect(table.verification).toMatchObject({ native_cells: "checked", table_boundaries: "not_verified", issues: [] });
    expect(table.merged_spans).toContainEqual({ row: 1, column: 6, row_span: 1, column_span: 3 });
    expect(table.merged_spans).toContainEqual({ row: 1, column: 9, row_span: 1, column_span: 3 });
    expect(table.rows[4].cells[0].text).toBe("(01/01/2021-31/12/2021)");
    expect(table.rows[23].cells[0].text).toBe("(01/01/2022-31/12/2022)");
    expect(table.rows[21].cells[0].text).toBe("Balances at end of the period (III+IV+…+X+XI)");
    expect(table.rows[40].cells[17].text).toBe("153,124,120");
    expect(result.verification.report_complete).toBe(false);
  });
  it("links both 5.5 references to the full equity dipnote and its child passages", () => {
    const result = build(), table = result.tables.find(t => t.id === "p20:equityframe0")!;
    expect(table.dipnote_links).toHaveLength(2);
    for (const row of [9, 28]) {
      const link = table.dipnote_links.find(l => l.row === row)!;
      expect(link).toMatchObject({ marker: "5.5", column: 1, status: "resolved" });
      const target = result.notes.find(n => n.id === link.target_ids[0])!;
      expect(target.page_start).toBe(174);
      expect(target.page_end).toBe(174);
      expect(target.passage_ids.length).toBeGreaterThan(10);
    }
  });
});
