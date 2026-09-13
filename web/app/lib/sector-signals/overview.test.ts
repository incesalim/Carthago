import { describe, expect, it } from "vitest";
import { evaluateOverviewSignals, overviewCpiAverage, type OverviewSignalInputs } from "./overview";

const monthly = (values: Array<number | null>, start = 0) => values.map((value, index) => {
  const date = new Date(Date.UTC(2025, start + index, 1));
  return { period: date.toISOString().slice(0, 7), value };
});
const input = (): OverviewSignalInputs => ({
  roe: monthly([25], 12), cpiAverage: monthly([30], 12),
  npl: monthly([1, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6], 6),
  car: monthly([18, ...Array(11).fill(18), 17]), ldr: monthly([101], 12),
});

describe("overview research-signal contract", () => {
  it("retains all four legacy identities and literal conditions with dated, bilingual facts", () => {
    const signals = evaluateOverviewSignals(input());
    expect(signals.map(signal => signal.id)).toEqual(["overview:real-roe", "overview:npl-streak", "overview:car-drift", "overview:funding-stretch"]);
    expect(signals.map(signal => signal.rule)).toEqual(["(1+roe)/(1+cpi_12m_avg) − 1 < 0", "consecutive_rise(npl) ≥ 6m", "Δcar_12m < −0.5pp", "published TL+FC loan/deposit > 100%"]);
    expect(signals.every(signal => signal.state === "active")).toBe(true);
    expect(signals.every(signal => signal.asOf === "2026-01" && signal.title.tr && signal.criterion.en && signal.facts.every(fact => fact.unit && fact.asOf))).toBe(true);
  });

  it("honours strict threshold boundaries and gives neutral inactive summaries", () => {
    const values = input();
    values.roe[0].value = 30;
    values.npl.at(-1)!.value = 1.5;
    values.car.at(-1)!.value = 17.5;
    values.ldr[0].value = 100;
    const signals = evaluateOverviewSignals(values);
    expect(signals.every(signal => signal.state === "clear")).toBe(true);
    expect(signals[0].summary.en).not.toContain("negative");
    expect(signals[2].facts.find(fact => fact.key === "car-change")?.value).toBe(-0.5);
  });

  it("never calls missing inputs clear and preserves disclosed zero", () => {
    expect(evaluateOverviewSignals({ roe: [], cpiAverage: [], npl: [], car: [], ldr: [] }).every(signal => signal.state === "unavailable")).toBe(true);
    const values = input();
    values.roe.at(-1)!.value = null;
    values.npl.at(-2)!.value = null;
    values.car[0].value = null;
    values.ldr.at(-1)!.value = 0;
    const signals = evaluateOverviewSignals(values);
    expect(signals.map(signal => signal.state)).toEqual(["unavailable", "unavailable", "unavailable", "clear"]);
    expect(signals[3].facts[0].value).toBe(0);
  });

  it("aligns ROE and CPI to the same month and refuses to fill a missing aligned value", () => {
    const values = input();
    values.roe = monthly([20, 35], 12);
    values.cpiAverage = monthly([30], 12);
    let signal = evaluateOverviewSignals(values)[0];
    expect(signal.asOf).toBe("2026-01");
    expect(signal.state).toBe("active");
    expect(signal.facts[0].value).toBe(20);
    values.roe = monthly([20, null], 12);
    values.cpiAverage = monthly([30, 30], 12);
    signal = evaluateOverviewSignals(values)[0];
    expect(signal.state).toBe("unavailable");
    expect(signal.facts[0].value).toBeNull();
  });

  it("does not count gaps as consecutive months or compare CAR against the wrong year", () => {
    const values = input();
    values.npl.splice(3, 1);
    values.car[0].period = "2024-12";
    const signals = evaluateOverviewSignals(values);
    expect(signals[1].state).toBe("unavailable");
    expect(signals[2].state).toBe("unavailable");
  });

  it("does not shift the CPI average across missing monthly index disclosures", () => {
    const raw = monthly(Array.from({ length: 30 }, (_, i) => 100 + i)).map(row => ({ period_date: `${row.period}-01`, value: row.value }));
    const complete = overviewCpiAverage(raw);
    expect(complete.at(-1)?.value).not.toBeNull();
    raw[12].value = null;
    expect(overviewCpiAverage(raw).at(-1)?.value).toBeNull();
    raw[12].value = 0;
    expect(overviewCpiAverage(raw).at(-1)?.value).toBeNull();
    raw[12].value = 112;
    raw.at(-1)!.value = null;
    const missingLatest = overviewCpiAverage(raw).at(-1)!;
    expect(missingLatest.period).toBe(raw.at(-1)!.period_date.slice(0, 7));
    expect(missingLatest.value).toBeNull();
  });
});
