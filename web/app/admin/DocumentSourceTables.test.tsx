import { renderToStaticMarkup } from "react-dom/server";
import { readFileSync } from "node:fs";
import { describe, expect, it, vi } from "vitest";
import { SourceTablesBuilder } from "../lib/document-source-tables";
import { checkedReviewedTable } from "../lib/document-table-review";
import { DipnoteReadingView, SourceTablesReadingView } from "./DocumentSourceTables";

vi.mock("@opennextjs/cloudflare", () => ({ getCloudflareContext: vi.fn() }));
const f = JSON.parse(readFileSync(new URL("../../../tests/fixtures/document_primary_dipnotes_tomk.json", import.meta.url), "utf8"));
const builder = new SourceTablesBuilder(f.revision, f.sections);
for (const p of f.pages) builder.addPage(p.structure, p.source, f.reviewed_tables.filter((r: { page: number }) => r.page === p.source.page)
  .map((r: Record<string, unknown>) => checkedReviewedTable(r, p.source, p.structure, r.native_page_sha256, r.structure_page_sha256)));
const report = builder.finish(), filing = "TOMK|2023Q3|unconsolidated";

describe("table and dipnote reader", () => {
  it("shows prior figures, source states, note actions and pinned exports together", () => {
    const html = renderToStaticMarkup(<SourceTablesReadingView report={report} filing={filing} initialLane="balance_sheet_assets" />);
    for (const text of ["1.004.154", "Read note", "(1)", "8 columns", "Source-reviewed rows", "Download tables with dipnotes JSON", "data-cell-state=\"blank\"", "data-cell-state=\"dash\"", "source_hash=", "#page=10"]) expect(html.includes(text), text).toBe(true);
    expect(html).not.toContain("Unresolved note (V-I)");
    expect(html).toContain("not proof that every table");
    expect(html).not.toContain("Report complete");
  });
  it("keeps the note's qualification and embedded source table with its PDF citation", () => {
    const note = report.notes.find(n => n.address.group === "I" && n.address.item === "2")!;
    const html = renderToStaticMarkup(<DipnoteReadingView note={note} report={report} citation={`/api/admin/document-corpus?filing=${filing}&source_hash=${report.source.pdf_sha256}`} />);
    for (const text of ["Yatırım Fonları", "940.366", "Original note text", "table grids", "#page=38"]) expect(html.includes(text), text).toBe(true);
    expect(html).not.toContain("48.253");
  });
});
