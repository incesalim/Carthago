import { describe, expect, it } from "vitest";
import { firstQueryValue, queryChoice } from "./query-params";

describe("page query values", () => {
  it("uses the first repeated ticker without calling string methods on an array", () => {
    expect(firstQueryValue(["akbnk", "garan"])?.toUpperCase()).toBe("AKBNK");
    expect(firstQueryValue("akbnk")?.toUpperCase()).toBe("AKBNK");
    expect(firstQueryValue(undefined)).toBeUndefined();
    expect(firstQueryValue([])).toBeUndefined();
  });

  it("accepts a supported choice and rejects arbitrary URL states", () => {
    const modes = ["abs", "yoy", "real", "size"] as const;
    expect(queryChoice(["real", "size"], modes, "abs")).toBe("real");
    for (const value of [undefined, "", "bogus", "toString", ["bogus", "real"]]) {
      expect(queryChoice(value, modes, "abs")).toBe("abs");
    }
  });
});
