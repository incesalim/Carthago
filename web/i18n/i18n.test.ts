import { describe, expect, it, vi, beforeEach } from "vitest";
import { resolveLocale, LOCALE_COOKIE } from "./config";
import { createText } from "./text";
import { formatDateLabel, formatUnitLabel } from "./format";
import { createFormatters } from "../app/lib/chart-format";
import { chartSummary, toCsv } from "../app/lib/chart-csv";
import { overviewInsights } from "../app/lib/insights";
import { seriesFinding } from "../app/lib/chart-findings";
import { bankFlags, engineGate, ordinal } from "../app/lib/bank-brief";
import { runPhrase } from "../app/lib/prose";
import tr from "./tr.json";

const { setCookie } = vi.hoisted(() => ({ setCookie: vi.fn() }));
vi.mock("next/headers", () => ({ cookies: vi.fn(async () => ({ set: setCookie })) }));
import { setLocale } from "./actions";

describe("locale selection and persistence", () => {
  beforeEach(() => setCookie.mockClear());
  it("defaults to Turkish unless the visitor explicitly saved a supported choice", () => {
    expect(resolveLocale("en")).toBe("en");
    expect(resolveLocale("tr")).toBe("tr");
    expect(resolveLocale(undefined)).toBe("tr");
    expect(resolveLocale(null)).toBe("tr");
    expect(resolveLocale("")).toBe("tr");
    expect(resolveLocale("bogus")).toBe("tr");
  });
  it("saves only supported locales in a first-party preference cookie", async () => {
    await setLocale("tr");
    expect(setCookie).toHaveBeenCalledWith(LOCALE_COOKIE, "tr", expect.objectContaining({
      httpOnly: true, sameSite: "lax", path: "/", maxAge: 31_536_000,
    }));
    await expect(setLocale("arbitrary-value")).rejects.toThrow("Unsupported locale");
    expect(setCookie).toHaveBeenCalledTimes(1);
  });
});

describe("display translation", () => {
  const en = createText("en"), tx = createText("tr");
  it("isolates locales and preserves English, unknown text, data, and null", () => {
    const data = { bank_ticker: "AKBNK", amount_fc: null, amount_tl: 0 };
    expect(tx("Overview")).toBe("Genel Bakış");
    expect(en("Overview")).toBe("Overview");
    expect(en("2026-04")).toBe("2026-04");
    expect(tx("An original source quotation, 1,234.56")).toBe("An original source quotation, 1,234.56");
    expect(tx("__proto__")).toBe("__proto__");
    expect(tx("toString")).toBe("toString");
    expect(tx(null)).toBeNull();
    expect(tx(0)).toBe(0);
    expect(tx(data)).toBe(data);
    expect(en.locale).toBe("en");
    expect(tx.locale).toBe("tr");
  });
  it("interpolates by numbered slots without changing figures or interpreting markup", () => {
    expect(tx("{0} — public", { 0: "−12.50%" })).toBe("−12.50% — kamu");
    expect(en("{0} — public", { 0: "−12.50%" })).toBe("−12.50% — public");
    expect(tx("{0} — public", { 0: "<script>source</script>" })).toBe("<script>source</script> — kamu");
    expect(tx("{0} — public")).toBe("{0} — kamu");
    expect(tx(" {0} — public ", { 0: 0 })).toBe(" 0 — kamu ");
  });
  it("never introduces a slot not present in the English template", () => {
    for (const [source, translated] of Object.entries(tr)) {
      const expected = new Set(source.match(/\{\d+\}/g) ?? []);
      for (const slot of translated.match(/\{\d+\}/g) ?? []) {
        expect(expected.has(slot), `${source}: unexpected ${slot}`).toBe(true);
      }
    }
  });
  it("formats dates and chart values without touching storage units", () => {
    expect(formatDateLabel("2026-04-30", "tr")).toBe("30 Nis 2026");
    expect(formatDateLabel("2026Q1", "tr")).toBe("2026 1.Ç");
    expect(formatDateLabel("Q1 2026", "tr")).toBe("2026 1.Ç");
    expect(formatDateLabel("APR", "tr")).toBe("Nis");
    expect(formatDateLabel("SEP 10", "tr")).toBe("10 Eyl");
    expect(formatDateLabel("OCT 24 – NOV 14", "tr")).toBe("24 Eki – 14 Kas");
    expect(formatDateLabel("AUG 4–7", "tr")).toBe("4–7 Ağu");
    expect(formatDateLabel("OCT 24 – NOV 14", "en")).toBe("OCT 24 – NOV 14");
    expect(formatDateLabel("2026-02-31", "tr")).toBe("2026-02-31");
    expect(formatUnitLabel("−₺1,234.50bn", "tr")).toBe("−₺1,234.50 milyar");
    expect(formatUnitLabel("+4.4pp/yr", "tr")).toBe("+4.4 yüzde puan/yıl");
    expect(formatUnitLabel("+4.4pp", "en")).toBe("+4.4pp");
    expect(createFormatters("tr").pct(12.5, 1)).toBe("%12,5");
    expect(createFormatters("tr").bn(1_250_000, 2)).toBe("₺1.250,00 milyar");
    expect(createFormatters("en").bn(1_250_000, 2)).toBe("₺1,250.00 bn");
  });
});

