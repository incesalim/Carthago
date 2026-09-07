import { describe, expect, it } from "vitest";
import type { Queryable } from "../data";
import { EvidenceLog } from "./evidence";
import { runTool, type ToolContext } from "./tools";

function setup(statement: string, row: Record<string, unknown>) {
  const queries: string[] = [];
  const db: Queryable = { all: async <T>(sql: string): Promise<T[]> => {
    queries.push(sql);
    return sql.includes(`FROM bank_audit_${statement}`) ? [row] as T[] : [];
  } };
  const ctx: ToolContext = { db,
    snapshot: { id: "source-check", max_extracted_at: null, extraction_rows: 1 },
    log: new EvidenceLog(), defaults: { bank: "TOMK", period: "2024Q1", kind: "unconsolidated" },
  };
  return { ctx, queries };
}

describe("source evidence across existing statements", () => {
  it("carries comparative LCR's actual page into statement rows and history", async () => {
    const { ctx, queries } = setup("liquidity", { period: "2024Q1", lcr_total: 3768,
      lcr_fc: null, source_page: 34, lcr_source_json: JSON.stringify({ lcr_total: {
        status: "read", sources: [{ source_page: 36, raw_value: "3,768", period_type: "prior" }],
      } }),
    });
    const rows = await runTool(ctx, "get_statement_rows", { statement: "liquidity", period_type: "prior" });
    expect(rows.provenance.source_pages).toEqual([34, 36]);
    expect((rows.data as { rows: Record<string, unknown>[] }).rows[0].lcr_fc).toBeNull();
    const history = await runTool(ctx, "get_row_history", { statement: "liquidity", column: "lcr_total", period_type: "prior" });
    expect(history.provenance.source_pages).toEqual([34, 36]);
    expect(queries.find((q) => q.includes("ORDER BY period"))).toContain("lcr_source_json");
    expect(queries.find((q) => q.includes("ORDER BY period"))).toContain("period_type = 'prior'");
  });

  it.each([
    ["fx_position", "net_position", { currency: "TOTAL" }],
    ["repricing", "gap", { bucket: "total" }],
    ["loans_by_sector", "stage3_amount", { sector: "total" }],
    ["capital", "total_capital", {}],
  ])("keeps %s source pages in history", async (statement, column, identity) => {
    const { ctx, queries } = setup(statement, { period: "2024Q1", source_page: 31, [column]: 100 });
    const result = await runTool(ctx, "get_row_history", { statement, column, ...identity });
    expect(result.provenance.source_pages).toEqual([31]);
    expect(queries.find((q) => q.includes("ORDER BY period"))).toContain("source_page");
    if ("bucket" in identity) expect(queries.find((q) => q.includes("ORDER BY period"))).toContain("bucket = ?");
    if ("sector" in identity) expect(queries.find((q) => q.includes("ORDER BY period"))).toContain("sector = ?");
    if (statement === "fx_position") {
      const rows = await runTool(ctx, "get_statement_rows", { statement });
      expect(rows.provenance.source_pages).toEqual([31]);
    }
  });

  it("keeps old liquidity rows readable without evidence", async () => {
    for (const evidence of [null, "broken JSON", "[]"]) {
      const { ctx } = setup("liquidity", { lcr_total: 150, source_page: 34, lcr_source_json: evidence });
      const result = await runTool(ctx, "get_statement_rows", { statement: "liquidity" });
      expect(result.provenance.source_pages).toEqual([34]);
    }
  });
});
