import { describe, it, expect } from "vitest";
import {
  buildLoansBySector,
  SECTOR_GROUPS,
  GROUP_ORDER,
  GROUP_LABELS,
} from "./loans-by-sector";

type Row = {
  year: number;
  month: number;
  item_order: number;
  item_name: string;
  is_subtotal: number;
  total_amount: number | null;
  npl_amount: number | null;
  non_cash_amount: number | null;
};

const row = (
  o: Partial<Row> & Pick<Row, "year" | "month" | "item_order" | "item_name">,
): Row => ({ is_subtotal: 1, total_amount: 0, npl_amount: 0, non_cash_amount: 0, ...o });

// Two periods, thousand-TL inputs (as stored in table 5). Consumer (cards) +
// construction + the TOPLAM grand total, which the sectors must sum to.
const fixture = (): Row[] => [
  row({ year: 2025, month: 4, item_order: 68, item_name: "Kredi Kartları**", total_amount: 4_000_000, npl_amount: 160_000 }),
  row({ year: 2025, month: 4, item_order: 27, item_name: "İnşaat", total_amount: 1_000_000, npl_amount: 30_000 }),
  row({ year: 2025, month: 4, item_order: 70, item_name: "TOPLAM", total_amount: 5_000_000, npl_amount: 190_000 }),
  row({ year: 2026, month: 4, item_order: 68, item_name: "Kredi Kartları**", total_amount: 5_000_000, npl_amount: 250_000 }),
  row({ year: 2026, month: 4, item_order: 27, item_name: "İnşaat", total_amount: 1_000_000, npl_amount: 40_000 }),
  row({ year: 2026, month: 4, item_order: 70, item_name: "TOPLAM", total_amount: 6_000_000, npl_amount: 290_000 }),
];

describe("buildLoansBySector", () => {
  const d = buildLoansBySector(fixture(), new Map());

  it("converts thousand-TL to million-TL", () => {
    expect(d.totalBook).toBe(6000); // 6,000,000 thousand ÷ 1000
  });

  it("sectors partition the total (Σ sectors = TOPLAM)", () => {
    const sum = d.sectors.reduce((a, s) => a + s.book, 0);
    expect(sum).toBeCloseTo(d.totalBook, 6);
  });

  it("group shares sum to 100%", () => {
    const sum = d.groups.reduce((a, g) => a + g.share, 0);
    expect(sum).toBeCloseTo(100, 6);
  });

  it("derives the headline NPL ratio from stock ÷ book", () => {
    expect(d.headlineNplRatio).toBeCloseTo((290 / 6000) * 100, 6);
  });

  it("maps sectors to groups with correct per-sector NPL ratios", () => {
    const cards = d.sectors.find((s) => s.itemName === "Kredi Kartları**")!;
    expect(cards.group).toBe("consumer");
    expect(cards.nplRatio).toBeCloseTo(5.0, 6); // 250 / 5000
    const consumer = d.groups.find((g) => g.key === "consumer")!;
    expect(consumer.book).toBe(5000);
  });

  it("computes nominal YoY book growth month-over-year", () => {
    expect(d.bookYoYNominal.at(-1)?.value).toBeCloseTo(20, 6); // 6000/5000 − 1
  });

  it("computes 12m group-share movers that net to zero", () => {
    const deltas = d.movers
      .filter((m) => m.shareNow != null && m.shareThen != null)
      .map((m) => (m.shareNow as number) - (m.shareThen as number));
    expect(deltas.reduce((a, x) => a + x, 0)).toBeCloseTo(0, 6);
  });
});

describe("SECTOR_GROUPS overlay", () => {
  it("has exactly the 22 bold sector labels", () => {
    expect(Object.keys(SECTOR_GROUPS)).toHaveLength(22);
  });

  it("maps every label to a group in GROUP_ORDER", () => {
    const valid = new Set<string>(GROUP_ORDER);
    for (const { group } of Object.values(SECTOR_GROUPS)) {
      expect(valid.has(group)).toBe(true);
    }
  });

  it("labels every group in GROUP_ORDER", () => {
    for (const g of GROUP_ORDER) expect(GROUP_LABELS[g]).toBeTruthy();
  });

  it("buckets an unmapped bold sector into services and still reconciles", () => {
    const rows: Row[] = [
      row({ year: 2026, month: 4, item_order: 99, item_name: "Totally New Sector", total_amount: 2_000_000 }),
      row({ year: 2026, month: 4, item_order: 68, item_name: "Kredi Kartları**", total_amount: 4_000_000 }),
      row({ year: 2026, month: 4, item_order: 70, item_name: "TOPLAM", total_amount: 6_000_000 }),
    ];
    const d2 = buildLoansBySector(rows, new Map());
    expect(d2.groups.find((g) => g.key === "services")!.book).toBe(2000);
    const sum = d2.groups.reduce((a, g) => a + g.book, 0);
    expect(sum).toBeCloseTo(d2.totalBook, 6);
  });
});
