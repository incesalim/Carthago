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

interface SparkEntry { timestamp?: number[]; close?: (number | null)[] }

const TTL_MS = 60_000;
const TIMEOUT_MS = 2500;
// Per-isolate cache; nulls are cached too so a delisted/failed symbol isn't
// re-fetched every render within the TTL.
const _mem = new Map<string, { quote: LiveQuote | null; exp: number }>();

/** Latest close + its timestamp from a spark entry (skip Yahoo's trailing nulls). */
function parseSpark(e?: SparkEntry): LiveQuote | null {
  if (!e?.close || !e.timestamp) return null;
  for (let i = e.close.length - 1; i >= 0; i--) {
    const c = e.close[i];
    if (typeof c === "number" && Number.isFinite(c) && c > 0) {
      const ts = e.timestamp[i];
      return { price: c, asOf: typeof ts === "number" ? ts : Math.floor(Date.now() / 1000) };
    }
  }
  return null;
}

/** One batched spark request for all symbols (`.IS` appended). Never throws. */
async function fetchSpark(symbols: string[]): Promise<Map<string, LiveQuote>> {
  const out = new Map<string, LiveQuote>();
  try {
    const list = symbols.map((s) => `${s}.IS`).join(",");
    const url =
      `https://query1.finance.yahoo.com/v8/finance/spark` +
      `?symbols=${encodeURIComponent(list)}&range=1d&interval=1m`;
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
    if (!res.ok) return out;
    const data = (await res.json()) as Record<string, SparkEntry>;
    for (const sym of symbols) {
      const q = parseSpark(data[`${sym}.IS`]);
      if (q) out.set(sym, q);
    }
    return out;
  } catch {
    return out; // timeout / network / parse → callers fall back to the stored close
  }
}

/**
 * Latest Yahoo quotes for bare symbols (bank ticker or index code; ".IS" is
 * appended). ONE spark request per call regardless of symbol count, so the
 * cross-bank page (11 banks) isn't throttled by a burst of per-symbol fetches.
 * Symbols that fail are omitted — the caller falls back to the stored D1 close.
 * `BIST_LIVE_DISABLED=1` returns an empty map (prod kill switch, no deploy).
 */
export async function liveQuotes(symbols: string[]): Promise<Map<string, LiveQuote>> {
  const out = new Map<string, LiveQuote>();
  if (process.env.BIST_LIVE_DISABLED === "1" || symbols.length === 0) return out;

  const now = Date.now();
  const misses: string[] = [];
  for (const s of symbols) {
    const hit = _mem.get(s);
    if (hit && hit.exp > now) {
      if (hit.quote) out.set(s, hit.quote);
    } else {
      misses.push(s);
    }
  }
  if (misses.length) {
    const fetched = await fetchSpark(misses);
    for (const s of misses) {
      const q = fetched.get(s) ?? null;
      _mem.set(s, { quote: q, exp: now + TTL_MS });
      if (q) out.set(s, q);
    }
  }
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
