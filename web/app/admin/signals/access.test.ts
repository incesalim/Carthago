import { existsSync, readFileSync } from "node:fs";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { SignalSnapshot } from "../../lib/sector-signals";

const mocks = vi.hoisted(() => ({
  admin: vi.fn(), load: vi.fn(), locale: vi.fn(), redirect: vi.fn(), banks: vi.fn(),
  AdminAuthError: class AdminAuthError extends Error {},
}));
vi.mock("../../lib/admin-auth", () => ({ requireAdmin: mocks.admin, AdminAuthError: mocks.AdminAuthError }));
vi.mock("../../lib/sector-signals", () => ({ loadSignalSnapshot: mocks.load }));
vi.mock("next-intl/server", () => ({ getLocale: mocks.locale }));
vi.mock("next/navigation", () => ({ redirect: mocks.redirect }));
vi.mock("./SignalsView", () => ({ default: () => null }));
vi.mock("@/app/lib/audit", () => ({ bankSummaries: mocks.banks }));

import SignalsPage, { generateMetadata } from "./page";
import SignalsRedirect from "../../signals/page";
import sitemap from "../../sitemap";

const snapshot: SignalSnapshot = {
  schema: "carthago.sector-signals.v1", basis: "latest-available", evaluatedAt: "2026-09-13T12:00:00Z",
  failedSectors: [], signals: [],
};

beforeEach(() => {
  vi.resetAllMocks();
  mocks.admin.mockResolvedValue({ email: "admin" });
  mocks.load.mockResolvedValue(snapshot);
  mocks.locale.mockResolvedValue("tr");
  mocks.banks.mockResolvedValue([]);
  mocks.redirect.mockImplementation((destination: string): never => { throw new Error(`NEXT_REDIRECT:${destination}`); });
});

describe("internal signal page authorization", () => {
  it("redirects unauthenticated readers without collecting or serializing research data", async () => {
    mocks.admin.mockRejectedValue(new mocks.AdminAuthError("login required"));
    await expect(SignalsPage()).rejects.toThrow("NEXT_REDIRECT:/admin");
    expect(mocks.redirect).toHaveBeenCalledWith("/admin");
    expect(mocks.load).not.toHaveBeenCalled();
  });

  it("does not start data work while authorization is pending", async () => {
    let allow!: (identity: { email: string }) => void;
    mocks.admin.mockReturnValue(new Promise(resolve => { allow = resolve; }));
    const pending = SignalsPage();
    await Promise.resolve();
    expect(mocks.load).not.toHaveBeenCalled();
    allow({ email: "admin" });
    const page = await pending;
    expect(mocks.load).toHaveBeenCalledTimes(1);
    expect(page.props).toMatchObject({ snapshot, locale: "tr" });
    expect(mocks.redirect).not.toHaveBeenCalled();
  });

  it("fails closed if the authorization service fails unexpectedly", async () => {
    mocks.admin.mockRejectedValue(new Error("auth unavailable"));
    await expect(SignalsPage()).rejects.toThrow("auth unavailable");
    expect(mocks.load).not.toHaveBeenCalled();
  });

  it("does not return stale or fabricated observations when collection fails", async () => {
    mocks.load.mockRejectedValue(new Error("research data unavailable"));
    await expect(SignalsPage()).rejects.toThrow("research data unavailable");
    expect(mocks.admin).toHaveBeenCalledTimes(1);
    expect(mocks.redirect).not.toHaveBeenCalled();
  });

  it("marks the private page non-indexable without reading research data for metadata", async () => {
    expect(await generateMetadata()).toMatchObject({ robots: { index: false, follow: false } });
    expect(mocks.load).not.toHaveBeenCalled();
  });
});

describe("public signal entry points", () => {
  it("keeps the former page a no-data redirect to the authenticated route", () => {
    expect(() => SignalsRedirect()).toThrow("NEXT_REDIRECT:/admin/signals");
    expect(mocks.load).not.toHaveBeenCalled();
    expect(mocks.admin).not.toHaveBeenCalled();
  });

  it("has no public data API route and no public navigation or sitemap listing", async () => {
    expect(existsSync(new URL("../../api/sector-signals/route.ts", import.meta.url))).toBe(false);
    const nav = readFileSync(new URL("../../components/Nav.tsx", import.meta.url), "utf8");
    expect(nav).not.toMatch(/href\s*[:=]\s*["']\/(?:admin\/)?signals(?:["'#?])/);
    const entries = await sitemap();
    expect(entries.filter(entry => /\/(?:admin\/)?signals(?:$|[/?#])/.test(entry.url))).toEqual([]);
    expect(mocks.load).not.toHaveBeenCalled();
  });
});
