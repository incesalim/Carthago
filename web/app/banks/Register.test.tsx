import { renderToStaticMarkup } from "react-dom/server";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import Register, { type RegisterRow } from "./Register";

vi.mock("@/i18n/use-text", () => ({ useText: () => (value: unknown) => value }));
vi.mock("@/app/components/BankLogo", () => ({ default: () => null }));
vi.mock("@/app/lib/heatmap-normalize", () => import("../lib/heatmap-normalize"));
vi.mock("@/app/lib/search-text", () => import("../lib/search-text"));
vi.mock("@/app/components/ui/scroll-x", () => ({ ScrollX: ({ children }: { children: ReactNode }) => children }));

describe("bank register peer medians", () => {
  it("excludes clearing institutions from every ratio and keeps undisclosed ratios missing", () => {
    const common = { groupCode: "10004", groupLabel: "Dev & Inv", assets: 100e6, periods: 18, latest: "2026Q2" };
    const rows: RegisterRow[] = [
      { ...common, ticker: "A", name: "Lender A", excluded: false, roe: 0.1, npl: null, nim: null, car: 10 },
      { ...common, ticker: "B", name: "Lender B", excluded: false, roe: 0.3, npl: 0.03, nim: null, car: 20 },
      { ...common, ticker: "TAKAS", name: "Clearing bank", excluded: true, roe: 4, npl: 0.8, nim: 0.6, car: 90 },
    ];
    const html = renderToStaticMarkup(<Register rows={rows} groups={[["10004", "Dev & Inv"]]} latest="2026Q2" maxPeriods={18} />);
    const group = html.match(/<tbody><tr>(.*?)<\/tr>/)?.[1] ?? "";
    expect(group).toContain(">20.0%</td>");
    expect(group).toContain(">3.00%</td>");
    expect(group).toContain(">—</td>");
    expect(group).toContain(">15.0%</td>");
    expect(group).not.toContain("60.00%");
  });
});
