/**
 * Analyst V2 — evidence model + typed tools.
 * Fixtures are synthetic; the shapes mirror the real audit DDL.
 */
import { describe, expect, it } from "vitest";

import type { Queryable } from "../data";
import { canonical, evidenceId, EvidenceLog } from "./evidence";
import { runTool, snapshotIdOf, ToolError, toolCatalog, type ToolContext } from "./tools";

const EQ_ROWS = [
  { item_order: 1, hierarchy: "I.", item_name: "Balances at beginning of the period", paid_in_capital: 50, share_premium: 0, share_cancellation_profits: 0, other_capital_reserves: 0, oci_not_reclassified_1: 0, oci_not_reclassified_2: 0, oci_not_reclassified_3: 0, oci_reclassified_1: 0, oci_reclassified_2: 0, oci_reclassified_3: 0, profit_reserves: 30, prior_period_profit_loss: 0, period_net_profit_loss: 0, total_equity: 100, minority_interest: null, total_equity_incl_minority: null, source_page: 12 },
  { item_order: 2, hierarchy: "X.", item_name: "Others Changes", paid_in_capital: 0, share_premium: 0, share_cancellation_profits: 0, other_capital_reserves: 0, oci_not_reclassified_1: 0, oci_not_reclassified_2: 0, oci_not_reclassified_3: 0, oci_reclassified_1: 0, oci_reclassified_2: 0, oci_reclassified_3: 0, profit_reserves: 0, prior_period_profit_loss: -8, period_net_profit_loss: 0, total_equity: -8, minority_interest: null, total_equity_incl_minority: null, source_page: 12 },
  { item_order: 3, hierarchy: "XI.", item_name: "Period net profit", paid_in_capital: 0, share_premium: 0, share_cancellation_profits: 0, other_capital_reserves: 0, oci_not_reclassified_1: 0, oci_not_reclassified_2: 0, oci_not_reclassified_3: 0, oci_reclassified_1: 0, oci_reclassified_2: 0, oci_reclassified_3: 0, profit_reserves: 0, prior_period_profit_loss: 0, period_net_profit_loss: 23, total_equity: 23, minority_interest: null, total_equity_incl_minority: null, source_page: 12 },
  { item_order: 4, hierarchy: "", item_name: "Balances at end of the period", paid_in_capital: 50, share_premium: 0, share_cancellation_profits: 0, other_capital_reserves: 0, oci_not_reclassified_1: 0, oci_not_reclclassified_2: 0, oci_not_reclassified_3: 0, oci_reclassified_1: 0, oci_reclassified_2: 0, oci_reclassified_3: 0, profit_reserves: 30, prior_period_profit_loss: -8, period_net_profit_loss: 23, total_equity: 115, minority_interest: null, total_equity_incl_minority: null, source_page: 13 },
];

function mockDb(): Queryable {
  return {
    all: async <T>(sql: string, binds: unknown[] = []): Promise<T[]> => {
      if (/FROM bank_audit_extractions/.test(sql) && /MAX\(extracted_at\)/.test(sql)) {
        return [{ m: "2026-08-01T00:00:00", n: 1050 }] as T[];
      }
      if (/FROM bank_audit_equity_change/.test(sql)) {
        if (binds.includes("prior")) return [] as T[];
        return EQ_ROWS as T[];
      }
      if (/FROM bank_audit_validation/.test(sql)) {
        return [{ statement: "equity_change", checks_passed: 3, checks_failed: 2, failed_detail: "eq_columns_sum; eq_rollforward" }] as T[];
      }
      if (/FROM bank_audit_profit_loss p JOIN bank_audit_pl_roles/.test(sql)) {
        return [{ amount: 23 }] as T[];
      }
      if (/FROM bank_audit_npl_movement/.test(sql)) {
        return [
          { group_code: "III", opening_balance: 10, additions: 5, transfers_in: 1, transfers_out: 2, collections: 3, write_offs: 0, sold: 0, fx_diff: 0, closing_balance: 11 },
          { group_code: "V", opening_balance: 20, additions: 1, transfers_in: 2, transfers_out: 0, collections: 1, write_offs: 4, sold: 0, fx_diff: 0, closing_balance: 99 },
        ] as T[];
      }
      return [] as T[];
    },
  };
}

async function ctx(): Promise<ToolContext> {
  const db = mockDb();
  return {
    db,
    snapshot: await snapshotIdOf(db),
    log: new EvidenceLog(),
    defaults: { bank: "TESTBK", period: "2026Q1", kind: "unconsolidated" },
  };
}

