import { describe, expect, it } from "vitest";
import { buildInterestFlow, buildWaterfall, layoutInterestFlow } from "./pl-shape";
import type { PlRow } from "./audit";

/**
 * Fixture: AKBNK 2026Q1 unconsolidated, exactly as filed in
 * `bank_audit_profit_loss` (TL thousands). Every identity in the BRSA statement
 * holds on it, so it is the reference the waterfall and the interest fan must
 * reproduce without scaling, dropping or inventing a single line.
 *
 * Note 2.6 = "Diğer" (42,922) — an interest-expense line the standard catalog
 * does NOT name. It is 0.03 % of interest income: too small for the 0.1 %
 * reconciliation noise floor to care about, and exactly the kind of line a fan
 * would silently swallow. It must surface as an explicit "Other" node.
 */
const row = (hierarchy: string, amount: number | null, item_name = ""): PlRow => ({
  item_order: 0,
  hierarchy,
  item_name,
  footnote: null,
  amount,
});

const AKBNK_2026Q1: PlRow[] = [
  row("I.", 162_844_257),
  row("1.1", 110_822_398),
  row("1.2", 15_099_710),
  row("1.3", 342_089),
  row("1.4", 228_722),
  row("1.5", 35_895_906),
  row("1.6", 0),
  row("1.7", 455_432),
  row("II.", 122_247_415),
  row("2.1", 103_300_416),
  row("2.2", 1_894_023),
  row("2.3", 11_878_363),
  row("2.4", 4_931_891),
  row("2.5", 199_800, "Kiralama Faiz Giderleri"),
  row("2.6", 42_922),
  row("III.", 40_596_842),
  row("IV.", 30_158_371),
  row("V.", 71_114),
  row("VI.", -4_956_739),
  row("VII.", 3_394_927),
  row("VIII.", 69_264_515),
  row("IX.", 11_913_574),
  row("X.", 0),
  row("XI.", 13_672_673),
  row("XII.", 20_875_327),
  row("XIII.", 22_802_941),
  row("XIV.", 0),
  row("XV.", 3_312_504),
  row("XVI.", 0),
  row("XVII.", 26_115_445),
  row("XVIII.", 6_936_870),
  row("XIX.", 19_178_575),
  row("XXV.", 19_178_575),
];

const at = (steps: { id: string; running: number; reported: number }[], id: string) =>
  steps.find((s) => s.id === id)!;

describe("buildWaterfall", () => {
  it("reconciles every BRSA subtotal on a real filing", () => {
    const w = buildWaterfall(AKBNK_2026Q1);
    expect(w.renderable).toBe(true);

    // Each running total lands ON the filed subtotal — no scaling, no plug.
    expect(at(w.steps, "nii").running).toBe(40_596_842);
    expect(at(w.steps, "gross_op").running).toBe(69_264_515);
    expect(at(w.steps, "net_op").running).toBe(22_802_941);
    expect(at(w.steps, "pretax").running).toBe(26_115_445);
    expect(at(w.steps, "net_profit").running).toBe(19_178_575);
    expect(at(w.steps, "net_profit").reported).toBe(19_178_575);

    // Tax comes off the unambiguous subtotals (XVII − XIX), not the signed XVIII.
    expect(at(w.steps, "tax").reported).toBe(-6_936_870);

    // Expenses are outflows, the trading LOSS re-signs itself into one too.
    expect(w.steps.find((s) => s.id === "interest_expense")!.kind).toBe("out");
    expect(w.steps.find((s) => s.id === "trading")!.kind).toBe("out");
    expect(w.steps.find((s) => s.id === "net_fees")!.kind).toBe("in");
    // X. (other provisions) is zero — not filed as a bar.
    expect(w.steps.find((s) => s.id === "other_prov")).toBeUndefined();
  });

  it("suppresses rather than draws a bridge that does not close", () => {
    const broken = AKBNK_2026Q1.map((r) =>
      r.hierarchy === "IX." ? { ...r, amount: 999_999_999 } : r,
    );
    const w = buildWaterfall(broken);
    expect(w.renderable).toBe(false);
    expect(w.steps).toHaveLength(0);
    expect(w.notes[0]).toMatch(/does not reconcile/i);
  });

  it("computes its lead sentence, never authors it", () => {
    const w = buildWaterfall(AKBNK_2026Q1);
    // 122,247,415 / 162,844,257 = 75.1%
    expect(w.lead).toContain("₺75.1 leaves again as interest expense");
    expect(w.lead).toContain("tax takes 26.6%");
  });
});

describe("buildInterestFlow", () => {
  it("closes both fans against the filed interest income", () => {
    const f = buildInterestFlow(AKBNK_2026Q1);
    expect(f.renderable).toBe(true);
    expect(f.income).toBe(162_844_257);
    expect(f.nii).toBe(40_596_842);

    const srcSum = f.sources.reduce((s, n) => s + n.value, 0);
    const dstSum = f.dests.reduce((s, n) => s + n.value, 0);
    expect(srcSum).toBe(f.income); // Σ sources == filed I.
    expect(dstSum).toBe(f.income); // Σ destinations + NII == filed I.
  });

  it("gives the un-catalogued remainder an explicit Other node instead of dropping it", () => {
    const f = buildInterestFlow(AKBNK_2026Q1);
    // 1.7 "Diğer" — 455,432, above the reconciliation floor.
    expect(f.sources.find((n) => n.id === "src_other")?.value).toBe(455_432);
    // 2.6 "Diğer" — 42,922, BELOW the 0.1% noise floor but still a filed line.
    expect(f.dests.find((n) => n.id === "dst_other")?.value).toBe(42_922);
  });

  it("makes net interest income the hero of the right-hand fan", () => {
    const f = buildInterestFlow(AKBNK_2026Q1);
    expect(f.dests[0].id).toBe("nii");
    expect(f.dests[0].hero).toBe(true);
    // Deposits are the largest destination after the NII the bank keeps.
    expect(f.dests[1].id).toBe("dst_2.1");
  });

  it("suppresses the fan when the sub-items exceed the filed total", () => {
    const broken = AKBNK_2026Q1.map((r) =>
      r.hierarchy === "1.1" ? { ...r, amount: 900_000_000 } : r,
    );
    const f = buildInterestFlow(broken);
    expect(f.renderable).toBe(false);
    expect(f.notes[0]).toMatch(/MORE than the filed interest income/);
  });

  it("lays out without overlapping labels", () => {
    const f = buildInterestFlow(AKBNK_2026Q1);
    const l = layoutInterestFlow(f);
    for (const side of ["source", "dest"] as const) {
      const ys = l.nodes
        .filter((n) => n.side === side)
        .map((n) => n.labelY)
        .sort((a, b) => a - b);
      for (let i = 1; i < ys.length; i++) {
        expect(ys[i] - ys[i - 1]).toBeGreaterThanOrEqual(24.9);
      }
    }
    // Every ribbon carries a path, and the hero one is the NII.
    expect(l.ribbons.every((r) => r.path.startsWith("M "))).toBe(true);
    expect(l.ribbons.filter((r) => r.kind === "keep")).toHaveLength(1);
  });
});
