import { readFileSync } from "node:fs";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ContentReviewList } from "./DocumentContentReviews";

const annotation = JSON.parse(readFileSync(new URL("../../../tests/fixtures/document_annotations/tomk_2023q3_solo.json", import.meta.url), "utf8"));
describe("content review display", () => {
  it("retains three distinct capital ratios, context and original page links", () => {
    const html = renderToStaticMarkup(<ContentReviewList filing="TOMK|2023Q3|unconsolidated" findings={annotation.cases.filter((c: { kind: string }) => c.kind === "source_review")} />);
    for (const text of ["93,93", "93,75", "93,90", "80.980.325", "809.080.325", "aggregation contexts", "differences remain unresolved", "#page=26", "#page=28", "#page=50"]) expect(html).toContain(text);
  });
  it("does not interpret no notes as no discrepancies", () => {
    expect(renderToStaticMarkup(<ContentReviewList filing="TEST|2026Q1|consolidated" findings={[]} />)).toContain("does not establish that the report has no discrepancies");
  });
});
