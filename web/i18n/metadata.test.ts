import { describe, expect, it, vi } from "vitest";

const state = vi.hoisted(() => ({ locale: "en" }));
vi.mock("next-intl/server", () => ({ getLocale: vi.fn(async () => state.locale) }));
import { localizeMetadata } from "./metadata";

describe("localized metadata", () => {
  it("translates English titles without changing canonical URLs or indexing rules", async () => {
    const source = {
      title: { absolute: "Turkish Banking Sector Data, Financials & Analytics — Carthago" },
      description: "Turkish Banking Sector Data",
      alternates: { canonical: "/" },
      robots: { index: false, follow: false },
      openGraph: { title: "Turkish Banking Sector Data", url: "https://carthago.app" },
    };
    state.locale = "tr";
    const tr = await localizeMetadata(source);
    expect(tr.title).toEqual({ absolute: "Türkiye Bankacılık Sektörü Verileri, Finansallar ve Analiz — Carthago" });
    expect(tr.description).toBe("Türkiye Bankacılık Sektörü Verileri");
    expect(tr.alternates).toEqual(source.alternates);
    expect(tr.robots).toEqual(source.robots);
    expect(tr.openGraph).toMatchObject({ locale: "tr_TR", url: "https://carthago.app" });
    state.locale = "en";
    const en = await localizeMetadata(source);
    expect(en.title).toEqual(source.title);
    expect(en.description).toBe(source.description);
  });
});
