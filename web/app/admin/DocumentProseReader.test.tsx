import { renderToStaticMarkup } from "react-dom/server";
import { readFileSync } from "node:fs";
import { describe, expect, it, vi } from "vitest";
import { ProseBuilder } from "../lib/document-prose";
import { ProseReadingView } from "./DocumentProseReader";

vi.mock("@opennextjs/cloudflare", () => ({ getCloudflareContext: vi.fn() }));
vi.mock("@/app/lib/chart-format", () => import("../lib/chart-format"));

describe("report prose reading view", () => {
  it("shows management prose, short nil disclosures, heading context, original citations and structured export", () => {
    const c = JSON.parse(readFileSync(new URL("../../../tests/fixtures/document_prose_source_cases.json", import.meta.url), "utf8"))[0];
    const builder = new ProseBuilder(c.revision, c.sections);
    builder.addPage(c.pages[2].structure, c.pages[2].source);
    const citation = `/api/admin/document-corpus?filing=TOMK&source_hash=${c.revision.source.pdf_sha256}`;
    const html = renderToStaticMarkup(<ProseReadingView report={builder.report} citation={citation} onPage={() => {}} />);
    for (const text of ["Bulunmamaktadır.", "393.409 TL", "24.153 TL", "Ortaklık Yapısı", "Search report", "Download structured prose JSON", "source_hash=", "#page=50"]) expect(html).toContain(text);
    expect(html).not.toContain("1.447.500"); // table body is available via the explicit toggle/export
    expect(html).toContain("heading relationships and reading order still need review");
  });
});
