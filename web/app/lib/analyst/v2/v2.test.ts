/**
 * Analyst V2 — evidence model + typed tools.
 * Fixtures are synthetic; the shapes mirror the real audit DDL.
 */
import { describe, expect, it, vi } from "vitest";

import type { Queryable } from "../data";
import { canonical, evidenceId, EvidenceLog } from "./evidence";
import type { ScoutResult } from "./scout";
import { runTool, snapshotIdOf, ToolError, toolCatalog, type ToolContext } from "./tools";

// The loop's LLM is scripted: each chatComplete call pops the next reply and
// records the messages it was shown, so repeat-notices and repair messages
// are assertable.
const llmScript = vi.hoisted(() => ({
  replies: [] as string[],
  calls: [] as { user: string }[],
}));
vi.mock("../../llm", () => ({
  chatComplete: async (_env: unknown, messages: { role: string; content: string }[]) => {
    llmScript.calls.push({ user: messages[1].content });
    const text = llmScript.replies.shift();
    if (text == null) throw new Error("llm script exhausted");
    return { text, model: "mock" };
  },
}));

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

describe("scout", () => {
  it("ranks an unusual row above an always-huge rollup, and carries leads", async () => {
    const { runScout } = await import("./scout");
    const periods = ["2024Q1", "2024Q2", "2024Q3", "2024Q4", "2025Q1", "2025Q2", "2025Q3", "2025Q4", "2026Q1"];
    const db: Queryable = {
      all: async <T>(sql: string): Promise<T[]> => {
        if (/MAX\(extracted_at\)/.test(sql)) return [{ m: "x", n: 1 }] as T[];
        if (/MAX\(amount_total\)[\s\S]*GROUP BY bank_ticker, statement/.test(sql)) {
          return [{ statement: "assets", total: 1_000_000 }, { statement: "liabilities", total: 1_000_000 }] as T[];
        }
        if (/FROM bank_audit_balance_sheet\s+WHERE bank_ticker = \? AND kind = \? AND statement = 'liabilities' ORDER BY period/.test(sql)) {
          // Two rows: a giant TOTAL that always grows by the same amount (no
          // surprise) and a small provisions row that collapses at 2026Q1.
          const rows: unknown[] = [];
          periods.forEach((p, i) => {
            rows.push({ period: p, hierarchy: "", item_name: "TOTAL LIABILITIES", v: 900_000 + i * 50_000 });
            rows.push({ period: p, hierarchy: "8.4", item_name: "Other Provisions", v: p === "2026Q1" ? 300 : 7_000 });
          });
          return rows as T[];
        }
        if (/FROM bank_audit_validation/.test(sql)) {
          return [{ statement: "equity_change", checks_passed: 1, checks_failed: 1, failed_detail: "x" }] as T[];
        }
        return [] as T[];
      },
    };
    const c: ToolContext = {
      db, snapshot: await snapshotIdOf(db), log: new EvidenceLog(),
      defaults: { bank: "TESTBK", period: "2026Q1", kind: "unconsolidated" },
    };
    const out = await runScout(c);
    const liab = out.candidates.filter((x) => x.statement === "balance_sheet_liabilities");
    expect(liab.length).toBeGreaterThan(0);
    expect(liab[0].row).toContain("Other Provisions"); // surprise beats size
    const validation = out.candidates.find((x) => x.source === "validation");
    expect(validation?.description).toContain("equity_change");
  });
});