describe("localized analytical prose", () => {
  it("retains nulls, signs, and direction while translating deterministic reads", () => {
    const s = [{ period: "2026-03", value: 10 }, { period: "2026-04", value: 12 }];
    const data = { assetsYoY: s, loansYoY: [], depositsYoY: s, npl: s, car: s, ldr: s, roe: s };
    const en = overviewInsights(data), tx = overviewInsights(data, "tr");
    expect(tx.asOf).toBe(en.asOf);
    expect(tx.items.map(({ tone, href }) => ({ tone, href }))).toEqual(en.items.map(({ tone, href }) => ({ tone, href })));
    expect(tx.headline).toContain("Nis 2026");
    expect(tx.items[0].text).toContain("krediler —");
    expect(tx.items[0].text).toContain("12.0%");
    expect(tx.items[1].text).toContain("yükseliyor");
    expect(tx.items[3].text).not.toContain("m/m");
    expect(overviewInsights(data).headline).toBe(en.headline);
    expect(seriesFinding(s, { noun: "Capital adequacy" }, "tr")).toContain("yükseldi");
    expect(seriesFinding([...s].reverse(), { noun: "Capital adequacy" }, "tr")).toContain("düştü");
    expect(seriesFinding([], { noun: "Capital adequacy" }, "tr")).toBeNull();
    expect(runPhrase(9, "negative", "w", "tr")).toBe("9 hafta boyunca negatif");
    expect(runPhrase(0, "negative", "w", "tr")).toBeNull();
  });
  it("keeps the bank engine's missing-data gate and rule decisions intact", () => {
    expect(engineGate([], undefined, "tr").ready).toBe(false);
    expect(engineGate([], { auditedQuarters: 17, peerExcluded: true }, "tr").reason).toContain("17 denetimli çeyrek");
    expect(ordinal(12, "tr")).toBe("12.");
    expect(ordinal(12)).toBe("12th");
    const input = { car: 13, carQoq: -2, carRank: null, assetsQoqPct: null, roe: null, cpi12m: null, npl: null, nplRises: 0, nplMedian: null, stage2Share: null, costIncome: null, filings: 17, lcr: null, ldr: null };
    const en = bankFlags(input), tx = bankFlags(input, "tr");
    expect(tx.map(({ id, kind, rule }) => ({ id, kind, rule }))).toEqual(en.map(({ id, kind, rule }) => ({ id, kind, rule })));
    expect(tx[0].detail).toContain("%13.0");
    expect(tx[0].detail).toContain("%12 hedef");
  });
  it("localizes accessible chart descriptions without changing exported data", () => {
    const table = { columns: ["Period", "Loans", "Deposits"], rows: [["2026-03", 0, null], ["2026-04", 12.5, null]] };
    const original = structuredClone(table);
    const csv = toCsv(table);
    expect(chartSummary(table, "tr")).toContain("başlangıç 0, son 12,5");
    expect(chartSummary(table, "tr")).toContain("veri yok");
    expect(chartSummary(table)).toContain("no values");
    expect(table).toEqual(original);
    expect(toCsv(table)).toBe(csv);
  });
});
