import { describe, expect, it } from "vitest";
import { buildPlSankey, layoutPlSankey, type PlSankeyResult } from "./pl-sankey";
import type { PlRow } from "./audit";

// ---------------------------------------------------------------------------
// Fixture helpers
// ---------------------------------------------------------------------------

function rows(spec: Record<string, [string, number | null]>): PlRow[] {
  return Object.entries(spec).map(([hierarchy, [item_name, amount]], i) => ({
    item_order: i + 1,
    hierarchy,
    item_name,
    footnote: null,
    amount,
  }));
}

/** AKBNK-style filing: deductions stored as positive magnitudes, "(-)" labels. */
function plainBank(over: Partial<Record<string, number>> = {}): PlRow[] {
  const v = {
    I: 1000, II: 600, III: 400, IV: 120, V: 10, VI: 50, VII: 70,
    VIII: 650, IX: 100, X: 20, XI: 130, XII: 150, XIII: 250,
    XV: 5, XVI: -30, XVII: 225, XVIII: 45, XIX: 180, XXV: 180,
    ...over,
  };
  return rows({
    "I.": ["Interest Income", v.I],
    "II.": ["Interest Expense (-)", v.II],
    "III.": ["Net Interest Income", v.III],
    "IV.": ["Net Fees and Commissions", v.IV],
    "V.": ["Dividend Income", v.V],
    "VI.": ["Net Trading Income/(Loss)", v.VI],
    "VII.": ["Other Operating Income", v.VII],
    "VIII.": ["Gross Operating Profit", v.VIII],
    "IX.": ["Expected Credit Losses (-)", v.IX],
    "X.": ["Other Provisions (-)", v.X],
    "XI.": ["Personnel Expenses (-)", v.XI],
    "XII.": ["Other Operating Expenses (-)", v.XII],
    "XIII.": ["Net Operating Profit", v.XIII],
    "XV.": ["Equity Method Profit", v.XV],
    "XVI.": ["Net Monetary Position Profit/(Loss)", v.XVI],
    "XVII.": ["Pre-tax Profit", v.XVII],
    "XVIII.": ["Tax Provision (±)", v.XVIII],
    "XIX.": ["Net Profit From Continuing Operations", v.XIX],
    "XXV.": ["Net Period Profit", v.XXV],
  });
}

/** ING-style filing: same economics, contra lines stored NEGATIVE. */
function parenNegativeBank(): PlRow[] {
  return plainBank().map((r) =>
    ["II.", "IX.", "X.", "XI.", "XII."].includes(r.hierarchy) && r.amount != null
      ? { ...r, amount: -r.amount }
      : r,
  );
}

function linkValue(g: PlSankeyResult, source: string, target: string): number | undefined {
  return g.links.find((l) => l.source === source && l.target === target)?.value;
}