describe("evidence ids", () => {
  it("are stable and arg-order independent", () => {
    const a = evidenceId("t", { x: 1, y: "z" }, "snap");
    const b = evidenceId("t", { y: "z", x: 1 }, "snap");
    expect(a).toBe(b);
    expect(evidenceId("t", { x: 2, y: "z" }, "snap")).not.toBe(a);
    expect(canonical({ b: [1, { d: 2, c: 3 }], a: null })).toBe('{"a":null,"b":[1,{"c":3,"d":2}]}');
  });
});

describe("tool arg validation", () => {
  it("rejects unknown tools, params and enum violations; injects defaults", async () => {
    const c = await ctx();
    await expect(runTool(c, "no_such_tool", {})).rejects.toThrow(ToolError);
    await expect(runTool(c, "get_statement_rows", { statement: "equity_change", nope: 1 })).rejects.toThrow(/unknown param/);
    await expect(runTool(c, "get_statement_rows", { statement: "not_a_statement" })).rejects.toThrow(/must be one of/);
    const rec = await runTool(c, "get_statement_rows", { statement: "equity_change" });
    expect(rec.provenance.bank).toBe("TESTBK"); // defaults injected
    expect(rec.provenance.period).toBe("2026Q1");
  });

  it("requires a row selector for line-statement history", async () => {
    const c = await ctx();
    await expect(runTool(c, "get_row_history", { statement: "profit_loss" })).rejects.toThrow(/row identity/);
  });
});

describe("statement rows + evidence", () => {
  it("returns the FULL equity matrix with caveats, pages, and validation warnings", async () => {
    const c = await ctx();
    const rec = await runTool(c, "get_statement_rows", { statement: "equity_change" });
    const data = rec.data as { caveats: string[]; rows: Record<string, unknown>[] };
    expect(data.rows).toHaveLength(4);
    expect(Object.keys(data.rows[0])).toContain("prior_period_profit_loss"); // nothing curated away
    expect(data.caveats.join(" ")).toContain("WIDE MATRIX");
    expect(rec.provenance.source_pages).toEqual([12, 13]);
    expect(rec.validation_warnings.join(" ")).toContain("VALIDATION FAILING");
  });

  it("caches by evidence id — same question, same record", async () => {
    const c = await ctx();
    const a = await runTool(c, "get_statement_rows", { statement: "equity_change" });
    const b = await runTool(c, "get_statement_rows", { statement: "equity_change" });
    expect(b.evidence_id).toBe(a.evidence_id);
    expect(c.log.all()).toHaveLength(1);
  });
});

describe("equity movement ranking", () => {
  it("ranks movement rows by |total_equity| impact and flags boundaries", async () => {
    const c = await ctx();
    const rec = await runTool(c, "rank_statement_movements", { statement: "equity_change" });
    const data = rec.data as { ranked_by_total_equity_impact: { item_name: string; total_equity_impact: number; looks_like_boundary: boolean }[] };
    const ranked = data.ranked_by_total_equity_impact;
    expect(ranked[0].item_name).toContain("Balances"); // boundaries carry the largest values…
    expect(ranked[0].looks_like_boundary).toBe(true); // …and are flagged as such
    const movers = ranked.filter((r) => !r.looks_like_boundary);
    expect(movers[0].item_name).toBe("Period net profit");
    expect(movers[1].item_name).toBe("Others Changes");
  });
});

describe("reconciliations", () => {
  it("equity opening + movements = closing (reconciles on the fixture)", async () => {
    const c = await ctx();
    const rec = await runTool(c, "reconcile_statements", { reconciliation: "equity_opening_to_closing" });
    const d = rec.data as { movements_sum: number; verdict: string };
    expect(d.movements_sum).toBe(15); // −8 + 23
    expect(d.verdict).toBe("reconciles"); // 100 + 15 = 115
  });

  it("equity period-net column ties to the P&L role", async () => {
    const c = await ctx();
    const rec = await runTool(c, "reconcile_statements", { reconciliation: "equity_net_profit_vs_pl" });
    expect((rec.data as { verdict: string }).verdict).toBe("reconciles");
  });

  it("npl footing shows the formula and BREAKS loudly per group", async () => {
    const c = await ctx();
    const rec = await runTool(c, "reconcile_statements", { reconciliation: "npl_movement_footing" });
    const rows = rec.data as { group: string; verdict: string; computed_closing: number }[];
    expect(rows.find((r) => r.group === "III")?.verdict).toBe("reconciles"); // 10+5+1−2−3 = 11
    expect(rows.find((r) => r.group === "V")?.verdict).toBe("BREAKS"); // computed 18 ≠ 99
  });
});

describe("catalog", () => {
  it("lists every tool with signatures", () => {
    const cat = toolCatalog();
    for (const name of ["get_statement_rows", "reconcile_statements", "search_filing_text", "get_source_page"]) {
      expect(cat).toContain(name);
    }
  });
});