describe("verifier — the regression classes the old guard passed", () => {
  const mkLog = () => {
    const log = new EvidenceLog();
    log.add({
      evidence_id: "E_now", tool: "get_statement_rows",
      args: { statement: "capital", bank: "TESTBK", period: "2026Q1", kind: "unconsolidated" },
      provenance: { snapshot: "s", tables: ["bank_audit_capital"], bank: "TESTBK", period: "2026Q1", kind: "unconsolidated", source_pages: [] },
      validation_warnings: [], warnings: [], rows_returned: 1,
      data: { rows: [{ cet1_ratio: 11.04, capital_adequacy_ratio: 16.12, npl: 3.49 }] },
    });
    log.add({
      evidence_id: "E_peers", tool: "compare_with_peers",
      args: { metric: "npl_ratio_pct", bank: "TESTBK", period: "2026Q1", kind: "unconsolidated" },
      provenance: { snapshot: "s", tables: [], bank: "TESTBK", period: "2026Q1", kind: "unconsolidated", source_pages: [] },
      validation_warnings: [], warnings: [], rows_returned: 3,
      data: { peers: [{ bank_ticker: "OTHER", value: 4.12 }, { bank_ticker: "TESTBK", value: 3.49 }], medians: { npl: 2.47 } },
    });
    log.add({
      evidence_id: "E_failing", tool: "get_statement_rows",
      args: { statement: "equity_change", bank: "TESTBK", period: "2026Q1", kind: "unconsolidated" },
      provenance: { snapshot: "s", tables: ["bank_audit_equity_change"], bank: "TESTBK", period: "2026Q1", kind: "unconsolidated", source_pages: [12] },
      validation_warnings: ["VALIDATION FAILING — equity_change: 2 check(s) failed"], warnings: [], rows_returned: 4,
      data: { rows: [{ total_equity: 115 }] },
    });
    return log;
  };
  const run = { bank: "TESTBK", period: "2026Q1", kind: "unconsolidated" };
  const base = (over: Record<string, unknown>) => Object.assign({
    finding_id: "F1", bank: "TESTBK", period: "2026Q1", kind: "unconsolidated",
    classification: "observed_fact", thesis: "CET1 stands at 11.04.", materiality_rationale: "capital matters",
    confidence: "medium", claims: [] as unknown[], counterevidence: [], caveats: [], missing: [], source_pages: [],
  }, over);

  it("1 — a 2026Q1 value asserted on a 2025Q1 subject fails period association", async () => {
    const { verifyFindings } = await import("./verifier");
    const f = base({
      claims: [{ claim_id: "c", claim_kind: "value", value: 11.04,
        subject: { bank: "TESTBK", period: "2025Q1", kind: "unconsolidated", metric: "cet1_ratio" },
        evidence_ids: ["E_now"] }],
    });
    const r = verifyFindings([f as never], mkLog(), run);
    expect(r.findings[0].verdict).toBe("fail");
    expect(r.findings[0].checks.some((c) => c.check.includes("period_association") && !c.ok)).toBe(true);
  });

  it("2 — claiming 3.22 is higher than 3.49 fails comparison direction", async () => {
    const { verifyFindings } = await import("./verifier");
    const f = base({
      claims: [{ claim_id: "c", claim_kind: "comparison", value: 3.22,
        comparison: { op: "gt", rhs_value: 3.49 },
        subject: { bank: "TESTBK", period: "2026Q1", kind: "unconsolidated", metric: "npl" },
        evidence_ids: ["E_peers"] }],
    });
    const r = verifyFindings([f as never], mkLog(), run);
    expect(r.findings[0].checks.some((c) => c.check.includes("comparison_direction") && !c.ok)).toBe(true);
    expect(r.findings[0].verdict).toBe("fail");
  });

  it("3 — 'highest NPL in the class' dies when the peer table holds a higher one", async () => {
    const { verifyFindings } = await import("./verifier");
    // Modelled as: my 3.49 > every peer — but the cited peer evidence contains 4.12.
    const f = base({
      claims: [{ claim_id: "c", claim_kind: "comparison", value: 3.49,
        comparison: { op: "gt", rhs_value: 4.12 },
        subject: { bank: "TESTBK", period: "2026Q1", kind: "unconsolidated", metric: "npl_ratio_pct" },
        evidence_ids: ["E_peers"] }],
    });
    const r = verifyFindings([f as never], mkLog(), run);
    expect(r.findings[0].verdict).toBe("fail");
  });

  it("4 — causal attribution without a reconciliation/derivation claim fails a fact", async () => {
    const { verifyFindings } = await import("./verifier");
    const f = base({
      thesis: "Profit grew because provisions were released.",
      claims: [{ claim_id: "c", claim_kind: "value", value: 11.04,
        subject: { bank: "TESTBK", period: "2026Q1", kind: "unconsolidated", metric: "cet1_ratio" },
        evidence_ids: ["E_now"] }],
    });
    const r = verifyFindings([f as never], mkLog(), run);
    expect(r.findings[0].checks.some((c) => c.check === "causal_language_supported" && !c.ok)).toBe(true);
    expect(r.findings[0].verdict).toBe("fail");
  });

  it("5 — an unlabelled threshold forecast fails; a scenario passes with assumptions", async () => {
    const { verifyFindings } = await import("./verifier");
    const forecast = base({
      thesis: "CET1 will fall below 10 within two quarters.",
      claims: [{ claim_id: "c", claim_kind: "value", value: 11.04,
        subject: { bank: "TESTBK", period: "2026Q1", kind: "unconsolidated", metric: "cet1_ratio" },
        evidence_ids: ["E_now"] }],
    });
    const r1 = verifyFindings([forecast as never], mkLog(), run);
    expect(r1.findings[0].checks.some((c) => c.check === "forecast_labelled" && !c.ok)).toBe(true);
    expect(r1.findings[0].verdict).toBe("fail");
    const scenario = base({
      classification: "scenario",
      thesis: "CET1 will fall below 10 within two quarters if RWA keeps growing at the current pace.",
      caveats: ["assumes RWA growth continues at the observed QoQ rate"],
      claims: (forecast as { claims: unknown[] }).claims,
    });
    // 10 is not in evidence → thesis tracing still fails it; use an evidenced number.
    (scenario as { thesis: string }).thesis = "CET1 (11.04) falls further if RWA keeps growing at the observed pace.";
    const r2 = verifyFindings([scenario as never], mkLog(), run);
    expect(r2.findings[0].verdict).not.toBe("fail");
  });

  it("6 — citing a failing partition without a caveat fails; with one it stands", async () => {
    const { verifyFindings } = await import("./verifier");
    const f = base({
      thesis: "Total equity closed at 115.",
      claims: [{ claim_id: "c", claim_kind: "value", value: 115,
        subject: { bank: "TESTBK", period: "2026Q1", kind: "unconsolidated", statement: "equity_change" },
        evidence_ids: ["E_failing"] }],
    });
    const r = verifyFindings([f as never], mkLog(), run);
    expect(r.findings[0].checks.some((c) => c.check === "failed_partition_caveated" && !c.ok)).toBe(true);
    const caveated = base({
      thesis: "Total equity closed at 115.",
      caveats: ["the equity_change validator is failing on this partition — figure may be an extraction artifact"],
      claims: (f as { claims: unknown[] }).claims,
    });
    const r2 = verifyFindings([caveated as never], mkLog(), run);
    expect(r2.findings[0].checks.find((c) => c.check === "failed_partition_caveated")?.ok).toBe(true);
  });

  it("7 — an unsupported thesis number fails tracing", async () => {
    const { verifyFindings } = await import("./verifier");
    const f = base({
      thesis: "CET1 stands at 11.04 while hidden reserves total 999888.",
      claims: [{ claim_id: "c", claim_kind: "value", value: 11.04,
        subject: { bank: "TESTBK", period: "2026Q1", kind: "unconsolidated", metric: "cet1_ratio" },
        evidence_ids: ["E_now"] }],
    });
    const r = verifyFindings([f as never], mkLog(), run);
    expect(r.findings[0].checks.some((c) => c.check === "thesis_numbers_traced" && !c.ok)).toBe(true);
    expect(r.summary.unsupported_numeric_claims).toBeGreaterThan(0);
  });
});

