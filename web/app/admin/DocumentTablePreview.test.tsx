import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import fixture from "../../../tests/fixtures/document_equity_preview_wire.json";
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
