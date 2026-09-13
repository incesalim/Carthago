import { describe, expect, it } from "vitest";
import { groupSmallMultipleRows } from "./small-multiples";

describe("small-multiple evidence preservation", () => {
  it("retains missing observations between readings and a disclosed zero", () => {
    const rows = [
      { period: "2026-03", bank_type_code: "A", value: 0 },
      { period: "2026-01", bank_type_code: "A", value: 12 },
      { period: "2026-02", bank_type_code: "A", value: null },
      { period: "2026-04", bank_type_code: "A", value: null },
    ];
    expect(groupSmallMultipleRows(rows, ["A"])[0].rows).toEqual([
      { period: "2026-01", value: 12 }, { period: "2026-02", value: null },
      { period: "2026-03", value: 0 }, { period: "2026-04", value: null },
    ]);
    expect(rows[0].period).toBe("2026-03");
  });

  it("keeps an entirely undisclosed group visible and follows the requested peer order", () => {
    expect(groupSmallMultipleRows([
      { period: "2026-01", bank_type_code: "A", value: 8 },
      { period: "2026-01", bank_type_code: "B", value: null },
    ], ["B", "A", "C"])).toEqual([
      { code: "B", rows: [{ period: "2026-01", value: null }] },
      { code: "A", rows: [{ period: "2026-01", value: 8 }] },
    ]);
  });
});
