import { describe, expect, it, vi } from "vitest";
import { cacheKey, decode, decodeCache, encodeCache, supported, type BankList, type Handshake } from "./app-api-contract.generated";

vi.mock("@/app/lib/app-api-contract.generated", () => import("./app-api-contract.generated"));
vi.mock("@/app/lib/cf-env", () => ({ getEnv: async () => ({}), envFlag: () => false }));
import { GET as handshakeRoute } from "../api/app/v1/route";
import { appResponse } from "../api/app/v1/_shared";

const handshake: Handshake = { name: "Carthago Mobile API", version: 1, minSupportedClient: 1, web: "https://carthago.app", screens: {} };
const banks: BankList = { period: "2026Q2", count: 1, peers: 0, units: { amounts: "thousand TL", rates: "percent" }, rows: [{ ticker: "TEST", name: "Test bank", type: null, typeLabel: null, peerExcluded: true, totalAssets: 0, roe: null, roeAdjusted: null, npl: null, car: 0, cet1: null, nim: null, costIncome: null, periodsHeld: 1, latestPeriodHeld: "2026Q2" }] };

describe("mobile wire contract", () => {
  it("validates the actual uncached launch response", async () => {
    const response = await handshakeRoute();
    expect(response.headers.get("Cache-Control")).toBe("no-store");
    expect(decode("handshake", await response.json())).toMatchObject({ version: 1, minSupportedClient: 1 });
  });
  it("keeps null, zero and peer exclusions distinct across the server boundary", async () => {
    const wire = await appResponse("banks", banks).json();
    expect(decode("banks", wire).rows[0]).toMatchObject({ totalAssets: 0, roe: null, peerExcluded: true });
  });
  it("accepts additive fields and refuses missing required fields", () => {
    expect(decode("banks", { ...banks, extra: true })).toMatchObject(banks);
    expect(() => decode("banks", { ...banks, peers: undefined })).toThrow("banks.peers");
  });
  it.each(["million TL", "TL", "fraction"])("refuses an incompatible unit %s", (unit) => {
    expect(() => decode("banks", { ...banks, units: { ...banks.units, amounts: unit } })).toThrow();
  });
  it.each([undefined, "0", Infinity, NaN])("refuses malformed numeric data %s", (value) => {
    expect(() => decode("banks", { ...banks, rows: [{ ...banks.rows[0], car: value }] })).toThrow("rows[0].car");
  });
  it("refuses renamed fields before any data reaches the client", () => {
    const { rows, ...rest } = banks;
    expect(() => decode("banks", { ...rest, entries: rows })).toThrow("banks.rows");
  });
  it("allows empty datasets and nullable sections", () => {
    expect(decode("news", { source: "all", count: 0, items: [], briefing: null }).items).toEqual([]);
    expect(decode("banks", { ...banks, count: 0, peers: 0, rows: [], period: null }).rows).toEqual([]);
  });
  it("negotiates both namespace and minimum build", () => {
    expect(supported(handshake, 1)).toBe(true);
    expect(supported({ ...handshake, minSupportedClient: 2 }, 1)).toBe(false);
    expect(supported({ ...handshake, version: 2 }, 2)).toBe(false);
    expect(supported(handshake, NaN)).toBe(false);
  });
});

describe("validated offline cache", () => {
  const origin = "https://carthago.app", path = "/api/app/v1/banks";
  it("retains the fetch time and factual nulls across restart", () => {
    const raw = encodeCache(origin, path, banks, 12345);
    expect(decodeCache(origin, path, raw)).toEqual({ cachedAt: 12345, data: banks });
  });
  it("isolates origins, versions and request paths", () => {
    expect(cacheKey(origin, path)).not.toBe(cacheKey("http://localhost:3000", path));
    expect(cacheKey(origin, path)).not.toBe(cacheKey(origin, "/api/app/v1/news"));
    const raw = encodeCache(origin, path, banks);
    expect(() => decodeCache("http://localhost:3000", path, raw)).toThrow();
    expect(() => decodeCache(origin, path, raw.replace('"version":1', '"version":0'))).toThrow();
    expect(() => decodeCache(origin, "/api/app/v1/news", raw)).toThrow();
  });
  it("refuses corrupt, legacy and malformed cached values", () => {
    for (const raw of ["bad json", "null", JSON.stringify({ data: banks, cachedAt: 12345 }), encodeCache(origin, path, banks).replace('"peerExcluded":true', '"peerExcluded":"true"')]) {
      expect(() => decodeCache(origin, path, raw)).toThrow();
    }
  });
});

it("requires the economy screen's fields and declared units", () => {
  const units = { gdpGrowth: "% y/y", ipGrowth: "% y/y", unemployment: "%", cpiYoY: "% y/y", cpiMoM: "% m/m", exp12m: "%", fundingMonthly: "%", realRate: "%", usdtry: "TRY", reer: "index", ca12m: "USD bn, 12m", budgetPctGdp: "% GDP, 12m" };
  const data = { headline: { gdpGrowth: null, cpiYoY: 0, unemployment: null, fundingCost: null, realRate: null, usdtry: null, ca12m: null, budgetPctGdp: null }, series: Object.fromEntries(Object.keys(units).map((key) => [key, []])), units, source: "TCMB" };
  expect(decode("economy", data).headline.cpiYoY).toBe(0);
  expect(() => decode("economy", { ...data, headline: {} })).toThrow("headline.gdpGrowth");
  expect(() => decode("economy", { ...data, series: {} })).toThrow("series.gdpGrowth");
  expect(() => decode("economy", { ...data, units: { ...units, ca12m: "USD million" } })).toThrow("units.ca12m");
});
