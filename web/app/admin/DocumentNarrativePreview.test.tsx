import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import DocumentNarrativePreview, { type Narrative, type ReadingLayout } from "./DocumentNarrativePreview";

vi.mock("@/app/lib/chart-format", () => import("../lib/chart-format"));

const element = (id: string, text: string): Narrative => ({ id, text, kind: "paragraph_candidate",
  span_ids: [1], table_ids: [], heading_path: [] });

describe("source reading view", () => {
  it("shows the title before an earlier-stored footer and joins a source bullet with its text", () => {
    const elements = [element("footer", "AUDITOR CONTACT"), element("title", "AUDIT REPORT"),
      element("bullet", "• "), element("body", "SOURCE PARAGRAPH")];
    const layout: ReadingLayout = { issues: [], tree: { kind: "sequence", axis: "y", children: [
      { kind: "element", element_ids: ["title"] },
      { kind: "list_item_candidate", element_ids: ["bullet", "body"] },
      { kind: "element", element_ids: ["footer"] },
    ] } };
    const html = renderToStaticMarkup(<DocumentNarrativePreview elements={elements} layout={layout} />);
    expect(html.indexOf("AUDIT REPORT")).toBeLessThan(html.indexOf("SOURCE PARAGRAPH"));
    expect(html.indexOf("SOURCE PARAGRAPH")).toBeLessThan(html.indexOf("AUDITOR CONTACT"));
    expect(html).toContain("• SOURCE PARAGRAPH");
    expect(html).toContain("Reading order still needs review");
  });

  it.each(["missing", "duplicate", "unknown"])("falls back to every original text when references are %s", (change) => {
    const elements = [element("a", "FIRST ORIGINAL"), element("b", "SECOND ORIGINAL")];
    const ids = change === "missing" ? ["a"] : change === "duplicate" ? ["a", "a"] : ["a", "other"];
    const layout: ReadingLayout = { issues: [], tree: { kind: "element", element_ids: ids } };
    const html = renderToStaticMarkup(<DocumentNarrativePreview elements={elements} layout={layout} />);
    expect(html).toContain("incomplete source references");
    expect(html).toContain("FIRST ORIGINAL");
    expect(html).toContain("SECOND ORIGINAL");
  });

  it("retains column grouping and exposes unresolved areas", () => {
    const elements = [element("name", "PRINTED NAME"), element("role", "PRINTED ROLE"), element("other", "OTHER COLUMN")];
    const layout: ReadingLayout = { issues: [{ kind: "unresolved_overlap" }], tree: { kind: "sequence", axis: "x", children: [
      { kind: "unresolved_overlap", children: [{ kind: "element", element_ids: ["name"] }, { kind: "element", element_ids: ["role"] }] },
      { kind: "element", element_ids: ["other"] },
    ] } };
    const html = renderToStaticMarkup(<DocumentNarrativePreview elements={elements} layout={layout} />);
    expect(html).toContain("grid-template-columns:repeat(2, minmax(12rem, 1fr))");
    expect(html).toContain("Order unresolved in this area");
    expect(html.indexOf("PRINTED ROLE")).toBeLessThan(html.indexOf("OTHER COLUMN"));
  });
});
