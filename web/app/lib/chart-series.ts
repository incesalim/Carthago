/** Stable visual identities. Bulletin codes alone are ambiguous across cadences. */
const normalize = (value: string) => value.trim().toLowerCase().replace(/[–—]/g, "-");

const IDENTITIES: Record<string, number> = {
  sector: 0, state: 1, public: 1, domestic: 2, private: 2, foreign: 3,
  participation: 4, "dev & inv": 5,
  "sector roe": 0, "state roe": 1, "private roe": 2,
  tl: 0, "turkish lira": 0, fx: 1, "foreign currency": 1, metals: 3, "precious metals": 3,
  housing: 0, auto: 3, gpl: 2, "gen. purpose": 2, "general purpose": 2,
  cards: 1, retail: 1, "retail cards": 1, corporate: 4, "corporate cards": 4,
  nominal: 0, "nominal (y/y)": 0, fxadj: 1, "fx-adjusted": 1,
  real: 2, "real (cpi-deflated)": 2, realfx: 4, "real, constant fx": 4,
  cpi: 3, "cpi 12m avg": 3, "cpi 12m-avg": 3,
  "cbrt net reserves": 1,
  "gold": 3, "- of which gold": 3, "fx share": 1,
  "npl ratio by sme size": 1, "total sme npl ratio": 0, "gross reserves": 5, "net reserves": 1,
  inside: 5, "on-balance-sheet fx position": 5,
  outside: 1, "off-balance-sheet fx position": 1, "net fx position": 0,
  "monthly net profit": 0, "net profit": 0,
  demand: 0, maturity_1m: 1, maturity_1_3m: 2, maturity_3_6m: 3,
  maturity_6_12m: 4, maturity_over_12m: 5,
  bracket_10k: 0, bracket_50k: 1, bracket_250k: 2, bracket_1m: 3, bracket_over_1m: 4,
  prior: 5, previous: 5, current: 0,
  digital: 0, branch: 1, remote_rep: 0, remote_courier: 3, bulk: 4,
};

const MONTHLY_GROUPS: Record<string, number> = {
  "10001": 0, "10006": 1, "10005": 2, "10007": 3, "10003": 4, "10004": 5,
};

/** An untranslated label wins over a code reused by the weekly bulletin. */
export function chartSeriesIndex(key: string, fallback: number, label?: string): number {
  const labelled = label == null ? undefined : IDENTITIES[normalize(label)];
  return labelled ?? IDENTITIES[normalize(key)] ?? MONTHLY_GROUPS[key] ?? fallback;
}

/** Credit stages have explicit status colours, shared with the waterline. */
export function chartSeriesTone(key: string, label?: string): "warning" | "negative" | null {
  const names = [normalize(label ?? ""), normalize(key)];
  if (names.some(name => /^(stage ?2)(\b|$)/.test(name))) return "warning";
  if (names.some(name => /^(stage ?3)(\b|$)/.test(name))) return "negative";
  return null;
}
