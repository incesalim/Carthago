import { beforeEach, describe, expect, it, vi } from "vitest";
import type { SignalSnapshot } from "../../../lib/sector-signals";

const mocks = vi.hoisted(() => ({ gate: vi.fn(), load: vi.fn() }));
vi.mock("../../../lib/admin-auth", () => ({ requireAdminOr403: mocks.gate }));
vi.mock("../../../lib/sector-signals", () => ({ loadSignalSnapshot: mocks.load }));
import { GET } from "./route";

const snapshot: SignalSnapshot = {
  schema: "carthago.sector-signals.v1", basis: "latest-available", evaluatedAt: "2026-09-13T12:00:00Z", failedSectors: [],
  signals: [{
    id: "overview:real-roe", sector: "overview", state: "unavailable",
    title: { tr: "Reel getiri", en: "Real return" }, summary: { tr: "Veri eksik", en: "Data missing" },
    criterion: { tr: "Sıfırın altında", en: "Below zero" }, rule: "real_roe < 0", asOf: null, cadence: "monthly",
    source: { tr: "BDDK ve TÜFE", en: "BDDK and CPI" }, href: "/profitability#returns",
    facts: [{ key: "real-roe", label: { tr: "Reel getiri", en: "Real return" }, value: null, unit: "percent", asOf: null }],
  }],
};

beforeEach(() => {
  vi.resetAllMocks();
  mocks.gate.mockResolvedValue({ identity: { email: "admin" } });
  mocks.load.mockResolvedValue(snapshot);
});

function expectPrivate(response: Response) {
  expect(response.headers.get("Cache-Control")).toBe("private, no-store");
  expect(response.headers.get("X-Robots-Tag")).toBe("noindex, nofollow");
}

describe("internal signal API authorization", () => {
  it("returns a private denial without reading or returning observations", async () => {
    mocks.gate.mockResolvedValue({ response: Response.json({ error: "forbidden" }, { status: 403 }) });
    const response = await GET();
    expect(response.status).toBe(403);
    expectPrivate(response);
    expect(await response.json()).toEqual({ error: "forbidden" });
    expect(mocks.load).not.toHaveBeenCalled();
  });

  it("waits for authorization before loading the authenticated snapshot", async () => {
    let allow!: (gate: { identity: { email: string } }) => void;
    mocks.gate.mockReturnValue(new Promise(resolve => { allow = resolve; }));
    const pending = GET();
    await Promise.resolve();
    expect(mocks.load).not.toHaveBeenCalled();
    allow({ identity: { email: "admin" } });
    const response = await pending;
    expect(response.status).toBe(200);
    expectPrivate(response);
    expect(await response.json()).toEqual(snapshot);
    expect(mocks.load).toHaveBeenCalledTimes(1);
  });

  it("fails closed when authorization itself fails", async () => {
    mocks.gate.mockRejectedValue(new Error("authorization unavailable"));
    await expect(GET()).rejects.toThrow("authorization unavailable");
    expect(mocks.load).not.toHaveBeenCalled();
  });

  it("keeps an authenticated all-topic data failure private and unavailable", async () => {
    const failed = { ...snapshot, signals: [], failedSectors: ["overview" as const] };
    mocks.load.mockResolvedValue(failed);
    const response = await GET();
    expect(response.status).toBe(503);
    expectPrivate(response);
    expect(await response.json()).toEqual(failed);
  });

  it("does not fall back to another snapshot if collection throws", async () => {
    mocks.load.mockRejectedValue(new Error("collector unavailable"));
    await expect(GET()).rejects.toThrow("collector unavailable");
    expect(mocks.gate).toHaveBeenCalledTimes(1);
    expect(mocks.load).toHaveBeenCalledTimes(1);
  });
});
