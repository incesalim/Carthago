/** Presentation-only transforms for sector charts. Source rows stay untouched. */
export interface SectorTrendPoint {
  period: string;
  bank_type_code: string;
  value: number | null;
}

export interface SectorTrendReference {
  value: number;
  label: string;
}

export type SectorTrendRow = { period: string; [key: string]: string | number | null };

const GROUP_ORDER = ["Sector", "State", "Domestic", "Private", "Foreign", "Participation", "Dev & Inv"];

export function sectorSeriesCodes(data: SectorTrendPoint[], labels: Record<string, string>) {
  const codes = [...new Set([...Object.keys(labels), ...data.map((row) => row.bank_type_code)])];
  const rank = (code: string) => {
    const index = GROUP_ORDER.indexOf(labels[code]);
    return index < 0 ? Number.MAX_SAFE_INTEGER : index;
  };
  return codes.sort((a, b) => rank(a) - rank(b));
}

/** Missing points are explicit nulls, so a line never bridges a missing cell. */
export function pivotSectorTrend(data: SectorTrendPoint[], codes: string[]): SectorTrendRow[] {
  const periods = new Map<string, SectorTrendRow>();
  for (const row of data) {
    let period = periods.get(row.period);
    if (!period) {
      period = { period: row.period };
      for (const code of codes) period[code] = null;
      periods.set(row.period, period);
    }
    period[row.bank_type_code] = typeof row.value === "number" && Number.isFinite(row.value) ? row.value : null;
  }
  return [...periods.values()].sort((a, b) => a.period.localeCompare(b.period));
}

export function sectorLatestValues(data: SectorTrendPoint[], codes: string[], deltaPeriods?: number, deltaBasis: "periods" | "published" = "periods") {
  return codes.map((code) => {
    const rows = data.filter((row) => row.bank_type_code === code)
      .toSorted((a, b) => a.period.localeCompare(b.period));
    const index = rows.findLastIndex((row) => typeof row.value === "number" && Number.isFinite(row.value));
    const current = rows[index];
    const comparisonRows = deltaBasis === "published" ? rows.filter((row) => typeof row.value === "number" && Number.isFinite(row.value)) : rows;
    const comparisonIndex = deltaBasis === "published" ? comparisonRows.length - 1 : index;
    const prior = deltaPeriods != null && deltaPeriods > 0 ? comparisonRows[comparisonIndex - deltaPeriods] : undefined;
    return {
      code,
      value: current?.value ?? null,
      period: current?.period ?? null,
      delta: current?.value != null && prior?.value != null && Number.isFinite(prior.value)
        ? current.value - prior.value : null,
    };
  });
}

function niceStep(value: number): number {
  const magnitude = 10 ** Math.floor(Math.log10(value));
  const fraction = value / magnitude;
  const factor = [1, 2, 2.5, 5, 10].find((item) => item >= fraction) ?? 10;
  return factor * magnitude;
}

/** Line-chart scale: bounded by observed values and every stated reference. */
export function sectorTrendScale(
  values: Array<number | null>,
  references: SectorTrendReference[] = [],
  zeroLine = false,
): { domain: [number, number]; ticks: number[]; step: number } {
  const finite = values.filter((value): value is number => typeof value === "number" && Number.isFinite(value));
  for (const reference of references) if (Number.isFinite(reference.value)) finite.push(reference.value);
  if (zeroLine) finite.push(0);
  if (finite.length === 0) return { domain: [0, 1], ticks: [0, 0.25, 0.5, 0.75, 1], step: 0.25 };

  let low = Infinity;
  let high = -Infinity;
  for (const value of finite) { low = Math.min(low, value); high = Math.max(high, value); }
  const span = high - low || Math.max(Math.abs(high) * 0.2, 1);
  const padding = span * 0.07;
  let paddedLow = low - padding;
  let paddedHigh = high + padding;
  // Zero remains the edge when the data and requested baseline share a sign.
  if (zeroLine && low === 0) paddedLow = 0;
  if (zeroLine && high === 0) paddedHigh = 0;
  const step = niceStep((paddedHigh - paddedLow) / 4);
  const start = Math.floor(paddedLow / step);
  const end = Math.ceil(paddedHigh / step);
  const round = (value: number) => Number(value.toPrecision(12));
  const ticks = Array.from({ length: end - start + 1 }, (_, i) => round((start + i) * step));
  return { domain: [ticks[0], ticks[ticks.length - 1]], ticks, step };
}

/** Plot marks for weekly/monthly ownership groups share semantic colours. */
export function sectorPaletteIndex(label: string, fallback: number): number {
  const mapping: Record<string, number> = {
    Sector: 0, State: 1, Domestic: 2, Private: 2, Foreign: 3,
    Participation: 4, "Dev & Inv": 5,
  };
  return mapping[label] ?? fallback;
}
