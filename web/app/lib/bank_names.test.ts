import { describe, expect, it } from "vitest";
import {
  BANK_COUNT,
  PEER_BANK_COUNT,
  PEER_EXCLUDED_TICKERS,
  isPeerExcluded,
  peerExclusionSql,
  peersOnly,
} from "./bank_names";

/**
 * The rule these pin: a bank carried in the data is not automatically a peer.
 * Takasbank is BDDK-licensed and files standard BRSA reports, but it is the
 * central clearing house — no deposits, ~2.5% of assets in customer loans — so
 * putting it inside a sector ratio, a rank or an HHI compares unlike with unlike.
 *
 * The 2026-07-13 sector-page audit found it inside the audited CAR / LCR / stage
 * aggregates: `heatmap.ts` and `market-share.ts` enforced the exclusion, and
 * `audit-ratios.ts` / `credit-risk.ts` / `market-risk.ts` did not. These tests
 * cover the two helpers those three modules now share, so the next aggregate has
 * something to reach for instead of re-deriving the filter.
 */
describe("peer universe", () => {
  it("excludes the CCP, case-insensitively, and nobody else", () => {
    expect(isPeerExcluded("TAKAS")).toBe(true);
    expect(isPeerExcluded("takas")).toBe(true);
    // TSKB is a development bank and a genuine peer — one letter apart from the
    // exclusion, and the two have been confused before.
    expect(isPeerExcluded("TSKB")).toBe(false);
    expect(isPeerExcluded("GARAN")).toBe(false);
  });

  it("counts the peer population as the universe minus the exclusions", () => {
    expect(PEER_BANK_COUNT).toBe(BANK_COUNT - PEER_EXCLUDED_TICKERS.size);
    expect(PEER_BANK_COUNT).toBeLessThan(BANK_COUNT);
  });
});

describe("peersOnly", () => {
  it("drops excluded rows and keeps the rest in order", () => {
    const rows = [
      { bank_ticker: "GARAN", v: 1 },
      { bank_ticker: "TAKAS", v: 2 },
      { bank_ticker: "AKBNK", v: 3 },
    ];
    expect(peersOnly(rows).map((r) => r.v)).toEqual([1, 3]);
  });

  it("does not mutate the input (per-bank views read the same array)", () => {
    const rows = [{ bank_ticker: "TAKAS", v: 1 }];
    const out = peersOnly(rows);
    expect(out).toHaveLength(0);
    expect(rows).toHaveLength(1);
  });
});

describe("peerExclusionSql", () => {
  it("binds tickers as params — never interpolates them into SQL", () => {
    const { clause, params } = peerExclusionSql();
    expect(clause).toBe(" AND bank_ticker NOT IN (?)");
    expect(params).toEqual(["TAKAS"]);
    // one placeholder per param, always
    expect(clause.split("?").length - 1).toBe(params.length);
    expect(clause).not.toContain("TAKAS");
  });

  it("qualifies the column when the query joins", () => {
    expect(peerExclusionSql("l.bank_ticker").clause).toBe(
      " AND l.bank_ticker NOT IN (?)",
    );
  });
});
