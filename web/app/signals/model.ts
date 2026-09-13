import type { SectorKey } from "../lib/sector-pages";
import type { SectorSignal, SignalFact, SignalState, SignalText } from "../lib/sector-signals/types";
import { nf } from "../lib/chart-format";

export type SignalFilters = { sector: SectorKey | "all"; state: SignalState | "all"; query: string };
export const localText = (text: SignalText, locale: string) => locale === "tr" ? text.tr : text.en;

export function formatSignalFact(fact: SignalFact, locale: string) {
  if (fact.value == null) return "—";
  const tr = locale === "tr";
  // Keep small reconciliation amounts readable without turning them into zero.
  const unit = fact.unit === "TRYtrn" && Math.abs(fact.value) < 1 ? "TRYbn" : fact.unit;
  const amount = fact.unit === "TRYtrn" && unit === "TRYbn" ? fact.value * 1000 : fact.value;
  const magnitude = Math.abs(amount);
  const decimals = ["weeks", "months", "count"].includes(unit) ? 0
    : magnitude > 0 && magnitude < 0.1 ? Math.min(12, 1 - Math.floor(Math.log10(magnitude))) : 1;
  const value = nf(amount, decimals, tr ? "tr-TR" : "en-US");
  const units = { percent: "%", pp: tr ? "yüzde puan" : "pp", TRYbn: tr ? "milyar TL" : "bn TRY", TRYtrn: tr ? "trilyon TL" : "trn TRY", USDmn: tr ? "milyon USD" : "mn USD", ratio: "×", weeks: tr ? "hafta" : "weeks", months: tr ? "ay" : "months", count: "" };
  return unit === "percent" ? tr ? `%${value}` : `${value}%` : `${value} ${units[unit]}`.trim();
}

export function filterSignals(signals: SectorSignal[], filters: SignalFilters, locale: string) {
  const query = filters.query.trim().toLocaleLowerCase(locale);
  return signals.filter(signal =>
    (filters.sector === "all" || signal.sector === filters.sector) &&
    (filters.state === "all" || signal.state === filters.state) &&
    (!query || [signal.title, signal.summary, signal.criterion].some(text =>
      localText(text, locale).toLocaleLowerCase(locale).includes(query))),
  );
}
