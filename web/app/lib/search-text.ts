/** Match Turkish names and ASCII tickers regardless of keyboard or letter case.
 * Default lowercasing leaves a combining dot in İ; Turkish lowercasing alone
 * turns ASCII I into ı. Fold both forms, and accents, only for search matching.
 * Keep the original names and tickers for display, links and stored data.
 */
export function normalizeSearchText(value: string): string {
  return value.normalize("NFKD").replace(/\p{M}/gu, "").toLowerCase().replace(/ı/g, "i").trim();
}