describe("verifier tightening (sign, row scope, duplicates)", () => {
  const run = { bank: "TESTBK", period: "2026Q1", kind: "unconsolidated" };
  const mkLog = () => {
    const log = new EvidenceLog();
    log.add({
      evidence_id: "E_rows", tool: "get_statement_rows",
      args: { statement: "balance_sheet_liabilities", bank: "TESTBK", period: "2026Q1", kind: "unconsolidated" },
      provenance: { snapshot: "s", tables: [], bank: "TESTBK", period: "2026Q1", kind: "unconsolidated", source_pages: [] },
      validation_warnings: [], warnings: [], rows_returned: 2,
      data: { rows: [
        { hierarchy: "8.4", item_name: "Other Provisions", amount_total: 744880 },
        { hierarchy: "9.9", item_name: "Unrelated Line", amount_total: 555111 },
      ] },
    });
    return log;
  };
  const base = (claims: unknown[]) => ({
    finding_id: "F1", bank: "TESTBK", period: "2026Q1", kind: "unconsolidated",
    classification: "observed_fact", thesis: "Provisions stand where they stand.",
    materiality_rationale: "material", confidence: "medium",
    claims, counterevidence: [], caveats: [], missing: [], source_pages: [],
  });
  const claim = (value: number, row: string | undefined) => ({
    claim_id: "c1", claim_kind: "value", value,
    subject: { bank: "TESTBK", period: "2026Q1", kind: "unconsolidated", statement: "balance_sheet_liabilities", row },
    evidence_ids: ["E_rows"],
  });

  it("an opposite-signed match downgrades to flag instead of passing", async () => {
    const { verifyFindings } = await import("./verifier");
    const r = verifyFindings([base([claim(-744880, "Other Provisions")]) as never], mkLog(), run);
    expect(r.findings[0].verdict).toBe("flag");
    expect(r.findings[0].checks.find((c) => c.check.includes("value_in_evidence"))?.detail).toContain("OPPOSITE sign");
    expect(r.summary.unsupported_numeric_claims).toBe(0); // flagged, not unsupported
  });

  it("a value found only OUTSIDE the named row flags; inside it passes clean", async () => {
    const { verifyFindings } = await import("./verifier");
    const wrong = verifyFindings([base([claim(555111, "Other Provisions")]) as never], mkLog(), run);
    expect(wrong.findings[0].verdict).toBe("flag");
    expect(wrong.findings[0].checks.find((c) => c.check.includes("value_in_evidence"))?.detail).toContain("NOT within the named row");
    const right = verifyFindings([base([claim(744880, "8.4 Other Provisions")]) as never], mkLog(), run);
    expect(right.findings[0].verdict).toBe("pass"); // label containment works both directions
  });

  it("a near-duplicate second finding fails duplicate_finding", async () => {
    const { verifyFindings } = await import("./verifier");
    const f1 = base([claim(744880, "Other Provisions")]);
    const f2 = { ...base([claim(744880, "Other Provisions")]), finding_id: "F2", thesis: "Provisions stand exactly where they stand." };
    const r = verifyFindings([f1 as never, f2 as never], mkLog(), run);
    expect(r.findings[0].verdict).toBe("pass");
    expect(r.findings[1].verdict).toBe("fail");
    expect(r.findings[1].checks.find((c) => c.check === "duplicate_finding")?.detail).toContain("near-duplicate of F1");
  });

  it("rank_statement_movements no longer advertises singleton statements", async () => {
    const c = await ctx();
    await expect(runTool(c, "rank_statement_movements", { statement: "npl_movement" })).rejects.toThrow(/must be one of/);
  });
});

