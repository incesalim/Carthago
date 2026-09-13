import { describe, expect, it } from "vitest";
import { creditInsights, type SeriesPoint } from "./insights";

const point = (value: number | null, period = "2026-07-31"): SeriesPoint[] => [{ period, value }];
const base = { yoy: point(36), mom4: point(40), yoyState: point(39), yoyPrivate: point(34),
  fxShare: point(35), cardsYoY: point(42), smeYoY: point(38) };

describe("credit assessment framing", () => {
  it("leads with lending pace and groups while retaining real-growth context", () => {
    const read = creditInsights({ ...base, fxAdjusted13w: point(26),
      bridge: { nominal: 36, realFxAdj: -2, currencyPp: 8, inflationPp: 30 } });
    expect(read.headline).toContain("FX-adjusted 13-week annualized growth is 26.0%");
    expect(read.headline).toContain("State banks");
    expect(read.headline).not.toContain("mostly lira");
    expect(read.items.at(-2)?.text).toContain("shrank 2.0%");
    expect(read.items.some(item => item.text.includes("not adjusted for inflation"))).toBe(true);
  });

  it("does not claim real contraction when the real series is positive", () => {
    const read = creditInsights({ ...base,
      bridge: { nominal: 36, realFxAdj: 4, currencyPp: 2, inflationPp: 30 } });
    expect(read.items.map(item => item.text).join(" ")).not.toMatch(/not growing in real|shrank/);
    expect(read.items.at(-2)?.text).toContain("grew 4.0%");
  });

  it("does not present a stale momentum reading or invent a leading bank group", () => {
    const read = creditInsights({ ...base, yoyState: [], yoyPrivate: [],
      fxAdjusted13w: point(26, "2026-07-24") });
    expect(read.headline).not.toContain("13-week");
    expect(read.headline).not.toContain("banks");
  });

  it("retains missing latest observations as unavailable", () => {
    const read = creditInsights({ ...base, yoy: point(null), yoyState: [], yoyPrivate: [] });
    expect(read.headline).toBe("The latest annual loan-growth reading is unavailable.");
  });

  it("omits bank-group comparisons when either group trails the report date", () => {
    const read = creditInsights({ ...base, yoyState: point(50, "2026-07-24") });
    expect(read.headline).not.toContain("banks");
    expect(read.items.some(item => item.label === "Bank groups")).toBe(false);
  });

  it("compares bridge legs at their own date when the CPI series trails credit", () => {
    const read = creditInsights({ ...base, bridge: {nominal:36, nominalAtReal:39,
      asOfReal:"2026-06-26", realFxAdj:-2, currencyPp:10, inflationPp:31} });
    expect(read.headline).toContain("36.0%");
    expect(read.items.at(-1)?.text).toContain("2026-06-26");
    expect(read.items.at(-1)?.text).toContain("39.0%");
    expect(read.items.at(-1)?.text).not.toContain("36.0%");
  });
});
