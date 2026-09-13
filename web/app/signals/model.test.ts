import { describe, expect, it } from "vitest";
import { filterSignals, formatSignalFact } from "./model";
import { signalState, signalText, type SectorSignal } from "../lib/sector-signals/types";

const fixture = (id: string, state: SectorSignal["state"], sector: SectorSignal["sector"]): SectorSignal => ({
  id, state, sector, title: signalText("Credit conditions", "İhtiyaç kredileri"),
  summary: signalText("Observed growth", "Gözlenen büyüme"), criterion: signalText("Below zero", "Sıfırın altında"),
  source: signalText("BDDK", "BDDK"), rule: "growth < 0", asOf: "2026-08-28", cadence: "weekly", href: "/credit#growth", facts: [],
});
const signals = [fixture("credit:a", "active", "credit"), fixture("credit:b", "unavailable", "credit"), fixture("capital:c", "clear", "capital")];

describe("signal research view", () => {
  it("intersects topic, state and Turkish search without treating missing data as a clear condition", () => {
    expect(filterSignals(signals, { sector: "credit", state: "active", query: "ihtiyaç" }, "tr").map(s => s.id)).toEqual(["credit:a"]);
    expect(filterSignals(signals, { sector: "credit", state: "clear", query: "" }, "tr")).toEqual([]);
    expect(filterSignals(signals, { sector: "all", state: "unavailable", query: "sıfır" }, "tr").map(s => s.id)).toEqual(["credit:b"]);
  });
  it("keeps full records and their source dates available in the filtered export", () => {
    const result = filterSignals(signals, { sector: "all", state: "all", query: "" }, "en");
    expect(JSON.parse(JSON.stringify(result))).toEqual(signals);
    expect(result[0]).toBe(signals[0]);
  });
  it("does not infer absence of a signal from unavailable inputs", () => {
    expect(signalState(false, false)).toBe("unavailable");
    expect(signalState(false, true)).toBe("unavailable");
    expect(signalState(true, false)).toBe("clear");
    expect(signalState(true, true)).toBe("active");
  });
  it("preserves small nonzero reconciliation amounts and the stated tolerance", () => {
    const fact = { key: "gap", label: signalText("Gap", "Fark"), value: 0.001, unit: "TRYtrn" as const, asOf: "2026-04" };
    expect(formatSignalFact(fact, "tr")).toBe("1,0 milyar TL");
    expect(formatSignalFact({ ...fact, value: -0.00001 }, "en")).toBe("-0.010 bn TRY");
    expect(formatSignalFact({ ...fact, value: null }, "tr")).toBe("—");
    expect(formatSignalFact({ ...fact, value: 0 }, "en")).toBe("0.0 bn TRY");
  });
});
