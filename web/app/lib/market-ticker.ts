/**
 * Market ticker data (SERVER ONLY) — the live "flowing data" strip on
 * /economy and /news: BIST indices, FX, and global commodities (Brent, gold)
 * in one batched Yahoo `spark` request (via rawQuotes). All ~15-min delayed
 * during market hours, last close otherwise; on failure the strip is hidden.
 */
import { rawQuotes } from "./bist-live";

export interface TickerItem {
  label: string;
  value: string; // pre-formatted display string
  changePct: number | null; // day change, % (null when no prior close)
}

interface Spec {
  symbol: string; // Yahoo symbol
  label: string;
  fmt: (v: number) => string;
}

const GRAMS_PER_OZ = 31.1034768;
const nf = (v: number, d: number) =>
  new Intl.NumberFormat("en-US", { minimumFractionDigits: d, maximumFractionDigits: d }).format(v);

// Order: BIST indices → FX → commodities. (Gram gold ₺ is derived below.)
const SPECS: Spec[] = [
  { symbol: "XU100.IS", label: "BIST 100", fmt: (v) => nf(v, 0) },
  { symbol: "XBANK.IS", label: "BIST Banks", fmt: (v) => nf(v, 0) },
  { symbol: "XU030.IS", label: "BIST 30", fmt: (v) => nf(v, 0) },
  { symbol: "USDTRY=X", label: "USD/TRY", fmt: (v) => `₺${nf(v, 2)}` },
  { symbol: "EURTRY=X", label: "EUR/TRY", fmt: (v) => `₺${nf(v, 2)}` },
  { symbol: "BZ=F", label: "Brent", fmt: (v) => `$${nf(v, 2)}` },
  { symbol: "GC=F", label: "Gold/oz", fmt: (v) => `$${nf(v, 0)}` },
];

const dayChange = (price: number, prev: number | null): number | null =>
  prev && prev > 0 ? (price / prev - 1) * 100 : null;

export async function getMarketTicker(): Promise<TickerItem[]> {
  const quotes = await rawQuotes(SPECS.map((s) => s.symbol));
  const items: TickerItem[] = [];
  for (const spec of SPECS) {
    const r = quotes.get(spec.symbol);
    if (!r) continue;
    items.push({ label: spec.label, value: spec.fmt(r.price), changePct: dayChange(r.price, r.prevClose) });
  }
  // Gram gold in ₺ — the headline gold metric in Turkey: ($/oz ÷ g/oz) × USD/TRY.
  const gold = quotes.get("GC=F");
  const usd = quotes.get("USDTRY=X");
  if (gold && usd) {
    const gram = (gold.price / GRAMS_PER_OZ) * usd.price;
    const gc = gold.prevClose && gold.prevClose > 0 ? gold.price / gold.prevClose : null;
    const uc = usd.prevClose && usd.prevClose > 0 ? usd.price / usd.prevClose : null;
    items.push({
      label: "Gram Gold",
      value: `₺${nf(gram, 0)}`,
      changePct: gc != null && uc != null ? (gc * uc - 1) * 100 : null,
    });
  }
  return items;
}
