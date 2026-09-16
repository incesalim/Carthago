import { describe, expect, it, vi } from "vitest";
import { negotiate } from "./compatibility-state.generated";
import type { Handshake } from "./app-api-contract.generated";

const handshake: Handshake = { name: "Carthago Mobile API", version: 1, minSupportedClient: 1, web: "https://carthago.app", screens: {} };
function deps() {
  return { fetch: vi.fn(async () => handshake), save: vi.fn(async () => {}),
    previous: vi.fn(async (): Promise<Handshake | null> => handshake), hasScreen: vi.fn(async () => true),
    offline: (error: unknown) => error === "offline", build: 1 };
}
describe("mobile startup compatibility", () => {
  it("allows a supported online launch and saves the decision", async () => {
    const d = deps();
    expect(await negotiate(d)).toBe("ready");
    expect(d.save).toHaveBeenCalledWith(handshake);
    expect(d.previous).not.toHaveBeenCalled();
  });
  it("persists an unsupported build so an offline restart cannot bypass it", async () => {
    const d = deps(), unsupported = { ...handshake, minSupportedClient: 2 };
    d.fetch.mockResolvedValue(unsupported);
    expect(await negotiate(d)).toBe("upgrade");
    expect(d.save).toHaveBeenCalledWith(unsupported);
    d.fetch.mockRejectedValue("offline"); d.previous.mockResolvedValue(unsupported);
    expect(await negotiate(d)).toBe("upgrade");
    expect(d.hasScreen).not.toHaveBeenCalled();
  });
  it("uses offline data only with a compatible handshake AND a validated saved screen", async () => {
    const d = deps(); d.fetch.mockRejectedValue("offline");
    expect(await negotiate(d)).toBe("offline");
    d.hasScreen.mockResolvedValue(false);
    expect(await negotiate(d)).toBe("unavailable");
    d.hasScreen.mockResolvedValue(true); d.previous.mockResolvedValue(null);
    expect(await negotiate(d)).toBe("unavailable");
  });
  it.each(["malformed JSON", "502", "503", "contract mismatch"])("does not label %s as offline", async (error) => {
    const d = deps(); d.fetch.mockRejectedValue(error);
    expect(await negotiate(d)).toBe("unavailable");
    expect(d.hasScreen).not.toHaveBeenCalled();
  });
  it("recovers when a retry succeeds", async () => {
    const d = deps(); d.fetch.mockRejectedValueOnce("offline");
    expect(await negotiate(d)).toBe("offline");
    expect(await negotiate(d)).toBe("ready");
  });
});
