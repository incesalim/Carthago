import { readFileSync } from "node:fs";
import { gunzipSync } from "node:zlib";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { SourceTablesBuilder } from "../lib/document-source-tables";
import { DipnoteReadingView } from "./DocumentSourceTables";

vi.mock("@opennextjs/cloudflare", () => ({ getCloudflareContext: vi.fn() }));
const fixture = JSON.parse(gunzipSync(readFileSync(new URL("../../../tests/fixtures/document_capital_disclosure_garan.json.gz", import.meta.url))).toString("utf8"));
function result() {
  const builder = new SourceTablesBuilder(fixture.revision, fixture.sections);
  for (const p of fixture.pages) builder.addPage(p.structure, p.source, []);
  const report = builder.finish();
  return { report, note: report.notes.find(n => n.address.section === 4 && n.address.group === "1" && n.address.item === "1")! };
}
describe("capital disclosure reading", () => {
  it("shows every page grid, page context, qualifications and PDF citations", () => {
    const { report, note } = result();
    const html = renderToStaticMarkup(<DipnoteReadingView report={report} note={note} citation="/original?source=fixed" disclosure />);
    for (const page of [55, 56, 57, 58]) {
      expect(html).toContain(`aria-label="Source table on page ${page}"`);
      expect(html).toContain(`original#page=${page}`);
    }
    expect(html).toContain('aria-label="Disclosure 4.1.1"');
    expect(html).toContain("Printed page units");
    expect(html).toContain("Printed page context");
    expect(html).toContain("31 December 2022");
    expect(html).toContain("insurance subsidiary");
    expect(html).toContain("252 business days");
    expect(html).toContain("16.78%");
    expect(html).toContain("18.60");
    expect(html).not.toContain('aria-label="Source table on page 59"');
  });
  it("labels a source gap as incomplete instead of claiming a complete interval", () => {
    const { report, note } = result();
    const html = renderToStaticMarkup(<DipnoteReadingView report={report} note={{ ...note, boundary: "source_gap" }} citation="/original?source=fixed" disclosure />);
    expect(html).toContain("Incomplete source interval");
    expect(html).toContain("one or more intervening pages have no available source passages");
  });
});
