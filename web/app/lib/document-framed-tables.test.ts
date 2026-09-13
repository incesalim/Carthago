import { readFileSync } from "node:fs";
import { gunzipSync } from "node:zlib";
import { describe, expect, it, vi } from "vitest";
import { SourceTablesBuilder } from "./document-source-tables";

vi.mock("@opennextjs/cloudflare", () => ({ getCloudflareContext: vi.fn() }));
// Python compares every generated grid/anchor to this wire fixture. These
// selected source pages are not a full-report or financial-review certificate.
const grids = JSON.parse(gunzipSync(readFileSync(new URL("../../../tests/fixtures/document_framed_tables_garan.json.gz", import.meta.url))).toString("utf8"));
const notes = JSON.parse(readFileSync(new URL("../../../tests/fixtures/document_dipnotes_garan.json", import.meta.url), "utf8"));
function build() {
  const builder = new SourceTablesBuilder(notes.revision, notes.sections);
  for (let i = 0; i < grids.pages.length; i++) builder.addPage(grids.structures[i], grids.pages[i], []);
  for (const page of notes.pages) builder.addPage(page.structure, page.source, []);
  return builder.finish();
}

describe("framed table extraction through the admin reader", () => {
  it("keeps all eight columns and merged source headers on the three primary pages", () => {
    const result = build();
    for (const page of [15, 16, 17]) {
      const table = result.tables.find(t => t.page === page && t.method === "framed_currency_headers_and_source_words")!;
      expect(table.column_count).toBe(8);
      expect(table.verification.native_cells).toBe("checked");
      expect(table.verification.table_boundaries).toBe("not_verified");
      expect(table.merged_spans.length).toBe(7);
      expect(table.rows[2].cells[2].text).toBe("31 December 2022");
      expect(table.rows[2].cells[5].text).toBe("31 December 2021");
    }
    expect(result.verification.report_complete).toBe(false);
  });
  it("links the newly captured cash-assets row to its full 5.1.1 dipnote", () => {
    const result = build(), assets = result.tables.find(t => t.page === 15 && t.method === "framed_currency_headers_and_source_words")!;
    const cash = assets.rows.find(r => r.cells[0].text?.startsWith("1.1 Cash and Cash Equivalents"))!;
    expect(cash.cells[1].text).toBe("5.1.1");
    expect(cash.cells[4].text).toBe("271,499,741");
    expect(cash.cells[7].text).toBe("216,797,764");
    const link = assets.dipnote_links.find(l => l.row === cash.row)!;
    expect(link).toMatchObject({ marker: "5.1.1", column: 1, status: "resolved" });
    const target = result.notes.find(n => n.id === link.target_ids[0])!;
    expect(target.page_start).toBe(121);
    expect(target.page_end).toBe(123);
  });
  it("keeps blanks, dashes, covered header slots and negative source text distinct", () => {
    const table = build().tables.find(t => t.page === 16 && t.method === "framed_currency_headers_and_source_words")!;
    const upper = table.rows.findIndex(r => r.cells[0].text?.startsWith("XIII."));
    expect(table.rows[upper].cells[2]).toMatchObject({ text: "", state: "blank" });
    expect(table.rows[upper + 1].cells[2]).toMatchObject({ text: "-", state: "dash" });
    expect(table.rows[1].cells[0]).toMatchObject({ text: null, state: "absent" });
    const reclassified = table.rows.find(r => r.cells[0].text?.startsWith("16.4 "))!;
    expect(reclassified.cells[3].text).toBe("(177,731)");
  });
});
