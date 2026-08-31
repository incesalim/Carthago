/**
 * Shared number formatting for the dashboard charts.
 *
 * `nf` defaults to en-US for existing analytical callers; locale is explicit,
 * never mutable module state. `formatters`/`FormatKind` are the
 * common y-axis/tooltip value formats shared by ALL chart wrappers
 * (TrendChart, TimeSeriesChart, StackedArea, BarByBank, Sparkline) — don't
 * re-declare a local dict.
 */

export const nf = (v: number, d: number, locale = "en-US") =>
  new Intl.NumberFormat(locale, {
    minimumFractionDigits: d,
    maximumFractionDigits: d,
  }).format(v);

/** "2026-01-01" → "2026-Q1" (quarterly period start at month 01/04/07/10). */
export const fmtQuarter = (d: string) =>
  `${String(d).slice(0, 4)}-Q${Math.floor((Number(String(d).slice(5, 7)) - 1) / 3) + 1}`;

export type FormatKind = "pct" | "trn" | "bn" | "raw" | "rate" | "fx";

export const formatters: Record<FormatKind, (v: number, d: number) => string> = {
  pct: (v, d) => `${nf(v, d)}%`,
  trn: (v, d) => `₺${nf(v / 1_000_000, d)} trn`,
  bn: (v, d) => `₺${nf(v / 1_000, d)} bn`,
  raw: (v, d) => nf(v, d),
  // rate = a plain number that is semantically an interest rate (call-site clarity).
  rate: (v, d) => nf(v, d),
  fx: (v, d) => `₺${nf(v, d)}`,
};

/** Display-only formatters; input units remain the same in both languages. */
export function createFormatters(locale: string): typeof formatters {
  if (locale !== "tr") return formatters;
  const number = (v: number, d: number) => nf(v, d, "tr-TR");
  return {
    pct: (v, d) => `%${number(v, d)}`,
    trn: (v, d) => `₺${number(v / 1_000_000, d)} trilyon`,
    bn: (v, d) => `₺${number(v / 1_000, d)} milyar`,
    raw: number,
    rate: number,
    fx: (v, d) => `₺${number(v, d)}`,
  };
}
