import { readFileSync } from "node:fs";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { ReviewedTableList } from "../admin/DocumentReviewedTables";
import { getReviewedTables } from "./document-table-review";
import { parseCorpusRevision, type CorpusBucket } from "./document-corpus";

vi.mock("@opennextjs/cloudflare", () => ({ getCloudflareContext: vi.fn() }));
const fixture = JSON.parse(readFileSync(new URL("../../../tests/fixtures/document_table_review_risk_wire.json", import.meta.url), "utf8"));
const filing = fixture.index.filing;
const revision = parseCorpusRevision(fixture.index, filing)!;
const bucketFor = (index: unknown) => ({ get: vi.fn(async (key: string) => {
  const data = key === revision.evidence_key ? fixture.source_gzip : key === revision.structure_current?.key ? fixture.structure_gzip : null;
  if (!data) return { size: 100, uploaded: new Date(0), json: async () => index };
  const bytes = Buffer.from(data, "base64");
  return { size: bytes.length, uploaded: new Date(0), body: new ReadableStream<Uint8Array>({ start(c) { c.enqueue(bytes); c.close(); } }) };
}) }) as unknown as CorpusBucket;

describe("complete source-reviewed equity and risk tables", () => {
  it("serves all six tables, 99 rows and 746 slots with literal values and full source references", async () => {
    const tables = (await Promise.all([15, 30, 31, 33, 34].map(page => getReviewedTables(bucketFor(fixture.index), filing, revision, page)))).flat();
    expect(tables).toHaveLength(6);
    expect(tables.reduce((n, t) => n + t.rows.length, 0)).toBe(99);
    expect(tables.flatMap(t => t.rows).reduce((n, r) => n + r.cells.length, 0)).toBe(746);
    expect(tables.every(t => !t.absent_slots.length)).toBe(true);
    const equity = tables.find(t => t.page === 15)!;
    expect(equity.rows).toHaveLength(20);
    expect(equity.physical_table.row_count).toBe(4);
    expect(equity.rows[1].cells.slice(5, 11).map(c => c.text)).toEqual(["1", "2", "3", "4", "5", "6"]);
    expect(equity.rows.at(-1)?.cells.slice(12, 15).map(c => c.text)).toEqual(["(1.870)", "148.071", "1.646.196"]);
    const html = renderToStaticMarkup(createElement(ReviewedTableList, { tables: [equity], filing: "TOMK|2023Q3|unconsolidated", page: 15 }));
    expect(html.match(/<tr(?:\s|>)/g)).toHaveLength(20);
    expect(html.match(/<td(?:\s|>)/g)).toHaveLength(327);
    expect(html).toContain("20 rows · 17 columns");
    expect(html).toContain('colSpan="3"');
    expect(equity.source_context).toHaveLength(8);
    expect(html).toContain("Yabancı para çevirim farkları");
    expect(html).toContain("tutarları ifade eder)");
    const daily = tables.find(t => t.review_id === "complete_fx_daily_rates")!;
    expect(daily.rows).toHaveLength(7);
    expect(daily.rows[0].cells.map(c => c.text)).toEqual(["", "USD", "EURO"]);
    expect(daily.rows[1].cells.slice(1).map(c => c.text)).toEqual(daily.rows[2].cells.slice(1).map(c => c.text));
    expect(daily.rows.at(-1)?.cells.slice(1).map(c => c.text)).toEqual(["27,1751 TL", "28,9027 TL"]);
    expect(tables.find(t => t.page === 33)?.rows[1].cells[1].text).toBe("80.980.325");
    expect(tables.find(t => t.page === 34)?.rows.at(-1)?.cells.slice(2).map(c => c.text)).toEqual(["", "", "142.085.400", "-"]);
  });

  it.each([15, 30, 31, 33, 34])("refuses a corrupted reviewed value on page %s", async page => {
    const index = structuredClone(fixture.index);
    const record = index.resume_receipt.benchmark.checks[0].reviewed_tables.find((t: { page: number }) => t.page === page);
    if (record.reviewed_grid) record.reviewed_grid.rows.at(-1).at(-1).text = "invented";
    else record.physical_rows.at(-1)[record.physical_rows.at(-1).length - 1] = "invented";
    await expect(getReviewedTables(bucketFor(index), filing, revision, page)).rejects.toThrow();
  });

  it("refuses two review names for the same physical table", async () => {
    const index = structuredClone(fixture.index);
    const records = index.resume_receipt.benchmark.checks[0].reviewed_tables;
    const duplicate = structuredClone(records.find((t: { page: number }) => t.page === 30));
    duplicate.review_id = "another_name_for_the_same_table";
    records.push(duplicate);
    await expect(getReviewedTables(bucketFor(index), filing, revision, 30)).rejects.toThrow();
  });
});
