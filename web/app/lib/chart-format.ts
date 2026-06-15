/**
 * Shared number formatting for the dashboard charts.
 *
 * `nf` is the single en-US locale formatter (comma thousands + dot decimal,
 * e.g. 1,234,567.89) used by every chart. `formatters`/`FormatKind` are the
 * common y-axis/tooltip value formats shared by the bank-data charts
 * (TrendChart, StackedArea, BarByBank, Sparkline). Charts with bespoke value
 * kinds (e.g. TimeSeriesChart's rate/fx) keep their own dict but still use `nf`.
 */

export const nf = (v: number, d: number) =>
  new Intl.NumberFormat("en-US", {
    minimumFractionDigits: d,
    maximumFractionDigits: d,
  }).format(v);

export type FormatKind = "pct" | "trn" | "bn" | "raw";

export const formatters: Record<FormatKind, (v: number, d: number) => string> = {
  pct: (v, d) => `${nf(v, d)}%`,
  trn: (v, d) => `₺${nf(v / 1_000_000, d)} trn`,
  bn: (v, d) => `₺${nf(v / 1_000, d)} bn`,
  raw: (v, d) => nf(v, d),
};
