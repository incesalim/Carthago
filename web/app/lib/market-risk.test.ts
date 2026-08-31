import { beforeEach, describe, expect, it, vi } from "vitest";
import { bankMarketRiskDetail } from "./market-risk";

const rows = vi.hoisted(() => ({
  fx: [] as { bank_ticker: string; period: string; currency: string; net_position: number | null }[],
  cap: [] as { bank_ticker: string; period: string; total_capital: number | null }[],
  rp: [] as { bank_ticker: string; period: string; bucket: string; gap: number | null; rate_sensitive_assets: number | null }[],
}));

vi.mock("./db", () => ({
  cachedAll: vi.fn(async (sql: string) => {
    if (sql.includes("bank_audit_fx_position")) return rows.fx;
    if (sql.includes("bank_audit_capital")) return rows.cap;
    if (sql.includes("bank_audit_repricing")) return rows.rp;
    throw new Error(`Unexpected query: ${sql}`);
  }),
}));

beforeEach(() => {
  rows.fx = [];
  rows.cap = [{ bank_ticker: "AKBNK", period: "2026Q2", total_capital: 1_000 }];
  rows.rp = [];
});

describe("bankMarketRiskDetail signed FX headline", () => {
  it.each([-25, 0, 25])("preserves the direction and disclosed zero in TOTAL %s", async (net_position) => {
    rows.fx = [{ bank_ticker: "AKBNK", period: "2026Q2", currency: "TOTAL", net_position }];
    const detail = await bankMarketRiskDetail("unconsolidated", "AKBNK");
    expect(detail.fx.totalPct).toBe(net_position / 10);
    expect(detail.fx.period).toBe("2026Q2");
    expect(detail.hasData).toBe(true);
  });

  it.each([null, undefined])("does not infer a missing TOTAL from currency subtotals (%s)", async (total) => {
    rows.fx = [{ bank_ticker: "AKBNK", period: "2026Q2", currency: "USD", net_position: -25 }];
    if (total === null) rows.fx.push({ bank_ticker: "AKBNK", period: "2026Q2", currency: "TOTAL", net_position: null });
    const detail = await bankMarketRiskDetail("unconsolidated", "AKBNK");
    expect(detail.fx.items[0].pct).toBe(-2.5);
    expect(detail.fx.totalPct).toBeNull();
  });

  it("uses capital from the FX quarter even when repricing and capital have newer data", async () => {
    rows.fx = [{ bank_ticker: "AKBNK", period: "2026Q1", currency: "TOTAL", net_position: -25 }];
    rows.cap.push({ bank_ticker: "AKBNK", period: "2026Q1", total_capital: 500 });
    rows.rp = [{ bank_ticker: "AKBNK", period: "2026Q2", bucket: "total", gap: 0, rate_sensitive_assets: 10_000 }];
    const detail = await bankMarketRiskDetail("unconsolidated", "AKBNK");
    expect(detail.period).toBe("2026Q2");
    expect(detail.fx.period).toBe("2026Q1");
    expect(detail.fx.totalPct).toBe(-5);
  });

  it("withholds the ratio when capital exists only in another quarter or bank", async () => {
    rows.fx = [{ bank_ticker: "AKBNK", period: "2026Q1", currency: "TOTAL", net_position: -25 }];
    rows.cap.push({ bank_ticker: "GARAN", period: "2026Q1", total_capital: 500 });
    const detail = await bankMarketRiskDetail("unconsolidated", "AKBNK");
    expect(detail.fx.period).toBe("2026Q1");
    expect(detail.fx.totalPct).toBeNull();
  });
});
