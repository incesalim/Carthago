import { describe, expect, it } from "vitest";
import { buildCreditSignals, type CreditSignalInput } from "./credit";
import { buildDepositsSignals, type DepositSignalInput } from "./deposits";
import { buildLiquiditySignals, type LiquiditySignalInput } from "./liquidity";
import type { Pt } from "../series";
import type { SectorSignal } from "./types";

const latest = "2026-09-04";
const point = (value: number | null, period = latest): Pt[] => [{ period, value }];
const weekly = (values: (number | null)[]): Pt[] => values.map((value, i) => ({
  value, period: new Date(Date.parse(`${latest}T00:00:00Z`) - (values.length - 1 - i) * 7 * 86400000).toISOString().slice(0, 10),
}));
const get = (signals: SectorSignal[], code: string) => signals.find((s) => s.id.endsWith(`:${code}`))!;
const fact = (signal: SectorSignal, key: string) => signal.facts.find((f) => f.key === key)!;
const credit = (overrides: Partial<CreditSignalInput> = {}): CreditSignalInput => ({
  nominal: weekly(Array(8).fill(30)), realConstantFx: point(0), auto: weekly(Array(8).fill(-2)), autoLevels: point(40000), cards: weekly(Array(8).fill(35)), generalPurpose: weekly(Array(8).fill(34)), ...overrides,
});
const deposits = (overrides: Partial<DepositSignalInput> = {}): DepositSignalInput => ({
  depositGrowth: point(30), loanGrowth: point(33), tl: weekly(Array(53).fill(60)), fx: weekly(Array(53).fill(40)), maturity: [{ period: "2026-08", demand: 30, maturity_1m: 30, maturity_1_3m: 25, maturity_3_6m: 5, maturity_6_12m: 5, maturity_over_12m: 5 }], publishedLdr: point(100, "2026-08"), cpi: new Map([["2026-09", 30]]), ...overrides,
});
const liquidity = (overrides: Partial<LiquiditySignalInput> = {}): LiquiditySignalInput => ({
  privateLdr: point(95), dollarization: [{ period: "2025-09-05", value: 40 }, { period: latest, value: 41 }], lcr: point(100, "2026Q2"), nsfr: point(100, "2026Q2"),
  evds: {
    "TP.AB.TOPLAM": [{ period_date: latest, value: 100000 }],
    "TP.BL054": [{ period_date: latest, value: 80 * 40 * 1000000 }],
    "TP.BL122": [{ period_date: latest, value: 0 }],
    "TP.DK.USD.A": [{ period_date: latest, value: 40 }],
    "TP.APIFON3": [{ period_date: "2026-09-08", value: 0 }],
  },
  forwards: [{ period_date: "2026-08-31", value: -20000 }], ...overrides,
});

describe("funding research signal inventory", () => {
  it("retains all 15 unique legacy IDs, rules, bilingual explanations, dates and numeric facts", () => {
    const signals = [...buildCreditSignals(credit()), ...buildDepositsSignals(deposits()), ...buildLiquiditySignals(liquidity())];
    expect(signals.map((s) => s.id)).toEqual([
      "credit:real_credit_contraction", "credit:auto_contraction", "credit:unsecured_retail_hot",
      "deposits:reprice-cliff", "deposits:funding-gap", "deposits:real-base", "deposits:dollarization", "deposits:funding-stretch",
      "liquidity:thin-own-buffer", "liquidity:swap-dependence", "liquidity:tl-deficit", "liquidity:private-ldr", "liquidity:lcr-floor", "liquidity:nsfr-floor", "liquidity:re-dollarization",
    ]);
    for (const signal of signals) {
      expect(signal.rule.length).toBeGreaterThan(5);
      expect(signal.asOf).toBeTruthy();
      expect(signal.facts.length).toBeGreaterThan(0);
      for (const text of [signal.title, signal.summary, signal.criterion, signal.source]) {
        expect(text.en.length).toBeGreaterThan(5);
        expect(text.tr.length).toBeGreaterThan(5);
      }
      for (const f of signal.facts) expect(f.value == null || Number.isFinite(f.value)).toBe(true);
    }
  });
  it("does not clear any condition when every required input is missing", () => {
    const signals = [
      ...buildCreditSignals({ nominal: [], realConstantFx: [], auto: [], autoLevels: [], cards: [], generalPurpose: [] }),
      ...buildDepositsSignals({ depositGrowth: [], loanGrowth: [], tl: [], fx: [], maturity: [], publishedLdr: [], cpi: new Map() }),
      ...buildLiquiditySignals({ privateLdr: [], dollarization: [], lcr: [], nsfr: [], evds: {}, forwards: [] }),
    ];
    expect(signals).toHaveLength(15);
    expect(signals.every((s) => s.state === "unavailable")).toBe(true);
  });
});