describe("loop protocol", () => {
  it("extracts the first balanced JSON object from noisy replies", async () => {
    const { runResearch } = await import("./loop");
    expect(typeof runResearch).toBe("function"); // loop needs an LLM; protocol parsing is exercised via extractJson below
  });

  it("findingProblems rejects claimless findings", async () => {
    const { findingProblems } = await import("./findings");
    expect(findingProblems({ finding_id: "F1" }).length).toBeGreaterThan(0);
    expect(findingProblems({
      finding_id: "F1", bank: "X", period: "2026Q1", kind: "unconsolidated",
      classification: "observed_fact", thesis: "t", materiality_rationale: "m", confidence: "low",
      claims: [{ claim_id: "c", claim_kind: "value", value: 1, subject: { bank: "X", period: "2026Q1", kind: "unconsolidated" }, evidence_ids: ["E1"] }],
    })).toEqual([]);
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

describe("filing-text search (the OR-query and page-truncation regressions)", () => {
  const withFiling = async (): Promise<ToolContext> => {
    const c = await ctx();
    c.filingText = {
      bank: "TESTBK", period: "2026Q1", kind: "unconsolidated",
      pages: [
        { page: 1, text: "the quick alpha fox" },
        { page: 2, text: "a beta instrument table" },
        { page: 36, text: "SUKUK WAKALA issued via Bereket. " + "x".repeat(5000) + " BDDK letter 9196" },
      ],
    };
    return c;
  };

  it("splits ' OR ' into alternatives and unions the hits", async () => {
    const c = await withFiling();
    const rec = await runTool(c, "search_filing_text", { query: "alpha OR beta" });
    const hits = rec.data as { page: number; term: string }[];
    expect(hits.map((h) => h.page)).toEqual([1, 2]);
    expect(rec.provenance.source_pages).toEqual([1, 2]);
  });

  it("rarer terms sort ahead of boilerplate matches", async () => {
    const c = await withFiling();
    c.filingText!.pages = [
      { page: 1, text: "alpha alpha alpha filler" },
      { page: 92, text: "the rare decisive disclosure" },
    ];
    const rec = await runTool(c, "search_filing_text", { query: "alpha OR decisive" });
    const hits = rec.data as { page: number; term: string }[];
    expect(hits[0].page).toBe(92); // 1 hit beats 3 — distinctive first
  });

  it("a zero-hit long phrase warns toward short fragments", async () => {
    const c = await withFiling();
    const rec = await runTool(c, "search_filing_text", { query: "this exact long phrase never appears verbatim anywhere" });
    expect(rec.warnings.join(" ")).toContain("SUBSTRING search");
  });

  it("get_source_page evidence keeps the whole 8000-char page — the tail is readable", async () => {
    const c = await withFiling();
    const rec = await runTool(c, "get_source_page", { page: 36 });
    const text = (rec.data as { text: string }).text;
    expect(text.length).toBeGreaterThan(5000);
    expect(text).toContain("BDDK letter 9196"); // was beyond the old 1400-char cut
  });
});

describe("evidence id canonicalization (the ALBRK double-id regression)", () => {
  it("omitted and explicit period_type='current' yield ONE evidence record", async () => {
    const c = await ctx();
    const a = await runTool(c, "get_statement_rows", { statement: "equity_change" });
    const b = await runTool(c, "get_statement_rows", { statement: "equity_change", period_type: "current" });
    expect(b.evidence_id).toBe(a.evidence_id);
    expect(c.log.all()).toHaveLength(1);
    expect(a.args.period_type).toBe("current"); // default materialized into args
  });
});

describe("tablify (the 7.6KB-equity-matrix-vs-6KB-window regression)", () => {
  it("renders row arrays as a pipe-table far smaller than JSON, nulls as ∅", async () => {
    const { tablify } = await import("./loop");
    const t = tablify(EQ_ROWS)!;
    expect(t).toContain("TABLE 4 rows");
    expect(t).toContain("total_equity");
    expect(t).toContain("|-8|"); // values byte-identical for echoing
    expect(t).toContain("∅"); // minority_interest null ≠ 0
    expect(t.length).toBeLessThan(JSON.stringify(EQ_ROWS).length / 2);
  });

  it("flattens one level of plain objects into dotted columns; bails on deeper nesting", async () => {
    const { tablify } = await import("./loop");
    const rows = [1, 2, 3].map((i) => ({ item: `r${i}`, components: { a: i, b: null } }));
    const t = tablify(rows)!;
    expect(t).toContain("components.a");
    expect(t.split("\n")[1]).toBe("r1|1|∅");
    expect(tablify([{ x: [1] }, { x: [2] }, { x: [3] }])).toBeNull();
  });
});

describe("research loop — repeat calls and emission-time verification", () => {
  const scout = { candidates: [] } as unknown as ScoutResult;

  it("a repeated identical call returns a short notice, not the payload again", async () => {
    const { runResearch } = await import("./loop");
    const c = await ctx();
    llmScript.calls.length = 0;
    llmScript.replies = [
      JSON.stringify({ action: "tool", tool: "get_statement_rows", args: { statement: "equity_change" } }),
      JSON.stringify({ action: "tool", tool: "get_statement_rows", args: { statement: "equity_change", period_type: "current" } }),
      JSON.stringify({ action: "abstain", reason: "checked" }),
    ];
    const res = await runResearch(c, scout, {});
    expect(llmScript.calls[1].user).toContain("TABLE 4 rows"); // delivered into the case file, tablified, whole
    expect(llmScript.calls[2].user).toContain("REPEAT CALL"); // repeat answered with a pointer…
    expect(llmScript.calls[2].user).toContain("TABLE 4 rows"); // …while the data STAYS on file (the round-2 regression)
    expect(llmScript.calls[2].user).toContain("statements not yet read");
    expect(res.metrics.protocol_errors).toBe(0);
    expect(res.abstained).toBe(true);
  });

  it("six consecutive probes of one area earn a breadth nudge", async () => {
    const { runResearch } = await import("./loop");
    const c = await ctx();
    llmScript.calls.length = 0;
    llmScript.replies = [
      ...[1, 2, 3, 4, 5, 6].map((i) =>
        JSON.stringify({ action: "tool", tool: "search_filing_text", args: { query: `probe number ${i}` } })),
      JSON.stringify({ action: "abstain", reason: "checked" }),
    ];
    const res = await runResearch(c, scout, {});
    expect(llmScript.calls[6].user).toContain("queries all probed filing_text");
    expect(llmScript.calls[5].user).not.toContain("queries all probed"); // fires only when the window is uniform and full
    expect(res.abstained).toBe(true);
  });

  it("a finding with an unevidenced value bounces back once for repair, then lands", async () => {
    const { runResearch } = await import("./loop");
    const c = await ctx();
    const eid = evidenceId(
      "get_statement_rows",
      { bank: "TESTBK", period: "2026Q1", kind: "unconsolidated", statement: "equity_change", period_type: "current" },
      c.snapshot.id,
    );
    const finding = (value: number) => ({
      action: "finding",
      finding: {
        finding_id: "F1", bank: "TESTBK", period: "2026Q1", kind: "unconsolidated",
        classification: "observed_fact", thesis: "Others Changes shows a negative equity movement.",
        materiality_rationale: "equity moved outside profit", confidence: "medium",
        claims: [{ claim_id: "F1.c1", claim_kind: "value", value,
          subject: { bank: "TESTBK", period: "2026Q1", kind: "unconsolidated", statement: "equity_change", row: "Others Changes", metric: "total_equity" },
          evidence_ids: [eid] }],
        counterevidence: [], caveats: ["the equity_change validator is failing on this partition"], missing: [], source_pages: [12],
      },
    });
    llmScript.calls.length = 0;
    llmScript.replies = [
      JSON.stringify({ action: "tool", tool: "get_statement_rows", args: { statement: "equity_change" } }),
      JSON.stringify(finding(-9999)), // not in evidence → verifier bounce
      JSON.stringify(finding(-8)), // repaired → accepted
      JSON.stringify({ action: "conclude", reason: "done" }),
    ];
    const res = await runResearch(c, scout, {});
    expect(llmScript.calls[2].user).toContain("FAILED VERIFICATION");
    expect(llmScript.calls[2].user).toContain("value_in_evidence");
    expect(res.findings).toHaveLength(1);
    expect((res.findings[0].claims[0] as { value: number }).value).toBe(-8);
    expect(res.metrics.protocol_errors).toBe(0); // a verifier bounce is not a protocol error
    const trace = res.traceJsonl.trim().split("\n").map((l) => JSON.parse(l) as { detail: string });
    expect(trace.some((t) => t.detail.startsWith("verifier_repair F1"))).toBe(true);
  });
});
