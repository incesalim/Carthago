import type { MetadataRoute } from "next";
import { bankSummaries } from "@/app/lib/audit";

// Read D1 at request time (never at build — no Cloudflare context then), same
// as the pages. The per-bank query is itself KV-cached via `cachedAll`, so this
// doesn't hammer D1 on every crawl.
export const dynamic = "force-dynamic";

const BASE = "https://carthago.app";

type ChangeFrequency = NonNullable<
  MetadataRoute.Sitemap[number]["changeFrequency"]
>;

// Public content routes, one per app/ folder, in rough nav order. `/admin` is
// password-gated and `/api/*` isn't content, so both are omitted. Per-bank
// drill-downs (`/banks/[ticker]`) are appended dynamically below.
const STATIC_ROUTES: {
  path: string;
  priority: number;
  changeFrequency: ChangeFrequency;
}[] = [
  { path: "/", priority: 1.0, changeFrequency: "daily" },
  { path: "/sector", priority: 0.9, changeFrequency: "daily" },
  { path: "/sector/ratios", priority: 0.7, changeFrequency: "weekly" },
  { path: "/banks", priority: 0.9, changeFrequency: "weekly" },
  { path: "/cross-bank", priority: 0.8, changeFrequency: "weekly" },
  { path: "/capital", priority: 0.8, changeFrequency: "weekly" },
  { path: "/liquidity", priority: 0.8, changeFrequency: "weekly" },
  { path: "/asset-quality", priority: 0.8, changeFrequency: "weekly" },
  { path: "/profitability", priority: 0.8, changeFrequency: "weekly" },
  { path: "/credit", priority: 0.8, changeFrequency: "weekly" },
  { path: "/deposits", priority: 0.8, changeFrequency: "weekly" },
  { path: "/rates", priority: 0.7, changeFrequency: "weekly" },
  { path: "/market-risk", priority: 0.7, changeFrequency: "weekly" },
  { path: "/franchise", priority: 0.7, changeFrequency: "weekly" },
  { path: "/valuation", priority: 0.7, changeFrequency: "daily" },
  { path: "/ownership", priority: 0.6, changeFrequency: "monthly" },
  { path: "/disclosures", priority: 0.7, changeFrequency: "daily" },
  { path: "/earnings", priority: 0.7, changeFrequency: "weekly" },
  { path: "/regulation", priority: 0.7, changeFrequency: "weekly" },
  { path: "/news", priority: 0.7, changeFrequency: "daily" },
  { path: "/news/google", priority: 0.6, changeFrequency: "daily" },
  { path: "/digital", priority: 0.6, changeFrequency: "monthly" },
  { path: "/funds", priority: 0.6, changeFrequency: "daily" },
  { path: "/non-bank", priority: 0.6, changeFrequency: "monthly" },
  { path: "/non-bank/share-of-banking", priority: 0.5, changeFrequency: "monthly" },
  { path: "/economy", priority: 0.8, changeFrequency: "weekly" },
  { path: "/economy/inflation", priority: 0.6, changeFrequency: "monthly" },
  { path: "/economy/budget", priority: 0.6, changeFrequency: "monthly" },
  { path: "/economy/foreign-trade", priority: 0.6, changeFrequency: "monthly" },
  { path: "/economy/economic-growth", priority: 0.6, changeFrequency: "monthly" },
  { path: "/economy/balance-of-payments", priority: 0.6, changeFrequency: "monthly" },
  { path: "/pipeline", priority: 0.3, changeFrequency: "monthly" },
];

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const now = new Date();

  const staticEntries: MetadataRoute.Sitemap = STATIC_ROUTES.map((r) => ({
    url: `${BASE}${r.path}`,
    lastModified: now,
    changeFrequency: r.changeFrequency,
    priority: r.priority,
  }));

  let bankEntries: MetadataRoute.Sitemap = [];
  try {
    const banks = await bankSummaries();
    bankEntries = banks.map((b) => ({
      url: `${BASE}/banks/${b.bank_ticker}`,
      lastModified: now,
      changeFrequency: "weekly",
      priority: 0.7,
    }));
  } catch {
    // If D1 is momentarily unavailable, still serve the static sitemap rather
    // than 500 the whole thing — per-bank URLs get picked up next crawl.
  }

  return [...staticEntries, ...bankEntries];
}