describe("credit conditions", () => {
  it.each([[-0.01, "active"], [0, "clear"], [0.01, "clear"], [null, "unavailable"]] as const)("keeps the strict zero boundary for real credit: %s", (rate, state) => {
    expect(get(buildCreditSignals(credit({ realConstantFx: point(rate) })), "real_credit_contraction").state).toBe(state);
  });
  it("distinguishes seven negative observations after a positive one from eight negatives", () => {
    const seven = get(buildCreditSignals(credit({ auto: weekly([1, ...Array(7).fill(-1)]) })), "auto_contraction");
    const eight = get(buildCreditSignals(credit()), "auto_contraction");
    expect(seven.state).toBe("clear");
    expect(eight.state).toBe("active");
    expect(seven.rule).toBe("auto_yoy < 0 for 7w");
    expect(eight.rule).toBe("auto_yoy < 0 for 8w");
    expect(fact(eight, "loan_book").value).toBe(40);
    expect(fact(eight, "loan_book").unit).toBe("TRYbn");
  });
  it("does not clear an eight-observation run from only seven observations or an interrupted history", () => {
    for (const auto of [weekly(Array(7).fill(-1)), weekly([null, ...Array(7).fill(-1)])]) {
      expect(get(buildCreditSignals(credit({ auto })), "auto_contraction").state).toBe("unavailable");
    }
  });
  it("retains an active auto growth condition with a missing supplementary balance and explains the missing size", () => {
    const signal = get(buildCreditSignals(credit({ autoLevels: [] })), "auto_contraction");
    expect(signal.state).toBe("active");
    expect(fact(signal, "loan_book").value).toBeNull();
    expect(signal.summary.en).toContain("balance is unavailable");
  });
  it("requires both unsecured products to exceed the same-date sector comparator for eight observations", () => {
    expect(get(buildCreditSignals(credit()), "unsecured_retail_hot").state).toBe("active");
    expect(get(buildCreditSignals(credit({ generalPurpose: weekly([...Array(7).fill(34), 30]) })), "unsecured_retail_hot").state).toBe("clear");
    expect(get(buildCreditSignals(credit({ nominal: weekly([...Array(7).fill(30), null]) })), "unsecured_retail_hot").state).toBe("unavailable");
  });
  it("keeps the real series' own observation date when CPI lags nominal growth", () => {
    const signal = get(buildCreditSignals(credit({ realConstantFx: point(-1.8, "2026-08-28") })), "real_credit_contraction");
    expect(signal.asOf).toBe("2026-08-28");
    expect(fact(signal, "nominal_growth").asOf).toBe(latest);
  });
});

