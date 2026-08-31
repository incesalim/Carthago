import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { BankTabs } from "./BankTabs";

vi.mock("@/i18n/use-text", () => ({ useText: () => (value: unknown) => value }));
vi.mock("@/app/lib/cn", () => import("../../lib/cn"));

describe("bank tab navigation", () => {
  it("keeps financial controls on every tab so a round trip does not reset them", () => {
    const html = renderToStaticMarkup(<BankTabs ticker="AKBNK" active="financials"
      query="statement=is&mode=yoy&view=annual&kind=consolidated" />);
    const links = [...html.matchAll(/href="([^"]+)"/g)].map((match) =>
      new URL(match[1].replaceAll("&amp;", "&"), "https://carthago.app"));
    expect(links).toHaveLength(5);
    expect(links.map((link) => link.searchParams.get("tab"))).toEqual([null, "financials", "risk", "ownership", "news"]);
    for (const link of links) {
      expect(link.pathname).toBe("/banks/AKBNK");
      expect(link.searchParams.get("statement")).toBe("is");
      expect(link.searchParams.get("mode")).toBe("yoy");
      expect(link.searchParams.get("view")).toBe("annual");
      expect(link.searchParams.get("kind")).toBe("consolidated");
    }
  });
});
