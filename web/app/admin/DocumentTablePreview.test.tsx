import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import fixture from "../../../tests/fixtures/document_equity_preview_wire.json";
import taxFixture from "../../../tests/fixtures/document_segmented_tax_preview_wire.json";
import noteFixture from "../../../tests/fixtures/document_equity_notes_preview_wire.json";
import TablePreview from "./DocumentTablePreview";

describe("equity source lines in vertically spanning cells", () => {
  it("shows the final balance once and keeps all sixteen amount columns", () => {
    const markup = renderToStaticMarkup(<TablePreview {...fixture} />);
    const body = markup.split("<tbody>")[1].split("</tbody>")[0];
    const rows = [...body.matchAll(/<tr\b[^>]*>([\s\S]*?)<\/tr>/g)].map(m => m[1]);
    expect(rows).toHaveLength(21); // Two physical header rows and 19 source lines.
    expect(rows.slice(2).every(row => (row.match(/<td\b/g) ?? []).length === 17)).toBe(true);
    expect(body.match(/Dönem Sonu Bakiyesi\s+\(III/g)).toHaveLength(1);
    expect(rows.at(-1)?.match(/1\.646\.196/g)).toHaveLength(2);
    expect(rows.at(-1)).toContain("(1.870)");
    expect(rows.at(-1)).not.toContain("rowSpan=");
    expect(body.match(/rowSpan="2"/g)).toHaveLength(1); // The original stub header remains merged.
  });

  it("retains the original four-row grid when no line view is supplied", () => {
    const markup = renderToStaticMarkup(<TablePreview table={fixture.table} context={fixture.context} />);
    const body = markup.split("<tbody>")[1].split("</tbody>")[0];
    expect(body.match(/<tr\b/g)).toHaveLength(4);
    expect(body.match(/rowSpan="2"/g)).toHaveLength(2);
    expect(body.match(/Dönem Sonu Bakiyesi\s+\(III/g)).toHaveLength(1);
    expect(markup).not.toContain("Show separate source lines inside tall cells");
  });
});

it("keeps both tax header groups and distinguishes blank net slots from merged slots", () => {
  const markup = renderToStaticMarkup(<TablePreview {...taxFixture} />);
  const body = markup.split("<tbody>")[1].split("</tbody>")[0];
  const rows = [...body.matchAll(/<tr\b[^>]*>([\s\S]*?)<\/tr>/g)].map(m => m[1]);
  expect(rows).toHaveLength(8);
  expect(rows[0].match(/colSpan="2"/g)).toHaveLength(2);
  expect(rows[0]).toContain("Toplam Geçici Farklar");
  expect(rows[0]).toContain("varlıkları / (yükümlülükleri)");
  expect(rows.at(-1)?.match(/<td\b/g)).toHaveLength(5);
  expect(rows.at(-1)?.match(/\[empty source cell\]/g)).toHaveLength(2);
  expect(rows.at(-1)).toContain("11.936");
  expect(rows[4]).toContain("55.203");
  expect(markup).toContain("Printed rules and text positions");
});

it("shows each complete numbered explanation next to its original column reference", () => {
  const markup = renderToStaticMarkup(<TablePreview {...fixture} notes={noteFixture} />);
  const notes = markup.split("<ol")[1].split("</ol>")[0];
  expect(notes.match(/<li\b/g)).toHaveLength(6);
  expect(notes).toContain("Duran varlıklar birikmiş yeniden değerleme");
  expect(notes).toContain("tutarları ifade eder)");
  expect(notes).toContain("Column 6");
  expect(notes).toContain("Column 11");
  expect(markup).toContain("interpretation still needs review");
  expect(markup.split("<tbody>")[1].split("</tbody>")[0].match(/Dönem Sonu Bakiyesi\s+\(III/g)).toHaveLength(1);
});

it("keeps a split word's character ranges and its unresolved boundary visible", () => {
  const table = { id: "p1:ruled0", method: "pymupdf_lines_strict", n_cols: 3, row_count: 1,
    word_boundary_observations: [{ word_id: 7, text: "1Label", review_status: "unreviewed", cells: [
      { row: 0, column: 0, start: 0, end: 1 }, { row: 0, column: 1, start: 1, end: 6 }] }],
    rows: [{ index: 0, cells: [
      { column: 0, text: "1", word_ids: [7], source_fragments: [{ word_id: 7, start: 0, end: 1, text: "1" }] },
      { column: 1, text: "Label", word_ids: [7], source_fragments: [{ word_id: 7, start: 1, end: 6, text: "Label" }] },
      { column: 2, text: "0", word_ids: [8] }] }] };
  const markup = renderToStaticMarkup(<TablePreview table={table} />);
  const body = markup.split("<tbody>")[1].split("</tbody>")[0];
  expect(body).toContain("characters 1-1");
  expect(body).toContain("characters 2-6");
  expect(body).not.toContain("1Label");
  expect(body).toContain(">0</div>");
  expect(markup).toContain("Boundary review: 1 source word spans more than one cell");
  expect(markup).toContain("row 1, column 1; row 1, column 2");
  expect(markup).toContain("before interpreting the cells");
});