describe("deposit conditions", () => {
  it("keeps strict 85%, 3pp, zero and 100% thresholds", () => {
    const at = buildDepositsSignals(deposits());
    for (const code of ["reprice-cliff", "funding-gap", "real-base", "funding-stretch"]) expect(get(at, code).state).toBe("clear");
    const input = deposits({ loanGrowth: point(33.01), publishedLdr: point(100.01), cpi: new Map([["2026-09", 30.01]]) });
    input.maturity[0].demand = 31;
    const beyond = buildDepositsSignals(input);
    for (const code of ["reprice-cliff", "funding-gap", "real-base", "funding-stretch"]) expect(get(beyond, code).state).toBe("active");
  });
  it("does not treat undisclosed or zero-total maturity buckets as a valid clear condition", () => {
    const absent = deposits();
    absent.maturity[0].maturity_over_12m = null;
    expect(get(buildDepositsSignals(absent), "reprice-cliff").state).toBe("unavailable");
    const zero = deposits();
    zero.maturity = [{ period: "2026-08", demand: 0, maturity_1m: 0, maturity_1_3m: 0, maturity_3_6m: 0, maturity_6_12m: 0, maturity_over_12m: 0 }];
    expect(get(buildDepositsSignals(zero), "reprice-cliff").state).toBe("unavailable");
  });
  it("requires a common weekly date for the funding gap", () => {
    expect(get(buildDepositsSignals(deposits({ loanGrowth: point(35, "2026-08-28") })), "funding-gap").state).toBe("unavailable");
  });
  it("preserves Fisher deflation, actual CPI and lagged observation dates", () => {
    const signal = get(buildDepositsSignals(deposits({ depositGrowth: [{ period: "2026-08-28", value: 20 }, { period: latest, value: 40 }], cpi: new Map([["2026-08", 30]]) })), "real-base");
    expect(signal.state).toBe("active");
    expect(signal.rule).toBe("deposits_52w − cpi_yoy < 0");
    expect(fact(signal, "real_growth").value).toBeCloseTo((1.2 / 1.3 - 1) * 100);
    expect(fact(signal, "annual_cpi")).toMatchObject({ value: 30, asOf: "2026-08" });
    expect(fact(signal, "matched_nominal_growth")).toMatchObject({ value: 20, asOf: "2026-08-28" });
    expect(fact(signal, "latest_nominal_growth")).toMatchObject({ value: 40, asOf: latest });
  });
  it("keeps the 52-observation FX comparison and strict +1pp boundary", () => {
    const input = deposits();
    input.tl[input.tl.length - 1].value = 59;
    input.fx[input.fx.length - 1].value = 41;
    expect(get(buildDepositsSignals(input), "dollarization").state).toBe("clear");
    input.tl[input.tl.length - 1].value = 58.9;
    input.fx[input.fx.length - 1].value = 41.1;
    const active = get(buildDepositsSignals(input), "dollarization");
    expect(active.state).toBe("active");
    expect(fact(active, "base_share").asOf).toBe("2025-09-05");
    input.fx = input.fx.slice(1);
    expect(get(buildDepositsSignals(input), "dollarization").state).toBe("unavailable");
  });
  it("marks a missing latest FX input unavailable instead of scoring an older complete pair", () => {
    const input = deposits();
    input.fx[input.fx.length - 1].value = null;
    expect(get(buildDepositsSignals(input), "dollarization").state).toBe("unavailable");
  });
});

