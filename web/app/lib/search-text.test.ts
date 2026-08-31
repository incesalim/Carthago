import { describe, expect, it } from "vitest";
import { normalizeSearchText } from "./search-text";

describe("bank search", () => {
  it.each(["iş", "İş", "İŞ", "is", "IS", "ıŞ"])("finds İş Bankası with %s", (query) => {
    expect(normalizeSearchText("İş Bankası").includes(normalizeSearchText(query))).toBe(true);
  });

  it.each([
    ["VakıfBank", "vakif"],
    ["Yapı Kredi", "YAPI"],
    ["Şekerbank", "seker"],
    ["Dünya Katılım", "dunya katilim"],
    ["İş Bankası", "i\u0307s\u0327"],
    ["ISCTR", "isctr"],
    ["ICBCT", "icbct"],
  ])("finds %s with %s", (name, query) => {
    expect(normalizeSearchText(name).includes(normalizeSearchText(query))).toBe(true);
  });

  it("ignores surrounding whitespace and keeps unmatched banks out", () => {
    expect(normalizeSearchText("  İŞ  ")).toBe("is");
    expect(normalizeSearchText("Akbank").includes(normalizeSearchText("İş"))).toBe(false);
  });
});
