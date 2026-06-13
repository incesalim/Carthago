/**
 * BIST live-price overlay (SERVER ONLY) — request-time Yahoo Finance quote.
 *
 * The dashboard's stored prices come from the daily EOD cron (bist_prices in
 * D1). This module fetches the *latest* Yahoo price at page-render time and
 * overlays it on top of the stored valuation — ~15-min delayed during BIST
 * hours, last close when the market is shut. Everything price-linear is rescaled
 * (`applyLivePrice`); on any failure the caller simply keeps the stored value.
 *
 * Caching — deliberately NOT the Next data cache (KV): cachedAll's 12h window
 * exists to stay under Cloudflare's ~1k KV-writes/day cap, so a 60s KV cache
 * would blow it. Instead we use Cloudflare's edge cache (`cf.cacheTtl`, free,
 * no write cap) plus a per-isolate in-memory TTL map to dedupe within a warm
 * isolate (and to work in `next dev`, where `cf` is a no-op).
 */
import type { BistValuation } from "./bist";

export interface LiveQuote {
  price: number; // latest regular-market price, TL
  asOf: number; // regularMarketTime, unix seconds
}

interface YahooChart {
  chart?: {
    result?: Array<{
      meta?: { regularMarketPrice?: number; regularMarketTime?: number };
    }>;
  };
}

const TTL_MS = 60_000;
const TIMEOUT_MS = 2500;
const _mem = new Map<string, { quote: LiveQuote; exp: number }>();

async function fetchOne(symbol: string): Promise<LiveQuote | null> {
  const now = Date.now();
  const hit = _mem.get(symbol);
  if (hit && hit.exp > now) return hit.quote;
  try {
    const url =
      `https://query1.finance.yahoo.com/v8/finance/chart/` +
      `${encodeURIComponent(symbol)}.IS?range=1d&interval=1d`;
    // `cf` is a Cloudflare Workers fetch extension → CDN edge cache, NOT KV.
    const init: RequestInit & { cf?: { cacheTtl: number; cacheEverything: boolean } } = {
      cache: "no-store",
      signal: AbortSignal.timeout(TIMEOUT_MS),
      cf: { cacheTtl: 60, cacheEverything: true },
      headers: {
        "User-Agent": "Mozilla/5.0 (compatible; bddk-analysis/1.0)",
        Accept: "application/json",
      },
    };
    const res = await fetch(url, init);
    if (!res.ok) return null;
    const data = (await res.json()) as YahooChart;
    const meta = data?.chart?.result?.[0]?.meta;
    const price = meta?.regularMarketPrice;
    const asOf = meta?.regularMarketTime;
    if (
      typeof price !== "number" || !Number.isFinite(price) || price <= 0 ||
      typeof asOf !== "number"
    ) {
      return null;
    }
    const quote: LiveQuote = { price, asOf };
    _mem.set(symbol, { quote, exp: now + TTL_MS });
    return quote;
  } catch {
    return null; // timeout / network / parse → fall back to the stored close
  }
}

/**
 * Latest Yahoo quotes for bare symbols (bank ticker or index code; ".IS" is
 * appended). Symbols that fail are omitted — the caller falls back to D1.
 * `BIST_LIVE_DISABLED=1` returns an empty map (prod kill switch, no deploy).
 */
export async function liveQuotes(symbols: string[]): Promise<Map<string, LiveQuote>> {
  const out = new Map<string, LiveQuote>();
  if (process.env.BIST_LIVE_DISABLED === "1") return out;
  await Promise.all(
    symbols.map(async (sym) => {
      const q = await fetchOne(sym);
      if (q) out.set(sym, q);
    }),
  );
  return out;
}

/** Rescale a stored valuation onto a live price (every field is price-linear). */
export function applyLivePrice(v: BistValuation, q: LiveQuote): BistValuation {
  if (!v.price || v.price <= 0) return v;
  const r = q.price / v.price;
  return {
    ...v,
    price: q.price,
    marketCap: v.marketCap != null ? v.marketCap * r : null,
    pb: v.pb != null ? v.pb * r : null,
    pe: v.pe != null ? v.pe * r : null,
    dividendYield: v.dividendYield != null ? v.dividendYield / r : null,
    changePct1y: v.changePct1y != null ? (r * (1 + v.changePct1y / 100) - 1) * 100 : null,
    asOf: q.asOf,
    isLive: true,
  };
}

/**
 * Freshness label for the "Market & Valuation" header. During the trading day
 * (asOf is today in Istanbul) → "as of HH:MM · ~15-min delayed"; otherwise the
 * market is shut → "last close DD Mon".
 */
export function formatAsOf(asOf: number): string {
  const tz = "Europe/Istanbul";
  const d = new Date(asOf * 1000);
  const dayKey = (x: Date) =>
    new Intl.DateTimeFormat("en-CA", { timeZone: tz, year: "numeric", month: "2-digit", day: "2-digit" }).format(x);
  if (dayKey(d) === dayKey(new Date())) {
    const t = new Intl.DateTimeFormat("en-GB", {
      timeZone: tz, hour: "2-digit", minute: "2-digit", hour12: false,
    }).format(d);
    return `as of ${t} · ~15-min delayed`;
  }
  const day = new Intl.DateTimeFormat("en-GB", { timeZone: tz, day: "2-digit", month: "short" }).format(d);
  return `last close ${day}`;
}
