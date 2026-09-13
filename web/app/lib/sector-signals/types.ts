import type { SectorKey } from "../sector-pages";

/** Observations for research, never publication-ready conclusions or risk scores. */
export type SignalText = { en: string; tr: string };
export type SignalState = "active" | "clear" | "unavailable";
export interface SignalFact {
  key: string;
  label: SignalText;
  value: number | null;
  unit: "percent" | "pp" | "TRYbn" | "TRYtrn" | "USDmn" | "ratio" | "weeks" | "months" | "count";
  asOf: string | null;
}
export interface SectorSignal {
  /** Stable, unique sector:legacy-code identity. */
  id: string;
  sector: SectorKey;
  state: SignalState;
  title: SignalText;
  summary: SignalText;
  criterion: SignalText;
  /** Original deterministic condition, for reproducible research exports. */
  rule: string;
  asOf: string | null;
  cadence: "daily" | "weekly" | "monthly" | "quarterly" | "mixed";
  /** Names the data publisher and basis, including unlike observation clocks. */
  source: SignalText;
  href: string;
  facts: SignalFact[];
}
export const signalText = (en: string, tr: string): SignalText => ({ en, tr });
export function signalState(available: boolean, active: boolean): SignalState {
  return !available ? "unavailable" : active ? "active" : "clear";
}
