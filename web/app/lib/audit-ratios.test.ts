import { describe, expect, it, vi } from "vitest";
import { aggregateCapital, type CapRow } from "./audit-ratios";

// The quorum tests below drive the two SQL-backed exports, so D1 is stubbed:
// `cachedAll` answers from a fixture fleet instead of the database.
const fleet: { period: string; bank_ticker: string }[] = [
  ...Array.from({ length: 38 }, (_, i) => ({ period: "2026Q1", bank_ticker: `B${i}` })),
  { period: "2026Q2", bank_ticker: "TEB" }, // the lone early filer
];

vi.mock("./db", () => ({
  cachedAll: vi.fn(async (sql: string, params: unknown[] = []) => {
    if (/COUNT\(DISTINCT bank_ticker\)/.test(sql)) {
      const minBanks = params[params.length - 1] as number;
      const byPeriod = new Map<string, Set<string>>();
      for (const r of fleet) {
        if (!byPeriod.has(r.period)) byPeriod.set(r.period, new Set());
        byPeriod.get(r.period)!.add(r.bank_ticker);
      }
      const hit = [...byPeriod.entries()]
        .filter(([, banks]) => banks.size >= minBanks)
        .sort((a, b) => b[0].localeCompare(a[0]))[0];
      return hit ? [{ period: hit[0], n: hit[1].size }] : [];
    }
    // the row fetch — echo back whichever period it was asked for
    const period = params[1] as string;
    return fleet
      .filter((r) => r.period === period)
      .map((r) => ({
        bank_ticker: r.bank_ticker,
        period: r.period,
        cet1_capital: 10,
        additional_tier1_capital: null,
        tier1_capital: 12,
        total_capital: 16,
        total_rwa: 100,
      }));
  }),
}));

/**
 * The bug this pins: a bank missing ONE capital component used to add its RWA to
 * every denominator while adding nothing to that component's numerator, which
 * silently understated the ratio. ISCTR (2025Q4, 2026Q1) reports no CET1 while
 * carrying ~10.6% of sector RWA — that dragged the published sector CET1 from
 * 11.79% down to 10.56%.
 */
const row = (o: Partial<CapRow> & { bank_ticker: string; total_rwa: number }): CapRow => ({
  period: "2026Q1",
  cet1_capital: null,
  additional_tier1_capital: null,
  tier1_capital: null,
  total_capital: null,
  ...o,
});

const at = (out: ReturnType<typeof aggregateCapital>, code: string) =>
  out.find((r) => r.bank_type_code === code)?.value;

describe("aggregateCapital", () => {
  it("sums numerator and denominator over the SAME banks, per component", () => {
    const out = aggregateCapital([
      // a complete bank: CET1 10 / RWA 100 = 10%
      row({ bank_ticker: "A", cet1_capital: 10, tier1_capital: 12, total_capital: 16, total_rwa: 100 }),
      // no CET1 and no Tier-1 at all → must not drag CET1 down with its RWA
      row({ bank_ticker: "B", total_capital: 20, total_rwa: 100 }),
    ]);
    expect(at(out, "CET1")).toBeCloseTo(10, 6); // NOT 5 — B's RWA sits out of CET1
    expect(at(out, "CAR")).toBeCloseTo(18, 6); // both banks report total capital
  });

  it("recovers a missing CET1 from Tier-1 − AT1 (the ISCTR case)", () => {
    const out = aggregateCapital([
      row({
        bank_ticker: "ISCTR",
        cet1_capital: null,
        additional_tier1_capital: 22_061_250,
        tier1_capital: 420_695_564,
        total_capital: 515_125_095,
        total_rwa: 3_396_087_828,
      }),
    ]);
    // reproduces the ratio ISCTR prints in its own filing: 11.74%
    expect(at(out, "CET1")).toBeCloseTo(11.74, 2);
    expect(at(out, "TIER1")).toBeCloseTo(12.39, 2);
    expect(at(out, "CAR")).toBeCloseTo(15.17, 2);
  });

  it("drops a bank with no RWA (no ratio can be formed)", () => {
    const out = aggregateCapital([
      row({ bank_ticker: "A", cet1_capital: 10, total_capital: 16, total_rwa: 100 }),
      row({ bank_ticker: "Z", cet1_capital: 999, total_capital: 999, total_rwa: 0 }),
    ]);
    expect(at(out, "CET1")).toBeCloseTo(10, 6);
  });

  /**
   * The 2026-07-13 sector-page audit: TAKAS (a CCP, not a lender) was inside the
   * audited sector CAR. At 2026Q1 it moved the published figure 16.10% → 16.07%
   * and Tier-1 13.58% → 13.54%. Small, and wrong in kind: a clearing house's
   * capital over a clearing house's RWA is not part of a banking-sector ratio.
   */
  it("keeps the peer-excluded CCP out of the sector ratio", () => {
    const peers = [
      row({ bank_ticker: "A", cet1_capital: 10, tier1_capital: 12, total_capital: 16, total_rwa: 100 }),
    ];
    const withCcp = aggregateCapital([
      ...peers,
      row({ bank_ticker: "TAKAS", cet1_capital: 90, tier1_capital: 90, total_capital: 90, total_rwa: 100 }),
    ]);
    expect(at(withCcp, "CAR")).toBeCloseTo(at(aggregateCapital(peers), "CAR")!, 6);
    expect(at(withCcp, "CAR")).toBeCloseTo(16, 6); // NOT 53
  });

  it("keeps each period separate and sorted", () => {
    const out = aggregateCapital([
      row({ bank_ticker: "A", period: "2026Q1", cet1_capital: 12, total_capital: 16, total_rwa: 100 }),
      row({ bank_ticker: "A", period: "2025Q4", cet1_capital: 10, total_capital: 15, total_rwa: 100 }),
    ]);
    const cet1 = out.filter((r) => r.bank_type_code === "CET1");
    expect(cet1.map((r) => r.period)).toEqual(["2025Q4", "2026Q1"]);
    expect(cet1.map((r) => r.value)).toEqual([10, 12]);
  });
});

/**
 * The bug this pins: TEB filed 2026Q2 on 2026-07-26, alone, and a bare
 * `MAX(period)` made that quarter "the latest" the moment it was extracted. The
 * by-bank capital table — on `/capital` AND the home page — would have ranked
 * the sector's capital adequacy on a league of ONE bank, and kept doing so for
 * the weeks until the rest of the fleet filed. A quorum makes a new quarter
 * become "latest" only once enough of the fleet is in it to be a sector.
 */
describe("auditRatioLatestPeriod quorum", () => {
  it("ignores a quarter only one early filer has published", async () => {
    const { auditRatioLatestPeriod } = await import("./audit-ratios");
    expect(await auditRatioLatestPeriod()).toBe("2026Q1"); // NOT 2026Q2
  });

  it("takes the new quarter once the fleet clears the quorum", async () => {
    const { auditRatioLatestPeriod } = await import("./audit-ratios");
    expect(await auditRatioLatestPeriod("unconsolidated", 1)).toBe("2026Q2");
  });

  it("ranks banks in the quorum quarter, not the single filer's", async () => {
    const { perBankCapital } = await import("./audit-ratios");
    const { period, rows } = await perBankCapital();
    expect(period).toBe("2026Q1");
    expect(rows.length).toBe(38); // the fleet — not TEB on its own
  });
});
