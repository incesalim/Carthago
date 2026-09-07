import { describe, expect, it } from "vitest";
import type { Queryable } from "../data";
import { EvidenceLog } from "./evidence";
import { runTool, type ToolContext } from "./tools";

function context(source: string | null = JSON.stringify({
  capital_conservation_buffer_ratio: {
    status: "read", sources: [{ source_page: 29, raw_value: "2,5" }],
  },
})): { ctx: ToolContext; queries: string[] } {
  const queries: string[] = [];
  const db: Queryable = {
    all: async <T>(sql: string): Promise<T[]> => {
      queries.push(sql);
      if (sql.includes("FROM bank_audit_capital")) return [{
        period: "2023Q3", capital_conservation_buffer_ratio: 2.5,
        countercyclical_buffer_ratio: null, source_page: 26, buffer_source_json: source,
      }] as T[];
      return [];
    },
  };
  return { queries, ctx: { db,
    snapshot: { id: "test-source", max_extracted_at: null, extraction_rows: 1 },
    log: new EvidenceLog(),
    defaults: { bank: "TOMK", period: "2023Q3", kind: "unconsolidated" } } };
}

describe("capital buffers in existing analyst tools", () => {
  it("returns selected disclosures with their actual continuation page", async () => {
    const { ctx, queries } = context();
    const result = await runTool(ctx, "get_statement_rows", { statement: "capital" });
    const data = result.data as { rows: Record<string, unknown>[]; caveats: string[] };
    expect(data.rows[0].capital_conservation_buffer_ratio).toBe(2.5);
    expect(data.rows[0].countercyclical_buffer_ratio).toBeNull();
    expect(data.caveats.join(" ")).toContain("not full-table coverage");
    expect(result.provenance.source_pages).toEqual([26, 29]);
    expect(queries.some((q) => q.includes("buffer_source_json"))).toBe(true);
  });

  it("allows buffer series and carries source evidence into history", async () => {
    const { ctx, queries } = context();
    const result = await runTool(ctx, "get_row_history", {
      statement: "capital", column: "capital_conservation_buffer_ratio",
    });
    expect(result.provenance.source_pages).toEqual([26, 29]);
    expect(queries.find((q) => q.includes("ORDER BY period"))).toContain("buffer_source_json");
  });

  it.each([null, "broken JSON", "null", "[]", '{"x":{"sources":[null,{}, {"source_page":-1}]}}'])(
    "keeps historical rows readable with absent or invalid buffer evidence: %s", async (source) => {
      const { ctx } = context(source);
      const result = await runTool(ctx, "get_statement_rows", { statement: "capital" });
      expect(result.provenance.source_pages).toEqual([26]);
    },
  );
});
