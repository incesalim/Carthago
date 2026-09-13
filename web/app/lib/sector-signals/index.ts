import { loadOverviewSignals } from "./overview";
import { loadCreditSignals } from "./credit";
import { loadDepositsSignals } from "./deposits";
import { loadLiquiditySignals } from "./liquidity";
import { loadAssetQualitySignals } from "./asset-quality";
import { loadCapitalSignals } from "./capital";
import { loadProfitabilitySignals } from "./profitability";
import type { SectorKey } from "../sector-pages";
import type { SectorSignal } from "./types";

export interface SignalSnapshot {
  schema: "carthago.sector-signals.v1";
  basis: "latest-available";
  evaluatedAt: string;
  signals: SectorSignal[];
  failedSectors: SectorKey[];
}

const collectors: Partial<Record<SectorKey, () => Promise<SectorSignal[]>>> = {
  overview: loadOverviewSignals,
  credit: loadCreditSignals,
  deposits: loadDepositsSignals,
  liquidity: loadLiquiditySignals,
  "asset-quality": loadAssetQualitySignals,
  capital: loadCapitalSignals,
  profitability: loadProfitabilitySignals,
};

/** This is current source data, not an analyst's historical database snapshot. */
export async function loadSignalSnapshot(): Promise<SignalSnapshot> {
  const entries = Object.entries(collectors) as [SectorKey, () => Promise<SectorSignal[]>][];
  const results = await Promise.allSettled(entries.map(async ([sector, collect]) => {
    const signals = await collect();
    const ids = new Set<string>();
    for (const signal of signals) {
      if (signal.sector !== sector || !signal.id.startsWith(`${sector}:`) || ids.has(signal.id)) {
        throw new Error(`Invalid signal identity in ${sector}`);
      }
      ids.add(signal.id);
      if (signal.facts.some(fact => fact.value !== null && !Number.isFinite(fact.value))) {
        throw new Error(`Non-finite signal fact in ${sector}`);
      }
    }
    return signals;
  }));
  const signals: SectorSignal[] = [];
  const failedSectors: SectorKey[] = [];
  results.forEach((result, i) => {
    if (result.status === "fulfilled") signals.push(...result.value);
    else {
      failedSectors.push(entries[i][0]);
      console.error(`Sector signals unavailable: ${entries[i][0]}`, result.reason);
    }
  });
  return { schema: "carthago.sector-signals.v1", basis: "latest-available", evaluatedAt: new Date().toISOString(), signals, failedSectors };
}