describe("liquidity conditions", () => {
  it("preserves strict 25%, 95%, 100% and +1pp boundaries", () => {
    const at = buildLiquiditySignals(liquidity());
    for (const code of ["swap-dependence", "private-ldr", "lcr-floor", "nsfr-floor", "re-dollarization", "tl-deficit"]) expect(get(at, code).state).toBe("clear");
    const input = liquidity({ privateLdr: point(95.01), lcr: point(99.99), nsfr: point(99.99), forwards: [{ period_date: "2026-08-31", value: -20001 }], dollarization: [{ period: "2025-09-05", value: 40 }, { period: latest, value: 41.01 }] });
    input.evds["TP.APIFON3"][0].value = -1;
    const beyond = buildLiquiditySignals(input);
    for (const code of ["swap-dependence", "private-ldr", "lcr-floor", "nsfr-floor", "re-dollarization", "tl-deficit"]) expect(get(beyond, code).state).toBe("active");
  });
  it("keeps the strict 40% own-reserve boundary, original derivation and USD-million facts", () => {
    const input = liquidity({ forwards: [{ period_date: "2026-08-31", value: -40000 }] });
    const at = get(buildLiquiditySignals(input), "thin-own-buffer");
    expect(at.state).toBe("clear");
    expect(fact(at, "own_share").value).toBe(40);
    expect(fact(at, "gross_reserves")).toMatchObject({ value: 100000, unit: "USDmn", asOf: latest });
    expect(fact(at, "net_reserves").value).toBe(80000);
    input.forwards[0].value = -40001;
    expect(get(buildLiquiditySignals(input), "thin-own-buffer").state).toBe("active");
  });
  it("exposes monthly swap and weekly reserve dates separately", () => {
    const signal = get(buildLiquiditySignals(liquidity()), "swap-dependence");
    expect(signal.cadence).toBe("mixed");
    expect(fact(signal, "swap_stock")).toMatchObject({ value: 20000, asOf: "2026-08-31" });
    expect(fact(signal, "net_reserves").asOf).toBe(latest);
  });
  it("does not interpret a missing monthly swap position as zero swaps", () => {
    const signals = buildLiquiditySignals(liquidity({ forwards: [] }));
    expect(get(signals, "thin-own-buffer").state).toBe("unavailable");
    expect(get(signals, "swap-dependence").state).toBe("unavailable");
  });
  it.each(["TP.AB.TOPLAM", "TP.BL054", "TP.BL122", "TP.DK.USD.A"])("never coerces a runtime null reserve leg into zero: %s", (code) => {
    const input = liquidity();
    input.evds[code][0].value = null as unknown as number;
    const signals = buildLiquiditySignals(input);
    expect(get(signals, "thin-own-buffer").state).toBe("unavailable");
    expect(get(signals, "swap-dependence").state).toBe("unavailable");
    expect(fact(get(signals, "thin-own-buffer"), "own_reserves").value).toBeNull();
  });
  it("does not score an older reserve tuple when the latest balance-sheet input is incomplete", () => {
    const input = liquidity();
    input.evds["TP.BL054"].push({ period_date: "2026-09-11", value: 80 * 40 * 1000000 });
    const signals = buildLiquiditySignals(input);
    expect(get(signals, "thin-own-buffer").state).toBe("unavailable");
    expect(get(signals, "swap-dependence").state).toBe("unavailable");
  });
  it("uses the last observation on or before 364 days earlier, retaining its actual date", () => {
    const signal = get(buildLiquiditySignals(liquidity({ dollarization: [{ period: "2025-08-29", value: 30 }, { period: "2025-09-06", value: 50 }, { period: latest, value: 32 }] })), "re-dollarization");
    expect(signal.state).toBe("active");
    expect(fact(signal, "base_share").asOf).toBe("2025-08-29");
    expect(fact(signal, "share_change").value).toBe(2);
  });
  it("does not borrow an older available annual base through an explicitly missing base observation", () => {
    const signal = get(buildLiquiditySignals(liquidity({ dollarization: [{ period: "2025-08-29", value: 30 }, { period: "2025-09-05", value: null }, { period: latest, value: 32 }] })), "re-dollarization");
    expect(signal.state).toBe("unavailable");
  });
  it("retains distinct daily and quarterly dates and null quarterly disclosures", () => {
    const signals = buildLiquiditySignals(liquidity({ lcr: point(null, "2026Q2") }));
    expect(get(signals, "tl-deficit")).toMatchObject({ cadence: "daily", asOf: "2026-09-08" });
    expect(get(signals, "lcr-floor")).toMatchObject({ state: "unavailable", cadence: "quarterly", asOf: "2026Q2" });
    expect(get(signals, "nsfr-floor")).toMatchObject({ state: "clear", cadence: "quarterly", asOf: "2026Q2" });
  });
});
