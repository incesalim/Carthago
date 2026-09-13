/** Visitor-facing subjects. Data access and calculations stay in the route modules. */
export const SECTOR_PAGES = {
  overview: { href: "/", title: "Sector overview", description: "The Turkish banking sector: balance sheet, funding, profitability and risk." },
  credit: { href: "/credit", title: "Credit", description: "Loan growth, currency effects and lending by product and bank group." },
  deposits: { href: "/deposits", title: "Deposits", description: "Deposit growth, currency composition, maturities and loan funding." },
  liquidity: { href: "/liquidity", title: "Liquidity", description: "Lira funding, foreign-currency liquidity, reserves and regulatory ratios." },
  "asset-quality": { href: "/asset-quality", title: "Asset Quality", description: "Non-performing loans, credit stages, provisions and portfolio risk." },
  capital: { href: "/capital", title: "Capital", description: "Capital adequacy, capital composition, leverage and risk-weighted assets." },
  profitability: { href: "/profitability", title: "Profitability", description: "Profit formation, interest margins, operating costs and returns." },
  "market-risk": { href: "/market-risk", title: "Market Risk", description: "Foreign-exchange positions, repricing gaps and interest-rate scenarios." },
} as const;

export type SectorKey = keyof typeof SECTOR_PAGES;

export const RELATED_SECTORS: Record<SectorKey, SectorKey[]> = {
  overview: ["credit", "deposits", "asset-quality"],
  credit: ["deposits", "asset-quality"],
  deposits: ["credit", "liquidity"],
  liquidity: ["deposits", "market-risk"],
  "asset-quality": ["credit", "capital"],
  capital: ["asset-quality", "profitability"],
  profitability: ["deposits", "capital"],
  "market-risk": ["liquidity", "capital"],
};
