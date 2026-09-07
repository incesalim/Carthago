import { expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import fixture from "../../../tests/fixtures/document_navigation_preview_wire.json";
import DocumentNavigationPreview from "./DocumentNavigationPreview";

it("keeps complete printed entries, conflicting references and body banner links", () => {
  const markup = renderToStaticMarkup(<DocumentNavigationPreview navigation={fixture} onPage={() => {}} />);
  expect(markup.match(/<li\b/g)).toHaveLength(57);
  expect(markup).toContain("PDF pages 6–8");
  expect(markup).toContain("PDF pages 9–16");
  expect(markup).toContain("PDF pages 46–46");
  expect(markup).toContain("PDF pages 47–51");
  expect(markup).toContain("EBanka’nın");
  expect(markup).toContain("olmayan kuruluşlar hakkında kısa açıklama");
  expect(markup).toContain("Printed folio found on PDF page 45");
  expect(markup).toContain("Section banner on PDF page 46");
  expect(markup).toContain("Title repeated in a section list on PDF page 9");
  expect(markup.match(/Printed contents and body location differ/g)).toHaveLength(5);
});

it("keeps missing or ambiguous page links unresolved without converting them to zero", () => {
  const nav = structuredClone(fixture);
  nav.contents_entries = nav.contents_entries.slice(0, 1);
  const entry = nav.contents_entries[0];
  const missing = { ...nav, contents_entries: [{ ...entry, page_start: null, page_end: null, mapping_status: "unresolved", folio_sources: [] }] };
  const markup = renderToStaticMarkup(<DocumentNavigationPreview navigation={missing} onPage={() => {}} />);
  expect(markup).toContain("No unique printed folio found");
  expect(markup).not.toContain("PDF page 0");
  const ambiguous = { ...missing, contents_entries: [{ ...missing.contents_entries[0], mapping_status: "ambiguous", folio_sources: [{ page: 6 }, { page: 7 }] }] };
  expect(renderToStaticMarkup(<DocumentNavigationPreview navigation={ambiguous} onPage={() => {}} />)).toContain("More than one matching PDF page");
});

it("leaves earlier revisions readable", () => {
  expect(renderToStaticMarkup(<DocumentNavigationPreview onPage={() => {}} />)).toBe("");
});
