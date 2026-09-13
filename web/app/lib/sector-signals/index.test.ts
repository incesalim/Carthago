import { afterEach, describe, expect, it, vi } from "vitest";
import type { SectorSignal } from "./types";

const mocks = vi.hoisted(() => ({
  overview: vi.fn<() => Promise<SectorSignal[]>>(),
  credit: vi.fn<() => Promise<SectorSignal[]>>(),
  deposits: vi.fn<() => Promise<SectorSignal[]>>(),
  liquidity: vi.fn<() => Promise<SectorSignal[]>>(),
  asset: vi.fn<() => Promise<SectorSignal[]>>(),
  capital: vi.fn<() => Promise<SectorSignal[]>>(),
  profitability: vi.fn<() => Promise<SectorSignal[]>>(),
}));
vi.mock("./overview", () => ({ loadOverviewSignals: mocks.overview }));
vi.mock("./credit", () => ({ loadCreditSignals: mocks.credit }));
vi.mock("./deposits", () => ({ loadDepositsSignals: mocks.deposits }));
vi.mock("./liquidity", () => ({ loadLiquiditySignals: mocks.liquidity }));
vi.mock("./asset-quality", () => ({ loadAssetQualitySignals: mocks.asset }));
vi.mock("./capital", () => ({ loadCapitalSignals: mocks.capital }));
vi.mock("./profitability", () => ({ loadProfitabilitySignals: mocks.profitability }));
import { loadSignalSnapshot } from "./index";

const signal: SectorSignal = {
  id: "credit:real_credit_contraction", sector: "credit", state: "unavailable",
  title: { en: "Real credit", tr: "Reel kredi" }, summary: { en: "CPI missing", tr: "TÜFE eksik" },
  criterion: { en: "Below zero", tr: "Sıfırın altında" }, source: { en: "BDDK; CPI", tr: "BDDK; TÜFE" },
  asOf: null, cadence: "mixed", rule: "real < 0", href: "/credit#growth",
  facts: [{ key: "real", label: { en: "Growth", tr: "Büyüme" }, value: null, unit: "percent", asOf: null }],
};
function reset() {
  Object.values(mocks).forEach(mock => mock.mockResolvedValue([]));
  mocks.credit.mockResolvedValue([signal]);
  vi.spyOn(console, "error").mockImplementation(() => {});
}
afterEach(() => vi.restoreAllMocks());

describe("research snapshot failure boundaries", () => {
  it("retains null facts and records failed topics separately from non-triggered conditions", async () => {
    reset();
    mocks.deposits.mockRejectedValue(new Error("D1 unavailable"));
    const snapshot = await loadSignalSnapshot();
    expect(snapshot.failedSectors).toEqual(["deposits"]);
    expect(snapshot.signals).toEqual([signal]);
    expect(snapshot.basis).toBe("latest-available");
    expect(JSON.parse(JSON.stringify(snapshot)).signals[0].facts[0].value).toBeNull();
  });
  it("does not expose non-finite values as null after JSON serialization", async () => {
    reset();
    mocks.credit.mockResolvedValue([{ ...signal, facts: [{ ...signal.facts[0], value: Number.NaN }] }]);
    expect((await loadSignalSnapshot()).failedSectors).toEqual(["credit"]);
  });
  it("rejects ambiguous duplicated identities instead of silently dropping observations", async () => {
    reset();
    mocks.credit.mockResolvedValue([signal, signal]);
    const snapshot = await loadSignalSnapshot();
    expect(snapshot.signals).toEqual([]);
    expect(snapshot.failedSectors).toEqual(["credit"]);
  });
});