/** Σin == Σout at every node that has both inflows and outflows. */
function assertFluxConserved(g: PlSankeyResult) {
  for (const n of g.nodes) {
    const inflow = g.links.filter((l) => l.target === n.id).reduce((s, l) => s + l.value, 0);
    const outflow = g.links.filter((l) => l.source === n.id).reduce((s, l) => s + l.value, 0);
    if (inflow > 0 && outflow > 0) {
      expect(Math.abs(inflow - outflow), `flux at ${n.id}`).toBeLessThan(1e-6);
    }
    expect(n.value, `thickness of ${n.id}`).toBeGreaterThanOrEqual(Math.max(inflow, outflow) - 1e-6);
  }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("buildPlSankey — happy path", () => {
  it("builds a renderable graph with clean checks for a plain-sign bank", () => {
    const g = buildPlSankey(plainBank({ XVI: 0, XVII: 255, XVIII: 51, XIX: 204, XXV: 204, VIII: 650 }));
    expect(g.renderable).toBe(true);
    expect(g.worstPctDiff).toBeLessThanOrEqual(0.005);
    // Core ribbons
    expect(linkValue(g, "interest_income", "interest_expense")).toBe(600);
    expect(linkValue(g, "interest_income", "net_interest")).toBe(400);
    expect(linkValue(g, "net_interest", "gross_op")).toBe(400);
    expect(linkValue(g, "gross_op", "ecl")).toBe(100);
    expect(linkValue(g, "gross_op", "net_op")).toBe(250);
    expect(linkValue(g, "pretax", "tax")).toBe(51); // derived XVII − XIX
    expect(linkValue(g, "pretax", "net_profit")).toBe(204);
    assertFluxConserved(g);
  });

  it("normalizes a paren-negative bank to the same graph as the plain bank", () => {
    const a = buildPlSankey(plainBank());
    const b = buildPlSankey(parenNegativeBank());
    expect(b.links).toEqual(a.links);
    expect(b.nodes.map((n) => [n.id, n.value])).toEqual(a.nodes.map((n) => [n.id, n.value]));
  });
});

describe("negative re-routing", () => {
  it("re-routes a trading loss as an outflow of gross operating profit", () => {
    // VI = −50: VIII = 400+120+10−50+70 = 550; XIII = 150
    const g = buildPlSankey(
      plainBank({ VI: -50, VIII: 550, XIII: 150, XVI: 0, XVII: 155, XVIII: 31, XIX: 124, XXV: 124 }),
    );
    expect(g.renderable).toBe(true);
    expect(g.nodes.find((n) => n.id === "trading_loss")?.kind).toBe("rerouted");
    expect(linkValue(g, "gross_op", "trading_loss")).toBe(50);
    // Node thickness exceeds the filed VIII by the re-routed amount…
    expect(g.nodes.find((n) => n.id === "gross_op")?.value).toBe(600);
    // …but the label still reports the filed figure.
    expect(g.nodes.find((n) => n.id === "gross_op")?.reported).toBe(550);
    expect(g.notes.some((n) => n.includes("Net trading loss"))).toBe(true);
    assertFluxConserved(g);
  });

  it("re-routes a monetary-position loss as an outflow of pre-tax profit", () => {
    const g = buildPlSankey(plainBank()); // fixture has XVI = −30
    expect(g.renderable).toBe(true);
    expect(linkValue(g, "pretax", "monetary_loss")).toBe(30);
    expect(g.nodes.find((n) => n.id === "pretax")?.reported).toBe(225);
    expect(g.nodes.find((n) => n.id === "pretax")?.value).toBe(255); // 250 + 5 in
    assertFluxConserved(g);
  });

  it("adds a genuine expense reversal (negative deduction) back as a green inflow", () => {
    // DENIZ/BURGAN case: X. "Other provisions" is a net write-back, stored
    // NEGATIVE while personnel/interest stay positive. It must ADD to the flow,
    // not be abs()-ed and subtracted. Real net op = 650 − (100 − 20 + 130 + 150)
    // = 290, which reconciles exactly.
    const g = buildPlSankey(
      plainBank({ X: -20, XIII: 290, XVI: 0, XVII: 295, XVIII: 59, XIX: 236, XXV: 236 }),
    );
    expect(g.renderable).toBe(true);
    expect(g.worstPctDiff).toBe(0);
    const credit = g.nodes.find((n) => n.id === "other_prov_credit");
    expect(credit?.kind).toBe("source");
    expect(linkValue(g, "other_prov_credit", "gross_op")).toBe(20);
    // It is NOT drawn as an outflow deduction.
    expect(g.nodes.some((n) => n.id === "other_prov")).toBe(false);
    expect(g.links.some((l) => l.source === "gross_op" && l.target === "other_prov")).toBe(false);
    // Forward flow to net op reflects the credit.
    expect(linkValue(g, "gross_op", "net_op")).toBe(290);
    expect(g.notes.some((n) => n.includes("Provision reversal"))).toBe(true);
    assertFluxConserved(g);
  });

  it("normalizes a reversal identically under the paren-negative convention", () => {
    // Same economics as above but the bank stores expenses NEGATIVE (conv = −1);
    // the write-back is then stored POSITIVE. The graph must come out the same.
    const base = plainBank({ X: -20, XIII: 290, XVI: 0, XVII: 295, XVIII: 59, XIX: 236, XXV: 236 });
    const flipped = base.map((r) =>
      ["II.", "IX.", "X.", "XI.", "XII."].includes(r.hierarchy) && r.amount != null
        ? { ...r, amount: -r.amount }
        : r,
    );
    const a = buildPlSankey(base);
    const b = buildPlSankey(flipped);
    expect(b.renderable).toBe(true);
    expect(b.links).toEqual(a.links);
    expect(b.nodes.map((n) => [n.id, n.value])).toEqual(a.nodes.map((n) => [n.id, n.value]));
  });

  it("draws a tax credit as an inflow to net profit", () => {
    // XVII = 100, XIX = 130 → tax = −30 (credit)
    const g = buildPlSankey(
      plainBank({ XIII: 125, XVI: -30, XVII: 100, XVIII: -30, XIX: 130, XXV: 130, IX: 225 }),
    );
    expect(g.renderable).toBe(true);
    expect(linkValue(g, "tax_credit", "net_profit")).toBe(30);
    expect(g.links.some((l) => l.target === "tax")).toBe(false);
    expect(g.notes.some((n) => n.includes("net credit"))).toBe(true);
    assertFluxConserved(g);
  });
});

describe("loss-making periods", () => {
  it("balances an operating loss with a synthetic red source at gross op", () => {
    // Deductions 730 > gross 650 → XIII = −80; XVII = −80+5−30 = −105; tax 0
    const g = buildPlSankey(
      plainBank({ XII: 480, XIII: -80, XVII: -105, XVIII: 0, XIX: -105, XXV: -105 }),
    );
    expect(g.renderable).toBe(true);
    const fund = g.nodes.find((n) => n.id === "op_loss_fund");
    expect(fund?.kind).toBe("loss");
    expect(linkValue(g, "op_loss_fund", "gross_op")).toBe(80);
    expect(g.links.some((l) => l.source === "gross_op" && l.target === "net_op")).toBe(false);
    const result = g.nodes.find((n) => n.id === "net_profit");
    expect(result?.kind).toBe("loss");
    expect(result?.label).toBe("Net loss");
    expect(result?.reported).toBe(-105);
    assertFluxConserved(g);
  });
});

describe("fallbacks and degradation", () => {
  it("derives interest expense from I − III when II is missing", () => {
    const fixture = plainBank().filter((r) => r.hierarchy !== "II.");
    const g = buildPlSankey(fixture);
    expect(g.renderable).toBe(true);
    expect(linkValue(g, "interest_income", "interest_expense")).toBe(600);
    expect(linkValue(g, "interest_income", "net_interest")).toBe(400);
    expect(g.notes.some((n) => n.includes("derived as I."))).toBe(true);
    assertFluxConserved(g);
  });

  it("suppresses the chart when a subtotal is off by more than 5%", () => {
    const g = buildPlSankey(plainBank({ VIII: 900 })); // computed 650 vs filed 900
    expect(g.renderable).toBe(false);
    expect(g.worstPctDiff).toBeGreaterThan(0.05);
    expect(g.nodes).toHaveLength(0);
  });

  it("resolves a bare roman code stored without its trailing dot (VAKBN's VI)", () => {
    // VAKBN files roman VI ("Net trading") without a trailing dot and the
    // extractor keeps it verbatim. The dotted-key lookup used to drop the line,
    // overstating VIII/XIII and suppressing the chart every period. VI = −50:
    // VIII = 400+120+10−50+70 = 550; XIII = 150.
    const dotless = plainBank({
      VI: -50, VIII: 550, XIII: 150, XVI: 0, XVII: 155, XVIII: 31, XIX: 124, XXV: 124,
    }).map((r) => (r.hierarchy === "VI." ? { ...r, hierarchy: "VI" } : r));
    const g = buildPlSankey(dotless);
    expect(g.renderable).toBe(true);
    expect(g.worstPctDiff).toBeLessThanOrEqual(0.005);
    expect(linkValue(g, "gross_op", "trading_loss")).toBe(50);
    assertFluxConserved(g);
  });

  it("ignores a stray duplicate roman (footnote fragment) and uses the real subtotal", () => {
    // ZIRAAT/BURGAN bug: a "IV. = 1" fragment captured BEFORE the real IV. line.
    // "First wins" read the stray (1) and the flow couldn't balance; larger-
    // magnitude-wins keeps the real subtotal so the chart renders.
    const stray: PlRow = { item_order: 0, hierarchy: "IV.", item_name: "(IV.)", footnote: null, amount: 1 };
    const g = buildPlSankey([stray, ...plainBank()]);
    expect(g.renderable).toBe(true);
    expect(g.worstPctDiff).toBeLessThan(0.005);
    expect(linkValue(g, "net_fees", "gross_op")).toBe(120); // real IV., not the stray 1
  });

  it("suppresses a small (sub-5%) mismatch — exact reconciliation is required", () => {
    const g = buildPlSankey(plainBank({ VIII: 660 })); // computed 650 vs filed 660, ~1.5%
    expect(g.renderable).toBe(false);
    expect(g.worstPctDiff).toBeGreaterThan(0);
    expect(g.nodes).toHaveLength(0);
    expect(g.notes.some((n) => n.includes("does not reconcile"))).toBe(true);
  });

  it("fails safe when core lines are missing", () => {
    const g = buildPlSankey(rows({ "I.": ["Interest Income", 1000] }));
    expect(g.renderable).toBe(false);
  });

  it("treats near-zero subtotal diffs as rounding noise, not failures", () => {
    // XIII computed 1 vs filed 2: 50% relative, but within 0.1% of interest
    // income — must not suppress the chart.
    const g = buildPlSankey(
      plainBank({ XII: 399, XIII: 2, XVI: 0, XVII: 7, XVIII: 1, XIX: 6, XXV: 6 }),
    );
    expect(g.renderable).toBe(true);
    expect(g.worstPctDiff).toBe(0);
  });
});

describe("layoutPlSankey", () => {
  it("places nodes in their columns and emits one ribbon per link", () => {
    const g = buildPlSankey(plainBank());
    const l = layoutPlSankey(g);
    expect(l.ribbons).toHaveLength(g.links.length);
    expect(l.nodes).toHaveLength(g.nodes.length);
    // Columns increase left to right.
    const xByCol = new Map<number, number>();
    for (const n of l.nodes) xByCol.set(n.column, n.x);
    const cols = [...xByCol.entries()].sort((a, b) => a[0] - b[0]).map(([, x]) => x);
    for (let i = 1; i < cols.length; i++) expect(cols[i]).toBeGreaterThan(cols[i - 1]);
    // Everything fits the viewBox.
    for (const n of l.nodes) {
      expect(n.y).toBeGreaterThanOrEqual(0);
      expect(n.y + n.h).toBeLessThanOrEqual(l.H);
    }
  });
});

// ---------------------------------------------------------------------------
// The compressed BRSA template (participation banks)
// ---------------------------------------------------------------------------

/** DUNYAK / TOMK file a COMPRESSED template: fewer lines, so the roman ordinals
 *  shift. Net-operating lands at XII (not XIII), pre-tax at XVI (not XVII),
 *  continuing-ops net at XVIII, and the bottom line at XXIV (not XXV).
 *
 *  Same economics as `plainBank()` — only the numbering differs. Rendered
 *  against the standard ordinals, XII ("Other Operating Expenses" in the normal
 *  template) picks up NET OPERATING PROFIT and draws a profit as an expense,
 *  while XXV is absent so the bottom line renders blank. That is what shipped
 *  for DUNYAK 2024Q4: ₺1.616bn of profit under an expense label. */
function compressedTemplateBank(): PlRow[] {
  return rows({
    "I.": ["Kâr Payı Gelirleri", 1000],
    "II.": ["Kâr Payı Giderleri (-)", 600],
    "III.": ["Net Kâr Payı Geliri", 400],
    "IV.": ["Net Ücret ve Komisyon Gelirleri", 120],
    "V.": ["Temettü Gelirleri", 10],
    "VI.": ["Ticari Kâr/Zarar (Net)", 50],
    "VII.": ["Diğer Faaliyet Gelirleri", 70],
    "VIII.": ["Faaliyet Brüt Kârı", 650],
    "IX.": ["Beklenen Zarar Karşılıkları (-)", 100],
    "X.": ["Personel Giderleri (-)", 130],
    "XI.": ["Diğer Faaliyet Giderleri (-)", 170],
    "XII.": ["Net Faaliyet Kârı", 250],
    "XV.": ["Net Parasal Pozisyon Kârı/(Zararı)", -25],
    "XVI.": ["Vergi Öncesi Kâr", 225],
    "XVII.": ["Vergi Karşılığı (±)", 45],
    "XVIII.": ["Sürdürülen Faaliyetler Dönem Net Kârı", 180],
    "XXIV.": ["Dönem Net Kâr/Zararı", 180],
  });
}

/** What `bank_audit_pl_roles` resolves for that filing. */
const COMPRESSED_ROLES = {
  gross: "VIII.",
  opex_personnel: "X.",
  opex_other: "XI.",
  net_op: "XII.",
  pretax: "XVI.",
  tax: "XVII.",
  cont_net: "XVIII.",
  period_net: "XXIV.",
} as const;

describe("compressed template — the participation-bank ordinal shift", () => {
  it("renders correctly when the filer's own roles are supplied", () => {
    const g = buildPlSankey(compressedTemplateBank(), COMPRESSED_ROLES);

    expect(g.renderable, `notes: ${g.notes.join(" | ")}`).toBe(true);
    assertFluxConserved(g);

    // The bottom line is present and right — not blank.
    const result = g.nodes.find((n) => n.kind === "result");
    expect(result, "no result node — the bottom line rendered blank").toBeDefined();
    expect(result!.reported).toBe(180);
  });

  it("never draws net operating PROFIT as an expense", () => {
    const g = buildPlSankey(compressedTemplateBank(), COMPRESSED_ROLES);

    // XII. is net operating profit here. No terminal expense node may carry it.
    for (const n of g.nodes.filter((x) => x.kind === "deduction")) {
      expect(
        n.reported == null || Math.abs(n.reported) !== 250,
        `deduction node "${n.label}" carries the net-operating-profit figure`,
      ).toBe(true);
      expect(n.label, "a deduction is labelled as the operating result").not.toMatch(/Net Operating/i);
    }
  });

  it("REGRESSION: without the role map the same filing renders wrong", () => {
    // This is the shipped defect, pinned. Read against the standard ordinals,
    // XI. (here "Diğer Faaliyet Giderleri" = 170) and XII. (NET OPERATING PROFIT
    // = 250) are both taken as opex, the pre-tax/tax/net chain reads lines that
    // are one ordinal off, and XXV. does not exist at all.
    const g = buildPlSankey(compressedTemplateBank()); // no roles → defaults

    // It must NOT silently render a plausible-looking but wrong flow.
    const bottomLine = g.nodes.find((n) => n.kind === "result")?.reported ?? null;
    const wrong = !g.renderable || bottomLine !== 180;
    expect(
      wrong,
      "the default ordinals happened to produce the right answer — if the " +
        "template changed, update this test; do not delete the role map",
    ).toBe(true);
  });

  it("falls back to standard ordinals for a standard filing", () => {
    // A bank on the normal template must be unaffected by the new parameter,
    // whether or not roles are passed.
    const withoutRoles = buildPlSankey(plainBank());
    const withRoles = buildPlSankey(plainBank(), {
      gross: "VIII.", opex_personnel: "XI.", opex_other: "XII.", net_op: "XIII.",
      pretax: "XVII.", tax: "XVIII.", cont_net: "XIX.", period_net: "XXV.",
    });
    expect(withoutRoles.renderable).toBe(true);
    expect(withRoles.renderable).toBe(true);
    expect(withRoles.nodes.find((n) => n.kind === "result")?.reported)
      .toBe(withoutRoles.nodes.find((n) => n.kind === "result")?.reported);
  });
});
